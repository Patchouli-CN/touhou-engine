"""作品专属指令的委托 handler: 原指令透传到 EclHost 对应钩子。

engine 不实现这些指令的语义(弹幕/激光/敌人管理/符卡/音效属 games 侧),
但注册表必须全覆盖指令 union(漏网分派由测试断言兜底)。能通用解析的操作数
(生敌坐标/音效 id/boss interrupt)在 engine 侧烹好, 其余透传原指令。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ....schemas.ecl import (
    AddCherryPlus,
    AddLaserAngle,
    AdvanceClock,
    AimLaserAtPlayer,
    BeginSpellcard,
    BeginSpellcardV800,
    BindTimerCallbackToDeath,
    ClearBulletsForTransition,
    ClearEnemyFlags,
    ClearLasers,
    DeferBulletPattern,
    DisableBullets,
    DisableDeferBulletPattern,
    EclInstr,
    EnableBullets,
    EnableEnemyFlags,
    EndSpellcard,
    FreezeEclDuringBomb,
    HideClock,
    Idfk,
    InitBulletCmd,
    PlaySound,
    RemoveAllBullets,
    RemoveAllEnemies,
    RemoveBulletsRadius,
    SetAnm,
    SetBonusUpdatesDisabled,
    SetBoss,
    SetBossHealth,
    SetBossRunInterrupt,
    SetBulletRankParams,
    SetBulletSound,
    SetCanBeDamaged,
    SetDeathAnm,
    SetDeathCallbackSub,
    SetDeathCallbackSubV800,
    SetDeathType,
    SetDespawnOnOob,
    SetDrawGroup,
    SetEnemyCanDie,
    SetEnemyFlags,
    SetEnemyManagerValue,
    SetExtraVmFixedOffset,
    SetFormEffect,
    SetGlobalEffectColorMul,
    SetGrazeSize,
    SetGrazeSizeV800,
    SetHasContactHitbox,
    SetHasNoCollision,
    SetHitboxSize,
    SetHitboxSizeV800,
    SetIsHittable,
    SetIsProjectile,
    SetIsSurvivalSpellcard,
    SetItemDrop,
    SetItemDropCounts,
    SetLaserAngle,
    SetLaserHideWarning,
    SetLaserIdx,
    SetLaserOffsets,
    SetLaserPosRel,
    SetLaserStartLen,
    SetLastSpellFlags,
    SetLifeCallback,
    SetLifeCallbackSub,
    SetLifeCallbackThreshold,
    SetMoveAnm,
    SetMoveAnmSeq,
    SetMoveAnmV800,
    SetNoDamageDuringStop,
    SetNumBossLifeMarkers,
    SetPhaseStartLife,
    SetPrimaryVmInterrupt,
    SetPrimaryVmRotZ,
    SetScriptWaitTime,
    SetShootInterval,
    SetShootIntervalRand,
    SetShootOffset,
    SetShootOffsetV800,
    SetSpecialAnm,
    SetSpecialEffectPos,
    SetSpecialInteraction,
    SetSpellcardEffectTracking,
    SetStageScriptLabel,
    SetSubAnm,
    SetTimerCallback,
    SetTimerCallbackSub,
    SetTimerCallbackThreshold,
    SetTrail,
    SetVmAutoRotate,
    SetVmInterrupt,
    SetVmInterruptV800,
    SpawnAlignmentEffect,
    SpawnBulletPattern,
    SpawnEffect,
    SpawnEnemyAbs,
    SpawnEnemyRel,
    SpawnFamiliar,
    SpawnFamiliarInherit,
    SpawnFamiliarRel,
    SpawnItem,
    SpawnItems,
    SpawnLaserPattern,
    SpawnLaserPatternV800,
    SpawnMovingParticles,
    SpawnParticles,
    SpawnPointItems,
    SpawnPrevBulletPattern,
    StartStageBackgroundSequence,
    StopLaser,
    SuppressTimelineSpawns,
    TestLaserInUse,
    TestLaserNotInUse,
)
from ..state import EnemySpawn

if TYPE_CHECKING:
    from ..machine import EclMachine  # 仅类型检查期(机器运行时依赖本包)

from .base import Handler


def _spawn_enemy_abs(m: EclMachine, ins: SpawnEnemyAbs) -> None:
    # life > 0 才生(EclManager.cpp:1508-1524)
    if m.enemy.life > 0:
        m.host.spawn_enemy(
            EnemySpawn(
                sub_id=ins.sub_id,
                x=m.fval(ins.x),
                y=m.fval(ins.y),
                z=m.fval(ins.z),
                life=m.ival(ins.life),
                item_drop=m.ival(ins.item_drop),
                score=m.ival(ins.score),
            ),
            m,
        )


def _spawn_enemy_rel(m: EclMachine, ins: SpawnEnemyRel) -> None:
    if m.enemy.life > 0:
        e = m.enemy
        m.host.spawn_enemy(
            EnemySpawn(
                sub_id=ins.sub_id,
                x=m.fval(ins.x) + e.pos.x,
                y=m.fval(ins.y) + e.pos.y,
                z=m.fval(ins.z) + e.pos.z,
                life=m.ival(ins.life),
                item_drop=m.ival(ins.item_drop),
                score=m.ival(ins.score),
            ),
            m,
        )


def _play_sound(m: EclMachine, ins: PlaySound) -> None:
    m.host.play_sound(m, m.ival(ins.sound_idx))


def _set_boss_run_interrupt(m: EclMachine, ins: SetBossRunInterrupt) -> None:
    m.host.set_boss_interrupt(m.ival(ins.idx), m.ival(ins.interrupt))


def _spawn_bullets(m: EclMachine, ins: EclInstr) -> None:
    m.host.spawn_bullets(m, ins)


def _bullet_setup(m: EclMachine, ins: EclInstr) -> None:
    m.host.bullet_setup(m, ins)


def _clear_bullets(m: EclMachine, ins: EclInstr) -> None:
    m.host.clear_bullets(m, ins)


def _spawn_laser(m: EclMachine, ins: EclInstr) -> None:
    m.host.spawn_laser(m, ins)


def _laser_control(m: EclMachine, ins: EclInstr) -> None:
    m.host.laser_control(m, ins)


def _spawn_familiar(m: EclMachine, ins: EclInstr) -> None:
    m.host.spawn_familiar(m, ins)


def _clear_enemies(m: EclMachine, ins: EclInstr) -> None:
    m.host.clear_enemies(m, ins)


def _enemy_config(m: EclMachine, ins: EclInstr) -> None:
    m.host.enemy_config(m, ins)


def _spawn_items(m: EclMachine, ins: EclInstr) -> None:
    m.host.spawn_items(m, ins)


def _boss_control(m: EclMachine, ins: EclInstr) -> None:
    m.host.boss_control(m, ins)


#: 作品专属指令类 → 委托 handler
DELEGATED: dict[type[EclInstr], Handler] = {
    # 生敌/道具/音效( engine 烹参数)
    SpawnEnemyAbs: _spawn_enemy_abs,
    SpawnEnemyRel: _spawn_enemy_rel,
    PlaySound: _play_sound,
    SetBossRunInterrupt: _set_boss_run_interrupt,
    # 弹幕
    SpawnBulletPattern: _spawn_bullets,
    SpawnPrevBulletPattern: _spawn_bullets,
    InitBulletCmd: _bullet_setup,
    SetShootInterval: _bullet_setup,
    SetShootIntervalRand: _bullet_setup,
    DisableBullets: _bullet_setup,
    EnableBullets: _bullet_setup,
    DeferBulletPattern: _bullet_setup,
    DisableDeferBulletPattern: _bullet_setup,
    SetBulletSound: _bullet_setup,
    SetBulletRankParams: _bullet_setup,
    SetShootOffset: _bullet_setup,
    SetShootOffsetV800: _bullet_setup,
    RemoveAllBullets: _clear_bullets,
    ClearBulletsForTransition: _clear_bullets,
    RemoveBulletsRadius: _clear_bullets,
    # 激光
    SpawnLaserPattern: _spawn_laser,
    SpawnLaserPatternV800: _spawn_laser,
    SetLaserIdx: _laser_control,
    AddLaserAngle: _laser_control,
    SetLaserAngle: _laser_control,
    AimLaserAtPlayer: _laser_control,
    SetLaserPosRel: _laser_control,
    TestLaserNotInUse: _laser_control,
    TestLaserInUse: _laser_control,
    StopLaser: _laser_control,
    ClearLasers: _laser_control,
    SetLaserHideWarning: _laser_control,
    SetLaserStartLen: _laser_control,
    SetLaserOffsets: _laser_control,
    # 敌人管理
    SpawnFamiliar: _spawn_familiar,
    SpawnFamiliarRel: _spawn_familiar,
    SpawnFamiliarInherit: _spawn_familiar,
    RemoveAllEnemies: _clear_enemies,
    SpawnItem: _spawn_items,
    SpawnItems: _spawn_items,
    SpawnPointItems: _spawn_items,
    # 敌人配置(透传)
    SetAnm: _enemy_config,
    SetMoveAnm: _enemy_config,
    SetMoveAnmSeq: _enemy_config,
    SetMoveAnmV800: _enemy_config,
    SetSubAnm: _enemy_config,
    SetSpecialAnm: _enemy_config,
    SetDeathAnm: _enemy_config,
    SetHitboxSize: _enemy_config,
    SetHitboxSizeV800: _enemy_config,
    SetGrazeSize: _enemy_config,
    SetGrazeSizeV800: _enemy_config,
    SetHasContactHitbox: _enemy_config,
    SetCanBeDamaged: _enemy_config,
    SetIsHittable: _enemy_config,
    SetEnemyCanDie: _enemy_config,
    SetVmAutoRotate: _enemy_config,
    SetHasNoCollision: _enemy_config,
    SetIsSurvivalSpellcard: _enemy_config,
    SetIsProjectile: _enemy_config,
    SetSpecialInteraction: _enemy_config,
    SetDespawnOnOob: _enemy_config,
    SetEnemyFlags: _enemy_config,
    ClearEnemyFlags: _enemy_config,
    EnableEnemyFlags: _enemy_config,
    SetFormEffect: _enemy_config,
    SetTrail: _enemy_config,
    SetLifeCallbackThreshold: _enemy_config,
    SetLifeCallbackSub: _enemy_config,
    SetTimerCallbackThreshold: _enemy_config,
    SetTimerCallbackSub: _enemy_config,
    SetLifeCallback: _enemy_config,
    SetTimerCallback: _enemy_config,
    BindTimerCallbackToDeath: _enemy_config,
    SetDeathType: _enemy_config,
    SetDeathCallbackSub: _enemy_config,
    SetDeathCallbackSubV800: _enemy_config,
    SetPrimaryVmInterrupt: _enemy_config,
    SetVmInterrupt: _enemy_config,
    SetVmInterruptV800: _enemy_config,
    SetPrimaryVmRotZ: _enemy_config,
    SetItemDrop: _enemy_config,
    SetItemDropCounts: _enemy_config,
    SetDrawGroup: _enemy_config,
    SetNoDamageDuringStop: _enemy_config,
    SetExtraVmFixedOffset: _enemy_config,
    SetPhaseStartLife: _enemy_config,
    SpawnEffect: _enemy_config,
    SpawnParticles: _enemy_config,
    SpawnMovingParticles: _enemy_config,
    SpawnAlignmentEffect: _enemy_config,
    Idfk: _enemy_config,
    SetEnemyManagerValue: _enemy_config,
    SetSpecialEffectPos: _enemy_config,
    SetGlobalEffectColorMul: _enemy_config,
    # boss/符卡/作品机制(透传)
    SetBoss: _boss_control,
    BeginSpellcard: _boss_control,
    BeginSpellcardV800: _boss_control,
    EndSpellcard: _boss_control,
    SetBossHealth: _boss_control,
    SetNumBossLifeMarkers: _boss_control,
    SetScriptWaitTime: _boss_control,
    SetStageScriptLabel: _boss_control,
    SuppressTimelineSpawns: _boss_control,
    SetLastSpellFlags: _boss_control,
    SetSpellcardEffectTracking: _boss_control,
    FreezeEclDuringBomb: _boss_control,
    AddCherryPlus: _boss_control,
    StartStageBackgroundSequence: _boss_control,
    HideClock: _boss_control,
    AdvanceClock: _boss_control,
    SetBonusUpdatesDisabled: _boss_control,
}
