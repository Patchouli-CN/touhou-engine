"""炸弹: BombField 生命周期(触发/持续/伤害盒/清弹盒/结束时序) + 事件。

对照 BombData.cpp / Player.cpp 的作品无关段。机体炸弹逻辑走 ``_calc``
hook(作品查表分派), 资源消耗走 ``_tick_resource_cost`` hook; 触发后的计数
扣减/决死窗罚/符卡 used_bomb 记账由作品订阅 BombStarted 实现(旧
BombStartResult 的 delta 字段全部事件化)。消弹转道具: BombClearedBullet
事件 + 作品订阅 spawn 道具(模拟件 A 的事件订阅接缝)。
"""

from __future__ import annotations

from typing import Generic, TypeVar

import msgspec

from ..utils.math import Vec2
from .bullets import Bullet, BulletField
from .context import FrameContext
from .core import System, World
from .events import Event

# 清弹盒掉落道具类型的通用默认: 弹消点(C++ ItemType  bullet 消点项固定值 6;
# 作品层 spawn 时可按自己的道具体系解释 item_type)
ITEM_POINT_BULLET = 6

BOMB_RESPAWN_PENALTY = (
    6  # respawnTimer += 6, 封顶 initialRespawnTimer (Player.cpp:1750-1754)
)
BOMB_DURATION_PLACEHOLDER = 999  # 触发时占位 duration (Player.cpp:1736)


class BombStarted(Event, frozen=True, tag="bomb_started"):
    """炸弹触发(消耗/符卡 used_bomb/决死窗 +6 等由作品订阅入账)。"""

    x: float
    y: float
    focus: bool


class BombEnded(Event, frozen=True, tag="bomb_ended"):
    """炸弹持续结束(机体 calc 把 is_in_use 拉灭的当帧)。"""


class BombClearedBullet(Event, frozen=True, tag="bomb_cleared_bullet"):
    """一颗敌弹被清弹盒消掉(item_type=命中盒登记的掉落类型, 转道具由作品订阅)。"""

    x: float
    y: float
    item_type: int


class DamageBox(msgspec.Struct):
    """炸弹伤害盒(bombDamageBoxes): size 为全宽/全高, 判定 pos±size/2 (Player.cpp:914-915)。

    lifetime 即每帧伤害; damage 累计已造成伤害(供追踪类炸弹判断爆开, Player.cpp:926)。
    """

    pos: Vec2
    size: Vec2
    lifetime: int
    damage: int = 0

    @property
    def active(self) -> bool:
        """size.x>0 且 lifetime>0。"""
        return self.size.x > 0 and self.lifetime > 0


class ClearBox(msgspec.Struct):
    """炸弹清弹盒(bombClearBoxes, §D.2.6 / Player.cpp:949-999, 1658-1681)。

    - pos_z != 0 → 线性段 AABB: 宽=pos_z, 高=size.x (中心 pos 各取一半)。
    - pos_z == 0 且 size.y != 0 → 圆: dist²(center, pos) < size.y²。
    - 两者皆 0 → 空槽(不活跃)。
    tick (UpdateBombProjectiles): lifetime<=0 → 清零(size.y=0, pos_z=0);
    否则 lifetime--, size.y += growth (size.z, 半径增长)。
    """

    pos: Vec2
    size: Vec2  # size.x=线性段高, size.y=圆半径
    lifetime: int
    item_type: int
    pos_z: float = 0.0  # pos.z: 线性段宽
    growth: float = 0.0  # size.z: 半径每帧增长

    @property
    def active(self) -> bool:
        """非空槽。"""
        return self.pos_z != 0.0 or self.size.y != 0.0

    def tick(self) -> None:
        """Player::UpdateBombProjectiles 的清弹盒部分 (Player.cpp:1667-1679)。"""
        if self.lifetime <= 0:
            self.size = Vec2(self.size.x, 0.0)
            self.pos_z = 0.0
        else:
            self.lifetime -= 1
            self.size = Vec2(self.size.x, self.size.y + self.growth)

    def hits(self, center: Vec2, size: Vec2) -> bool:
        """CheckBombGraze: center±size/2 的弹盒是否命中此清弹盒 (Player.cpp:965-996)。"""
        if self.pos_z != 0.0:
            # 线性段: AABB, 宽=pos_z, 高=size.x
            return (
                abs(center.x - self.pos.x) <= (self.pos_z + size.x) / 2
                and abs(center.y - self.pos.y) <= (self.size.x + size.y) / 2
            )
        if self.size.y != 0.0:
            # 圆: dist² < size.y²
            d = center - self.pos
            return d.x * d.x + d.y * d.y < self.size.y * self.size.y
        return False


