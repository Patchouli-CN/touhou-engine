"""一帧的用户输入: 命名布尔字段, 替代引擎 InputFrame 的键位集合。"""

from __future__ import annotations

import msgspec

from ..engine.input import Button


class Input(msgspec.Struct, frozen=True):
    """一帧的按键输入(全部为"按住"语义; advance/bomb 按点按脉冲处理)。

    对话推进用 advance(= 对话中 Z 按下沿), 快进用 skip(= 按住 Ctrl)。
    """

    left: bool = False
    right: bool = False
    up: bool = False
    down: bool = False
    focus: bool = False
    shoot: bool = False
    bomb: bool = False
    advance: bool = False
    skip: bool = False

    @classmethod
    def none(cls) -> Input:
        """全空输入(不射击/不移动)。"""
        return cls()

    def _held(self) -> frozenset[Button]:
        """按住集合(沿由 Game 按上帧对比推导; bomb 按住也只触发一次按下沿)。"""
        held = set()
        if self.left:
            held.add(Button.LEFT)
        if self.right:
            held.add(Button.RIGHT)
        if self.up:
            held.add(Button.UP)
        if self.down:
            held.add(Button.DOWN)
        if self.focus:
            held.add(Button.FOCUS)
        if self.shoot:
            held.add(Button.SHOT)
        if self.bomb:
            held.add(Button.BOMB)
        if self.skip:
            held.add(Button.SKIP)
        return frozenset(held)
