"""渲染后端协议: 后端只认 SceneSnapshot + 事件流, 输入只出 InputFrame。

纯抽象, 不含任何渲染库; 具体后端(pygame 等)住 games/thNN/view/。
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..events import Event
from ..input import InputFrame
from ..snapshot import SceneSnapshot

__all__ = ["RenderBackend"]


class RenderBackend(ABC):
    """渲染后端: 窗口生命周期 + 每帧"画快照/采输入" + SE 播放。"""

    @abstractmethod
    def open(self, *, title: str, scale: int = 1) -> None:
        """开窗并准备渲染/音频资源。"""

    @abstractmethod
    def frame(
        self, events: tuple[Event, ...], snapshot: SceneSnapshot
    ) -> InputFrame | None:
        """渲染一帧并采集输入; 返回 None = 用户请求退出。"""

    @abstractmethod
    def play_sounds(self, ids: list[int]) -> None:
        """播一帧的 SE(sim 帧末 frame_sounds, idx 语义在 schemas 音效表)。"""

    @abstractmethod
    def close(self) -> None:
        """关窗释放资源。"""
