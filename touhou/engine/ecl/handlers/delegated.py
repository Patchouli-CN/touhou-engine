"""作品语义指令的委托 handler: 原指令透传到 EclHost 对应钩子。

engine 不实现这些指令的语义(弹幕/激光/敌人管理/符卡/音效属 games 侧),
DELEGATED 只注册两作共享的指令类; 委托函数本体是公开件(spawn_bullets/
enemy_config 等), 作品专属指令类由 games 侧绑定这些函数后注入 VM。
能通用解析的操作数(生敌坐标/音效 id/boss interrupt)在 engine 侧烹好。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ....schemas.ecl import (
    AddLaserAngle,
    AimLaserAtPlayer,
    BindTimerCallbackToDeath,
    ClearLasers,
    EclInstr,
    EndSpellcard,
    FreezeEclDuringBomb,
    InitBulletCmd,
    PlaySound,
    RemoveAllBullets,
    RemoveAllEnemies,
    RemoveBulletsRadius,
    SetAnm,
    SetBoss,
    SetBossHealth,
    SetBulletRankParams,
    SetBulletSound,
    SetDeathAnm,
    SetDeathType,
    SetIsSurvivalSpellcard,
    SetLaserAngle,
    SetLaserHideWarning,
    SetLaserIdx,
    SetLaserOffsets,
    SetLaserPosRel,
    SetLaserStartLen,
    SetLifeCallback,
    SetNumBossLifeMarkers,
    SetPrimaryVmInterrupt,
    SetPrimaryVmRotZ,
    SetShootInterval,
    SetShootIntervalRand,
    SetSubAnm,
    SetTrail,
    SetVmAutoRotate,
    SpawnBulletPattern,
    SpawnEffect,
    SpawnEnemyAbs,
    SpawnEnemyRel,
    SpawnItem,
    SpawnItems,
    SpawnMovingParticles,
    SpawnParticles,
    SpawnPointItems,
    SpawnPrevBulletPattern,
    StopLaser,
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


def set_boss_run_interrupt(m: EclMachine, ins: EclInstr) -> None:
    """设指定 boss 的 run_interrupt(烹好的操作数)。"""
    m.host.set_boss_interrupt(m.ival(ins.idx), m.ival(ins.interrupt))  # type: ignore[attr-defined]


# ---- 泛型委托(原指令透传宿主钩子; 作品专属类由 games 侧绑定) ----


def spawn_bullets(m: EclMachine, ins: EclInstr) -> None:
    """弹幕发射(SpawnBulletPattern/SpawnPrevBulletPattern)。"""
    m.host.spawn_bullets(m, ins)


def bullet_setup(m: EclMachine, ins: EclInstr) -> None:
    """弹幕参数配置(InitBulletCmd/SetShootInterval/SetBulletSound/SetShootOffset 等)。"""
    m.host.bullet_setup(m, ins)


def clear_bullets(m: EclMachine, ins: EclInstr) -> None:
    """清弹(RemoveAllBullets/ClearBulletsForTransition/RemoveBulletsRadius)。"""
    m.host.clear_bullets(m, ins)


def spawn_laser(m: EclMachine, ins: EclInstr) -> None:
    """激光发射(SpawnLaserPattern 系)。"""
    m.host.spawn_laser(m, ins)


def laser_control(m: EclMachine, ins: EclInstr) -> None:
    """激光控制(SetLaserIdx/角度/位置/停止/测试等)。"""
    m.host.laser_control(m, ins)


def spawn_familiar(m: EclMachine, ins: EclInstr) -> None:
    """使魔系生敌(SpawnFamiliar*)。"""
    m.host.spawn_familiar(m, ins)


def clear_enemies(m: EclMachine, ins: EclInstr) -> None:
    """清敌(REMOVE_ALL_ENEMIES)。"""
    m.host.clear_enemies(m, ins)


def enemy_config(m: EclMachine, ins: EclInstr) -> None:
    """敌人状态配置(anm/判定盒/标志位/回调登记/掉落/特效等)。"""
    m.host.enemy_config(m, ins)


def spawn_items(m: EclMachine, ins: EclInstr) -> None:
    """道具掉落(SpawnItem/SpawnItems/SpawnPointItems)。"""
    m.host.spawn_items(m, ins)


def boss_control(m: EclMachine, ins: EclInstr) -> None:
    """boss/符卡/作品机制指令(SetBoss/BeginSpellcard/时刻/樱点等)。"""
    m.host.boss_control(m, ins)


#: 作品语义指令类 → 委托 handler(两作共享部分)
DELEGATED: dict[type[EclInstr], Handler] = {
    # 生敌/道具/音效( engine 烹参数)
    SpawnEnemyAbs: _spawn_enemy_abs,
    SpawnEnemyRel: _spawn_enemy_rel,
    PlaySound: _play_sound,
    # 弹幕
    SpawnBulletPattern: spawn_bullets,
    SpawnPrevBulletPattern: spawn_bullets,
    InitBulletCmd: bullet_setup,
    SetShootInterval: bullet_setup,
    SetShootIntervalRand: bullet_setup,
    SetBulletSound: bullet_setup,
    SetBulletRankParams: bullet_setup,
    RemoveAllBullets: clear_bullets,
    RemoveBulletsRadius: clear_bullets,
    # 激光
    SetLaserIdx: laser_control,
    AddLaserAngle: laser_control,
    SetLaserAngle: laser_control,
    AimLaserAtPlayer: laser_control,
    SetLaserPosRel: laser_control,
    StopLaser: laser_control,
    ClearLasers: laser_control,
    SetLaserHideWarning: laser_control,
    SetLaserStartLen: laser_control,
    SetLaserOffsets: laser_control,
    # 敌人管理
    RemoveAllEnemies: clear_enemies,
    SpawnItem: spawn_items,
    SpawnItems: spawn_items,
    SpawnPointItems: spawn_items,
    # 敌人配置(透传)
    SetAnm: enemy_config,
    SetSubAnm: enemy_config,
    SetDeathAnm: enemy_config,
    SetVmAutoRotate: enemy_config,
    SetIsSurvivalSpellcard: enemy_config,
    SetTrail: enemy_config,
    SetLifeCallback: enemy_config,
    BindTimerCallbackToDeath: enemy_config,
    SetDeathType: enemy_config,
    SetPrimaryVmInterrupt: enemy_config,
    SetPrimaryVmRotZ: enemy_config,
    SpawnEffect: enemy_config,
    SpawnParticles: enemy_config,
    SpawnMovingParticles: enemy_config,
    # boss/符卡/作品机制(透传)
    SetBoss: boss_control,
    EndSpellcard: boss_control,
    SetBossHealth: boss_control,
    SetNumBossLifeMarkers: boss_control,
    FreezeEclDuringBomb: boss_control,
}
