"""实体快照 Struct 群(不可变; Game.snapshot() 的产出, 供外部渲染/AI 观测)。"""

from __future__ import annotations

import msgspec

from .events import GamePhase


class PlayerSnapshot(msgspec.Struct, frozen=True):
    x: float
    y: float
    state: str  # alive/spawning/dead/invulnerable
    focus: bool
    invulnerable: bool
    hitbox: float  # 自机判定半宽(作品按 .sht 注入)


class BulletSnapshot(msgspec.Struct, frozen=True):
    x: float
    y: float
    angle: float
    speed: float
    sprite: int  # 弹型模板号(作品数值表定义)
    hitbox: float  # 判定半径(碰撞盒半宽, 与引擎实际判定同源)


class EnemySnapshot(msgspec.Struct, frozen=True):
    x: float
    y: float
    life: int
    radius: float
    is_boss: bool


class ItemSnapshot(msgspec.Struct, frozen=True):
    x: float
    y: float
    kind: int  # 道具类型号(语义由作品定义)


class LaserSnapshot(msgspec.Struct, frozen=True):
    x: float
    y: float
    angle: float
    width: float
    active: bool  # 全宽命中态(SPAWNING/DESPAWNING 为 False)


class BossSnapshot(msgspec.Struct, frozen=True):
    name: str
    x: float
    y: float
    life: float
    max_life: float
    spellcard_active: bool


class Snapshot(msgspec.Struct, frozen=True):
    """某一帧的实体全景(由 Game.snapshot() 按需构造)。"""

    frame: int
    phase: GamePhase
    player: PlayerSnapshot
    boss: BossSnapshot | None
    bullets: tuple[BulletSnapshot, ...] = ()
    enemies: tuple[EnemySnapshot, ...] = ()
    items: tuple[ItemSnapshot, ...] = ()
    lasers: tuple[LaserSnapshot, ...] = ()
