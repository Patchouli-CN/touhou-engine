"""bomb 演出: 六机体 12 套视觉 (BombData.cpp 各 *Draw) + 暗转/无敌环/cutin 横幅。

起止由 BombStarted/BombEnded 事件驱动; 机体视觉每帧读 world.bomb 的
sub_info 摆位 (C++ 里 subInfo->vms 由 *Calc ExecuteAnmIdx 启动、*Draw 摆位,
sim 侧不持 VM, 本层按相同条件自持 AnmMachine)。暗转 (DarkenViewport,
BombData.cpp:31-61) 原是 Stage::SmoothBlendColor 全局色调, 用游戏区黑罩近似;
cutin + 符卡名横幅 = Gui::ShowBombNamePortrait (Gui.cpp:343-362)。
清弹盒/伤害盒原版即无视觉 (纯逻辑盒); BombClearedBullet 无专属演出
(消弹转道具, 道具视觉走 items 层)。
"""

from __future__ import annotations

import math

from ....engine import SpriteDraw, TextDraw
from ....engine.anm import AnmBank, AnmMachine
from ....engine.rng import Rng
from ..bomb import (
    CHAR_MARISA_A,
    CHAR_MARISA_B,
    CHAR_REIMU_A,
    CHAR_REIMU_B,
    CHAR_SAKUYA_A,
    CHAR_SAKUYA_B,
)
from ..snapshot import GAME_X, GAME_Y
from .effects import FxParticles
from .spellcard import _FACE_ANM, _vm_sprite

# 机体 bomb 脚本(文件内键 = C 全局 id - 0x400 装载基址, AnmIdx.hpp:239-248)
_SCR_REIMU_A = 133  # 8 珠 × 4 vm
_SCR_REIMU_B = 137  # 4 结界光束
_SCR_REIMU_B_FOCUS = 141  # 3 重结界
_SCR_MARISA_A = 5  # 星, i%3
_SCR_MARISA_B = 12  # 3 旋转激光臂
_SCR_MARISA_B_FOCUS = 8  # 4 魔炮
_SCR_SAKUYA_A = 5  # 刀, +(i&1)
_SCR_SAKUYA_A_FOCUS = 7
_SCR_SAKUYA_A_HIT = 96  # 1120: 命中钉住的刀 (BombData.cpp:1294/1467)
_SCR_SAKUYA_B = 9  # 4 方阵
_SCR_SAKUYA_B_FOCUS = 13  # 2 时停领域
_SCR_INVULN_RING = 0x2DA - 0x200  # SpawnBombInvulnEffect → SpawnSpecialEffect(25)

# cutin/横幅脚本 (Gui.cpp:343-362, 键 = C 全局 id - 装载基址)
_SCR_PORTRAIT = 1  # face 链 ANM_SCRIPT_FACE_SPELLCARD_PORTRAIT (AnmIdx.hpp:251)
_SCR_DECOR_L = 4  # AnmIdx.hpp:254
_SCR_DECOR_R = 6  # AnmIdx.hpp:256
_SPR_DECOR = 12  # ANM_SPRITE_FACE_SPELLCARD_DECOR (AnmIdx.hpp:260)
_SCR_NAME_BG = 1  # ascii ANM_SCRIPT_ASCII_SPELLCARD_NAME_BG (AnmIdx.hpp:147)
_SCR_NAME_TEXT = 4  # text.anm ANM_SCRIPT_TEXT_SPELLCARD_NAME (AnmIdx.hpp:274)
_NAME_SPRITE_W = 320  # text.anm sprite 宽(左缘基准, old bomb_view.py:101)

