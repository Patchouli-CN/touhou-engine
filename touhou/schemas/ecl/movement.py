"""ECL 移动指令(位置/速度/限时位移/轨道/移动边界), 两作共享部分。"""

from __future__ import annotations

from .base import EclInstr, FloatOperand, IntOperand

# 语义出处 Reference/th07/src/th07/EclManager.cpp 各 case +
# v800: EclRunLow.inl:496-632 / EclHelpers.cpp:27-87 / EclDependencies.cpp:99-274


class SetAngularVel(EclInstr, frozen=True, tag="set_angular_vel"):
    """设角速度(移动模式 1)。"""

    velocity: FloatOperand


class SetMoveAccel(EclInstr, frozen=True, tag="set_move_accel"):
    """设移动加速度(移动模式 1)。"""

    accel: FloatOperand


class MoveAtPlayer(EclInstr, frozen=True, tag="move_at_player"):
    """朝自机方向 + angle_offset 直飞。"""

    angle_offset: FloatOperand
    speed: FloatOperand


class MoveDirTime(EclInstr, frozen=True, tag="move_dir_time"):
    """限时角度位移(duration <= 0 = angle/speed 直飞)。"""

    duration: IntOperand
    easing: IntOperand
    angle: FloatOperand
    speed: FloatOperand


class SetMovementBounds(EclInstr, frozen=True, tag="set_movement_bounds"):
    """设移动范围下限/上限。"""

    x_min: FloatOperand
    y_min: FloatOperand
    x_max: FloatOperand
    y_max: FloatOperand


class DisableMovementBounds(EclInstr, frozen=True, tag="disable_movement_bounds"):
    """关移动范围限制。"""
