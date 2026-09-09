"""handler 公共件: Step 协议、Handler 类型、角度归一化与跳转/插值小帮手。"""

from __future__ import annotations

import enum
import math
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..vm import AnmMachine


class Step(enum.Enum):
    """handler 结果: 主循环据此收尾; 返回 None = pc 递增继续。"""

    JUMPED = enum.auto()  # pc 已被 handler 改写, 不递增继续
    HALT = enum.auto()  # 脚本结束, 不进帧尾
    YIELD = enum.auto()  # 本帧到此, 进帧尾


Handler = Callable[["AnmMachine", Any], "Step | None"]


def add_norm_angle(a: float, b: float) -> float:
    """a+b 包到 [-pi, pi]。"""
    # utils::AddNormalizeAngle 语义, 移植自 old/touhou/engine/view/anm_vm.py:26
    a += b
    while a > math.pi:
        a -= 2 * math.pi
    while a < -math.pi:
        a += 2 * math.pi
    return a


def cond_jump(vm: AnmMachine, ok: bool, dest: int, set_time: int) -> Step | None:
    """条件成立则跳转。"""
    if ok:
        vm.jump_to(dest, set_time)
        return Step.JUMPED
    return None


def pos_interp_begin(
    vm: AnmMachine, duration: int, ease: int, final: list[float]
) -> None:
    """位置插值公共setup: 起点取 pos 还是 offset 看 use_offset。"""
    # AnmManager.cpp:1773-1786
    vm.pos_interp.restart(duration, ease)
    vm.pos_initial = list(vm.offset if vm.use_offset else vm.pos)
    vm.pos_final = final
