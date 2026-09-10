"""th07 的自机: 樱之结界状态机 + PlayerField 子类 + 子机(option)位置机 + 死亡结算。

结界语义照抄 old/touhou/games/th07/bomb.py 的 Border(Player.cpp
ActivateBorder/UpdateState/BreakBorder*); 子机状态机照抄
old/touhou/games/th07/player.py §A.4(optionState 五态)。
"""

from __future__ import annotations

import math
from collections.abc import Callable
from enum import IntEnum

import msgspec

from ...engine.context import FrameContext
from ...engine.player import PlayerField
from ...utils.math import Vec2
from .globals import CHERRY_MAX_RANGE

# ---- 结界常量(Player.cpp / BombData.cpp) ----
BORDER_DURATION = 540  # 结界持续帧数(invulnerabilityTimer=540)
BORDER_BREAK_INVULN = 40  # 破裂后无敌/borderInvulnerabilityTime
BORDER_CHERRY_GAIN = 10000  # 自然破: cherryMax/cherry 各 +10000
ITEM_CHERRY_SMALL = 8  # 破裂清屏掉小樱点(Player.cpp:2182)

# ---- 死亡结算常量(Player.cpp UpdateDeath) ----
DEATH_POWER_LOSS = 16
DEATH_SUBRANK_PENALTY = 1600
CHERRY_PENALTY_CAP = 100000  # 非咲夜
CHERRY_PENALTY_CAP_SAKUYA = 60000

# ---- 子机常量(§A.4) ----
FOCUS_TRANSITION_FRAMES = 8
OPTION_FOCUS_ANGLE = 0.22439948  # 咲夜B focus 子机夹角半宽
OPTION_ANGLE_MIN = -2.1991148
OPTION_ANGLE_MAX = -0.9424778
OPTION_ANGLE_CENTER = -1.5707964  # -pi/2
OPTION_ANGLE_RETURN_STEP = 0.06283186
OPTION_ANGLE_RETURN_EPS = 0.03141593


class BorderState(IntEnum):
    """结界状态(hasBorder)。"""

    NONE = 0
    READY = 1  # 满樱待激活
    ACTIVE = 2  # 结界展开中


class Border(msgspec.Struct):
    """樱之结界(ActivateBorder/UpdateState/BreakBorder* 的纯逻辑)。

    上层职责: 满樱时 ready_border(); 每帧 READY 且非 bomb 时 activate_border(),
    ACTIVE 时 tick(); 中弹/按 bomb 键/死亡时 break_border()。
    """

    has_border: BorderState = BorderState.NONE
    invulnerability_timer: int = 0
    border_timer: int = 0  # 激活时定格 540, cherryPlus 公式分母
    border_invulnerability_time: int = 0

    def ready_border(self) -> None:
        """满樱信号 → READY(GameManager.cpp:928-931 → ActivateBorder 的延迟路径)。"""
        if self.has_border == BorderState.NONE:
            self.has_border = BorderState.READY

    def activate_border(self, *, bombing: bool = False) -> bool:
        """Player::ActivateBorder (Player.cpp:2087-2144): 非 bomb 时 READY→ACTIVE。"""
        if self.has_border != BorderState.READY or bombing:
            return False
        self.invulnerability_timer = BORDER_DURATION
        self.border_timer = BORDER_DURATION
        self.has_border = BorderState.ACTIVE
        return True

    def tick(self, *, cherry: int, cherry_start: int, cherry_max: int) -> tuple[int, BorderBreakResult | None]:
        """每帧: 冷却递减 + cherryPlus 倒计时公式; 归零自然破。

        cherryPlus = cherryStart + invuln*50000/borderTimer (C++ i32 乘除,
        Player.cpp:1952-1959); 返回 (cherry_plus 显示值, 自然破结果或 None)。
        """
        if self.border_invulnerability_time != 0:
            self.border_invulnerability_time -= 1
        if self.has_border != BorderState.ACTIVE:
            return cherry_start, None
        plus = self.invulnerability_timer * 50000 // self.border_timer
        if plus < 0:
            plus = 0
        cherry_plus = cherry_start + plus
        self.invulnerability_timer -= 1
        if self.invulnerability_timer <= 0:
            result = self.break_border_naturally(
                cherry=cherry, cherry_start=cherry_start, cherry_max=cherry_max
            )
            return result.cherry_plus, result
        return cherry_plus, None

    def break_border_naturally(
        self, *, cherry: int, cherry_start: int, cherry_max: int
    ) -> BorderBreakResult:
        """Player::BreakBorderNaturally: +10000 上限/樱点, 得分 (cherry-cherryStart)*10。"""
        cherry_max = min(cherry_max + BORDER_CHERRY_GAIN, cherry_start + CHERRY_MAX_RANGE)
        cherry = min(cherry + BORDER_CHERRY_GAIN, cherry_max)
        score = (cherry - cherry_start) * 10
        self.has_border = BorderState.NONE
        self.invulnerability_timer = BORDER_BREAK_INVULN
        self.border_invulnerability_time = BORDER_BREAK_INVULN
        return BorderBreakResult(
            cherry=cherry, cherry_max=cherry_max, cherry_plus=cherry_start, score=score
        )

    def break_border(self) -> None:
        """Player::BreakBorder (Player.cpp:2148-2182): 主动破/中弹破/死亡破。

        上层: 清 captureScore/isCapturing, cherry_plus=cherry_start,
        全屏清弹圆(半径 32 每帧 +16 持续 50 帧, 掉小樱点)。
        """
        self.has_border = BorderState.NONE
        self.invulnerability_timer = BORDER_BREAK_INVULN
        self.border_invulnerability_time = BORDER_BREAK_INVULN

    @property
    def active(self) -> bool:
        """结界展开中。"""
        return self.has_border == BorderState.ACTIVE


