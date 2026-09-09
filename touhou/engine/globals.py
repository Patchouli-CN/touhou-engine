"""作品全局状态骨架: 分数追赶(真实分/显示分) + 不透明计数器组 + 事件。

engine 只给形态: guiScore 追赶数学 (GameManager::OnUpdate) 与命名计数器;
字段语义(残机/bomb 数/火力/死亡/重试...)由作品自定, 增减全产事件供
view/api/replay 消费。
"""

from __future__ import annotations

import msgspec

from .context import FrameContext
from .core import System, World
from .events import Event

# 分数上限 (GameManager::OnUpdate / CutChain)
SCORE_MAX = 999999999

# guiScore 每帧追赶增量上限 (GameManager::OnUpdate)
GUI_SCORE_INCREMENT_MAX = 578910


class ScoreChanged(Event, frozen=True, tag="score_changed"):
    """真实分入账(add_score; delta 是入账后的实际增量)。"""

    delta: int
    score: int


class CounterChanged(Event, frozen=True, tag="counter_changed"):
    """一个命名计数器变化(残机/bomb/火力等, 语义由作品定)。"""

    name: str
    delta: float
    value: float


class GlobalsField(msgspec.Struct):
    """一局游戏的全局状态骨架: 分数三元组 + 命名计数器组。"""

    # ---- 分数 ----
    score: int = 0  # 真实分(=显示分语义)
    gui_score: int = 0  # HUD 显示分, 每帧向 score 追赶
    gui_score_difference: int = 0  # 当前帧追赶步长(单调只增)
    # ---- 计数器组(作品自定字段语义) ----
    counters: dict[str, float] = msgspec.field(default_factory=dict)

    # ---- 分数 (§0.2) ----
    def add_score(self, v: int, ctx: FrameContext) -> None:
        """入参为代码值(=显示分*10), 真实入账 v//10 (GameManager::AddScore)。"""
        delta = v // 10
        self.score += delta
        ctx.events.emit(ScoreChanged(delta, self.score))

    def tick_gui_score(self) -> None:
        """每帧: guiScore 追赶 score (GameManager::OnUpdate)。

        inc = (score-guiScore)>>5, 最小 1 最大 578910;
        guiScoreDifference 单调只增不降, 追上后归零。
        """
        if self.score >= 1000000000:
            self.score = SCORE_MAX
        if self.gui_score == self.score:
            return
        if self.score < self.gui_score:
            self.score = self.gui_score
        inc = (self.score - self.gui_score) >> 5
        if inc >= GUI_SCORE_INCREMENT_MAX:
            inc = GUI_SCORE_INCREMENT_MAX
        elif inc == 0:
            inc = 1
        if self.gui_score_difference < inc:
            self.gui_score_difference = inc
        if self.gui_score + self.gui_score_difference > self.score:
            self.gui_score_difference = self.score - self.gui_score
        self.gui_score += self.gui_score_difference
        if self.gui_score >= self.score:
            self.gui_score_difference = 0
            self.gui_score = self.score

    def snap_gui_score(self) -> None:
        """显示分立即对齐真实分 (GameManager::CutChain, 结算/切关时用)。"""
        if self.score >= 1000000000:
            self.score = SCORE_MAX
        self.gui_score = self.score
        self.gui_score_difference = 0

    # ---- 计数器组 ----
    def counter(self, name: str) -> float:
        """读计数器(未设过为 0)。"""
        return self.counters.get(name, 0.0)

    def set_counter(self, name: str, value: float, ctx: FrameContext) -> None:
        """写计数器并产 CounterChanged。"""
        old = self.counters.get(name, 0.0)
        self.counters[name] = value
        ctx.events.emit(CounterChanged(name, value - old, value))

    def adjust(self, name: str, delta: float, ctx: FrameContext) -> float:
        """增减计数器并产 CounterChanged, 返回新值。"""
        value = self.counters.get(name, 0.0) + delta
        self.counters[name] = value
        ctx.events.emit(CounterChanged(name, delta, value))
        return value


class GlobalsSystem(System[World]):
    """LOGIC 槽: 显示分每帧追赶真实分。"""

    def __init__(self, field: GlobalsField) -> None:
        self.field = field

    def tick(self, world: World, ctx: FrameContext) -> None:
        self.field.tick_gui_score()