#: (character, focus) → (立绘 sprite 文件内键, 符卡名) (ShowBombNamePortrait 调用点实参;
#: 魔理沙A 散 +3 / 魔理沙B 散 +1 等同 face 文件姿势差分, BombData.cpp:137-1659)
_BOMB_CUTIN: dict[tuple[int, bool], tuple[int, str]] = {
    (CHAR_REIMU_A, False): (1, "霊符「夢想封印　散」"),  # BombData.cpp:137
    (CHAR_REIMU_A, True): (1, "霊符「夢想封印　集」"),  # :337
    (CHAR_REIMU_B, False): (1, "夢符「封魔陣」"),  # :539
    (CHAR_REIMU_B, True): (1, "夢符「二重結界」"),  # :652
    (CHAR_MARISA_A, False): (3, "魔符「スターダストレヴァリエ」"),  # :732
    (CHAR_MARISA_A, True): (2, "魔符「ミルキーウェイ」"),  # :843
    (CHAR_MARISA_B, False): (1, "恋符「ノンディレクショナルレーザー」"),  # :995
    (CHAR_MARISA_B, True): (2, "恋符「マスタースパーク」"),  # :1124
    (CHAR_SAKUYA_A, False): (1, "幻符「インディスクリミネイト」"),  # :1226
    (CHAR_SAKUYA_A, True): (1, "幻符「殺人ドール」"),  # :1360
    (CHAR_SAKUYA_B, False): (3, "時符「パーフェクトスクウェア」"),  # :1532
    (CHAR_SAKUYA_B, True): (3, "時符「プライベートスクウェア」"),  # :1659
}

Z_RING = 27.0  # 无敌环: Effect 层 (draw prio 9 < Bullet 10)
Z_DARKEN = 55.0  # 暗转黑罩: 压游戏区全部(判定点 51 之上), Gui 层不受影响
Z_BOMB = 56.0  # bomb 本体: 黑罩之上(原版 AnmManager 在 Stage 色调之后绘制)
Z_PORTRAIT = 100.0  # 以下为 Gui 层(不裁剪不振屏, 与宣言横幅同段)
Z_NAME_BG = 101.0


def _darken_alpha(timer: int, duration: int) -> int:
    """DarkenViewport (BombData.cpp:31-61) 的明暗系数 → 黑罩 alpha 近似。

    原版 rgb = 128 - t*80/60 (淡入) / 48 (保持) / 对称淡出, 经 SmoothBlendColor
    作全局色调; 折成黑罩透明度 (0 → 160 → 0), 同旧 bomb_view 口径。
    """
    if timer < 60:
        c = 128 - timer * 80 // 60
    elif timer >= duration - 60:
        c = 128 - (duration - timer) * 80 // 60
    else:
        c = 48
    return max(0, min(255, (128 - c) * 2))