class BorderBreakResult(msgspec.Struct):
    """BreakBorderNaturally 的入账透出(Player.cpp:2004-2034)。"""

    cherry: int
    cherry_max: int
    cherry_plus: int  # = cherry_start
    score: int  # (cherry - cherry_start) * 10 (代码值)
    invulnerability_timer: int = BORDER_BREAK_INVULN


class Th07PlayerField(PlayerField):
    """th07 的自机: 结界命中拦截(_intercept_hit) + 结界引用。

    border 与 on_border_break 由 world 装配; 结界 ACTIVE 时被弹不破防死,
    转主动破(world 做清弹圆/入账), 拦截本次死亡。
    """

    border: Border = msgspec.field(default_factory=Border)
    on_border_break: Callable[[], None] | None = None

    def _intercept_hit(self, ctx: FrameContext) -> bool:
        """结界 ACTIVE 时拦截命中 → 主动破(Player.cpp CalcKillboxCollision 返回 2 分支)。"""
        if not self.border.active:
            return False
        if self.on_border_break is not None:
            self.on_border_break()
        return True


class OptionState(IntEnum):
    """子机状态机(§A.4 optionState)。"""

    HIDDEN = 0
    UNFOCUSED = 1
    FOCUSING = 2
    FOCUSED = 3
    UNFOCUSING = 4