class BombSubInfo(msgspec.Struct):
    """PlayerBombSubInfo 的逻辑部分 (§D.1): 子弹状态机 0=空 1=飞行 2=爆开。

    pos/vel 对应 bombRegionPositions/bombRegionVelocities; accel/accel_vec/
    angle_drift/sub_timer 的复用语义由作品层各机体 calc 定义。
    """

    state: int = 0
    counter: int = 0
    speed: float = 0.0
    accel: float = 0.0
    angle: float = 0.0
    pos: Vec2 = msgspec.field(default_factory=Vec2.zero)
    vel: Vec2 = msgspec.field(default_factory=Vec2.zero)
    accel_vec: Vec2 = msgspec.field(default_factory=Vec2.zero)
    angle_drift: float = 0.0
    sub_timer: int = 0


class BombContext(msgspec.Struct):
    """bombCalc 的每帧外部输入的通用子集(作品层子类追加专属字段)。"""

    player_pos: Vec2
    difficulty: int = 1


BombCtxT = TypeVar("BombCtxT", bound=BombContext)


class BombField(msgspec.Struct, Generic[BombCtxT]):
    """一次炸弹的生命周期 (PlayerBombInfo + UpdateBorderAndBombState 的 bomb 分支)。

    上层每帧消费 damage_boxes(伤害) / clear_boxes(清弹) /
    invulnerability_timer(首帧设定的无敌) / invulnerable(bomb 期间
    playerState=INVULNERABLE) / move_speed_multiplier(炸弹中移速倍率)。

    扩展点:
    - ``_calc(ctx, bctx)``: stub, 子类实现机体炸弹逻辑(查表分派);
    - ``_tick_resource_cost(in_use)``: 每帧资源消耗 hook, 基类无消耗;
    - ``_reset_run_state()``: start() 时重置作品专属运行状态的 hook。
    """

    is_in_use: bool = False
    is_focus: bool = False
    duration: int = 0
    timer: int = 0
    has_ticked: bool = False  # ZunTimer: current != previous
    invulnerability_timer: int = 0
    invulnerable: bool = True
    move_speed_multiplier: float = 1.0
    start_pos: Vec2 = msgspec.field(default_factory=Vec2.zero)
    item_type: int = ITEM_POINT_BULLET  # CheckBombGraze 命中后透出的掉落类型
    damage_boxes: list[DamageBox] = msgspec.field(default_factory=list)
    clear_boxes: list[ClearBox] = msgspec.field(default_factory=list)
    sub_info: list[BombSubInfo] = msgspec.field(default_factory=list)

    # ---- 触发/结束 ----
    def try_start(
        self,
        ctx: FrameContext,
        bctx: BombCtxT,
        *,
        focus: bool,
        bombs_remaining: float,
        respawn_timer: int,
        border_invulnerability_time: int,
        bomb_pressed: bool,
    ) -> bool:
        """炸弹触发门槛 (UpdateBorderAndBombState 触发分支, Player.cpp:1719-1755)。

        条件: 非 bomb 中 && respawn_timer != 0 && bombs > 0 &&
        border_invulnerability_time == 0 && 按下 bomb 键 (对话框/结界破分支
        属作品侧, 先判断完再调本方法)。成功即 start(含当帧一次 calc)。
        """
        if (
            self.is_in_use
            or not bomb_pressed
            or respawn_timer == 0
            or bombs_remaining <= 0
            or border_invulnerability_time != 0
        ):
            return False
        self.start(ctx, bctx, focus=focus)
        return True

    def start(self, ctx: FrameContext, bctx: BombCtxT, *, focus: bool) -> None:
        """触发炸弹 (Player.cpp:1732-1744)。duration/invuln 由机体 calc 首帧设定。"""
        self.is_in_use = True
        self.is_focus = focus
        self.duration = BOMB_DURATION_PLACEHOLDER
        self.timer = 0
        self.has_ticked = True  # ZunTimer operator=: previous=-999 → 视为已 tick
        self.invulnerability_timer = 0
        self.invulnerable = True
        self.move_speed_multiplier = 1.0
        self.start_pos = bctx.player_pos
        self.damage_boxes = [DamageBox(Vec2.zero(), Vec2.zero(), 0) for _ in range(112)]
        self.clear_boxes = []
        self.sub_info = [
            BombSubInfo() for _ in range(128)
        ]  # C++ subInfo[128] (Player.hpp:116)
        self._reset_run_state()
        self._calc(ctx, bctx)  # 触发当帧立刻调用一次
        ctx.events.emit(BombStarted(bctx.player_pos.x, bctx.player_pos.y, focus))

    def tick(self, ctx: FrameContext, bctx: BombCtxT) -> bool:
        """推进一帧 (Player::OnUpdate: UpdateBombProjectiles → UpdateBorderAndBombState)。

        UpdateBombProjectiles 每帧无条件执行 (Player.cpp:2231), 即使 bomb 已结束
        (清弹盒可比 bomb 活得久, 如旧灵梦B 集中 lifetime=210 > duration=190)。
        is_in_use 拉灭当帧产 BombEnded。返回是否仍在进行。
        """
        # UpdateBombProjectiles (Player.cpp:1658-1681): 伤害盒 size.x 清零, 清弹盒推进
        for box in self.damage_boxes:
            box.size = Vec2(0.0, box.size.y)
        for cbox in self.clear_boxes:
            cbox.tick()
        if not self.is_in_use:
            self._tick_resource_cost(False)
            return False
        self._tick_resource_cost(True)
        self._calc(ctx, bctx)
        if not self.is_in_use:
            ctx.events.emit(BombEnded())
        return self.is_in_use

    def _calc(self, ctx: FrameContext, bctx: BombCtxT) -> None:
        """机体炸弹逻辑 stub —— 子类实现(作品查表分派)。"""
        raise NotImplementedError("机体炸弹逻辑由作品层子类实现")

    def _tick_resource_cost(self, in_use: bool) -> None:
        """每帧资源消耗 hook(无消耗的作品留空)。"""

    def _reset_run_state(self) -> None:
        """start() 时重置作品专属运行状态的 hook。"""

    def _free_clear_slot(self) -> ClearBox:
        """Spawn* 的槽位搜索: 首个空槽(pos_z==0 且 size.y==0), 全满写第 96 槽。

        C++ 循环只扫 0..94, 落空后写 bomb[95] (Player.cpp:2044-2050/2069-2075)。
        """
        for box in self.clear_boxes:
            if box.pos_z == 0.0 and box.size.y == 0.0:
                return box
        if len(self.clear_boxes) < 96:
            box = ClearBox(Vec2.zero(), Vec2.zero(), 0, ITEM_POINT_BULLET)
            self.clear_boxes.append(box)
            return box
        return self.clear_boxes[95]

    def _spawn_clear(
        self, pos: Vec2, *, radius: float, growth: float, lifetime: int, item_type: int
    ) -> ClearBox:
        """Player::SpawnBombEffect (Player.cpp:2063-2084): 清弹圆, 半径每帧 +growth。

        照抄 C++: 复用槽时只写 pos/size.y/size.z/lifetime/itemType, 不动 size.x/pos_z。
        """
        box = self._free_clear_slot()
        box.pos = pos
        box.size = Vec2(box.size.x, radius)
        box.lifetime = lifetime
        box.item_type = item_type
        box.growth = growth
        return box

    def _spawn_projectile(
        self, pos: Vec2, *, width: float, height: float, item_type: int
    ) -> ClearBox:
        """Player::SpawnBombProjectile (Player.cpp:2038-2060): 线性段清弹盒。

        pos.z=width(段宽), size.x=height(段高), lifetime=0 (下帧 UpdateBombProjectiles
        清零, 仅存活当帧); 照抄 C++: 复用槽时不动 size.y/size.z。
        """
        box = self._free_clear_slot()
        box.pos = pos
        box.pos_z = width
        box.size = Vec2(height, box.size.y)
        box.lifetime = 0
        box.item_type = item_type
        return box

    # ---- 清弹判定 (CheckBombGraze) ----
    def check_bomb_graze(self, center: Vec2, size: Vec2) -> int:
        """Player::CheckBombGraze: 弹盒命中任一清弹盒 → 返回 2 并透出 item_type。"""
        for box in self.clear_boxes:
            if box.hits(center, size):
                self.item_type = box.item_type
                return 2
        return 0

    def clear_bullets(self, bullets: BulletField, ctx: FrameContext) -> int:
        """清弹盒 vs 全场敌弹: 命中的消掉并逐颗产 BombClearedBullet, 返回颗数。

        消弹本身产 BulletDespawned(CLEARED); 转道具由作品订阅 BombClearedBullet
        (模拟件 A 的事件订阅接缝)。出生态弹不吃炸弹盒 (C++ CheckBombGraze
        只在判定路径里触发)。
        """
        bsize = Vec2(bullets.bullet_radius * 2.0, bullets.bullet_radius * 2.0)
        hits: list[tuple[Bullet, int]] = []
        for b in bullets.alive():
            if b.spawn_state:
                continue
            if self.check_bomb_graze(b.pos, bsize):
                hits.append((b, self.item_type))
        doomed = {id(b) for b, _ in hits}
        for b, item_type in hits:
            ctx.events.emit(BombClearedBullet(b.pos.x, b.pos.y, item_type))
        bullets.clear_where(lambda b: id(b) in doomed, ctx.events)
        return len(hits)

    # ---- 敌侧面伤害 (CalcDamageToEnemy 的炸弹盒部分) ----
    def damage_to(self, enemy_pos: Vec2, enemy_half: Vec2) -> int:
        """对 enemy 的总伤害: lifetime 即每帧伤害, 同时累计入 box.damage (Player.cpp:907-927)。"""
        total = 0
        for box in self.damage_boxes:
            if box.size.x <= 0.0:
                continue
            if _aabb(box.pos, box.size / 2, enemy_pos, enemy_half):
                total += box.lifetime
                box.damage += box.lifetime
        return total

    def hits(self, enemy_pos: Vec2, enemy_half: Vec2) -> bool:
        """伤害盒是否与敌人盒相交(纯判定, 不累计 box.damage)。

        对应 CalcDamageToEnemy 的 collisionOut 置位条件 (Player.cpp:939-942):
        炸弹中且任一伤害盒命中 → *param_3=1。
        """
        for box in self.damage_boxes:
            if box.size.x <= 0.0:
                continue
            if _aabb(box.pos, box.size / 2, enemy_pos, enemy_half):
                return True
        return False


