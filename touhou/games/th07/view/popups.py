"""弹字与横幅文字层: AsciiManager 弹字 + Gui 状态横幅 + 关卡标题。

- 收点弹字 (AsciiManager.cpp DrawPopups): world.frame_popups 透出 (x, y,
  代码值, ARGB, 槽), 8x8 字形 (ascii.anm sprite 0-30), 寿命 60 帧
  (AsciiManager.cpp:56-60), 字形按 timer 三段切换, 透明度按到自机距离平方
  衰减 (:1085-1103); value=-1 恒 sprite 10 (48x8 PowerUp 字形)。
- 状态横幅 (Gui.cpp:278-318 OnDraw + :1350-1369 滑入): Full Power Mode! /
  CherryPoint Max! / Supernatural Border!! 边沿检测 world 状态触发
  (C++ 是 ShowStatusPopup 调用点, 这里等效); 前 30 帧 x=416→104 滑入,
  y=168, 180 帧消。
- BONUS 横幅 (Gui.cpp:79-86 ShowBonusScore + :1330-1349): boss 清场累计分,
  world.frame_bonus_score 透出, 同款滑入, y=48, 250 帧消。
- Spell Card Bonus! (Gui.cpp:99-106/:319-338): 符卡捕获触发, 红字 +
  2 倍粉字居中, 280 帧消。
- 关卡标题 (Gui.cpp:673-674 ExecuteVmsAnms(stageTextVm, 2048, 5)): std{N}txt.anm
  5 台脚本 VM 自时序入场/淡出; MSG_MUSIC 的 BGM 行重触发 (Gui.cpp:959-973)。

字符贴图中心锚换算用 ascii.anm 的 sprite 宽高; 坐标系: 弹字=游戏区(加窗口
偏移), 横幅/标题=窗口坐标直出。
"""

from __future__ import annotations

from ....engine import SpriteDraw
from ....engine.anm import AnmBank, AnmMachine
from ....engine.rng import Rng
from ..snapshot import GAME_X, GAME_Y
from .spellcard import _vm_sprite

Z_POPUP = 120.0  # 弹字/横幅: Gui 层(不裁剪不振屏)
Z_STAGE_TITLE = 110.0

_POPUP_LIFE = 60  # 弹字寿命 (AsciiManager.cpp:56-60)
_POPUP_CAP1 = 720  # CreatePopup1 环形槽容量 (AsciiManager)
_POPUP_CAP2 = 3  # CreatePopup2 (弹消点) 槽容量

# 横幅滑入 (Gui.cpp:1332-1343): timer<30 时 x = 416 - timer*312/30, 之后 104
_SLIDE_FRAMES = 30
_SLIDE_X_START = 416.0
_SLIDE_X_END = 104.0

# 状态横幅文本/颜色/步进/横缩 (Gui.cpp:280-317; 颜色 ARGB 取 RGB)
_STATUS_FULL_POWER = 1
_STATUS_BORDER = 2
_STATUS_CHERRY_MAX = 3
_STATUS_TEXT = {
    _STATUS_FULL_POWER: ("Full Power Mode!", (192, 176, 255), 14.0, 1.0),
    _STATUS_BORDER: ("Supernatural Border!!", (224, 176, 255), 11.0, 0.9),
    _STATUS_CHERRY_MAX: ("CherryPoint Max!", (192, 176, 255), 14.0, 1.0),
}
_STATUS_Y = 168.0
_STATUS_LIFE = 180
_BONUS_Y = 48.0
_BONUS_LIFE = 250
_SC_BONUS_LIFE = 280

_TITLE_SCRIPTS = 5  # ExecuteVmsAnms(vms, 2048, 5) (Gui.cpp:673-674)
_SCR_BGM_LINE = 4  # BGM 行脚本 (Gui.cpp:962-963, 键 = 2052-0x800)
_SCR_BGM_LINE_EX = 5  # EX 面 (currentStage==6) 用 (Gui.cpp:967-968)
_SPR_BGM_BASE = 3  # sprite = 2051+musicIdx, 键 = -0x800 (Gui.cpp:970-973)


def _slide_x(timer: int) -> float:
    """横幅滑入 x (Gui.cpp:1332-1343)。"""
    if timer < _SLIDE_FRAMES:
        return timer * -312.0 / _SLIDE_FRAMES + _SLIDE_X_START
    return _SLIDE_X_END


class _Popup:
    """一个收点弹字 (AsciiManagerPopup 子集)。"""

    __slots__ = ("x", "y", "value", "rgb", "kind", "timer")

    def __init__(self, x: float, y: float, value: int, argb: int, kind: int) -> None:
        self.x, self.y = x, y
        self.value = value
        self.rgb = ((argb >> 16) & 255, (argb >> 8) & 255, argb & 255)
        self.kind = kind
        self.timer = 0


