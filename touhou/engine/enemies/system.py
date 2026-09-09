"""敌人系统的管线槽位落位: LOGIC 跑 ECL/bomb 盒, COLLISION 先体术后自机弹。"""

from __future__ import annotations

from ..bomb import BombField
from ..context import FrameContext
from ..core import System, World
from ..player import PlayerField
from ..shots import ShotField
from .field import EnemyField


class BombDamageSystem(System[World]):
    """LOGIC 槽: bomb 伤害盒对敌结算(挂在 EnemyEclSystem 前, 对齐旧帧内作用点)。"""

    def __init__(self, field: EnemyField, bombs: BombField) -> None:
        self.field = field
        self.bombs = bombs

    def tick(self, world: World, ctx: FrameContext) -> None:
        self.field.bomb_damage_pass(self.bombs, ctx)


class EnemyEclSystem(System[World]):
    """LOGIC 槽: 逐敌 ECL 步进/回调/despawn。"""

    def __init__(self, field: EnemyField) -> None:
        self.field = field

    def tick(self, world: World, ctx: FrameContext) -> None:
        self.field.step(ctx)


class EnemyContactSystem(System[World]):
    """COLLISION 槽: 体术判定(在 EnemyShotSystem 前挂载, 同 C++ 伤害段顺序)。"""

    def __init__(self, field: EnemyField, player: PlayerField) -> None:
        self.field = field
        self.player = player

    def tick(self, world: World, ctx: FrameContext) -> None:
        self.field.contact_pass(self.player, ctx)


class EnemyShotSystem(System[World]):
    """COLLISION 槽: 自机弹伤害/graze 追加/索敌/击坠结算, 产 EnemyDamaged/EnemyDied。"""

    def __init__(
        self, field: EnemyField, shots: ShotField, bombs: BombField | None = None
    ) -> None:
        self.field = field
        self.shots = shots
        self.bombs = bombs

    def tick(self, world: World, ctx: FrameContext) -> None:
        self.field.damage_pass(self.shots, self.bombs, ctx)