class BombSystem(System[World]):
    """LOGIC 槽: bomb 每帧推进(盒清零/清弹盒生长/机体 calc/结束事件)。

    触发由作品输入 system 调 BombField.try_start(门槛需作品侧状态)。
    bctx 由作品侧每帧同步(player_pos/difficulty 等)。
    """

    def __init__(self, field: BombField[BombCtxT], bctx: BombCtxT) -> None:
        self.field = field
        self.bctx = bctx

    def tick(self, world: World, ctx: FrameContext) -> None:
        self.field.tick(ctx, self.bctx)


class BombClearSystem(System[World]):
    """LOGIC 槽: 清弹盒消弹(挂在 EnemyEclSystem 前, 对齐旧 _apply_bomb_boxes 位置)。

    不门控 is_in_use: 清弹盒可比 bomb 活得久(C++ CheckBombGraze 由弹侧
    每帧无条件走, 盒槽空自然无命中)。
    """

    def __init__(self, field: BombField[BombCtxT], bullets: BulletField) -> None:
        self.field = field
        self.bullets = bullets

    def tick(self, world: World, ctx: FrameContext) -> None:
        self.field.clear_bullets(self.bullets, ctx)


# 一个简单的 AABB 相交(盒中心 + 半宽)
def _aabb(a_center: Vec2, a_half: Vec2, b_center: Vec2, b_half: Vec2) -> bool:
    return (
        abs(a_center.x - b_center.x) < a_half.x + b_half.x
        and abs(a_center.y - b_center.y) < a_half.y + b_half.y
    )
