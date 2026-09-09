"""引擎：模拟、脚本 VM、渲染后端。"""

from __future__ import annotations

from .assembly import (
    GameAssembly,
    GameData,
    ResourcePaths,
    SaveSemantics,
    ScriptSet,
    check_assembly,
)
from .context import Command, CommandQueue, FrameContext
from .core import Pipeline, Slot, System, World, tick_frame
from .events import Event, EventHandler, EventStream
from .input import Button, InputFrame, MenuAction
from .rng import Rng
from .snapshot import (
    EffectDraw,
    SceneSnapshot,
    SnapshotBuilder,
    SpriteDraw,
    TextDraw,
)

__all__ = [
    "Button",
    "Command",
    "CommandQueue",
    "EffectDraw",
    "Event",
    "EventHandler",
    "EventStream",
    "FrameContext",
    "GameAssembly",
    "GameData",
    "InputFrame",
    "MenuAction",
    "Pipeline",
    "ResourcePaths",
    "Rng",
    "SaveSemantics",
    "SceneSnapshot",
    "ScriptSet",
    "Slot",
    "SnapshotBuilder",
    "SpriteDraw",
    "System",
    "TextDraw",
    "World",
    "check_assembly",
    "tick_frame",
]
