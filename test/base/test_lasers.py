"""激光场测试: 三态机 / 命中与擦激光 / 清弹连带 / 事件流。

数值权威: th07/src/th07/BulletManager.cpp 激光段, 移植自 old/tests/test_lasers.py
按新接口改写。
"""

from __future__ import annotations

import math

from touhou.engine import (
    FrameContext,
    Laser,
    LaserCollisionSystem,
    LaserField,
    LaserGraze,
    LaserHit,
    LaserMovementSystem,
    LaserSpawned,
    LaserState,
    Pipeline,
    Rng,
    Slot,
    World,
    laser_hits_player,
    tick_frame,
)
from touhou.engine.lasers import LASER_CAP
from touhou.utils.math import Vec2


def _ctx() -> FrameContext:
    return FrameContext(Rng(0))


# ======================================================================
# 三态机 (Laser::step)
# ======================================================================
def test_three_state_machine() -> None:
    f = LaserField()
    lsr = f.spawn(
        Vec2(100, 100),
        0.0,
        _ctx(),
        aimed=False,
        duration=60,
        start_time=20,
        end_time=30,
    )
    assert lsr is not None and lsr.state == LaserState.SPAWNING
    for _ in range(25):
        lsr.step()
    assert lsr.state == LaserState.ACTIVE
    for _ in range(70):
        lsr.step()
    assert lsr.state == LaserState.DESPAWNING
    assert lsr.in_use  # end_time=30 未耗尽
    for _ in range(40):
        lsr.step()
    assert not lsr.in_use


def test_start_time_zero_spawns_active() -> None:
    f = LaserField()
    lsr = f.spawn(Vec2(0, 0), 0.0, _ctx(), aimed=False, start_time=0)
    assert lsr is not None and lsr.state == LaserState.ACTIVE


def test_aimed_laser_rotates_toward_player() -> None:
    f = LaserField()
    f.player_pos = Vec2(384, 400)  # 玩家在右侧
    lsr = f.spawn(Vec2(192, 100), 0.0, _ctx(), aimed=True)
    # 朝向玩家的角 = atan2(400-100, 384-192) > 0 (右下方)
    assert lsr is not None and lsr.angle > 0


def test_spawn_cap_64() -> None:
    """同时在场上限 64 条, 满了返回 None 且不产事件。"""
    f = LaserField()
    ctx = _ctx()
    got: list = []
    ctx.events.subscribe(got.append)
    for _ in range(LASER_CAP):
        assert f.spawn(Vec2(0, 0), 0.0, ctx, aimed=False) is not None
    assert f.spawn(Vec2(0, 0), 0.0, ctx, aimed=False) is None
    ctx.events.flush()
    assert len([e for e in got if isinstance(e, LaserSpawned)]) == LASER_CAP


# ======================================================================
# 命中/擦激光几何 (laser_hits_player)
# ======================================================================
def test_hit_when_on_laser() -> None:
    # 竖激光: 自 (0,0) 沿 +x 长 160, 玩家在激光轨迹上(x=100)
    f = LaserField()
    lsr = f.spawn(Vec2(0, 0), 0.0, _ctx(), aimed=False, start_length=160.0)
    assert lsr is not None
    hit, _ = laser_hits_player(lsr, Vec2(100, 0), 4.0)
    assert hit  # 玩家在 laser 盒内(长度内、沿中线)


def test_graze_expands_box() -> None:
    f = LaserField()
    lsr = f.spawn(Vec2(0, 0), 0.0, _ctx(), aimed=False, width=8.0, start_length=160.0)
    assert lsr is not None
    # 玩家在激光一侧, y 偏差 30: 命中带=半宽4+玩家半径4=8, 擦带外扩到 8+48=56
    hit, graze = laser_hits_player(lsr, Vec2(80, 30), 4.0, graze_extra=48.0)
    assert not hit  # 30 > 8
    assert graze  # 30 < 56


# ======================================================================
# check_player 事件化 (每帧最多一条 hit/graze, 命中窗口门控)
# ======================================================================
def _active_laser_field(player: Vec2) -> LaserField:
    f = LaserField()
    f.spawn(Vec2(0, 0), 0.0, _ctx(), aimed=False, start_time=0, start_length=160.0)
    f.player_pos = player
    return f


def test_check_player_emits_hit_once_per_frame() -> None:
    f = _active_laser_field(Vec2(100, 0))  # 玩家在激光上
    ctx = _ctx()
    got: list = []
    ctx.events.subscribe(got.append)
    f.check_player(ctx)
    ctx.events.flush()
    hits = [e for e in got if isinstance(e, LaserHit)]
    assert len(hits) == 1 and (hits[0].x, hits[0].y) == (100.0, 0.0)
    assert not [e for e in got if isinstance(e, LaserGraze)]  # 命中不兼擦


def test_check_player_graze_throttled_per_12_frames() -> None:
    f = _active_laser_field(Vec2(80, 30))  # 擦带内命中带外
    ctx = _ctx()
    got: list = []
    ctx.events.subscribe(got.append)
    for _ in range(13):
        f.check_player(ctx)
        f.step()  # timer 推进: 擦激光 12 帧节流
    ctx.events.flush()
    graze = [e for e in got if isinstance(e, LaserGraze)]
    assert len(graze) == 2  # timer=0 与 timer=12 两帧


