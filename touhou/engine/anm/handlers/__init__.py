"""ANM 指令 handler 注册表: HANDLERS = {指令类: handler}, VM 主循环按 type 查表分派。"""

from __future__ import annotations

from ....schemas.anm_script import AnmInstr
from .base import Handler, Step, add_norm_angle
from .control import CONTROL
from .mathops import MATH
from .visual import VISUAL

#: 指令类 → handler; VM 主循环 HANDLERS[type(ins)] 查表分派, 无 if/elif 链
HANDLERS: dict[type[AnmInstr], Handler] = {**CONTROL, **VISUAL, **MATH}

__all__ = ["HANDLERS", "Handler", "Step", "add_norm_angle"]
