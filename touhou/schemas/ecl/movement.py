"""ECL 移动指令(位置/速度/限时位移/轨道/移动边界)。"""

from __future__ import annotations

from .base import EclInstr, FloatOperand, IntOperand

# 语义出处 Reference/th07/src/th07/EclManager.cpp 各 case +
# v800: EclRunLow.inl:496-632 / EclHelpers.cpp:27-87 / EclDependencies.cpp:99-274


class SetPos(EclInstr, frozen=True, tag="set_pos"):
    """直接设位置(x/y/z)。"""

    x: FloatOperand
    y: FloatOperand
    z: FloatOperand


class SetPosV800(EclInstr, frozen=True, tag="set_pos_v800"):
    """直接设位置(v800 版: 只有 x/y, z 恒 0)。"""

    x: FloatOperand
    y: FloatOperand


class SetAxisSpeed(EclInstr, frozen=True, tag="set_axis_speed"):
    """设轴向速度并按 atan2 回算朝向(v0 专属)。"""

    x: FloatOperand
    y: FloatOperand
    z: FloatOperand


class SetAngularVel(EclInstr, frozen=True, tag="set_angular_vel"):
    """设角速度(移动模式 1)。"""

    velocity: FloatOperand


class SetMoveSpeed(EclInstr, frozen=True, tag="set_move_speed"):
    """设移动速度(v0 专属, 移动模式 1)。"""

    speed: FloatOperand


class SetMoveAccel(EclInstr, frozen=True, tag="set_move_accel"):
    """设移动加速度(移动模式 1)。"""

    accel: FloatOperand


class MoveAtPlayer(EclInstr, frozen=True, tag="move_at_player"):
    """朝自机方向 + angle_offset 直飞。"""

    angle_offset: FloatOperand
    speed: FloatOperand


class MoveAtPlayerTime(EclInstr, frozen=True, tag="move_at_player_time"):
    """限时朝自机位移(duration <= 0 = 直飞, v800 专属)。"""

    # EclRunLow.inl:543-560
    duration: IntOperand
    easing: IntOperand
    angle: FloatOperand
    speed: FloatOperand


class MoveDirTime(EclInstr, frozen=True, tag="move_dir_time"):
    """限时角度位移(duration <= 0 = angle/speed 直飞)。"""

    duration: IntOperand
    easing: IntOperand
    angle: FloatOperand
    speed: FloatOperand


class MoveBoundaryAware(EclInstr, frozen=True, tag="move_boundary_aware"):
    """朝屏外逃的限时位移(duration <= 0 = 直飞, v800 专属)。"""

    # BeginBoundaryAwareMove(EclDependencies.cpp:122-185)
    duration: IntOperand
    easing: IntOperand
    speed: FloatOperand


class MoveRandomBiased(EclInstr, frozen=True, tag="move_random_biased"):
    """3/4 概率偏向自机的随机限时位移(duration <= 0 = 直飞, v800 专属)。"""

    # ApplyRandomBiasedMove(EclDependencies.cpp:188-274)
    duration: IntOperand
    easing: IntOperand
    speed: FloatOperand


class MovePosTime(EclInstr, frozen=True, tag="move_pos_time"):
    """限时移动到目标点(x/y/z, 位移插值)。"""

    duration: IntOperand
    easing: IntOperand
    x: FloatOperand
    y: FloatOperand
    z: FloatOperand


class MovePosTimeV800(EclInstr, frozen=True, tag="move_pos_time_v800"):
    """限时移动到目标点(v800 版: 只有 x/y)。"""

    # ConfigureRelativeMotion(EclHelpers.cpp:59-87)
    duration: IntOperand
    easing: IntOperand
    x: FloatOperand
    y: FloatOperand


class SetMovePolar(EclInstr, frozen=True, tag="set_move_polar"):
    """angle + speed 直飞(v800 专属, 移动模式 1)。"""

    angle: FloatOperand
    speed: FloatOperand


class MoveOrbit(EclInstr, frozen=True, tag="move_orbit"):
    """绕指定原点轨道(v0 版: 原点 x/y/z, 移动模式 3)。"""

    duration: IntOperand
    origin_x: FloatOperand
    origin_y: FloatOperand
    origin_z: FloatOperand
    angle: FloatOperand
    angular_vel: FloatOperand
    radius: FloatOperand
    radial_vel: FloatOperand


class MoveOrbitV800(EclInstr, frozen=True, tag="move_orbit_v800"):
    """绕指定原点轨道(v800 版: 原点只有 x/y)。"""

    duration: IntOperand
    origin_x: FloatOperand
    origin_y: FloatOperand
    angle: FloatOperand
    angular_vel: FloatOperand
    radius: FloatOperand
    radial_vel: FloatOperand


class MoveOrbitAroundSelf(EclInstr, frozen=True, tag="move_orbit_around_self"):
    """绕当前位置轨道(半径 0 起, v800 专属)。"""

    duration: IntOperand
    angle: FloatOperand
    angular_vel: FloatOperand
    radial_vel: FloatOperand


class SetOrbitVels(EclInstr, frozen=True, tag="set_orbit_vels"):
    """设轨道角速度/径向速度(v800 专属, 移动模式 3)。"""

    duration: IntOperand
    angular_vel: FloatOperand
    radial_vel: FloatOperand


class SetOrbitRadius(EclInstr, frozen=True, tag="set_orbit_radius"):
    """设轨道半径/径向速度(v0 专属)。"""

    radius: FloatOperand
    radial_vel: FloatOperand


class SetOrbitAngle(EclInstr, frozen=True, tag="set_orbit_angle"):
    """设轨道角/角速度(v0 专属)。"""

    angle: FloatOperand
    angular_vel: FloatOperand


class SetMoveInterpTimerPolar(EclInstr, frozen=True, tag="set_move_interp_timer_polar"):
    """设移动插值定时器(v0 专属, 移动模式 1)。"""

    duration: IntOperand


class SetMoveInterpTimerRadial(
    EclInstr, frozen=True, tag="set_move_interp_timer_radial"
):
    """设移动插值定时器(v0 专属, 移动模式 3)。"""

    duration: IntOperand


class SetMoveInterpTimerInterp(
    EclInstr, frozen=True, tag="set_move_interp_timer_interp"
):
    """设移动插值定时器(v0 专属, 移动模式 2)。"""

    duration: IntOperand


class SetMovementBounds(EclInstr, frozen=True, tag="set_movement_bounds"):
    """设移动范围下限/上限。"""

    x_min: FloatOperand
    y_min: FloatOperand
    x_max: FloatOperand
    y_max: FloatOperand


class DisableMovementBounds(EclInstr, frozen=True, tag="disable_movement_bounds"):
    """关移动范围限制。"""


class SetMinPlayerDistance(EclInstr, frozen=True, tag="set_min_player_distance"):
    """距自机过近压住弹幕的距离阈值(v800 专属, 存平方)。"""

    # EclRunHigh.inl:922-935
    distance: FloatOperand
