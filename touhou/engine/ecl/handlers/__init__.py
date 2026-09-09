"""ECL 指令 handler 注册表: HANDLERS = {指令类: handler}, VM 主循环按 type 查表分派。"""

from __future__ import annotations

from ....schemas.ecl import EclInstr
from .base import Handler, Step
from .control import CONTROL
from .delegated import DELEGATED
from .mathops import MATH
from .movement import MOVEMENT

#: 指令类 → handler; VM 主循环 HANDLERS[type(ins)] 查表分派, 无 if/elif 链。
#: 作品专属指令在 delegated 里注册为宿主钩子透传(engine 不实现其语义)
HANDLERS: dict[type[EclInstr], Handler] = {**CONTROL, **MATH, **MOVEMENT, **DELEGATED}

__all__ = ["HANDLERS", "Handler", "Step"]
