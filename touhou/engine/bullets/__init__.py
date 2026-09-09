"""敌弹: 命令系统 + 弹场状态容器 + MOVEMENT/COLLISION 槽 system。"""

from __future__ import annotations

from .commands import (
    NUM_SLOTS,
    OFFSCREEN_GRACE,
    OFFSCREEN_GRACE_FRAMES,
    BulletCommand,
    BulletState,
    CmdFlag,
    CmdState,
    step_bullet,
)
from .field import (
    GRAZE_EXPAND,
    Aim,
    Bullet,
    BulletDespawned,
    BulletField,
    BulletGraze,
    BulletHit,
    BulletSpawned,
    BulletTypeSpec,
    Burst,
    DespawnCause,
    rank_lerp,
    rank_lerp_int,
)
from .system import BulletCollisionSystem, BulletMovementSystem

__all__ = [
    "GRAZE_EXPAND",
    "NUM_SLOTS",
    "OFFSCREEN_GRACE",
    "OFFSCREEN_GRACE_FRAMES",
    "Aim",
    "Bullet",
    "BulletCollisionSystem",
    "BulletCommand",
    "BulletDespawned",
    "BulletField",
    "BulletGraze",
    "BulletHit",
    "BulletMovementSystem",
    "BulletSpawned",
    "BulletState",
    "BulletTypeSpec",
    "Burst",
    "CmdFlag",
    "CmdState",
    "DespawnCause",
    "rank_lerp",
    "rank_lerp_int",
    "step_bullet",
]