class ScorePopups:
    """收点弹字池: feed 消费 world.frame_popups, step 推进/产出 SpriteDraw。"""

    def __init__(self) -> None:
        self._popups: list[_Popup] = []

    def __len__(self) -> int:
        return len(self._popups)

    def feed(self, world) -> None:
        """登记本帧透出的弹字; 同槽超容量覆盖最旧 (CreatePopup1/2 环形)。"""
        for x, y, value, argb, kind in world.frame_popups:
            cap = _POPUP_CAP2 if kind == 2 else _POPUP_CAP1
            same = [p for p in self._popups if p.kind == kind]
            while len(same) >= cap:
                self._popups.remove(same.pop(0))
            self._popups.append(_Popup(x, y, value, argb, kind))

    def step(self, player_pos: tuple[float, float]) -> list[SpriteDraw]:
        """DrawPopups (AsciiManager.cpp:1052-1129); player_pos 为游戏区坐标。"""
        out: list[SpriteDraw] = []
        alive: list[_Popup] = []
        for p in self._popups:
            p.timer += 1
            if p.timer > _POPUP_LIFE:
                continue
            alive.append(p)
            digits = str(p.value) if p.value >= 0 else "\n"  # -1 → PowerUp 字形
            x = GAME_X + p.x - (len(digits) << 2)  # :1081 count<<2
            y = GAME_Y + p.y
            dx, dy = player_pos[0] - p.x, player_pos[1] - p.y
            d2 = dx * dx + dy * dy
            if d2 > 4096:
                alpha = 208
            elif d2 > 1024:
                alpha = int(80 + (d2 - 1024) * 128 / 3072)
            else:
                alpha = 80
            for ch in digits:
                d = 10 if ch == "\n" else ord(ch) - ord("0")
                # 字形三段切换 (:1109-1123); PowerUp 字形恒 sprite 10
                if p.timer < 52 or d == 10:
                    sid = d
                elif p.timer < 56:
                    sid = d + 11
                else:
                    sid = d + 21
                # 8x8 字形中心锚 (+4,+4)
                out.append(
                    SpriteDraw(
                        f"ascii.anm:{sid}",
                        x + 4.0,
                        y + 4.0,
                        z=Z_POPUP,
                        alpha=alpha,
                        color=p.rgb,
                    )
                )
                x += 8.0
        self._popups = alive
        return out


class StatusBanner:
    """状态横幅: Full Power/Cherry Max/Border 的边沿检测 + 滑入横幅。"""

    def __init__(self) -> None:
        self._kind = 0  # 0 = 隐藏
        self._timer = 0
        self._prev_power = 0.0
        self._prev_cherry_maxed = False
        self._prev_border = False

    def step(self, world) -> list[SpriteDraw]:
        g = world.th07
        power = float(g.power)
        maxed = g.cherry >= g.cherry_max
        border = bool(world.player.border.active)
        # ShowStatusPopup 调用点的边沿等效 (ItemManager.cpp:231 等 /
        # GameManager.cpp:927-944 / Player.cpp:2137)
        if power >= 128.0 and self._prev_power < 128.0:
            self._kind, self._timer = _STATUS_FULL_POWER, 0
        if maxed and not self._prev_cherry_maxed:
            self._kind, self._timer = _STATUS_CHERRY_MAX, 0
        if border and not self._prev_border:
            self._kind, self._timer = _STATUS_BORDER, 0
        self._prev_power = power
        self._prev_cherry_maxed = maxed
        self._prev_border = border
        if not self._kind:
            return []
        self._timer += 1
        if self._timer >= _STATUS_LIFE:
            self._kind = 0
            return []
        text, rgb, step, xscale = _STATUS_TEXT[self._kind]
        return _ascii_line(
            text, _slide_x(self._timer), _STATUS_Y, rgb, Z_POPUP, step, xscale
        )


