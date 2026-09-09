"""引擎：模拟、脚本 VM、渲染后端。"""

from __future__ import annotations

from .anm import (
    AnmBank,
    AnmMachine,
    AnmScript,
    InterpChannel,
    SpriteSlot,
    build_bank,
    build_script,
)
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
    "AnmBank",
    "AnmMachine",
    "AnmScript",
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
    "InterpChannel",
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
    "SpriteSlot",
    "System",
    "TextDraw",
    "World",
    "build_bank",
    "build_script",
    "check_assembly",
    "tick_frame",
]
