"""道具: 三态运动学(下落/吸附/生成动画) + 收集判定, 类型/分值语义全走事件。"""

from __future__ import annotations

import msgspec

from ..utils.math import Vec2
from .context import FrameContext
from .core import System, World
from .events import Event

# 状态(ItemManager.cpp 的 state 值)
STATE_FALL = 0  # 下落
STATE_ATTRACT = 1  # 向玩家吸附
STATE_SPAWN = 2  # 生成动画(60 帧飞向目标后转下落)

# 吸附速度/吸附半径默认值(.sht itemCollectSpeed/itemCollectRadius)
ITEM_COLLECT_SPEED = 4.0
ITEM_COLLECT_RADIUS = 16.0

#: 道具类型是作品概念(P 点/符点/残机…), engine 只透传不透明 kind 整数;
#: 分值/资源结算由作品 system 订阅 ItemCollected 实现


class ItemCollected(Event, frozen=True, tag="item_collected"):
    """一个道具被收集(收点盒相交且玩家可收)。"""

    kind: int
    x: float
    y: float
    auto_collect: bool = False  # 自动收集来的(旧: 仅结界收集标满分用)


class ItemDropped(Event, frozen=True, tag="item_dropped"):
    """一个道具掉出屏幕底边被删除(惩罚由作品订阅, 旧: DecreaseSubrank(3))。"""

    kind: int
    x: float
    y: float


class Item(msgspec.Struct):
    """一个道具的通用运动学状态; kind 是不透明类型号(语义在作品侧)。"""

    pos: Vec2 = Vec2.zero()
    start: Vec2 = Vec2.zero()  # 每帧落速/吸附速度
    state: int = STATE_FALL
    auto_collect: bool = False
    timer: int = 0
    target: Vec2 | None = None  # 生成动画目标(若非空)
    start_pos: Vec2 | None = None  # 生成动画起点
    kind: int = 0

    def drop(self) -> None:
        """出生: 向上初速, 随后加速下落。"""
        self.state = STATE_FALL
        self.start = Vec2(0, -2.2)
        self.target = self.start_pos = None

    def spawn_to(self, target: Vec2) -> None:
        """生成动画: 60 帧从当前位置飞向 target, 然后下落。"""
        self.state = STATE_SPAWN
        self.timer = 0
        self.target = target
        self.start_pos = self.pos

    def step(self, dt: float = 1.0) -> None:
        """下落状态的速度渐变: 向上不超 -2.2, 每帧 +0.03 加速到 +3.0 封顶。"""
        if self.state != STATE_FALL:
            return
        if self.start.y < -2.2:
            self.start = Vec2(self.start.x, -2.2)
        if self.start.y < 3.0:
            self.start = Vec2(self.start.x, min(self.start.y + 0.03 * dt, 3.0))


class ItemField(msgspec.Struct):
    """道具场状态容器: 道具列表 + 判定配置(作品侧每帧同步玩家相关字段)。

    扩展点: ``_status_change(item)`` —— 决定道具是否进入吸附(作品层实现各自
    触发条件, 如收集线/结界; 旧 item_base.ItemWorldBase._status_change);
    基类默认不触发吸附。
    """

    items: list[Item] = msgspec.field(default_factory=list)
    player_pos: Vec2 = Vec2(192, 400)
    player_alive: bool = True
    player_spawning: bool = False  # 玩家重生中: 不收点(旧 PlayerState.SPAWNING==1)
    item_collect_speed: float = ITEM_COLLECT_SPEED
    item_collect_radius: float = ITEM_COLLECT_RADIUS

    # ---- 生成 ----
    def spawn(self, at: Vec2, kind: int, state: int = STATE_FALL) -> Item:
        """放一个道具(state: 0=下落 1=吸附 2=生成动画走 Item.spawn_to)。"""
        # C++ SpawnItem 还有 3→1/4→0 的映射, 旧实现用不到, 不搬
        item = Item(pos=at, start=Vec2(0, -2.2), state=state, kind=kind)
        self.items.append(item)
        return item

    # ---- 每帧(MOVEMENT 槽) ----
    def step(self, ctx: FrameContext, dt: float = 1.0) -> None:
        """推进所有道具; 掉出底边的删除并产 ItemDropped 事件。"""
        keep: list[Item] = []
        for item in self.items:
            self._status_change(item)
            if item.state == STATE_SPAWN and item.target is not None:
                # 60 帧插值飞向目标
                item.timer += 1
                t = min(item.timer / 60.0, 1.0)
                item.pos = (item.start_pos or item.pos).lerp(item.target, t)
                if item.timer >= 60:
                    item.state = STATE_FALL
                    item.start = Vec2.zero()
            elif item.state == STATE_ATTRACT:
                item.start = (
                    self.player_pos - item.pos
                ).normalized() * self.item_collect_speed
                item.pos = item.pos + item.start * dt
            else:  # STATE_FALL
                item.step(dt)  # 速度渐变
                item.pos = item.pos + item.start * dt
            # 出屏(底边)删除 (ItemManager OnUpdate)
            if item.pos.y >= 448 + 16:
                ctx.events.emit(ItemDropped(item.kind, item.pos.x, item.pos.y))
            else:
                keep.append(item)
        self.items = keep

    def _status_change(self, item: Item) -> None:
        """决定 item 是否进入吸附(非生成动画中); 基类不吸附, 作品层覆盖。"""

    # ---- 收集(COLLISION 槽) ----
    def collect_pickup(self, item: Item) -> bool:
        """收集判定: 与玩家收点盒相交且玩家非死亡/重生。"""
        if not self.player_alive or self.player_spawning:
            return False
        return item.pos.distance(self.player_pos) <= self.item_collect_radius

    def collect_pass(self, ctx: FrameContext) -> None:
        """收走本帧可收的道具并产 ItemCollected 事件(结算由作品订阅)。"""
        keep: list[Item] = []
        for item in self.items:
            if self.collect_pickup(item):
                ctx.events.emit(
                    ItemCollected(item.kind, item.pos.x, item.pos.y, item.auto_collect)
                )
            else:
                keep.append(item)
        self.items = keep

    # ---- 批量操作 (ItemManager::RemoveAllItems / ActivateAllItems) ----
    def remove_all_items(self) -> None:
        """全部道具转吸附, 速度 (0,-0.5)。"""
        for item in self.items:
            item.state = STATE_ATTRACT
            item.start = Vec2(0.0, -0.5)

    def activate_all_items(self) -> None:
        """吸附中的道具转回下落, 速度 (0,-0.9)。"""
        for item in self.items:
            if item.state == STATE_ATTRACT:
                item.state = STATE_FALL
                item.start = Vec2(0.0, -0.9)

    def remove(self, item: Item) -> None:
        """摘除指定道具。"""
        if item in self.items:
            self.items.remove(item)

    def clear(self) -> None:
        """清空。"""
        self.items.clear()

    def alive(self) -> list[Item]:
        """在场道具列表(内部容器, 别改)。"""
        return self.items

    def __len__(self) -> int:
        return len(self.items)


class ItemMovementSystem(System[World]):
    """MOVEMENT 槽: 道具推进(三态运动学 + 出屏删除)。"""

    def __init__(self, field: ItemField) -> None:
        self.field = field

    def tick(self, world: World, ctx: FrameContext) -> None:
        self.field.step(ctx)


class ItemCollectSystem(System[World]):
    """COLLISION 槽: 收点判定, 产 ItemCollected 事件。"""

    def __init__(self, field: ItemField) -> None:
        self.field = field

    def tick(self, world: World, ctx: FrameContext) -> None:
        self.field.collect_pass(ctx)
