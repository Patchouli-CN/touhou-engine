"""弹系统的管线槽位落位: MOVEMENT 推进 / COLLISION 判定, 共享一个 BulletField。"""

from __future__ import annotations

from ..context import FrameContext
from ..core import System, World
from .field import BulletField


class BulletMovementSystem(System[World]):
    """MOVEMENT 槽: 弹推进/命令更新器/出界消弹/消弹窗口递减。"""

    def __init__(self, field: BulletField) -> None:
        self.field = field

    def tick(self, world: World, ctx: FrameContext) -> None:
        self.field.step(ctx)


class BulletCollisionSystem(System[World]):
    """COLLISION 槽: 擦弹/命中候选判定, 产 BulletGraze/BulletHit 事件。"""

    def __init__(self, field: BulletField) -> None:
        self.field = field

    def tick(self, world: World, ctx: FrameContext) -> None:
        self.field.check_player(ctx)
