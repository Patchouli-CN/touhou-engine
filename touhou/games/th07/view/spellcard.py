"""boss 符卡宣言演出: Gui::ShowSpellcard 横幅 + Stage spellcardVms 魔法阵 + 符卡环。

- 横幅 (Gui.cpp:368-416 ShowSpellcard / :56-61 EndEnemySpellcard): 立绘 +
  左右装饰 cutin (face 链脚本, 自时序收场), 符卡名运动 VM (text.anm 脚本 5,
  文字用 TextDraw 右对齐近似), 名底条/捕获分指示 (ascii 脚本 0/2, interrupt
  1 入场 2 退场), 捕获分递减数字 + 历史取得/遭遇 (Gui.cpp:1755-1815)。
- 魔法阵 (EclManager.cpp:676-682): 宣言启动 eff 脚本 VM 组, 收场撤掉;
  画在实体之下(Stage draw prio 4)。黑罩淡入随 3D 背景单留待(现背景是纯色)。
- 符卡环 (EclManager.cpp:700-708): etama 脚本(0x2da 空间)跟随 boss, scale
  插值到 1/8。

脚本坐标即窗口坐标, 不换算; sprite 键为链式全局 id 空间(build_bank
flat_layout=False), C 全局 id - 装载基址 = 文件内键。
"""

from __future__ import annotations

from ....engine import SpriteDraw, TextDraw
from ....engine.anm import AnmBank, AnmMachine
from ....engine.rng import Rng
from ..snapshot import GAME_X, GAME_Y

_FACE_ANM = ("face_rm00.anm", "face_mr00.anm", "face_sk00.anm")
_ANM_OFFSET_FACE = 0x4A0  # face 链装载基址 (AnmIdx.hpp:105)
# ShowSpellcard 调用点实参 (Gui.cpp:372-407), 键 = C 全局 id - 基址
_SCR_PORTRAIT = 1187 - _ANM_OFFSET_FACE  # 立绘脚本 (face 链局部 3)
_SCR_DECOR_L = 1189 - _ANM_OFFSET_FACE  # 左/上装饰脚本
_SCR_DECOR_R = 1191 - _ANM_OFFSET_FACE  # 右/下装饰脚本
_SPR_DECOR = 1196 - _ANM_OFFSET_FACE  # 装饰 sprite (局部 12)
_SCR_NAME_BG = 0  # ascii.anm 符卡名底条 (Gui.cpp:677-678)
_SCR_INDICATOR = 2  # ascii.anm 捕获分指示 (Gui.cpp:679-680)
_SCR_NAME_TEXT = 5  # text.anm 符卡名运动脚本 (Gui.cpp:405-407)
_NAME_SPRITE_W = 320  # text.anm sprite 5 宽(右对齐基准, old spellcard_view.py:58)
_SPR_DIGIT = 132  # ascii.anm 数字 sprite 基址 (AnmIdx.hpp:161)

# 魔法阵脚本表 (EclManager.cpp:676-682 + EffectManager.cpp:861-940 按关装载):
# stage → ((eff 文件, 文件内链式脚本键组), ...)
_SC_BG_VMS: dict[int, tuple[tuple[str, tuple[int, ...]], ...]] = {
    1: (("eff01.anm", (0,)),),
    2: (("eff02.anm", (0,)),),
    3: (("eff03.anm", (0,)),),
    4: (
        ("eff04.anm", (0,)),
        ("eff04b.anm", (0,)),
    ),
    5: (("eff05.anm", (0, 1)),),
    6: (("eff06.anm", (0, 1)),),
    7: (("eff07.anm", (0, 1)),),
    8: (("eff08.anm", (0, 1)),),
}
_SCR_SPELL_RING = 0x2DA - 0x200  # etama 符卡环脚本 (AnmIdx.hpp:215)

Z_CIRCLE = 5.0  # 魔法阵: 背景之上实体之下 (Stage draw prio 4 < Enemy 5)
Z_RING = 28.0  # 符卡环: Effect 层 (draw prio 9)
Z_PORTRAIT = 100.0  # 以下为 Gui 层(不裁剪不振屏, backend z>=100 约定)
Z_NAME_BG = 101.0
Z_NAME = 102.0
Z_DIGIT = 103.0


