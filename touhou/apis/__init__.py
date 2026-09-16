"""对外 API 层 —— 作品无关的 Pythonic 门面(basic/world)与魔改口(modding)。

全能力开放层(架构讨论稿 §2.5): 写操作走命令队列帧边界统一应用, 重任务
submit 上 worker 池, 读走快照/副本。作品解析走 TouhouRegistry, 本层不
import games.*(AST 守护钉死)。
"""

from __future__ import annotations

from .basic import Game, GameWorld
from .events import GameEvent, GameEventKind, GamePhase
from .input import Input
from .snapshots import (
    BossSnapshot,
    BulletSnapshot,
    EnemySnapshot,
    ItemSnapshot,
    LaserSnapshot,
    PlayerSnapshot,
    Snapshot,
)
from .world import TouhouWorld, TouhouWorldEventStream

__all__ = [
    "BossSnapshot",
    "BulletSnapshot",
    "EnemySnapshot",
    "Game",
    "GameEvent",
    "GameEventKind",
    "GamePhase",
    "GameWorld",
    "Input",
    "ItemSnapshot",
    "LaserSnapshot",
    "PlayerSnapshot",
    "Snapshot",
    "TouhouWorld",
    "TouhouWorldEventStream",
]
