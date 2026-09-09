"""敌人模块: EnemyField 状态容器 + ECL 挂载的 Enemy + 伤害结算 + 管线 system。"""

from __future__ import annotations

from .damage import DAMAGE_CAP, DamageSettle, settle_damage
from .enemy import (
    Enemy,
    EnemyDamaged,
    EnemyDespawned,
    EnemyDied,
    EnemyEscaped,
    EnemyLifeCallback,
    EnemySpawned,
    EnemyTimerCallback,
)
from .field import EnemyField, Targeting
from .system import (
    BombDamageSystem,
    EnemyContactSystem,
    EnemyEclSystem,
    EnemyShotSystem,
)

__all__ = [
    "DAMAGE_CAP",
    "BombDamageSystem",
    "DamageSettle",
    "Enemy",
    "EnemyContactSystem",
    "EnemyDamaged",
    "EnemyDespawned",
    "EnemyDied",
    "EnemyEclSystem",
    "EnemyEscaped",
    "EnemyField",
    "EnemyLifeCallback",
    "EnemyShotSystem",
    "EnemySpawned",
    "EnemyTimerCallback",
    "Targeting",
    "settle_damage",
]