def _vm_sprite(
    vm: AnmMachine,
    image: str,
    x: float,
    y: float,
    z: float,
    *,
    no_rotation: bool = False,
) -> SpriteDraw | None:
    """VM 当前状态 → SpriteDraw(不可见/无 sprite 返回 None)。"""
    if not vm.visible or vm.active_sprite_idx < 0:
        return None
    return SpriteDraw(
        image,
        x + vm.offset[0],
        y + vm.offset[1],
        z=z,
        rotation=0.0 if no_rotation else vm.rotation[2],
        alpha=vm.color[3],
        scale_x=vm.scale[0],
        scale_y=vm.scale[1],
        color=(vm.color[0], vm.color[1], vm.color[2]),
        blend_mode=vm.blend_mode,
    )


class MagicCircle:
    """符卡魔法阵: 宣言起按关启动 eff 脚本 VM 组 + 黑罩淡入, 收场全撤。

    黑罩 (Stage.cpp spellCardState): 宣言起 60 帧场景上叠黑 (alpha=ticks*255/60,
    Stage.cpp:482-491 + OnDrawLowPrio 的 DrawSquare), 之后游戏区黑底只画
    魔法阵; 收场 state=0 即撤。后端按 "misc:veil" 语义键填游戏区黑。
    """

    _FADE = 60  # state 1 时长 (Stage.cpp:482)

    def __init__(self, rng: Rng) -> None:
        self._rng = rng
        self._vms: list[tuple[AnmMachine, str, AnmBank]] = []
        self._ticks = 0

    @property
    def active(self) -> bool:
        return bool(self._vms)

    def begin(self, bank_of, stage_no: int) -> None:
        """EclManager.cpp:676-682: 按关脚本表逐台起 VM。"""
        self._vms = []
        self._ticks = 0
        for name, keys in _SC_BG_VMS.get(stage_no, ()):
            bank: AnmBank | None = bank_of(name)
            if bank is None:
                continue
            for key in keys:
                vm = AnmMachine(self._rng)
                vm.start(bank.scripts.get(key))
                if vm.alive:
                    self._vms.append((vm, name, bank))

    def end(self) -> None:
        """EndSpellcard: state=0, VM 停画 (Stage.cpp:849)。"""
        self._vms = []

    def step(self) -> list[SpriteDraw]:
        out: list[SpriteDraw] = []
        if self._vms:
            self._ticks += 1
            # 黑罩: 游戏区中心, z 在魔法阵之下 (state 2 后恒 255 = 黑底)
            alpha = min(255, self._ticks * 255 // self._FADE)
            out.append(
                SpriteDraw(
                    "misc:veil",
                    GAME_X + 192.0,
                    GAME_Y + 224.0,
                    z=Z_CIRCLE - 1.0,
                    alpha=alpha,
                )
            )
        for vm, name, bank in self._vms:
            vm.execute()
            # ANM_22 anchor=3: pos 是 quad 左上, 平移成中心锚
            # (AnmManager.cpp:1011-1041; 与标题 scene 同口径)
            w = h = 0.0
            slot = bank.sprites.get(vm.active_sprite_idx)
            if slot is not None:
                w, h = float(slot.sprite.w), float(slot.sprite.h)
            x = vm.pos[0] + (w * abs(vm.scale[0]) / 2.0 if vm.anchor & 1 else 0.0)
            y = vm.pos[1] + (h * abs(vm.scale[1]) / 2.0 if vm.anchor & 2 else 0.0)
            spr = _vm_sprite(vm, f"{name}:{vm.active_sprite_idx}", x, y, Z_CIRCLE)
            if spr is not None:
                out.append(spr)
        return out


class SpellRing:
    """符卡环: etama 脚本跟随 boss, scale 插值 1/8 (EclManager.cpp:700-708)。"""

    def __init__(self, rng: Rng) -> None:
        self._rng = rng
        self._vm: AnmMachine | None = None

    def begin(self, bank: AnmBank | None, time_limit: int) -> None:
        self._vm = None
        if bank is None:
            return
        vm = AnmMachine(self._rng)
        vm.start(bank.scripts.get(_SCR_SPELL_RING))
        if not vm.alive:
            return
        # scaleInterpFinal = 1/8, 时长 = 符卡时限 (EclManager.cpp:702-707)
        vm.scale_initial = list(vm.scale)
        vm.scale_final = [vm.scale[0] / 8.0, vm.scale[1] / 8.0]
        vm.scale_interp.restart(max(1, time_limit), 0)
        self._vm = vm

    def end(self) -> None:
        self._vm = None

    def step(self, boss_pos: tuple[float, float] | None) -> list[SpriteDraw]:
        vm = self._vm
        if vm is None:
            return []
        vm.execute()
        if not vm.alive or boss_pos is None:
            self._vm = None
            return []
        spr = _vm_sprite(
            vm,
            f"etama.anm:{vm.active_sprite_idx}",
            GAME_X + boss_pos[0],
            GAME_Y + boss_pos[1],
            Z_RING,
        )
        return [spr] if spr is not None else []


class SpellcardBanner:
    """符卡宣言横幅: begin/end 边沿 + cutin/名条/捕获分数字的 VM 宿主。"""

    def __init__(self, rng: Rng) -> None:
        self._rng = rng
        self._cutin: list[tuple[AnmMachine, str, float, float, bool]] = []
        # (vm, 图键, 锚w, 锚h, no_rotation)
        self._name: AnmMachine | None = None  # 名运动 VM (无贴图, TextDraw 渲染)
        self._name_bg: AnmMachine | None = None
        self._indicator: AnmMachine | None = None
        self._name_text = ""
        self._sc_idx = -1  # 宣言时的全局符卡号(catk 下标)
        self._bonus_remaining = 0  # 剩余捕获分最后值(boss 撤掉后沿用)

    @property
    def active(self) -> bool:
        return bool(self._cutin) or self._name is not None

    def begin(self, world, bank_of) -> None:
        """Gui::ShowSpellcard (Gui.cpp:368-416); 名字取 world.spellcard_name。"""
        boss = world.boss
        self._cutin = []
        self._name = None
        self._name_bg = None
        self._indicator = None
        self._name_text = world.spellcard_name
        self._sc_idx = boss.spellcard_idx if boss is not None else -1
        gui_id = boss.spellcard_face if boss is not None else -1
        face = bank_of(_FACE_ANM[world.character // 2])
        face_st = bank_of(f"face_{world.stage_no:02d}_00.anm")
        if face is not None and gui_id >= 0:
            # 立绘 (Gui.cpp:370-394): 运动 VM 跑 face 链脚本, 贴图换 face_NN_00
            vm = AnmMachine(self._rng)
            vm.start(face.scripts.get(_SCR_PORTRAIT))
            if vm.alive:
                image = f"{_FACE_ANM[world.character // 2]}:{vm.active_sprite_idx}"
                w = h = 0.0
                if face_st is not None:
                    slot = face_st.sprites.get(gui_id)
                    if slot is not None:
                        image = f"face_{world.stage_no:02d}_00.anm:{gui_id}"
                        w, h = float(slot.sprite.w), float(slot.sprite.h)
                # offset.x 按 sprite 宽分档 (Gui.cpp:379-393)
                vm.offset[0] = -288.0 if w > 256 else (-112.0 if w > 128 else 0.0)
                self._cutin.append((vm, image, w, h, True))  # DrawNoRotation
            for key, no_rot in ((_SCR_DECOR_L, True), (_SCR_DECOR_R, False)):
                vm = AnmMachine(self._rng)
                vm.start(face.scripts.get(key))
                if not vm.alive:
                    continue
                vm.active_sprite_idx = _SPR_DECOR  # SetActiveSprite (Gui.cpp:398-404)
                slot = face.sprites.get(_SPR_DECOR)
                w = float(slot.sprite.w) if slot is not None else 0.0
                h = float(slot.sprite.h) if slot is not None else 0.0
                self._cutin.append(
                    (
                        vm,
                        f"{_FACE_ANM[world.character // 2]}:{_SPR_DECOR}",
                        w,
                        h,
                        no_rot,
                    )
                )
        ascii_bank = bank_of("ascii.anm")
        if ascii_bank is not None:
            bg = AnmMachine(self._rng)
            bg.start(ascii_bank.scripts.get(_SCR_NAME_BG))
            if bg.alive:
                bg.pending_interrupt = 1  # 入场 (Gui.cpp:412)
                self._name_bg = bg
            ind = AnmMachine(self._rng)
            ind.start(ascii_bank.scripts.get(_SCR_INDICATOR))
            if ind.alive:
                ind.pending_interrupt = 1  # Gui.cpp:413
                self._indicator = ind
        text = bank_of("text.anm")
        if text is not None:
            vm = AnmMachine(self._rng)
            vm.start(text.scripts.get(_SCR_NAME_TEXT))
            if vm.alive:
                self._name = vm

    def end(self) -> None:
        """Gui::EndEnemySpellcard (Gui.cpp:56-61); cutin VM 由自身脚本收尾。"""
        if self._name is not None:
            self._name.pending_interrupt = 1
        if self._name_bg is not None:
            self._name_bg.pending_interrupt = 2
        if self._indicator is not None:
            self._indicator.pending_interrupt = 2

    def step(self, world) -> tuple[list[SpriteDraw], list[TextDraw]]:
        sprites: list[SpriteDraw] = []
        texts: list[TextDraw] = []
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
        ind = self._indicator
        if ind is not None:
            ind.execute()
            if not ind.alive:
                self._indicator = None
                ind = None
        if name is not None and name.visible:
            nx = name.pos[0] + name.offset[0]
            ny = name.pos[1] + name.offset[1]
            if bg is not None:
                # bg.pos = name.pos, DrawNoRotation (Gui.cpp:1751-1752)
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
                # DrawStringFormat 右对齐 (Gui.cpp:408-411): 右缘 = pos.x +
                # sprite 宽/2 × scale; 文字宽按全角 15px/字近似(TextDraw 无右锚)
                right = nx + _NAME_SPRITE_W * name.scale[0] / 2.0
                texts.append(
                    TextDraw(
                        self._name_text,
                        right - len(self._name_text) * 15.0,
                        ny - 8.0,
                        size=15,
                        rgba=(255, 240, 240, name.color[3]),
                    )
                )
            if ind is not None:
                # DrawNoRotation(spellcardBonusIndicator) (Gui.cpp:1754), 自身脚本位
                spr = _vm_sprite(
                    ind,
                    f"ascii.anm:{ind.active_sprite_idx}",
                    ind.pos[0],
                    ind.pos[1],
                    Z_NAME_BG,
                    no_rotation=True,
                )
                if spr is not None:
                    sprites.append(spr)
                self._capture_bonus(world, ind, sprites)
        return sprites, texts

    # ---- 捕获分递减数字 + 历史 (Gui.cpp:1755-1815, captureBonusVm) ----
    def _capture_bonus(self, world, ind: AnmMachine, out: list[SpriteDraw]) -> None:
        boss = world.boss
        if boss is not None:
            # EndSpellcard 只清 isActive, captureScore 保留 → 滑出期间定格;
            # boss 撤掉后沿用最后值(C++ spellcardInfo 是独立常驻槽)
            self._bonus_remaining = (
                boss.capture_score + boss.graze_bonus_score if boss.is_capturing else 0
            )
        remaining = self._bonus_remaining
        x = ind.pos[0] - 40.0
        y = ind.pos[1]
        divisor = 10000000
        leading = False
        for _ in range(8):
            d, remaining = divmod(remaining, divisor)
            if d:
                leading = True
            if leading or divisor == 1:
                out.append(SpriteDraw(f"ascii.anm:{_SPR_DIGIT + d}", x, y, z=Z_DIGIT))
            x += 7.0
            divisor //= 10
        # 历史两段: catk[符卡].successes/attempts[本机], 99 封顶, 十位 0 省略
        succ = atte = 0
        if 0 <= self._sc_idx < len(world.store.catk):
            entry = world.store.catk[self._sc_idx]
            succ = min(entry["successes"][world.character], 99)
            atte = min(entry["attempts"][world.character], 99)
        x += 36.0
        if succ // 10:
            out.append(
                SpriteDraw(f"ascii.anm:{_SPR_DIGIT + succ // 10}", x, y, z=Z_DIGIT)
            )
        x += 7.0
        out.append(SpriteDraw(f"ascii.anm:{_SPR_DIGIT + succ % 10}", x, y, z=Z_DIGIT))
        x += 14.0
        if atte // 10:
            out.append(
                SpriteDraw(f"ascii.anm:{_SPR_DIGIT + atte // 10}", x, y, z=Z_DIGIT)
            )
        x += 7.0
        out.append(SpriteDraw(f"ascii.anm:{_SPR_DIGIT + atte % 10}", x, y, z=Z_DIGIT))
