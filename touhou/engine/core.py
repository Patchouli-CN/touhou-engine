"""World/System 管线骨架与每帧主循环。"""

from __future__ import annotations

import enum
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Generic, TypeVar

import msgspec

from .context import FrameContext
from .snapshot import SceneSnapshot

if TYPE_CHECKING:
    from .assembly import GameAssembly


class World(msgspec.Struct):
    """模拟状态容器基类, 作品子类加自己的字段。"""

    frame: int = 0

    @classmethod
    def compose(cls, assembly: GameAssembly, **params: Any) -> World:
        """按开局参数造出这一局的世界; 作品覆写, 装配入口经注册表按此契约调用。"""
        raise NotImplementedError(f"{cls.__name__} 未实现装配契约 compose")


W = TypeVar("W", bound=World)


class System(ABC, Generic[W]):
    """管线节点基类, 作品子类实现 tick。"""

    @abstractmethod
    def tick(self, world: W, ctx: FrameContext) -> None:
        """处理一帧。"""


class Slot(enum.Enum):
    """管线槽位: engine 定执行序, 作品往槽里挂 system。"""

    INPUT = "input"
    LOGIC = "logic"
    MOVEMENT = "movement"
    COLLISION = "collision"
    OUTPUT = "output"


class Pipeline(Generic[W]):
    """有序 system 槽位清单。"""

    def __init__(self) -> None:
        self._systems: dict[Slot, list[System[W]]] = {slot: [] for slot in Slot}

    def add(self, slot: Slot, system: System[W]) -> None:
        """往槽位末尾挂一个 system, 同槽按挂载序执行。"""
        self._systems[slot].append(system)

    def systems(self, slot: Slot) -> list[System[W]]:
        """槽位内的 system(按挂载序)。"""
        return self._systems[slot]


def tick_frame(world: W, pipeline: Pipeline[W], ctx: FrameContext) -> SceneSnapshot:
    """一帧主循环: 帧边界应用命令 → 槽位序跑 system → 出快照 → 帧末清空事件。"""
    ctx.commands.apply(world, ctx)
    for slot in Slot:
        for system in pipeline.systems(slot):
            system.tick(world, ctx)
    world.frame += 1
    snapshot = ctx.draw.build(world.frame)
    ctx.events.flush()
    return snapshot
