"""th07 专属 ECL 指令的 handler 绑定: 指令类 → engine 机制 handler。

handler 语义是流派通用件(住 engine/ecl/handlers), 这里只做 v0 专属指令类
到机制 handler 的装配; EclMachine(extra_handlers=...) 注入。
"""

from __future__ import annotations

from ...engine.ecl import Handler
from ...engine.ecl.handlers import control, delegated, mathops, movement
from ...schemas.ecl import EclInstr
from .ecl_instrs import (
    AddCherryPlus,
    BeginSpellcard,
    DisableBullets,
    EnableBullets,
    GetExitAngle,
    Idfk,
    MoveOrbit,
    MovePosTime,
    Rand,
    RandAdd,
    RandFloat,
    RandFloatAdd,
    RandFloatRange,
    SetAxisSpeed,
    SetBossRunInterrupt,
    SetCanBeDamaged,
    SetDeathCallbackSub,
    SetDespawnOnOob,
    SetEnemyCanDie,
    SetGlobalEffectColorMul,
    SetGrazeSize,
    SetHasContactHitbox,
    SetHasNoCollision,
    SetHitboxSize,
    SetIsHittable,
    SetIsProjectile,
    SetLifeCallbackSub,
    SetLifeCallbackThreshold,
    SetMoveAnm,
    SetMoveInterpTimerInterp,
    SetMoveInterpTimerPolar,
    SetMoveInterpTimerRadial,
    SetMoveSpeed,
    SetOrbitAngle,
    SetOrbitRadius,
    SetPeriodicCallback,
    SetPos,
    SetRunInterrupt,
    SetScriptWaitTime,
    SetShootOffset,
    SetSpecialEffectPos,
    SetTimerCallbackSub,
    SetTimerCallbackThreshold,
    SetVmInterrupt,
    SpawnLaserPattern,
    TestLaserNotInUse,
)

#: v0 专属指令类 → handler(EclMachine 的 extra_handlers)
ECL_EXTRA_HANDLERS: dict[type[EclInstr], Handler] = {
    # 控制流/VM 机制
    SetRunInterrupt: control.set_run_interrupt,
    SetPeriodicCallback: control.set_periodic_callback,
    # 随机/逃角
    Rand: mathops.rand,
    RandAdd: mathops.rand_add,
    RandFloat: mathops.rand_float,
    RandFloatAdd: mathops.rand_float_add,
    RandFloatRange: mathops.rand_float_range,
    GetExitAngle: mathops.get_exit_angle,
    # 移动
    SetPos: movement.set_pos,
    SetAxisSpeed: movement.set_axis_speed,
    SetMoveSpeed: movement.set_move_speed,
    MovePosTime: movement.move_pos_time,
    MoveOrbit: movement.move_orbit,
    SetOrbitRadius: movement.set_orbit_radius,
    SetOrbitAngle: movement.set_orbit_angle,
    SetMoveInterpTimerPolar: movement.move_interp_timer(1),
    SetMoveInterpTimerRadial: movement.move_interp_timer(3),
    SetMoveInterpTimerInterp: movement.move_interp_timer(2),
    # 弹幕/激光
    DisableBullets: delegated.bullet_setup,
    EnableBullets: delegated.bullet_setup,
    SetShootOffset: delegated.bullet_setup,
    SpawnLaserPattern: delegated.spawn_laser,
    TestLaserNotInUse: delegated.laser_control,
    # 敌人配置
    SetMoveAnm: delegated.enemy_config,
    SetHitboxSize: delegated.enemy_config,
    SetGrazeSize: delegated.enemy_config,
    SetHasContactHitbox: delegated.enemy_config,
    SetCanBeDamaged: delegated.enemy_config,
    SetIsHittable: delegated.enemy_config,
    SetEnemyCanDie: delegated.enemy_config,
    SetHasNoCollision: delegated.enemy_config,
    SetIsProjectile: delegated.enemy_config,
    SetDespawnOnOob: delegated.enemy_config,
    SetLifeCallbackThreshold: delegated.enemy_config,
    SetLifeCallbackSub: delegated.enemy_config,
    SetTimerCallbackThreshold: delegated.enemy_config,
    SetTimerCallbackSub: delegated.enemy_config,
    SetDeathCallbackSub: delegated.enemy_config,
    SetVmInterrupt: delegated.enemy_config,
    SetSpecialEffectPos: delegated.enemy_config,
    SetGlobalEffectColorMul: delegated.enemy_config,
    Idfk: delegated.enemy_config,
    # boss/符卡/作品机制
    BeginSpellcard: delegated.boss_control,
    SetBossRunInterrupt: delegated.set_boss_run_interrupt,
    SetScriptWaitTime: delegated.boss_control,
    AddCherryPlus: delegated.boss_control,
}
