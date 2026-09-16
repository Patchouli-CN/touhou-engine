"""通用东方弹幕游戏框架: 包根是公共 API 门面(作品经注册表接入, import 即登记)。"""

from __future__ import annotations

from . import games as games  # 作品发现清单: import 即触发向 TouhouRegistry 登记
from .apis import (
    BossSnapshot,
    BulletSnapshot,
    EnemySnapshot,
    Game,
    GameEvent,
    GameEventKind,
    GamePhase,
    Input,
    ItemSnapshot,
    LaserSnapshot,
    PlayerSnapshot,
    Snapshot,
    TouhouWorld,
    TouhouWorldEventStream,
)
from .engine.registry import TouhouRegistry

__all__ = [
    "BossSnapshot",
    "BulletSnapshot",
    "EnemySnapshot",
    "Game",
    "GameEvent",
    "GameEventKind",
    "GamePhase",
    "Input",
    "ItemSnapshot",
    "LaserSnapshot",
    "PlayerSnapshot",
    "Snapshot",
    "TouhouRegistry",
    "TouhouWorld",
    "TouhouWorldEventStream",
]
