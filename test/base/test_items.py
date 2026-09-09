"""道具场测试: 三态运动学 / 收集判定 / 批量操作 / 事件流。

数值权威: th07/src/th07/ItemManager.cpp, 语义移植自 old/touhou/engine/item_base.py
(旧实现无独立引擎层单测, 本文件按同语义新写)。
"""

from __future__ import annotations

from touhou.engine import (
    ITEM_COLLECT_RADIUS,
    ITEM_COLLECT_SPEED,
    STATE_ATTRACT,
    STATE_FALL,
    STATE_SPAWN,
    FrameContext,
    Item,
    ItemCollected,
    ItemCollectSystem,
    ItemDropped,
    ItemField,
    ItemMovementSystem,
    Pipeline,
    Rng,
    Slot,
    World,
    tick_frame,
)
from touhou.utils.math import Vec2


def _ctx() -> FrameContext:
    return FrameContext(Rng(0))


# ======================================================================
# 下落运动学 (ItemBase.step: 向上不超 -2.2, 每帧 +0.03 到 +3.0 封顶)
# ======================================================================
def test_drop_initial_velocity_and_fall_acceleration() -> None:
    it = Item(pos=Vec2(100, 100))
    it.drop()
    assert it.state == STATE_FALL and it.start == Vec2(0, -2.2)
    f = ItemField(items=[it])
    f.step(_ctx())
    # 速度渐变(+0.03)先于位移: 首帧 start.y=-2.17, pos 按新速度走
    assert abs(it.start.y - (-2.2 + 0.03)) < 1e-9
    assert abs(it.pos.y - (100 - 2.2 + 0.03)) < 1e-9
    for _ in range(200):
        f.step(_ctx())
    assert it.start.y == 3.0  # 封顶


def test_fall_upward_velocity_clamped() -> None:
    # 出生初速比 -2.2 更向上时先压回 -2.2, 当帧照常 +0.03(两个 if 都跑)
    it = Item(pos=Vec2(100, 100), start=Vec2(0, -5.0))
    f = ItemField(items=[it])
    f.step(_ctx())
    assert abs(it.start.y - (-2.2 + 0.03)) < 1e-9


# ======================================================================
# 生成动画 (STATE_SPAWN: 60 帧插值飞向目标后转下落)
# ======================================================================
def test_spawn_to_lerps_60_frames_then_falls() -> None:
    it = Item(pos=Vec2(0, 0))
    it.spawn_to(Vec2(120, 60))
    assert it.state == STATE_SPAWN
    f = ItemField(items=[it])
    f.step(_ctx())
    assert it.pos == Vec2(2.0, 1.0)  # t=1/60
    for _ in range(58):
        f.step(_ctx())
    assert it.state == STATE_SPAWN and it.pos == Vec2(118.0, 59.0)  # t=59/60
    f.step(_ctx())  # 第 60 帧: 到顶转下落, start 归零
    assert it.state == STATE_FALL and it.start == Vec2.zero()


# ======================================================================
# 吸附 (STATE_ATTRACT: 朝玩家等速直线)
# ======================================================================
def test_attract_moves_toward_player_at_collect_speed() -> None:
    it = Item(pos=Vec2(100, 100), state=STATE_ATTRACT)
    f = ItemField(items=[it])
    f.player_pos = Vec2(100, 200)  # 正下方 100px
    f.step(_ctx())
    assert it.pos.distance(Vec2(100, 100 + ITEM_COLLECT_SPEED)) < 1e-9


def test_status_change_hook_drives_attract() -> None:
    """吸附触发是作品语义: 基类不吸附, 子类覆写 _status_change(收集线等)。"""
    it = Item(pos=Vec2(100, 200))
    f = ItemField(items=[it])
    f.step(_ctx())
    assert it.state == STATE_FALL  # 基类不触发

    class _LineField(ItemField):
        """y 越过收集线(128)即吸附的测试子类。"""

        def _status_change(self, item: Item) -> None:
            if item.state == STATE_FALL and item.pos.y < 128:
                item.state = STATE_ATTRACT

    it2 = Item(pos=Vec2(100, 100))
    f2 = _LineField(items=[it2])
    f2.player_pos = Vec2(100, 300)
    f2.step(_ctx())
    assert it2.state == STATE_ATTRACT