def test_spawning_laser_no_hit_before_hitbox_start() -> None:
    """SPAWNING 且 timer < hitbox_start_time 不判(出现期窄命中窗口)。"""
    f = LaserField()
    f.spawn(
        Vec2(0, 0),
        0.0,
        _ctx(),
        aimed=False,
        start_time=20,
        hitbox_start_time=20,
        start_length=160.0,
    )
    f.player_pos = Vec2(100, 0)
    ctx = _ctx()
    got: list = []
    ctx.events.subscribe(got.append)
    f.check_player(ctx)
    ctx.events.flush()
    assert not got


def test_hit_disabled_gate() -> None:
    """hit_enabled=False(旧: 炸弹中/非 ALIVE)不产 LaserHit。"""
    f = _active_laser_field(Vec2(100, 0))
    f.hit_enabled = False
    ctx = _ctx()
    got: list = []
    ctx.events.subscribe(got.append)
    f.check_player(ctx)
    ctx.events.flush()
    assert not [e for e in got if isinstance(e, LaserHit)]


# ======================================================================
# remove_all (BulletManager.cpp:439-471 / :524-550)
# ======================================================================
def _remove_all_laser(
    *,
    flags: int = 0,
    offset_a: float = 0.0,
    offset_b: float = 100.0,
    angle: float = 0.0,
    state: LaserState = LaserState.ACTIVE,
) -> tuple[LaserField, Laser]:
    f = LaserField()
    lsr = f.spawn(
        Vec2(50, 50),
        angle,
        _ctx(),
        aimed=False,
        duration=999,
        start_time=20,
        end_time=30,
    )
    assert lsr is not None
    lsr.flags = flags
    lsr.offset_a = offset_a
    lsr.offset_b = offset_b
    lsr.state = state
    return f, lsr


def test_remove_all_despawns_lasers() -> None:
    """进 DESPAWNING, timer=0, width=targetWidth, hitboxEndTime=0。"""
    f, lsr = _remove_all_laser()
    lsr.width = 3.0
    points = f.remove_all()
    assert lsr.state == LaserState.DESPAWNING
    assert lsr.timer == 0
    assert lsr.width == lsr.target_width
    assert lsr.hitbox_end_time == 0
    assert points == []  # 默认不出道具点


def test_remove_all_flag4_exemption() -> None:
    """flags&4 的激光 skip_flag4=True 时豁免; False(DespawnBullets/param=10) 不豁免。"""
    f, lsr = _remove_all_laser(flags=4)
    f.remove_all(skip_flag4=True)
    assert lsr.state == LaserState.ACTIVE
    assert lsr.hitbox_end_time == 40
    f2, lsr2 = _remove_all_laser(flags=4)
    f2.remove_all(skip_flag4=False)
    assert lsr2.state == LaserState.DESPAWNING
    assert lsr2.hitbox_end_time == 0


def test_remove_all_returns_item_points_along_laser() -> None:
    """spawn_items 沿线记点, DESPAWNING 中的不出点但照清 hitboxEndTime。"""
    # 自 startOffset 起每 32px 一点; spawn_at_pos 另加原点(仅 DespawnBullets 路径)
    f, _ = _remove_all_laser(offset_a=0.0, offset_b=100.0, angle=0.0)
    points = f.remove_all(spawn_items=True)
    # angle=0 → 沿 +x: x = 50+0/32/64/96, y = 50
    assert [(round(p.x), round(p.y)) for p in points] == [
        (50, 50),
        (82, 50),
        (114, 50),
        (146, 50),
    ]
    f, _ = _remove_all_laser(offset_a=0.0, offset_b=100.0, angle=math.pi / 2)  # 沿 +y
    points = f.remove_all(spawn_items=True, spawn_at_pos=True)
    assert [(round(p.x), round(p.y)) for p in points] == [
        (50, 50),
        (50, 50),
        (50, 82),
        (50, 114),
        (50, 146),
    ]
    # 已 DESPAWNING: 不出点, hitboxEndTime 照样清零
    f, lsr = _remove_all_laser(state=LaserState.DESPAWNING)
    points = f.remove_all(spawn_items=True)
    assert points == []
    assert lsr.hitbox_end_time == 0


# ======================================================================
# 槽位落位
# ======================================================================
def test_pipeline_slots_movement_then_collision() -> None:
    """MOVEMENT 槽推进, COLLISION 槽判定, 事件帧末 flush。"""
    f = LaserField()
    f.spawn(
        Vec2(0, 0),
        0.0,
        FrameContext(Rng(0)),
        aimed=False,
        start_time=0,
        start_length=160.0,
    )
    f.player_pos = Vec2(100, 0)
    world = World()
    pipe: Pipeline[World] = Pipeline()
    pipe.add(Slot.MOVEMENT, LaserMovementSystem(f))
    pipe.add(Slot.COLLISION, LaserCollisionSystem(f))
    ctx = _ctx()
    got: list = []
    ctx.events.subscribe(got.append)
    tick_frame(world, pipe, ctx)
    assert [type(e).__name__ for e in got] == ["LaserHit"]
