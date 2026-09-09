"""移动 handler: 位置/速度/限时位移/轨道/移动边界。

语义移植 old/touhou/games/th07/ecl_vm.py 与 old/touhou/games/th08/ecl_vm.py
同名 handler; 两作同布局不同语义的指令按 m.file.version 分版本(格式版本是
数据属性, 非作品名分支)。
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from ....schemas.ecl import (
    DisableMovementBounds,
    EclInstr,
    MoveAtPlayer,
    MoveAtPlayerTime,
    MoveBoundaryAware,
    MoveDirTime,
    MoveOrbit,
    MoveOrbitAroundSelf,
    MoveOrbitV800,
    MovePosTime,
    MovePosTimeV800,
    MoveRandomBiased,
    SetAngularVel,
    SetAxisSpeed,
    SetMinPlayerDistance,
    SetMoveAccel,
    SetMoveInterpTimerInterp,
    SetMoveInterpTimerPolar,
    SetMoveInterpTimerRadial,
    SetMovementBounds,
    SetMovePolar,
    SetMoveSpeed,
    SetOrbitAngle,
    SetOrbitRadius,
    SetOrbitVels,
    SetPos,
    SetPosV800,
)
from ..num import add_norm_angle, f32, norm_angle
from ..state import PLAYFIELD_W, Vec3

if TYPE_CHECKING:
    from ..machine import EclMachine  # 仅类型检查期(机器运行时依赖本包)

from .base import Handler


def _set_pos(m: EclMachine, ins: SetPos) -> None:
    e = m.enemy
    e.pos.set(m.fval(ins.x), m.fval(ins.y), m.fval(ins.z))
    e.clamp_pos()


def _set_pos_v800(m: EclMachine, ins: SetPosV800) -> None:
    e = m.enemy
    e.pos.set(m.fval(ins.x), m.fval(ins.y), 0.0)
    e.clamp_pos()


def _set_axis_speed(m: EclMachine, ins: SetAxisSpeed) -> None:
    e = m.enemy
    e.axis_speed.set(m.fval(ins.x), m.fval(ins.y), m.fval(ins.z))
    e.angle = f32(math.atan2(e.axis_speed.y, e.axis_speed.x))
    e.move_mode = 0


def _set_angular_vel(m: EclMachine, ins: SetAngularVel) -> None:
    e = m.enemy
    e.angular_velocity = m.fval(ins.velocity)
    e.move_mode = 1


def _set_move_speed(m: EclMachine, ins: SetMoveSpeed) -> None:
    e = m.enemy
    e.move_speed = m.fval(ins.speed)
    e.move_mode = 1


def _set_move_accel(m: EclMachine, ins: SetMoveAccel) -> None:
    e = m.enemy
    e.move_acceleration = m.fval(ins.accel)
    e.move_mode = 1


def _set_move_polar(m: EclMachine, ins: SetMovePolar) -> None:
    """Angle + speed 直飞(v800, 移动模式 1)。"""
    e = m.enemy
    e.angle = norm_angle(m.fval(ins.angle))
    e.move_speed = m.fval(ins.speed)
    e.move_mode = 1
    e.move_interp_timer = e.move_interp_start_time = 0


def _move_at_player(m: EclMachine, ins: MoveAtPlayer) -> None:
    e = m.enemy
    e.angle = add_norm_angle(m.angle_to_player(), m.fval(ins.angle_offset))
    e.move_speed = m.fval(ins.speed)
    if m.file.version == 0:
        e.move_mode = 1  # v0 顺手进模式 1; v800 只设 angle/speed(EclRunLow.inl:534-541)


def _configure_polar_motion(
    m: EclMachine, duration: int, easing: int, angle: float, speed: float
) -> None:
    """限时角度位移(mode 2): duration 帧内走完 speed*duration 的极位移。"""
    # ConfigurePolarMotion(EclHelpers.cpp:27-54) / v0 同形(EclManager.cpp:1379-1401)
    e = m.enemy
    e.move_interp.set(
        f32(math.cos(angle) * speed * duration),
        f32(math.sin(angle) * speed * duration),
        0.0,
    )
    e.move_interp_start_pos = e.pos.copy()
    e.move_interp_timer = e.move_interp_start_time = duration
    # v0 的 easing 参数带低字节掩码, v800 没有
    e.interp_easing = easing & 0xFF if m.file.version == 0 else easing
    e.move_mode = 2
    if e.mirror:
        e.move_interp.x = -e.move_interp.x


def _move_dir_time(m: EclMachine, ins: MoveDirTime) -> None:
    e = m.enemy
    duration = m.ival(ins.duration)
    if duration <= 0:
        e.angle = norm_angle(m.fval(ins.angle))
        e.move_speed = m.fval(ins.speed)
        e.move_mode = 1
        e.move_interp_timer = e.move_interp_start_time = (
            duration if m.file.version == 0 else 0
        )
    else:
        _configure_polar_motion(
            m,
            duration,
            m.ival(ins.easing),
            norm_angle(m.fval(ins.angle)),
            m.fval(ins.speed),
        )


def _move_at_player_time(m: EclMachine, ins: MoveAtPlayerTime) -> None:
    """限时朝自机位移(v800; duration <= 0 = 瞄准直飞)。"""
    # EclRunLow.inl:543-560
    e = m.enemy
    duration = m.ival(ins.duration)
    if duration <= 0:
        e.angle = add_norm_angle(m.fval(ins.angle), m.angle_to_player())
        e.move_speed = m.fval(ins.speed)
        e.move_mode = 1
        e.move_interp_timer = e.move_interp_start_time = m.ival(ins.duration)
    else:
        # else 分支是不带瞄准的 ConfigurePolarMotion(EclRunLow.inl:558-560)
        _configure_polar_motion(
            m,
            duration,
            m.ival(ins.easing),
            norm_angle(m.fval(ins.angle)),
            m.fval(ins.speed),
        )


def _timed_polar_displacement(
    m: EclMachine, duration: int, easing: int, speed: float, angle: float
) -> None:
    """给定已算好的角度装 mode 2 极位移(不镜像翻转)。"""
    # StartTimedPolarDisplacement(EclDependencies.cpp:99-119)
    e = m.enemy
    e.move_interp.set(
        f32(math.cos(angle) * speed * duration),
        f32(math.sin(angle) * speed * duration),
        0.0,
    )
    e.move_interp_start_pos = e.pos.copy()
    e.move_interp_timer = e.move_interp_start_time = duration
    e.interp_easing = easing
    e.move_mode = 2


def _move_boundary_aware(m: EclMachine, ins: MoveBoundaryAware) -> None:
    """朝屏外逃的限时位移(v800)。"""
    e = m.enemy
    duration = m.ival(ins.duration)
    angle = m.exit_angle()
    if duration <= 0:
        e.angle = angle
        e.move_speed = m.fval(ins.speed)
        e.move_mode = 1
        e.move_interp_timer = e.move_interp_start_time = 0
    else:
        _timed_polar_displacement(
            m, duration, m.ival(ins.easing), m.fval(ins.speed), angle
        )


def _move_random_biased(m: EclMachine, ins: MoveRandomBiased) -> None:
    """3/4 概率偏向自机的随机限时位移(v800)。"""
    # ApplyRandomBiasedMove(EclDependencies.cpp:188-274)
    e = m.enemy
    px, _, _ = m.host.player_position(m)
    if m.rng.int_below(4) != 0:
        if px < e.pos.x:
            wrapped = px + PLAYFIELD_W
            if e.pos.x - px < wrapped - e.pos.x:
                angle = add_norm_angle(m.rng.unit() * 1.5707964 + 2.3561945, 0.0)
            else:
                angle = add_norm_angle(m.rng.unit() * 1.5707964 - 0.78539819, 0.0)
        else:
            wrapped = px - PLAYFIELD_W
            if px - e.pos.x < e.pos.x - wrapped:
                angle = f32(m.rng.unit() * 1.5707964 - 0.78539819)
            else:
                angle = add_norm_angle(m.rng.unit() * 1.5707964 + 2.3561945, 0.0)
    else:
        angle = f32(m.rng.unit() * 2.0 * math.pi - math.pi)
    if e.pos.y < e.lower_move_limit.y + 48.0 and angle < 0.0:
        angle = -angle
    if e.pos.y > e.upper_move_limit.y - 48.0 and angle > 0.0:
        angle = -angle
    duration = m.ival(ins.duration)
    if duration <= 0:
        e.angle = angle
        e.move_speed = m.fval(ins.speed)
        e.move_mode = 1
        e.move_interp_timer = e.move_interp_start_time = 0
    else:
        _timed_polar_displacement(
            m, duration, m.ival(ins.easing), m.fval(ins.speed), angle
        )


def _move_pos_time(m: EclMachine, ins: MovePosTime) -> None:
    e = m.enemy
    new_pos = Vec3(m.fval(ins.x), m.fval(ins.y), m.fval(ins.z))
    e.move_interp = Vec3(new_pos.x - e.pos.x, new_pos.y - e.pos.y, new_pos.z - e.pos.z)
    e.move_interp_start_pos = e.pos.copy()
    e.move_interp_timer = e.move_interp_start_time = m.ival(ins.duration)
    e.interp_easing = m.ival(ins.easing) & 0xFF
    e.move_mode = 2
    e.axis_speed = Vec3()
    if e.mirror:
        e.move_interp.x = -e.move_interp.x


def _move_pos_time_v800(m: EclMachine, ins: MovePosTimeV800) -> None:
    """ConfigureRelativeMotion(EclHelpers.cpp:59-87): 目标点转位移插值(无 z)。"""
    e = m.enemy
    e.move_interp = Vec3(m.fval(ins.x) - e.pos.x, m.fval(ins.y) - e.pos.y, 0.0)
    e.move_interp_start_pos = e.pos.copy()
    e.move_interp_timer = e.move_interp_start_time = m.ival(ins.duration)
    e.interp_easing = m.ival(ins.easing)
    e.move_mode = 2
    e.axis_speed = Vec3()
    if e.mirror:
        e.move_interp.x = -e.move_interp.x


def _move_orbit(m: EclMachine, ins: MoveOrbit) -> None:
    e = m.enemy
    e.move_interp_timer = e.move_interp_start_time = m.ival(ins.duration)
    e.move_interp_start_pos.set(
        m.fval(ins.origin_x), m.fval(ins.origin_y), m.fval(ins.origin_z)
    )
    e.move_angle = m.fval(ins.angle)
    e.move_angular_velocity = m.fval(ins.angular_vel)
    e.move_radius = m.fval(ins.radius)
    e.move_radial_velocity = m.fval(ins.radial_vel)
    e.move_mode = 3


def _move_orbit_v800(m: EclMachine, ins: MoveOrbitV800) -> None:
    e = m.enemy
    e.move_interp_timer = e.move_interp_start_time = m.ival(ins.duration)
    e.move_interp_start_pos.set(m.fval(ins.origin_x), m.fval(ins.origin_y), 0.0)
    e.move_angle = m.fval(ins.angle)
    e.move_angular_velocity = m.fval(ins.angular_vel)
    e.move_radius = m.fval(ins.radius)
    e.move_radial_velocity = m.fval(ins.radial_vel)
    e.move_mode = 3


def _move_orbit_around_self(m: EclMachine, ins: MoveOrbitAroundSelf) -> None:
    """绕当前位置轨道(半径 0 起, v800)。"""
    e = m.enemy
    e.move_interp_timer = e.move_interp_start_time = m.ival(ins.duration)
    e.move_interp_start_pos = e.pos.copy()
    e.move_angle = m.fval(ins.angle)
    e.move_angular_velocity = m.fval(ins.angular_vel)
    e.move_radius = 0.0
    e.move_radial_velocity = m.fval(ins.radial_vel)
    e.move_mode = 3


def _set_orbit_vels(m: EclMachine, ins: SetOrbitVels) -> None:
    e = m.enemy
    e.move_interp_timer = e.move_interp_start_time = m.ival(ins.duration)
    e.move_angular_velocity = m.fval(ins.angular_vel)
    e.move_radial_velocity = m.fval(ins.radial_vel)
    e.move_mode = 3


def _set_orbit_radius(m: EclMachine, ins: SetOrbitRadius) -> None:
    e = m.enemy
    e.move_radius = m.fval(ins.radius)
    e.move_radial_velocity = m.fval(ins.radial_vel)


def _set_orbit_angle(m: EclMachine, ins: SetOrbitAngle) -> None:
    e = m.enemy
    e.move_angle = m.fval(ins.angle)
    e.move_angular_velocity = m.fval(ins.angular_vel)


# 移动插值定时器 3 合一(v0): polar(模式1) / radial(模式3) / interp(模式2)
_MOVE_INTERP_MODE = {
    SetMoveInterpTimerPolar: 1,
    SetMoveInterpTimerRadial: 3,
    SetMoveInterpTimerInterp: 2,
}


def _set_move_interp_timer(m: EclMachine, ins: EclInstr) -> None:
    e = m.enemy
    e.move_mode = _MOVE_INTERP_MODE[type(ins)]
    e.move_interp_timer = e.move_interp_start_time = m.ival(ins.duration)  # type: ignore[attr-defined]


def _set_movement_bounds(m: EclMachine, ins: SetMovementBounds) -> None:
    e = m.enemy
    e.lower_move_limit.x = m.fval(ins.x_min)
    e.lower_move_limit.y = m.fval(ins.y_min)
    e.upper_move_limit.x = m.fval(ins.x_max)
    e.upper_move_limit.y = m.fval(ins.y_max)
    e.has_movement_bounds = 1


def _disable_movement_bounds(m: EclMachine, ins: DisableMovementBounds) -> None:
    m.enemy.has_movement_bounds = 0


def _set_min_player_distance(m: EclMachine, ins: SetMinPlayerDistance) -> None:
    d = m.fval(ins.distance)
    m.enemy.min_player_dist_sq = f32(d * d)


#: 移动指令类 → handler
MOVEMENT: dict[type[EclInstr], Handler] = {
    SetPos: _set_pos,
    SetPosV800: _set_pos_v800,
    SetAxisSpeed: _set_axis_speed,
    SetAngularVel: _set_angular_vel,
    SetMoveSpeed: _set_move_speed,
    SetMoveAccel: _set_move_accel,
    SetMovePolar: _set_move_polar,
    MoveAtPlayer: _move_at_player,
    MoveAtPlayerTime: _move_at_player_time,
    MoveDirTime: _move_dir_time,
    MoveBoundaryAware: _move_boundary_aware,
    MoveRandomBiased: _move_random_biased,
    MovePosTime: _move_pos_time,
    MovePosTimeV800: _move_pos_time_v800,
    MoveOrbit: _move_orbit,
    MoveOrbitV800: _move_orbit_v800,
    MoveOrbitAroundSelf: _move_orbit_around_self,
    SetOrbitVels: _set_orbit_vels,
    SetOrbitRadius: _set_orbit_radius,
    SetOrbitAngle: _set_orbit_angle,
    SetMoveInterpTimerPolar: _set_move_interp_timer,
    SetMoveInterpTimerRadial: _set_move_interp_timer,
    SetMoveInterpTimerInterp: _set_move_interp_timer,
    SetMovementBounds: _set_movement_bounds,
    DisableMovementBounds: _disable_movement_bounds,
    SetMinPlayerDistance: _set_min_player_distance,
}
