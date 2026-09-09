"""ANM 脚本 VM: 指令即数据 + handler 注册分派, 纯模拟。"""

from __future__ import annotations

from .bank import AnmBank, AnmScript, SpriteSlot, build_bank, build_script
from .handlers import HANDLERS, Step
from .vm import AnmMachine, InterpChannel

__all__ = [
    "HANDLERS",
    "AnmBank",
    "AnmMachine",
    "AnmScript",
    "InterpChannel",
    "SpriteSlot",
    "Step",
    "build_bank",
    "build_script",
]
