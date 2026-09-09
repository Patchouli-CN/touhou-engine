"""handler 公共件: Step 协议与 Handler 类型。"""

from __future__ import annotations

import enum
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..machine import EclMachine


class Step(enum.Enum):
    """handler 结果: 主循环据此收尾; 返回 None = pc 递增继续。"""

    JUMPED = enum.auto()  # pc 已被 handler 改写, 不递增继续
    HALT = enum.auto()  # 脚本结束(宿主应 despawn)
    RESTART = enum.auto()  # 上下文已切换(call/ret/interrupt), 主循环重取指令


Handler = Callable[["EclMachine", Any], "Step | None"]
