"""事件流: sim 对外通讯的唯一通道。"""

from __future__ import annotations

from collections.abc import Callable

import msgspec


class Event(msgspec.Struct, frozen=True, tag_field="type"):
    """事件基类, 作品事件子类挂 tag 组成 tagged union。"""


EventHandler = Callable[[Event], None]


class EventStream:
    """帧内收集事件, 帧末 flush 给订阅者后清空。"""

    def __init__(self) -> None:
        self._pending: list[Event] = []
        self._handlers: list[EventHandler] = []

    def emit(self, event: Event) -> None:
        """帧内产事件(system/命令用)。"""
        self._pending.append(event)

    def subscribe(self, handler: EventHandler) -> None:
        """订阅事件(view/api/replay 消费方), 帧末逐事件回调。"""
        self._handlers.append(handler)

    def flush(self) -> None:
        """帧末把本帧事件发给全部订阅者并清空。"""
        pending, self._pending = self._pending, []
        for event in pending:
            for handler in self._handlers:
                handler(event)