class BombFx:
    """一次 bomb 的演出: 触发边沿建 VM, 每帧 step 产出 (sprites, texts)。"""

    def __init__(self, rng: Rng) -> None:
        self._rng = rng
        self._key: tuple[int, bool] | None = None  # (character, focus), None=未在 bomb
        self._anm_name = ""
        self._bank: AnmBank | None = None  # 机体 player0N.anm
        self._etama: AnmBank | None = None
        self._fixed: list[AnmMachine] = []  # 固定阵列 VM (非 sub 驱动)
        self._pool: dict[int, list[AnmMachine]] = {}  # sub 驱动 VM
        self._trails: dict[int, list[tuple[float, float]]] = {}
        self._sakuya_hit: set[int] = set()  # 咲夜A 已换 1120 的刀
        self._squares_started = False  # 咲夜B 散 timer==30 方阵
        # ---- 无敌红环 (独立倒计时, 可活过 bomb) ----
        self._ring: AnmMachine | None = None
        self._ring_left = 0
        # ---- cutin/横幅 (Gui 层, cutin 由自身脚本收尾) ----
        self._cutin: list[tuple[AnmMachine, str, float, float, bool]] = []
        self._name: AnmMachine | None = None  # 名运动 VM (无贴图, TextDraw 渲染)
        self._name_bg: AnmMachine | None = None
        self._name_text = ""

    @property
    def running(self) -> bool:
        """Bomb 本体演出进行中(暗转+机体视觉)。"""
        return self._key is not None

    @property
    def active(self) -> bool:
        """任一演出件仍在(本体/环/cutin/横幅)。"""
        return (
            self._key is not None
            or self._ring is not None
            or bool(self._cutin)
            or self._name is not None
        )

    # ---- 触发/结束 ----
    def begin(self, world, *, focus: bool, bank_of) -> None:
        """BombStarted: 按 (character, focus) 起固定阵列 VM + 无敌环 + cutin/横幅。"""
        char: int = world.character
        self._key = (char, focus)
        self._anm_name = f"player0{char // 2}.anm"
        self._bank = bank_of(self._anm_name)
        self._etama = bank_of("etama.anm")
        self._fixed = []
        self._pool = {}
        self._trails = {}
        self._sakuya_hit = set()
        self._squares_started = False
        self._start_ring(world.bomb)
        self._start_cutin(char, focus, bank_of)
        bank = self._bank
        if bank is None:
            return

        def fixed(keys) -> None:
            for key in keys:
                vm = AnmMachine(self._rng)
                vm.start(bank.scripts.get(key))
                if vm.alive:
                    self._fixed.append(vm)

        if (char, focus) == (CHAR_REIMU_B, False):
            fixed(range(_SCR_REIMU_B, _SCR_REIMU_B + 4))  # BombData.cpp:547-551
        elif (char, focus) == (CHAR_REIMU_B, True):
            fixed(range(_SCR_REIMU_B_FOCUS, _SCR_REIMU_B_FOCUS + 3))  # :660-664
        elif (char, focus) == (CHAR_MARISA_A, False):
            fixed(_SCR_MARISA_A + i % 3 for i in range(8))  # :740-744
        elif (char, focus) == (CHAR_MARISA_B, False):
            fixed(range(_SCR_MARISA_B, _SCR_MARISA_B + 3))  # :1003-1006
        elif (char, focus) == (CHAR_MARISA_B, True):
            fixed(range(_SCR_MARISA_B_FOCUS, _SCR_MARISA_B_FOCUS + 4))  # :1132-1135
        elif (char, focus) == (CHAR_SAKUYA_B, True):
            fixed(range(_SCR_SAKUYA_B_FOCUS, _SCR_SAKUYA_B_FOCUS + 2))  # :1670-1673
            for i in range(2):
                p = world.bomb.sub_info[i].pos
                self._trails[i] = [(p.x, p.y)] * 32  # trails 全填出发点 (:1674-1678)
        # ReimuA/MarisaA 集/SakuyaA/SakuyaB 散为 sub 驱动, 每帧 sync 启动

    def end(self) -> None:
        """BombEnded: 本体 VM 全撤 (C++: draw 停止调用即消失), 横幅走收场 interrupt。"""
        self._key = None
        self._fixed = []
        self._pool = {}
        self._trails = {}
        self._sakuya_hit = set()
        self._squares_started = False
        # EndPlayerSpellcard (Gui.cpp:49-53): 横幅名 interrupt 1, 底条 2
        if self._name is not None:
            self._name.pending_interrupt = 1
        if self._name_bg is not None:
            self._name_bg.pending_interrupt = 2

    # ---- 无敌红环 (SpawnBombInvulnEffect, BombData.cpp:63-85) ----
    def _start_ring(self, bomb) -> None:
        self._ring = None
        self._ring_left = 0
        if self._etama is None:
            return
        vm = AnmMachine(self._rng)
        vm.start(self._etama.scripts.get(_SCR_INVULN_RING))
        if not vm.alive:
            return
        frames = max(1, bomb.invulnerability_timer)
        # scaleInterp → 1/16, 历时 invulnerabilityTimer 帧 (BombData.cpp:73-80)
        vm.scale_initial = list(vm.scale)
        vm.scale_final = [vm.scale[0] / 16.0, vm.scale[1] / 16.0]
        vm.scale_interp.restart(frames, 0)
        vm.int_vars1[0] = frames
        vm.angle_vel[2] *= -1.0
        vm.color = [255, 64, 64, 255]
        self._ring = vm
        self._ring_left = frames

    def _step_ring(self, world, out: list[SpriteDraw]) -> None:
        """环跟随自机 (Player.cpp:1915-1930), 自倒计时归零即消(等价无敌计时)。"""
        vm = self._ring
        if vm is None:
            return
        self._ring_left -= 1
        if self._ring_left <= 0:
            self._ring = None
            return
        vm.execute()
        if not vm.alive:
            self._ring = None
            return
        p = world.player.pos
        spr = _vm_sprite(
            vm, f"etama.anm:{vm.active_sprite_idx}", GAME_X + p.x, GAME_Y + p.y, Z_RING
        )
        if spr is not None:
            out.append(spr)

    # ---- cutin/横幅 ----
    def _start_cutin(self, char: int, focus: bool, bank_of) -> None:
        """Gui::ShowBombNamePortrait (Gui.cpp:343-362): 立绘+左右装饰+名底条+名 VM。"""
        sprite_id, self._name_text = _BOMB_CUTIN[(char, focus)]
        self._cutin = []
        self._name = None
        self._name_bg = None
        face_name = _FACE_ANM[char // 2]
        face: AnmBank | None = bank_of(face_name)
        if face is not None:
            vm = AnmMachine(self._rng)
            vm.start(face.scripts.get(_SCR_PORTRAIT))
            if vm.alive:
                vm.active_sprite_idx = sprite_id  # SetActiveSprite (Gui.cpp:348)
                slot = face.sprites.get(sprite_id)
                w = float(slot.sprite.w) if slot is not None else 0.0
                h = float(slot.sprite.h) if slot is not None else 0.0
                self._cutin.append((vm, f"{face_name}:{sprite_id}", w, h, True))
            for key, no_rot in ((_SCR_DECOR_L, True), (_SCR_DECOR_R, False)):
                vm = AnmMachine(self._rng)
                vm.start(face.scripts.get(key))
                if not vm.alive:
                    continue
                vm.active_sprite_idx = _SPR_DECOR  # SetActiveSprite (:350-356)
                slot = face.sprites.get(_SPR_DECOR)
                w = float(slot.sprite.w) if slot is not None else 0.0
                h = float(slot.sprite.h) if slot is not None else 0.0
                self._cutin.append((vm, f"{face_name}:{_SPR_DECOR}", w, h, no_rot))
        ascii_bank: AnmBank | None = bank_of("ascii.anm")
        if ascii_bank is not None:
            bg = AnmMachine(self._rng)
            bg.start(ascii_bank.scripts.get(_SCR_NAME_BG))
            if bg.alive:
                bg.pending_interrupt = 1  # 入场 (Gui.cpp:362)
                self._name_bg = bg
        text: AnmBank | None = bank_of("text.anm")
        if text is not None:
            vm = AnmMachine(self._rng)
            vm.start(text.scripts.get(_SCR_NAME_TEXT))
            if vm.alive:
                self._name = vm

    def _step_cutin(self, sprites: list[SpriteDraw], texts: list[TextDraw]) -> None:
        """Gui::OnUpdate/OnDraw 的 bomb cutin 段 (Gui.cpp:1295-1303/1727-1747)。"""
        cutin: list[tuple[AnmMachine, str, float, float, bool]] = []
        for vm, image, w, h, no_rot in self._cutin:
            vm.execute()
            if vm.alive:
                cutin.append((vm, image, w, h, no_rot))
            # anchor 位: pos 是 quad 左上 → 中心锚平移 (AnmManager.cpp:1019-1046)
            x = vm.pos[0] + (w * abs(vm.scale[0]) / 2.0 if vm.anchor & 1 else 0.0)
            y = vm.pos[1] + (h * abs(vm.scale[1]) / 2.0 if vm.anchor & 2 else 0.0)
            spr = _vm_sprite(vm, image, x, y, Z_PORTRAIT, no_rotation=no_rot)
            if spr is not None:
                sprites.append(spr)
        self._cutin = cutin
        name = self._name
        if name is not None:
            name.execute()
            if not name.alive:
                self._name = None
                name = None
        bg = self._name_bg
        if bg is not None:
            bg.execute()
            if not bg.alive:
                self._name_bg = None
                bg = None
        if name is None or not name.visible:
            return
        nx = name.pos[0] + name.offset[0]
        ny = name.pos[1] + name.offset[1]
        if bg is not None:
            # bg.pos = name.pos, DrawNoRotation (Gui.cpp:1745-1746)
            spr = _vm_sprite(
                bg,
                f"ascii.anm:{bg.active_sprite_idx}",
                nx,
                ny,
                Z_NAME_BG,
                no_rotation=True,
            )
            if spr is not None:
                sprites.append(spr)
        if self._name_text:
            # DrawVmTextFmt (Gui.cpp:359-361): 字形纹理外链, TextDraw 渲染;
            # 文字左缘 = pos.x - sprite 宽/2·scale (中心锚 quad)
            left = nx - _NAME_SPRITE_W * name.scale[0] / 2.0
            texts.append(
                TextDraw(
                    self._name_text,
                    left,
                    ny - 8.0,
                    size=15,
                    rgba=(240, 240, 255, name.color[3]),
                )
            )

    # ==================================================================
    # 每帧
    # ==================================================================
    def step(
        self, world, particles: FxParticles
    ) -> tuple[list[SpriteDraw], list[TextDraw]]:
        """推进一帧: 暗转 + 机体本体 + 无敌环 + cutin/横幅。"""
        sprites: list[SpriteDraw] = []
        texts: list[TextDraw] = []
        if self._key is not None:
            bomb = world.bomb
            alpha = _darken_alpha(bomb.timer, bomb.duration)
            if alpha > 0:
                sprites.append(
                    SpriteDraw(
                        "misc:veil",
                        GAME_X + 192.0,
                        GAME_Y + 224.0,
                        z=Z_DARKEN,
                        alpha=alpha,
                    )
                )
            self._step_body(world, particles, sprites)
        self._step_ring(world, sprites)
        self._step_cutin(sprites, texts)
        return sprites, texts

    # ==================================================================
    # 12 套 bomb 本体 (对照各 *Draw)
    # ==================================================================
    def _body(
        self,
        out: list[SpriteDraw],
        vm: AnmMachine,
        x: float,
        y: float,
        *,
        rotation: float | None = None,
        scale: tuple[float, float] | None = None,
        alpha: int | None = None,
    ) -> None:
        """VM 当前状态 → 游戏区 SpriteDraw(anchor 位按 quad 左上平移)。"""
        if not vm.visible or vm.active_sprite_idx < 0:
            return
        sx = vm.scale[0] if scale is None else scale[0]
        sy = vm.scale[1] if scale is None else scale[1]
        if vm.anchor & 3 and self._bank is not None:
            slot = self._bank.sprites.get(vm.active_sprite_idx)
            if slot is not None:
                if vm.anchor & 1:
                    x += slot.sprite.w * abs(sx) / 2.0
                if vm.anchor & 2:
                    y += slot.sprite.h * abs(sy) / 2.0
        out.append(
            SpriteDraw(
                f"{self._anm_name}:{vm.active_sprite_idx}",
                GAME_X + x,
                GAME_Y + y,
                z=Z_BOMB,
                rotation=vm.rotation[2] if rotation is None else rotation,
                alpha=vm.color[3] if alpha is None else alpha,
                scale_x=sx,
                scale_y=sy,
                color=(vm.color[0], vm.color[1], vm.color[2]),
                blend_mode=vm.blend_mode,
            )
        )

    def _mk1(self, key: int) -> AnmMachine | None:
        """起一台机体脚本 VM(bank 缺或脚本缺 → None)。"""
        if self._bank is None:
            return None
        vm = AnmMachine(self._rng)
        vm.start(self._bank.scripts.get(key))
        return vm if vm.alive else None

    def _pool_sync(self, world, count: int, mk) -> None:
        """Sub state 0→非0 建 VM, →0 撤 (C++: *Calc 启动 / draw 停画即消)。"""
        bomb = world.bomb
        for i in range(count):
            if bomb.sub_info[i].state != 0:
                if i not in self._pool:
                    made = mk(i)
                    if made:
                        self._pool[i] = made
            elif i in self._pool:
                del self._pool[i]

    def _step_body(self, world, particles: FxParticles, out: list[SpriteDraw]) -> None:
        char, focus = self._key
        if char == CHAR_REIMU_A:
            self._reimu_a(world, out)
        elif char == CHAR_REIMU_B:
            self._reimu_b(world, focus, out)
        elif char == CHAR_MARISA_A:
            if focus:
                self._marisa_a_focus(world, out)
            else:
                self._marisa_a_spread(world, out)
        elif char == CHAR_MARISA_B:
            self._marisa_b(world, focus, out)
        elif char == CHAR_SAKUYA_A:
            self._sakuya_a(world, focus, particles, out)
        elif focus:
            self._sakuya_b_focus(world, out)
        else:
            self._sakuya_b_spread(world, out)

    def _reimu_a(self, world, out: list[SpriteDraw]) -> None:
        """8 珠 × 4 vm, pos = 珠位 + vm->offset, DrawNoRotation。"""
        # BombReimuADraw/Focus (BombData.cpp:263-305/484-512)
        bomb = world.bomb

        def mk(i: int) -> list[AnmMachine]:
            vms = []
            for j in range(4):  # BombData.cpp:178-183/:374-379
                vm = self._mk1(_SCR_REIMU_A + j)
                if vm is not None:
                    vms.append(vm)
            return vms

        self._pool_sync(world, 8, mk)
        for i, vms in self._pool.items():
            sub = bomb.sub_info[i]
            for vm in vms:
                vm.execute()
                self._body(
                    out,
                    vm,
                    sub.pos.x + vm.offset[0],
                    sub.pos.y + vm.offset[1],
                    rotation=0.0,
                )

    def _reimu_b(self, world, focus: bool, out: list[SpriteDraw]) -> None:
        """锚点 (sub_info.pos 或 startPos) + vm->offset, Draw (带旋转)。"""
        # BombReimuBDraw/Focus (BombData.cpp:615-632/695-714)
        bomb = world.bomb
        for i, vm in enumerate(self._fixed):
            vm.execute()
            base = bomb.start_pos if focus else bomb.sub_info[i].pos
            self._body(out, vm, base.x + vm.offset[0], base.y + vm.offset[1])

    def _marisa_a_spread(self, world, out: list[SpriteDraw]) -> None:
        """每星同 vm 连画 3 次 (残影), scale 3.2/2.2/1.0。"""
        # BombMarisaADraw (BombData.cpp:781-811)
        bomb = world.bomb
        for i, vm in enumerate(self._fixed):
            vm.execute()
            p, v = bomb.sub_info[i].pos, bomb.sub_info[i].vel
            self._body(out, vm, p.x, p.y, scale=(3.2, 3.2))
            self._body(
                out, vm, p.x - v.x * 6 - 32.0, p.y - v.y * 6 - 32.0, scale=(2.2, 2.2)
            )
            self._body(out, vm, p.x - v.x * 10.0, p.y - v.y * 10.0, scale=(1.0, 1.0))

    def _marisa_a_focus(self, world, out: list[SpriteDraw]) -> None:
        """拖尾 trails[3]/[7], scale 3.2/2.2/1.3。"""
        # BombMarisaADrawFocus (BombData.cpp:928-961)
        bomb = world.bomb

        def mk(i: int) -> list[AnmMachine]:
            vm = self._mk1(_SCR_MARISA_A + i % 3)
            if vm is None:
                return []
            p = bomb.sub_info[i].pos
            self._trails[i] = [(p.x, p.y)] * 8  # trails[8] 全填出发点 (:868-872)
            return [vm]

        self._pool_sync(world, 24, mk)
        for i in [i for i in self._trails if i not in self._pool]:
            del self._trails[i]
        for i, vms in self._pool.items():
            vm = vms[0]
            vm.execute()
            sub = bomb.sub_info[i]
            trail = self._trails[i]
            self._body(out, vm, sub.pos.x, sub.pos.y, scale=(3.2, 3.2))
            self._body(out, vm, trail[3][0], trail[3][1], scale=(2.2, 2.2))
            self._body(out, vm, trail[7][0], trail[7][1], scale=(1.3, 1.3))
            trail.insert(0, (sub.pos.x, sub.pos.y))
            del trail[8:]

    def _marisa_b(self, world, focus: bool, out: list[SpriteDraw]) -> None:
        """以自机为根 pos += dir(accel)·sprite 高·scale.y/2, rotation.z = accel + π/2。"""
        # BombMarisaBDraw/Focus (BombData.cpp:1078-1104/1177-1206)
        bomb = world.bomb
        p = world.player.pos
        for i, vm in enumerate(self._fixed):
            vm.execute()
            if focus:
                accel = i * (math.pi / 5.0) / 3.0 - math.pi + math.tau / 5.0  # :1181
            else:
                accel = bomb.sub_info[i].accel  # accel 被复用为臂角度
            h = 0.0
            if self._bank is not None:
                slot = self._bank.sprites.get(vm.active_sprite_idx)
                if slot is not None:
                    h = float(slot.sprite.h)
            d = h * vm.scale[1] / 2.0
            vm.rotation[2] = accel + math.pi / 2
            self._body(out, vm, p.x + math.cos(accel) * d, p.y + math.sin(accel) * d)

    def _sakuya_a(
        self, world, focus: bool, particles: FxParticles, out: list[SpriteDraw]
    ) -> None:
        """96 刀, rotation.z = angle + π/2; 命中换 anm 1120。"""
        # BombSakuyaADraw/Focus (BombData.cpp:1312-1340/1482-1511)
        bomb = world.bomb
        base = _SCR_SAKUYA_A_FOCUS if focus else _SCR_SAKUYA_A

        def mk(i: int) -> list[AnmMachine]:
            vm = self._mk1(base + (i & 1))
            return [vm] if vm is not None else []

        self._pool_sync(world, 96, mk)
        for i, vms in self._pool.items():
            vm = vms[0]
            sub = bomb.sub_info[i]
            dmg = bomb.damage_boxes[i].damage
            if i not in self._sakuya_hit and (
                (not focus and dmg >= 30) or (focus and dmg > 0)
            ):
                # 命中钉住: ExecuteAnmIdx(1120) (BombData.cpp:1294/1467)
                if self._bank is not None:
                    vm.start(self._bank.scripts.get(_SCR_SAKUYA_A_HIT))
                self._sakuya_hit.add(i)
                if focus:
                    # SpawnParticles(0, pos, 1, 0xffff80ff) (:1443-1445)
                    particles.spawn(self._etama, 0, sub.pos.x, sub.pos.y, 1, 0xFFFF80FF)
            vm.execute()
            vm.rotation[2] = sub.angle + math.pi / 2
            self._body(out, vm, sub.pos.x, sub.pos.y)
        # 撤掉的刀清命中标记, 防槽位复用串状态
        self._sakuya_hit &= set(self._pool)

    def _sakuya_b_spread(self, world, out: list[SpriteDraw]) -> None:
        """4 方阵, timer==30 启动, vm->pos = (192±128, 224±128), Draw。"""
        # BombSakuyaBDraw (BombData.cpp:1608-1633); 方阵锚点 :1563-1570
        bomb = world.bomb
        if not self._squares_started and bomb.timer >= 30:
            if self._bank is not None:
                for i in range(4):
                    vm = self._mk1(_SCR_SAKUYA_B + i)
                    if vm is not None:
                        vm.pos[0] = 192.0 + (128.0 if i & 1 else -128.0)
                        vm.pos[1] = 224.0 + (128.0 if i // 2 else -128.0)
                        self._fixed.append(vm)
            self._squares_started = True
        for i, vm in enumerate(self._fixed):
            if not bomb.sub_info[i].state:
                continue
            vm.execute()
            self._body(out, vm, vm.pos[0], vm.pos[1])

    def _sakuya_b_focus(self, world, out: list[SpriteDraw]) -> None:
        """2 领域 + 残影环 (trails[3,7,…,31], alpha = old - old*j/32)。"""
        # BombSakuyaBDrawFocus (BombData.cpp:1740-1774)
        bomb = world.bomb
        for i, vm in enumerate(self._fixed):
            sub = bomb.sub_info[i]
            if not sub.state:
                continue
            vm.execute()
            trail = self._trails[i]
            old_alpha = vm.color[3]
            self._body(out, vm, sub.pos.x, sub.pos.y)
            for j in range(3, 32, 4):
                self._body(
                    out,
                    vm,
                    trail[j][0],
                    trail[j][1],
                    alpha=old_alpha - old_alpha * j // 32,
                )
            trail.insert(0, (sub.pos.x, sub.pos.y))
            del trail[32:]