# ======================================================================
# 收集判定 + 事件
# ======================================================================
def test_collect_emits_event_and_removes() -> None:
    """收点盒(半径 16)内且玩家可收 → ItemCollected(kind/pos/auto_collect) 并移除。"""
    it = Item(pos=Vec2(100, 110), kind=7, auto_collect=True)
    f = ItemField(items=[it])
    f.player_pos = Vec2(100, 100)
    ctx = _ctx()
    got: list = []
    ctx.events.subscribe(got.append)
    f.collect_pass(ctx)
    ctx.events.flush()
    assert len(f) == 0
    assert got == [ItemCollected(7, 100.0, 110.0, True)]


def test_collect_gated_by_player_state() -> None:
    """玩家死亡/重生中不收(旧: !playerAlive || playerState==SPAWNING)。"""
    it = Item(pos=Vec2(100, 100), kind=1)
    f = ItemField(items=[it])
    f.player_pos = Vec2(100, 100)
    ctx = _ctx()
    got: list = []
    ctx.events.subscribe(got.append)
    f.player_alive = False
    f.collect_pass(ctx)
    f.player_alive = True
    f.player_spawning = True
    f.collect_pass(ctx)
    assert len(f) == 1 and not got
    f.player_spawning = False
    f.collect_pass(ctx)
    ctx.events.flush()
    assert len(f) == 0 and len(got) == 1


def test_collect_radius_edge() -> None:
    """收点盒边界: 距离恰等于半径收, 超过不收。"""
    f = ItemField()
    f.player_pos = Vec2(100, 100)
    near = f.spawn(Vec2(100 + ITEM_COLLECT_RADIUS, 100), 1)
    far = f.spawn(Vec2(100 + ITEM_COLLECT_RADIUS + 0.5, 100), 2)
    f.collect_pass(_ctx())
    assert near not in f.alive() and far in f.alive()


# ======================================================================
# 出屏删除 + ItemDropped 事件
# ======================================================================
def test_offscreen_bottom_drops_with_event() -> None:
    """掉出底边(y >= 448+16)删除并产 ItemDropped(惩罚由作品订阅)。"""
    f = ItemField()
    f.spawn(Vec2(100, 466.5), 3)
    f.spawn(Vec2(100, 100), 4)
    ctx = _ctx()
    got: list = []
    ctx.events.subscribe(got.append)
    f.step(ctx)
    ctx.events.flush()
    assert len(f) == 1
    assert len(got) == 1
    e = got[0]
    assert isinstance(e, ItemDropped) and e.kind == 3
    assert abs(e.y - (466.5 - 2.2 + 0.03)) < 1e-9  # 速度渐变后位移的位置上抛


# ======================================================================
# 批量操作 (ItemManager::RemoveAllItems / ActivateAllItems)
# ======================================================================
def test_remove_all_and_activate_all() -> None:
    """remove_all: 全转吸附 (0,-0.5); activate_all: 吸附中转回下落 (0,-0.9)。"""
    f = ItemField()
    a = f.spawn(Vec2(10, 10), 0)
    b = f.spawn(Vec2(20, 20), 1, state=STATE_ATTRACT)
    f.remove_all_items()
    assert a.state == STATE_ATTRACT and a.start == Vec2(0.0, -0.5)
    assert b.state == STATE_ATTRACT and b.start == Vec2(0.0, -0.5)
    a.start = Vec2(3.0, 0.0)  # 已被吸附推动过的
    f.activate_all_items()
    assert a.state == STATE_FALL and a.start == Vec2(0.0, -0.9)
    assert b.state == STATE_FALL and b.start == Vec2(0.0, -0.9)


# ======================================================================
# 槽位落位
# ======================================================================
def test_pipeline_slots_movement_then_collect() -> None:
    """MOVEMENT 槽推进, COLLISION 槽收集, 事件帧末 flush。"""
    f = ItemField()
    f.spawn(Vec2(100, 100), 5)
    f.player_pos = Vec2(100, 103)  # 收点半径内, 但 movement 先把它推离
    world = World()
    pipe: Pipeline[World] = Pipeline()
    pipe.add(Slot.MOVEMENT, ItemMovementSystem(f))
    pipe.add(Slot.COLLISION, ItemCollectSystem(f))
    ctx = _ctx()
    got: list = []
    ctx.events.subscribe(got.append)
    tick_frame(world, pipe, ctx)
    assert len(f) == 0  # 上飘 2.2px 后距离 5.2 仍在收点盒内
    assert [type(e).__name__ for e in got] == ["ItemCollected"]