class BonusBanners:
    """BONUS 清场横幅 + Spell Card Bonus! 横幅。"""

    def __init__(self) -> None:
        self._bonus = 0
        self._bonus_timer = 0
        self._sc_bonus = 0
        self._sc_timer = 0

    def on_spellcard_captured(self, score: int) -> None:
        """ShowSpellcardBonus (Gui.cpp:99-106; 调用点 EclManager.cpp:784)。"""
        self._sc_bonus = score
        self._sc_timer = 0

    def step(self, world) -> list[SpriteDraw]:
        out: list[SpriteDraw] = []
        if world.frame_bonus_score:
            # ShowBonusScore (Gui.cpp:79-86)
            self._bonus = world.frame_bonus_score
            self._bonus_timer = 0
        if self._bonus:
            self._bonus_timer += 1
            if self._bonus_timer >= _BONUS_LIFE:
                self._bonus = 0
            else:
                out += _ascii_line(
                    f"BONUS {self._bonus:8d}",
                    _slide_x(self._bonus_timer),
                    _BONUS_Y,
                    (255, 255, 128),  # 0xffffff80 (Gui.cpp:273)
                    Z_POPUP,
                    14.0,
                    1.0,
                )
        if self._sc_bonus:
            self._sc_timer += 1
            if self._sc_timer >= _SC_BONUS_LIFE:
                self._sc_bonus = 0
            else:
                # "Spell Card Bonus!" 红字居中 (Gui.cpp:321-325)
                title = "Spell Card Bonus!"
                x = (384.0 - len(title) * 16.0) / 2.0 + 32.0
                out += _ascii_line(title, x, 80.0, (255, 0, 0), Z_POPUP, 14.0, 1.0)
                # "+%d" 2 倍粉字居中 (Gui.cpp:326-334)
                num = f"+{self._sc_bonus}"
                x = (384.0 - len(num) * 32.0) / 2.0 + 32.0
                out += _ascii_line(num, x, 96.0, (255, 128, 128), Z_POPUP, 32.0, 2.0)
        return out


def _ascii_line(
    text: str,
    x: float,
    y: float,
    rgb: tuple[int, int, int],
    z: float,
    step: float,
    xscale: float,
) -> list[SpriteDraw]:
    """一行 16x16 ascii 字形 (c → sprite ord(c)-1); x/y 为左上, 输出中心锚。"""
    out: list[SpriteDraw] = []
    for ch in text:
        if ch == " ":
            x += step
            continue
        out.append(
            SpriteDraw(
                f"ascii.anm:{ord(ch) - 1}",
                x + 8.0 * xscale,
                y + 8.0,
                z=z,
                scale_x=xscale,
                color=rgb,
            )
        )
        x += step
    return out


class StageTitle:
    """关卡标题 VM 组: set_stage 重建 5 台 + MSG_MUSIC 的 BGM 行重触发。"""

    def __init__(self, rng: Rng) -> None:
        self._rng = rng
        self._stage = -1
        self._vms: list[tuple[AnmMachine, str]] = []
        self._music_vm: tuple[AnmMachine, str] | None = None

    def sync_stage(self, bank_of, stage_no: int) -> None:
        """换关重建 (Gui::ActualAddedCallback 的按关加载段, Gui.cpp:521-648)。"""
        if stage_no == self._stage:
            return
        self._stage = stage_no
        self._vms = []
        self._music_vm = None
        bank: AnmBank | None = bank_of(f"std{stage_no}txt.anm")
        if bank is None:
            return
        for key in range(_TITLE_SCRIPTS):
            vm = AnmMachine(self._rng)
            vm.start(bank.scripts.get(key))
            if vm.alive:
                self._vms.append((vm, f"std{stage_no}txt.anm"))

    def on_music(self, bank_of, music_idx: int) -> None:
        """MSG_MUSIC (Gui.cpp:959-973): BGM 行重入场 + 曲名 sprite。"""
        bank: AnmBank | None = bank_of(f"std{self._stage}txt.anm")
        if bank is None:
            return
        # C++ currentStage 0-based ==6 即 EX 面 → 链式键 5
        key = _SCR_BGM_LINE_EX if self._stage == 7 else _SCR_BGM_LINE
        vm = AnmMachine(self._rng)
        vm.start(bank.scripts.get(key))
        if not vm.alive:
            return
        vm.active_sprite_idx = _SPR_BGM_BASE + music_idx
        self._music_vm = (vm, f"std{self._stage}txt.anm:{_SPR_BGM_BASE + music_idx}")

    def step(self) -> list[SpriteDraw]:
        """Gui::OnDraw stageTextVm 段 (Gui.cpp:1723-1726): Draw(含旋转)。"""
        out: list[SpriteDraw] = []
        alive: list[tuple[AnmMachine, str]] = []
        for vm, name in self._vms:
            vm.execute()
            if not vm.alive:
                continue
            alive.append((vm, name))
            spr = _vm_sprite(
                vm,
                f"{name}:{vm.active_sprite_idx}",
                vm.pos[0],
                vm.pos[1],
                Z_STAGE_TITLE,
            )
            if spr is not None:
                out.append(spr)
        self._vms = alive
        if self._music_vm is not None:
            vm, image = self._music_vm
            vm.execute()
            if not vm.alive:
                self._music_vm = None
            else:
                spr = _vm_sprite(vm, image, vm.pos[0], vm.pos[1], Z_STAGE_TITLE)
                if spr is not None:
                    out.append(spr)
        return out