class OptionMachine(msgspec.Struct):
    """子机位置机: 非咲夜B 平移插值 / 咲夜B 旋转, 每帧产出两子机位置。

    出处 old/touhou/games/th07/player.py _update_options_plain/_rotating。
    """

    rotating: bool = False  # 咲夜B
    state: OptionState = OptionState.UNFOCUSED
    focus_movement_timer: int = 0
    option_angle: float = OPTION_ANGLE_CENTER
    options: list[Vec2] = msgspec.field(default_factory=list)

    def step(self, pos: Vec2, velocity: Vec2, *, focus: bool, firing: bool) -> list[Vec2]:
        """推进一帧并返回两个子机的世界坐标。"""
        if self.rotating:
            self._step_angle(velocity, focus=focus, firing=firing)
            self._step_rotating(pos, focus=focus)
        else:
            self._step_plain(pos, focus=focus)
        return self.options

    def _step_plain(self, pos: Vec2, *, focus: bool) -> None:
        """非咲夜B: (±24,0) ↔ (±8,-32), 8 帧过渡; x 随 t², y 随 t。"""
        st = self.state
        if st == OptionState.HIDDEN:
            self.focus_movement_timer = 0
            return
        ox = oy = 0.0
        if st == OptionState.UNFOCUSED:
            ox = 24.0
            self.focus_movement_timer = 0
            if focus:
                self.state = OptionState.FOCUSING
        if self.state == OptionState.FOCUSING:
            self.focus_movement_timer += 1
            t = self.focus_movement_timer / 8.0
            oy = -32.0 + (1.0 - t) * 32.0
            ox = -16.0 * t * t + 24.0
            if self.focus_movement_timer >= FOCUS_TRANSITION_FRAMES:
                self.state = OptionState.FOCUSED
            elif not focus:
                self.state = OptionState.UNFOCUSING
                self.focus_movement_timer = 8 - self.focus_movement_timer
        elif self.state == OptionState.FOCUSED:
            ox, oy = 8.0, -32.0
            self.focus_movement_timer = 0
            if not focus:
                self.state = OptionState.UNFOCUSING
        elif self.state == OptionState.UNFOCUSING:
            self.focus_movement_timer += 1
            t = self.focus_movement_timer / 8.0
            oy = -32.0 + 32.0 * t
            ox = -16.0 * (1.0 - t * t) + 24.0
            if self.focus_movement_timer >= FOCUS_TRANSITION_FRAMES:
                self.state = OptionState.UNFOCUSED
            elif focus:
                self.state = OptionState.FOCUSING
                self.focus_movement_timer = 8 - self.focus_movement_timer
        self.options = [pos + Vec2(-ox, oy), pos + Vec2(ox, oy)]

    def _step_rotating(self, pos: Vec2, *, focus: bool) -> None:
        """咲夜B: 两子机绕 optionAngle 旋转半径 24; focus 收窄到 ±0.2244。"""
        st = self.state
        if st == OptionState.HIDDEN:
            self.focus_movement_timer = 0
            return
        base = Vec2.from_angle(self.option_angle + math.pi / 2, 24.0)
        tgt1 = Vec2.from_angle(self.option_angle + OPTION_FOCUS_ANGLE, 24.0)
        tgt0 = Vec2.from_angle(self.option_angle - OPTION_FOCUS_ANGLE, 24.0)
        if st == OptionState.UNFOCUSED:
            self.focus_movement_timer = 0
            if focus:
                self.state = OptionState.FOCUSING
            else:
                self.options = [pos - base, pos + base]
                return
        if self.state == OptionState.FOCUSING:
            if not focus:
                self.state = OptionState.UNFOCUSING
                self.focus_movement_timer = 8 - self.focus_movement_timer
            else:
                self.focus_movement_timer += 1
                t = self.focus_movement_timer / 8.0
                if self.focus_movement_timer >= FOCUS_TRANSITION_FRAMES:
                    self.state = OptionState.FOCUSED
                self.options = [pos + (-base).lerp(tgt0, t), pos + base.lerp(tgt1, t)]
                return
        if self.state == OptionState.FOCUSED:
            self.focus_movement_timer = 0
            if not focus:
                self.state = OptionState.UNFOCUSING
            else:
                self.options = [pos + tgt0, pos + tgt1]
                return
        if self.state == OptionState.UNFOCUSING:
            if focus:
                self.state = OptionState.FOCUSING
                self.focus_movement_timer = 8 - self.focus_movement_timer
            else:
                self.focus_movement_timer += 1
                t = 1.0 - self.focus_movement_timer / 8.0
                if self.focus_movement_timer >= FOCUS_TRANSITION_FRAMES:
                    self.state = OptionState.UNFOCUSED
                self.options = [pos + (-base).lerp(tgt0, t), pos + base.lerp(tgt1, t)]

    def _step_angle(self, velocity: Vec2, *, focus: bool, firing: bool) -> None:
        """OptionAngle 随横向速度摆动/回中(C++ 仅射击且非 focus 时更新)。"""
        if not firing or focus:
            return
        vx = velocity.x
        if vx != 0.0:
            self.option_angle += (vx / 4.0) * math.pi / 5.0 / 10.0
            if self.option_angle < OPTION_ANGLE_MIN:
                self.option_angle = OPTION_ANGLE_MIN
            elif self.option_angle > OPTION_ANGLE_MAX:
                self.option_angle = OPTION_ANGLE_MAX
        elif abs(self.option_angle - OPTION_ANGLE_CENTER) > OPTION_ANGLE_RETURN_EPS:
            step = OPTION_ANGLE_RETURN_STEP
            if self.option_angle > OPTION_ANGLE_CENTER:
                step = -step
            self.option_angle += step
        else:
            self.option_angle = OPTION_ANGLE_CENTER


class DeathSettle(msgspec.Struct):
    """死亡倒计时归 0 的结算(UpdateDeath, th07 扩展: 樱罚/subrank)。"""

    has_lives: bool
    new_power: float
    drop_power_big: int = 0
    drop_power_small: int = 0
    drop_full_power: int = 0
    cherry_penalty: int = 0  # 已 cap + 向下取整 10
    activate_all_items: bool = False
    subrank_delta: int = -DEATH_SUBRANK_PENALTY


def settle_death(
    *, power: float, lives: float, cherry: int, cherry_start: int,
    cherry_penalty_multiplier: float, is_sakuya: bool,
) -> DeathSettle:
    """死亡结算(出处 old/touhou/games/th07/player.py:290 _settle_death)。"""
    if lives > 0:
        # 有残机: power>16 则 -16 否则归 0; 掉 1 大 P + 5 小 P
        new_power = 0.0 if int(power) <= DEATH_POWER_LOSS else power - DEATH_POWER_LOSS
        penalty = int((cherry - cherry_start) * cherry_penalty_multiplier)
        cap = CHERRY_PENALTY_CAP_SAKUYA if is_sakuya else CHERRY_PENALTY_CAP
        if penalty > cap:
            penalty = cap
        penalty -= penalty % 10
        return DeathSettle(
            True,
            new_power,
            drop_power_big=1,
            drop_power_small=5,
            cherry_penalty=penalty,
            activate_all_items=True,
        )
    # 无残机: power 归 0, 掉 5 个 FULL_POWER
    return DeathSettle(False, 0.0, drop_full_power=5)
