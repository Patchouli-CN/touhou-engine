"""th07 的快照生产: OUTPUT 槽 system, 每帧把世界状态翻译成 SceneSnapshot。

坐标系 = 640x480 窗口逻辑像素(游戏区 384x448 在 (32,16)), 后端只管 blit。
贴图键: 有 anm 数据时 ``<anm文件名>:<链式全局sprite id>``(后端按 AnmBank
寻址); 无数据(合成世界/单测)退化为语义键(``enemy:3``/``item:1``…), 后端
画占位色块, 两边互不知道对方是否存在。

出处对照(贴图映射表): old/touhou/games/th07/view/sprite_view.py 模块头注释。
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from ...engine import FrameContext, SpriteDraw, System, TextDraw
from ...engine.anm import AnmBank, AnmMachine, build_bank
from ...engine.enemies import Enemy
from ...engine.player import PlayerState
from ...engine.rng import Rng
from ...schemas.anm import parse_anm
from ...schemas.archive import load_entry
from .data import bullet_active_sprite_idx
from .ecl_state import EnemyExtras
from .player import OptionState

if TYPE_CHECKING:
    from .world import Th07World

# ---- 窗口布局(出处 old sprite_view.py:71-73) ----
WIN_W, WIN_H = 640, 480
GAME_W, GAME_H = 384, 448
GAME_X, GAME_Y = 32, 16

# ---- 贴图映射常量 ----
_ETAMA = "etama.anm"
_ETAMA_C_BASE = 0x200  # etama 的 C 文件基址; 链式全局 id = C 全局 id - 0x200
_LASER_SPRITE_BASE = 152  # etama entry0 激光段 16 色(出处 old sprite_view.py:113)
_ITEM_SCRIPT_BASE = 196  # 链式 entry1 基址 168 + 局部 script 28(ItemManager.cpp:91)
_ROTATE_BULLET_TYPES = (2, 4, 5, 6, 8)  # 长条弹按速度方向转(米/滴/针/箭/刀)
_SPAWN_ALPHA = 96  # 出生态弹本体透明度
_PLAYER_C_BASE = 0x400  # 自机 anm 的 C 文件基址(自机弹 anmFileIdx 同空间)
_PLAYER_IDLE_FRAMES = 8  # 静止 sprite 0..7 慢摇(8 帧一切)
_PLAYER_TILT_SPRITE = 12  # 侧移倾斜帧(左倾; 右移水平翻转)
_OPTION_SCRIPTS = (128, 129)  # 子机脚本(Player.cpp:2451-2452)


def _gx(x: float) -> float:
    """游戏区坐标 → 窗口坐标。"""
    return GAME_X + x


def _gy(y: float) -> float:
    """游戏区坐标 → 窗口坐标。"""
    return GAME_Y + y


class _EnemyVis:
    """一个敌人的 view 侧动画账本: 主 VM + 两个 sub anm VM。"""

    __slots__ = ("vm", "gid", "intr", "subs")

    def __init__(self) -> None:
        self.vm = AnmMachine(Rng(0))
        self.gid = -1
        self.intr = 0
        self.subs: dict[int, tuple[AnmMachine, int]] = {}


class Th07SnapshotSystem(System["Th07World"]):
    """OUTPUT 槽: 世界状态 → ctx.draw(敌人/弹/道具/自机/激光/HUD)。"""

    def __init__(self, *, anm_version: int = 2) -> None:
        self._anm_version = anm_version
        self._rng = Rng(0)  # view VM 专用, 不碰 sim rng
        self._banks: dict[str, AnmBank | None] = {}
        self._stage_no = -1
        self._enemy_vis: dict[int, _EnemyVis] = {}
        self._item_gids: dict[int, int | None] = {}
        self._shot_vms: dict[
            int, tuple[AnmMachine, int]
        ] = {}  # 弹池下标 → (VM, 脚本键)
        self._option_vms: list[AnmMachine] = []

    # ---- anm 数据(惰性; 无 archive → 全 None → 语义键兜底) ----
    def _bank(self, world: Th07World, name: str) -> AnmBank | None:
        if name in self._banks:
            return self._banks[name]
        bank: AnmBank | None = None
        if world.archive is not None:
            try:
                anm = parse_anm(
                    load_entry(world.archive, name),
                    version=self._anm_version,
                    flat_layout=False,
                )
                bank = build_bank(anm, flat_layout=False)
            except (KeyError, ValueError):
                bank = None  # 资源缺失: 本文件全走语义键兜底
        self._banks[name] = bank
        return bank

    def _sync_stage(self, world: Th07World) -> None:
        """换关时换敌贴图包并清动画账本。"""
        if world.stage_no == self._stage_no:
            return
        self._stage_no = world.stage_no
        self._banks.pop(f"stg{self._stage_no}enm.anm", None)
        self._enemy_vis.clear()

    # ---- 主入口 ----
    def tick(self, world: Th07World, ctx: FrameContext) -> None:
        self._sync_stage(world)
        self._emit_lasers(world, ctx)
        self._emit_enemies(world, ctx)
        self._emit_shots(world, ctx)
        self._emit_bullets(world, ctx)
        self._emit_items(world, ctx)
        self._emit_player(world, ctx)
        self._emit_hud(world, ctx)

    # ---- 敌人(stgNenm.anm 脚本 VM; 出处 old sprite_view.py:477-574) ----
    def _emit_enemies(self, world: Th07World, ctx: FrameContext) -> None:
        host = world.host
        bank = self._bank(world, f"stg{world.stage_no}enm.anm")
        alive_ids: set[int] = set()
        for e in world.enemies.enemies:
            if not e.active or e.anm_idx < 0:
                continue  # 无贴图敌人原版也不画(EnemyManager.cpp:697)
            alive_ids.add(e.enemy_id)
            if bank is None or host is None:
                x, y = e.pos2
                ctx.draw.sprites.append(
                    SpriteDraw(f"enemy:{e.anm_idx}", _gx(x), _gy(y), z=10.0)
                )
                continue
            vis = self._enemy_vis.setdefault(e.enemy_id, _EnemyVis())
            extras = host.extras_of(e.machine)
            x, y = e.pos2
            self._emit_sub_anm(ctx, vis, bank, extras, 0, x, y, z=9.0)
            self._step_enemy_vm(ctx, vis, bank, e, extras, x, y)
            self._emit_sub_anm(ctx, vis, bank, extras, 1, x, y, z=11.0)
        for gone in set(self._enemy_vis) - alive_ids:
            del self._enemy_vis[gone]

    def _step_enemy_vm(
        self,
        ctx: FrameContext,
        vis: _EnemyVis,
        bank: AnmBank,
        e: Enemy,
        extras: EnemyExtras,
        x: float,
        y: float,
    ) -> None:
        vm = vis.vm
        if vis.gid != e.anm_idx:  # SET_ANM 切换 → 换脚本重跑
            vis.gid = e.anm_idx
            vm.start(bank.scripts.get(e.anm_idx))
        else:
            if extras.primary_vm_interrupt != vis.intr:
                vis.intr = extras.primary_vm_interrupt
                if extras.primary_vm_interrupt:
                    vm.pending_interrupt = extras.primary_vm_interrupt
            if extras.primary_vm_auto_rotate:
                # EnemyManager.cpp:1194
                vm.rotation[2] = e.machine.enemy.angle
            vm.execute()
        if not vm.visible or vm.active_sprite_idx < 0:
            return
        ctx.draw.sprites.append(
            SpriteDraw(
                f"stg{self._stage_no}enm.anm:{vm.active_sprite_idx}",
                _gx(x + vm.offset[0]),
                _gy(y + vm.offset[1]),
                z=10.0,
                rotation=vm.rotation[2],
                alpha=vm.color[3],
                scale_x=vm.scale[0],
                scale_y=vm.scale[1],
                color=(vm.color[0], vm.color[1], vm.color[2]),
                blend_mode=vm.blend_mode,
            )
        )

    def _emit_sub_anm(
        self,
        ctx: FrameContext,
        vis: _EnemyVis,
        bank: AnmBank,
        extras: EnemyExtras,
        slot: int,
        x: float,
        y: float,
        *,
        z: float,
    ) -> None:
        slid = extras.sub_anm_idx[slot]
        if slid < 0:
            vis.subs.pop(slot, None)  # C: anmFileIdx=-1 停画
            return
        sub = vis.subs.get(slot)
        if sub is None or sub[1] != slid:
            svm = AnmMachine(self._rng)
            svm.start(bank.scripts.get(slid))
            sub = (svm, slid)
            vis.subs[slot] = sub
        else:
            sub[0].execute()
        svm = sub[0]
        if not svm.visible or svm.active_sprite_idx < 0:
            return
        ctx.draw.sprites.append(
            SpriteDraw(
                f"stg{self._stage_no}enm.anm:{svm.active_sprite_idx}",
                _gx(x + svm.offset[0]),
                _gy(y + svm.offset[1]),
                z=z,
                rotation=svm.rotation[2],
                alpha=svm.color[3],
                scale_x=svm.scale[0],
                scale_y=svm.scale[1],
                color=(svm.color[0], svm.color[1], svm.color[2]),
                blend_mode=svm.blend_mode,
            )
        )

    # ---- 敌弹(data.py 弹型表 → etama sprite; 出处 old sprite_view.py:776-815) ----
    def _emit_bullets(self, world: Th07World, ctx: FrameContext) -> None:
        for b in world.bullets.alive():
            gid = bullet_active_sprite_idx(b.sprite, b.sprite_offset) - _ETAMA_C_BASE
            rot = 0.0
            if b.sprite in _ROTATE_BULLET_TYPES and b.vel.length > 0.05:
                # 长条弹朝速度方向(sprite 原生朝上)
                rot = math.atan2(b.vel.y, b.vel.x) + math.pi / 2
            ctx.draw.sprites.append(
                SpriteDraw(
                    f"{_ETAMA}:{gid}",
                    _gx(b.pos.x),
                    _gy(b.pos.y),
                    z=30.0,
                    rotation=rot,
                    alpha=_SPAWN_ALPHA if b.spawn_state else 255,
                )
            )

    # ---- 道具(etama script 探针解 sprite; old sprite_view.py:576-600) ----
    def _item_gid(self, world: Th07World, kind: int) -> int | None:
        if kind in self._item_gids:
            return self._item_gids[kind]
        gid: int | None = None
        bank = self._bank(world, _ETAMA)
        if bank is not None:
            script = bank.scripts.get(_ITEM_SCRIPT_BASE + kind)
            if script is not None:
                probe = AnmMachine(self._rng)
                probe.start(script)
                if probe.active_sprite_idx >= 0:
                    gid = probe.active_sprite_idx
        self._item_gids[kind] = gid
        return gid

    def _emit_items(self, world: Th07World, ctx: FrameContext) -> None:
        for it in world.items.alive():
            kind = int(it.kind)
            if kind > 9:
                continue
            gid = self._item_gid(world, kind)
            image = f"{_ETAMA}:{gid}" if gid is not None else f"item:{kind}"
            ctx.draw.sprites.append(
                SpriteDraw(image, _gx(it.pos.x), _gy(it.pos.y), z=40.0)
            )

    # ---- 自机弹(.sht anmFileIdx → 脚本 VM; old sprite_view.py:602-674) ----
    def _emit_shots(self, world: Th07World, ctx: FrameContext) -> None:
        anm_name = f"player0{world.character // 2}.anm"
        bank = self._bank(world, anm_name)
        alive: set[int] = set()
        for i, shot in enumerate(world.shots.pool):
            if shot.bullet_state == 0 or not shot.anm_file_idx:
                continue
            alive.add(i)
            key = shot.anm_file_idx - _PLAYER_C_BASE
            if shot.bullet_state == 2:
                key += 32  # 命中爆发动画(Player.cpp:895)
            if bank is None:
                ctx.draw.sprites.append(
                    SpriteDraw(
                        f"shot:{shot.anm_file_idx}",
                        _gx(shot.pos.x),
                        _gy(shot.pos.y),
                        z=25.0,
                    )
                )
                continue
            slot = self._shot_vms.get(i)
            if slot is None or slot[1] != key:
                svm = AnmMachine(self._rng)
                svm.start(bank.scripts.get(key))
                slot = (svm, key)
                self._shot_vms[i] = slot
            else:
                slot[0].execute()
            svm = slot[0]
            if not svm.visible or svm.active_sprite_idx < 0:
                continue
            ctx.draw.sprites.append(
                SpriteDraw(
                    f"{anm_name}:{svm.active_sprite_idx}",
                    _gx(shot.pos.x + svm.offset[0]),
                    _gy(shot.pos.y + svm.offset[1]),
                    z=25.0,
                    rotation=svm.rotation[2],
                    alpha=svm.color[3],
                    scale_x=svm.scale[0],
                    scale_y=svm.scale[1],
                    color=(svm.color[0], svm.color[1], svm.color[2]),
                    blend_mode=svm.blend_mode,
                )
            )
        for gone in set(self._shot_vms) - alive:
            del self._shot_vms[gone]

    # ---- 激光(etama 激光段拉伸旋转; old sprite_view.py:817-878) ----
    def _emit_lasers(self, world: Th07World, ctx: FrameContext) -> None:
        bank = self._bank(world, _ETAMA)
        for lz in world.lasers.alive():
            length = lz.offset_b - lz.offset_a
            if length <= 1.0:
                continue
            color = max(0, min(15, int(lz.color)))
            # 视觉宽度: SPAWNING 渐宽 / DESPAWNING 渐窄(原版由 anm 脚本驱动)
            w = lz.width
            if int(lz.state) == 0:
                w = max(1.0, lz.width * lz.timer / max(1, lz.start_time))
            elif int(lz.state) == 2:
                w = max(1.0, lz.width * (1.0 - lz.timer / max(1, lz.end_time)))
            dx, dy = math.cos(lz.angle), math.sin(lz.angle)
            cx = lz.pos.x + dx * (lz.offset_a + length / 2)
            cy = lz.pos.y + dy * (lz.offset_a + length / 2)
            gid = _LASER_SPRITE_BASE + color
            nw = nh = 16.0  # 无数据兜底: 按 16px 方形条算缩放
            if bank is not None:
                slot = bank.sprites.get(gid)
                if slot is not None:
                    nw, nh = float(slot.sprite.w), float(slot.sprite.h)
            warning = (
                int(lz.state) == 0
                and lz.timer < lz.hitbox_start_time
                and not lz.hide_warning
            )
            ctx.draw.sprites.append(
                SpriteDraw(
                    f"{_ETAMA}:{gid}",
                    _gx(cx),
                    _gy(cy),
                    z=20.0,
                    rotation=lz.angle + math.pi / 2,
                    alpha=120 if warning else 190,
                    scale_x=max(w * 2, 2.0) / nw,
                    scale_y=length / nh,
                )
            )

    # ---- 自机(player0N.anm 代表帧直取; old sprite_view.py:885-951) ----
    def _emit_player(self, world: Th07World, ctx: FrameContext) -> None:
        p = world.player
        if p.state == PlayerState.DEAD:
            return
        anm_name = f"player0{world.character // 2}.anm"
        alpha = 255
        if p.invulnerability_timer and p.invulnerability_timer % 8 < 2:
            alpha = 110  # 无敌帧闪烁
        vx = p.velocity.x
        if vx < -0.05:
            gid, flip = _PLAYER_TILT_SPRITE, 1.0
        elif vx > 0.05:
            gid, flip = _PLAYER_TILT_SPRITE, -1.0
        else:
            gid, flip = world.frame // 8 % _PLAYER_IDLE_FRAMES, 1.0
        ctx.draw.sprites.append(
            SpriteDraw(
                f"{anm_name}:{gid}",
                _gx(p.pos.x),
                _gy(p.pos.y),
                z=50.0,
                alpha=alpha,
                scale_x=flip,
            )
        )
        # 子机(脚本带 ANGVEL 旋转; 位置 = options.step 产出)
        if world.options.state != OptionState.HIDDEN and len(world.shots.options) == 2:
            bank = self._bank(world, anm_name)
            while len(self._option_vms) < 2:
                svm = AnmMachine(self._rng)
                script = (
                    bank.scripts.get(_OPTION_SCRIPTS[len(self._option_vms)])
                    if bank is not None
                    else None
                )
                svm.start(script)
                self._option_vms.append(svm)
            for svm, op in zip(self._option_vms, world.shots.options, strict=True):
                svm.execute()
                if not svm.visible or svm.active_sprite_idx < 0:
                    continue
                ctx.draw.sprites.append(
                    SpriteDraw(
                        f"{anm_name}:{svm.active_sprite_idx}",
                        _gx(op.x),
                        _gy(op.y),
                        z=49.0,
                        rotation=svm.rotation[2],
                        alpha=alpha,
                    )
                )
        if p.focus:
            # focus 判定点(红环白点; 后端程序化绘制)
            ctx.draw.sprites.append(
                SpriteDraw("misc:hitpoint", _gx(p.pos.x), _gy(p.pos.y), z=51.0)
            )

    # ---- HUD/对话/结算文本(右栏 + 覆盖层) ----
    def _emit_hud(self, world: Th07World, ctx: FrameContext) -> None:
        texts = ctx.draw.texts
        g = world.th07
        gl = world.globals
        rows = (
            ("SCORE", f"{gl.gui_score:09d}"),
            ("PLAYER", f"x{int(g.lives)}"),
            ("BOMB", f"x{int(g.bombs)}"),
            ("POWER", f"{int(g.power)}"),
            ("GRAZE", f"{g.graze_in_total}"),
            ("POINT", f"{g.point_items_collected_this_stage}"),
            ("CHERRY", f"{g.cherry} / {g.cherry_max}"),
        )
        for i, (label, value) in enumerate(rows):
            y = 24 + i * 28
            texts.append(
                TextDraw(label, 412.0, float(y), size=15, rgba=(170, 200, 255, 255))
            )
            texts.append(TextDraw(value, 500.0, float(y), size=15))
        if g.cherry_plus > g.cherry_start:
            texts.append(
                TextDraw(
                    f"CherryPlus {g.cherry_plus}",
                    412.0,
                    24.0 + len(rows) * 28,
                    size=13,
                    rgba=(255, 170, 200, 255),
                )
            )
        boss = world.boss
        if boss is not None and boss.is_active and boss.max_life > 0:
            frac = max(0.0, min(1.0, boss.life / boss.max_life))
            filled = int(frac * 32)
            texts.append(
                TextDraw(
                    f"BOSS [{'=' * filled}{' ' * (32 - filled)}]",
                    float(GAME_X + 8),
                    float(GAME_Y + 4),
                    size=13,
                    rgba=(255, 90, 110, 255),
                )
            )
        self._emit_stage_results(world, ctx)
        if world.game_over:
            texts.append(
                TextDraw(
                    "GAME OVER",
                    float(GAME_X + GAME_W // 2 - 60),
                    float(GAME_Y + GAME_H // 2),
                    size=24,
                    rgba=(255, 80, 80, 255),
                )
            )
        elif world.cleared:
            texts.append(
                TextDraw(
                    "ALL CLEAR!",
                    float(GAME_X + GAME_W // 2 - 60),
                    float(GAME_Y + GAME_H // 2),
                    size=24,
                    rgba=(255, 230, 130, 255),
                )
            )

    def _emit_stage_results(self, world: Th07World, ctx: FrameContext) -> None:
        panel = world.stage_results
        if panel is None:
            return
        texts = ctx.draw.texts
        title = "All Clear" if panel.all_clear else f"Stage {panel.stage} Clear"
        texts.append(
            TextDraw(
                title,
                float(GAME_X + 90),
                float(GAME_Y + 100),
                size=22,
                rgba=(255, 230, 130, 255),
            )
        )
        for i, (label, _value) in enumerate(panel.lines):
            texts.append(
                TextDraw(
                    label,
                    float(GAME_X + 80),
                    float(GAME_Y + 150 + i * 22),
                    size=15,
                )
            )
        texts.append(
            TextDraw(
                f"Total = {panel.total}0",
                float(GAME_X + 80),
                float(GAME_Y + 160 + len(panel.lines) * 22),
                size=15,
                rgba=(255, 230, 130, 255),
            )
        )
