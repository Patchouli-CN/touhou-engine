"""帧上下文: 贯穿管线的输入/事件/快照/RNG/命令队列接缝。"""

from __future__ import annotations

import threading
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from ..utils.logger import LoggerManager
from .events import EventStream
from .input import InputFrame
from .rng import Rng
from .snapshot import SnapshotBuilder

log = LoggerManager.get_logger("ENGINE")

if TYPE_CHECKING:
    from .core import World


class Command(ABC):
    """写操作命令: 调用方随时入队, 帧边界统一应用(apis §2.5 接缝)。"""

    @abstractmethod
    def apply(self, world: World, ctx: FrameContext) -> None:
        """帧边界执行, 改世界状态。"""


class CommandQueue:
    """写操作命令队列: 任意线程可入队, 帧边界 drain 后按入队序应用。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._pending: list[Command] = []

    def push(self, command: Command) -> None:
        """入队(线程安全), 下一个帧边界生效。"""
        with self._lock:
            self._pending.append(command)

    def apply(self, world: World, ctx: FrameContext) -> None:
        """帧边界 drain 并执行; 单条炸记日志继续, 不许拖垮模拟。"""
        with self._lock:
            pending, self._pending = self._pending, []
        for command in pending:
            try:
                command.apply(world, ctx)
            except Exception:
                log.exception("命令应用失败, 跳过: {}", type(command).__name__)


class FrameContext:
    """一帧的上下文: 输入/事件流/快照出口/RNG/写命令队列。"""

    def __init__(self, rng: Rng, input: InputFrame | None = None) -> None:
        self.input = input if input is not None else InputFrame()
        self.rng = rng
        self.events = EventStream()
        self.draw = SnapshotBuilder()
        self.commands = CommandQueue()
