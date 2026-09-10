"""th07 炸弹测试: 参数表/CherryDrain/触发/六机体 12 套 calc parity + world 集成 smoke。

数值权威: th07/src/th07/BombData.cpp 与 Player.cpp; 用例改写自
old/tests/game_test/th07/test_th07_bomb.py(樱之结界用例属 player.py, 不在此)。
"""

from __future__ import annotations

import math
from collections import Counter

import pytest

from touhou.engine import Button, FrameContext, InputFrame, Rng
from touhou.engine.bomb import BombStarted
from touhou.engine.enemies import EnemyDamaged
from touhou.engine.player import PlayerDeathSettled, PlayerState
from touhou.games.th07.bomb import (
    BOMB_PARAMS,
    EVENT_END_PLAYER_SPELLCARD,
    EVENT_REMOVE_ALL_ITEMS,
    EVENT_STOP_BULLET_MOVEMENT,
    Th07BombContext,
    Th07BombField,
    compute_bomb_cherry_drain,
)
from touhou.games.th07.compose import compose
from touhou.games.th07.player import BorderState
from touhou.games.th07.world import Th07World, compose_world
from touhou.utils.math import Vec2

from .conftest import needs_data


class _FixedRng(Rng):
    """unit() 恒 0.5 的确定性 rng(对齐旧测试的 rng_float=lambda: 0.5)。"""

    def unit(self) -> float:
        return 0.5


def _ctx(*, fixed: bool = False) -> FrameContext:
    return FrameContext(_FixedRng(0) if fixed else Rng(0))


def _bctx(**kw) -> Th07BombContext:
    base = {
        "player_pos": Vec2(100.0, 300.0),
        "cherry": 101000.0,
        "cherry_start": 1000.0,
        "difficulty": 1,
    }
    base.update(kw)
    return Th07BombContext(**base)  # type: ignore[arg-type]


BCTX = _bctx()
BCTX_ENEMY = _bctx(last_enemy_hit=Vec2(276.0, 300.0))


def _started(
    bctx: Th07BombContext = BCTX, *, fixed: bool = False, **kw
) -> Th07BombField:
    b = Th07BombField(character=kw.pop("character", 0))
    b.start(_ctx(fixed=fixed), bctx, focus=kw.pop("focus", False))
    return b


def _tick_through(
    b: Th07BombField, ctx: FrameContext, bctx: Th07BombContext, timer: int
) -> None:
    """推进到处理完 bombTimer==timer (start 已处理 timer 0)。"""
    while b.timer <= timer:
        b.tick(ctx, bctx)


# ---- §D.3 参数表抽样 (BombData.cpp 各 *Calc 首帧) ----


def test_bomb_params_table_spot_check() -> None:
    assert BOMB_PARAMS[(0, False)].duration == 140  # BombData.cpp:137
    assert BOMB_PARAMS[(0, False)].invulnerability == 200
    assert BOMB_PARAMS[(0, False)].drain_min_cost == 4000
    assert BOMB_PARAMS[(0, False)].drain_scale == pytest.approx(0.20)
    p = BOMB_PARAMS[(3, True)]  # BombData.cpp:1107-1120
    assert (p.duration, p.invulnerability, p.drain_min_cost) == (340, 390, 10000)
    assert p.drain_scale == pytest.approx(0.41)
    p = BOMB_PARAMS[(5, True)]  # BombData.cpp:1633-1659
    assert (p.duration, p.invulnerability, p.drain_min_cost) == (300, 420, 6000)
    p = BOMB_PARAMS[(2, False)]  # BombData.cpp:723-739
    assert (p.duration, p.invulnerability, p.drain_min_cost) == (200, 250, 8000)


# ---- ComputeBombCherryDrain (BombData.cpp:87-112) ----


def test_cherry_drain_normal() -> None:
    # drain=int(100000*0.2)=20000; /140=142→140; minCost=4000/140=28→20; max=140
    d = compute_bomb_cherry_drain(
        cherry=101000,
        cherry_start=1000,
        difficulty=1,
        bomb_duration=140,
        min_cost=4000,
        scale=0.20,
    )
    assert d == 140


def test_cherry_drain_difficulty_divisors() -> None:
    base = dict(
        cherry=101000, cherry_start=1000, bomb_duration=140, min_cost=4000, scale=0.20
    )
    assert compute_bomb_cherry_drain(difficulty=2, **base) == 70  # 20000/2/140=71→70
    assert compute_bomb_cherry_drain(difficulty=3, **base) == 30  # 20000/4/140=35→30
    assert compute_bomb_cherry_drain(difficulty=4, **base) == 40  # 6666/140=47→40
    assert compute_bomb_cherry_drain(difficulty=5, **base) == 40


def test_cherry_drain_min_cost_floor() -> None:
    # drain=0 (cherry==cherryStart) → minCost=4000/140=28→20 生效
    d = compute_bomb_cherry_drain(
        cherry=1000,
        cherry_start=1000,
        difficulty=1,
        bomb_duration=140,
        min_cost=4000,
        scale=0.20,
    )
    assert d == 20


def test_cherry_drain_float_truncation() -> None:
    # (i32)(f32) 向零截断: int(149*0.2)=29 → /10=2 → 2-2%10=0; minCost=0 → 0
    d = compute_bomb_cherry_drain(
        cherry=1149,
        cherry_start=1000,
        difficulty=1,
        bomb_duration=10,
        min_cost=0,
        scale=0.20,
    )
    assert d == 0


# ---- 触发门槛 (Player.cpp:1719-1755) ----


def _try(bomb: Th07BombField | None = None, **kw) -> tuple[bool, Th07BombField]:
    args = dict(
        focus=False,
        bombs_remaining=3.0,
        respawn_timer=30,
        border_invulnerability_time=0,
        bomb_pressed=True,
    )
    args.update(kw)
    b = bomb or Th07BombField()
    return b.try_start(_ctx(), BCTX, **args), b


def test_start_bomb_success() -> None:
    ctx = _ctx()
    got: list = []
    ctx.events.subscribe(got.append)
    b = Th07BombField()
    started = b.try_start(
        ctx,
        BCTX,
        focus=False,
        bombs_remaining=3.0,
        respawn_timer=30,
        border_invulnerability_time=0,
        bomb_pressed=True,
    )
    assert started
    # 首帧初始化已在当帧 calc 里完成 (ReimuA)
    assert b.is_in_use and not b.is_focus
    assert b.duration == 140 and b.invulnerability_timer == 200
    assert b.cherry_drain == 140 and b.timer == 1
    assert EVENT_REMOVE_ALL_ITEMS in b.events
    ctx.events.flush()
    ev = [e for e in got if isinstance(e, BombStarted)]
    assert len(ev) == 1 and ev[0].x == 100.0


def test_start_bomb_rejections() -> None:
    assert not _try(bomb_pressed=False)[0]
    assert not _try(respawn_timer=0)[0]
    assert not _try(bombs_remaining=0)[0]
    assert not _try(border_invulnerability_time=10)[0]
    b = _started()  # bomb 中
    assert not _try(b)[0]


def test_all_twelve_bombs_dispatch() -> None:
    """12 套 (character, focus) 全部可分派, 首帧初始化与参数表一致。"""
    bctx = _bctx()
    for character in range(6):
        for focus in (False, True):
            b = Th07BombField(character=character)
            b.start(_ctx(fixed=True), bctx, focus=focus)
            params = BOMB_PARAMS[(character, focus)]
            assert b.is_in_use and b.duration == params.duration
            assert b.invulnerability_timer == params.invulnerability
            assert b.cherry_drain == compute_bomb_cherry_drain(
                cherry=bctx.cherry,
                cherry_start=bctx.cherry_start,
                difficulty=bctx.difficulty,
                bomb_duration=params.duration,
                min_cost=params.drain_min_cost,
                scale=params.drain_scale,
            )
            assert b.invulnerable and b.timer == 1


# ---- ReimuA 非集中: 珠弹节奏 (BombData.cpp:116-256) ----


def test_reimu_a_orb_spawn_rhythm() -> None:
    ctx = _ctx()
    b = _started()
    # timer 12 (=8 起首个 %6==0) 出第一个珠
    while b.timer <= 11:
        b.tick(ctx, BCTX)
        assert b.sub_info[0].state == 0
    b.tick(ctx, BCTX)  # 处理 timer==12
    sub = b.sub_info[0]
    assert sub.state == 1
    assert sub.speed == pytest.approx(14.6)  # 15 - 0.4 (当帧即衰减)
    # 角度 0: -pi/2 → 向上, 位置当帧移动
    assert sub.pos.x == pytest.approx(BCTX.player_pos.x, abs=1e-4)
    assert sub.pos.y == pytest.approx(300.0 - 14.6)
    # 每 6 帧一个: timer 18 出第二个
    while b.timer <= 18:
        b.tick(ctx, BCTX)
    assert b.sub_info[1].state == 1
    assert b.damage_boxes[0].size.x == 48.0  # 飞行中伤害盒 48×48
    assert b.damage_boxes[0].lifetime == 8


def test_reimu_a_orb_explosion() -> None:
    ctx = _ctx()
    b = _started()
    # 第 63 次衰减 speed=-10.2 < -10 → timer 74 爆开
    _tick_through(b, ctx, BCTX, 74)
    sub = b.sub_info[0]
    assert sub.state == 2
    # C++ 同帧覆写: 爆开帧伤害盒最终为 48×48/8 (BombData.cpp:220-229)
    box = b.damage_boxes[0]
    assert box.size == Vec2(48.0, 48.0) and box.lifetime == 8
    # 爆开清弹圆 SpawnBombEffect(64, 4.2667, 30)
    boom = [c for c in b.clear_boxes if c.growth == pytest.approx(4.266667)]
    assert len(boom) == 1
    assert boom[0].size.y == pytest.approx(64.0) and boom[0].lifetime == 30
    # 后续帧: 256×256/lifetime=2, 清弹圆半径增长
    b.tick(ctx, BCTX)
    box = b.damage_boxes[0]
    assert box.size == Vec2(256.0, 256.0) and box.lifetime == 2
    assert sub.counter == 1
    assert boom[0].size.y == pytest.approx(64.0 + 4.266667)
    assert boom[0].lifetime == 29
    # 爆开后 30 帧 (timer 104) 珠消失
    _tick_through(b, ctx, BCTX, 104)
    assert b.sub_info[0].state == 0


def test_reimu_a_lifecycle_and_drain() -> None:
    ctx = _ctx()
    b = _started()
    ticks = 0
    while b.is_in_use:
        b.tick(ctx, BCTX)
        ticks += 1
        assert b.drain_applied == b.cherry_drain  # 每帧扣 (Player.cpp:1705-1708)
        assert b.invulnerable  # bomb 期间 INVULNERABLE
    assert ticks == 140  # duration=140: start 处理 timer0, 再 140 帧后 timer==140 结束
    assert EVENT_END_PLAYER_SPELLCARD in b.events
    b.tick(ctx, BCTX)  # 结束后 drain 透出清零
    assert b.drain_applied == 0


# ---- ReimuA 集中: 追踪珠 (BombData.cpp:310-474) ----


def test_reimu_a_focused() -> None:
    ctx = _ctx(fixed=True)
    b = _started(focus=True, fixed=True)
    assert b.duration == 300 and b.invulnerability_timer == 360
    assert b.move_speed_multiplier == pytest.approx(0.6)
    # timer 64 的 i==0 跳过, timer 80 出第一个珠 (i=1)
    _tick_through(b, ctx, BCTX, 80)
    assert b.sub_info[0].state == 0
    sub = b.sub_info[1]
    assert sub.state == 1 and sub.accel > 0
    # 累计伤害 >= 100 → 爆开: 256×256/400 (集中版不被覆写)
    b.damage_boxes[1].damage = 100
    b.tick(ctx, BCTX)
    assert sub.state == 2
    box = b.damage_boxes[1]
    assert box.size == Vec2(256.0, 256.0) and box.lifetime == 400
    boom = [c for c in b.clear_boxes if c.growth == pytest.approx(6.6666665)]
    assert len(boom) == 1 and boom[0].lifetime == 15
    assert boom[0].size.y == pytest.approx(32.0)


# ---- ReimuB 非集中: 结界光束 (BombData.cpp:512-601) ----


def test_reimu_b_unfocused_init() -> None:
    b = _started(character=1)
    assert b.duration == 140 and b.invulnerability_timer == 200
    assert b.cherry_drain == 120  # 17000/140=121→120; min 3000/140=21→20
    # 4 条光束锚点在触发帧定格
    assert b.sub_info[0].pos == Vec2(100.0, 224.0)
    assert b.sub_info[1].pos == Vec2(192.0, 300.0)
    assert b.sub_info[2].pos == Vec2(100.0, 224.0)
    assert b.sub_info[3].pos == Vec2(192.0, 300.0)
    # 首帧 (timer==0) 不布置任何盒 (C++ if/else)
    assert len(b.clear_boxes) == 0
    assert b.damage_boxes[0].size.x == 0.0


def test_reimu_b_unfocused_beams() -> None:
    ctx = _ctx()
    b = _started(character=1)
    b.tick(ctx, BCTX)  # timer==1 (奇数): 段移到锚点 + 伤害盒
    assert len(b.clear_boxes) == 4
    # SpawnBombProjectile: 62×448 竖 / 384×62 横, lifetime=0
    assert [c.pos_z for c in b.clear_boxes] == [62.0, 384.0, 62.0, 384.0]
    assert [c.size.x for c in b.clear_boxes] == [448.0, 62.0, 448.0, 62.0]
    assert all(c.lifetime == 0 and c.item_type == 6 for c in b.clear_boxes)
    assert b.clear_boxes[0].pos == Vec2(100.0, 224.0)  # 竖束锚点
    assert b.clear_boxes[1].pos == Vec2(192.0, 300.0)  # 横束锚点
    # 伤害盒 size=(段宽,段高), lifetime=16
    assert b.damage_boxes[0].size == Vec2(62.0, 448.0)
    assert b.damage_boxes[1].size == Vec2(384.0, 62.0)
    assert b.damage_boxes[0].pos == Vec2(100.0, 224.0)
    assert b.damage_boxes[1].pos == Vec2(192.0, 300.0)
    assert all(b.damage_boxes[i].lifetime == 16 for i in range(4))
    b.tick(ctx, BCTX)  # timer==2 (偶数): 段留在玩家位置, 伤害盒不刷新
    assert all(c.pos == BCTX.player_pos for c in b.clear_boxes)
    assert b.damage_boxes[0].size.x == 0.0
    assert len(b.clear_boxes) == 4  # lifetime=0 槽位复用, 不无限增长


def test_reimu_b_unfocused_lifecycle() -> None:
    ctx = _ctx()
    b = _started(character=1)
    ticks = 0
    while b.is_in_use:
        b.tick(ctx, BCTX)
        ticks += 1
        assert b.drain_applied == 120 and b.invulnerable
    assert ticks == 140
    assert EVENT_END_PLAYER_SPELLCARD in b.events


# ---- ReimuB 集中: 大结界圆 (BombData.cpp:645-694) ----


def test_reimu_b_focused() -> None:
    ctx = _ctx()
    b = _started(character=1, focus=True)
    assert b.duration == 190 and b.invulnerability_timer == 250
    assert b.cherry_drain == 80  # 17000/190=89→80; min 3000/190=15→10
    assert b.move_speed_multiplier == pytest.approx(0.4)
    assert b.start_pos == BCTX.player_pos
    # 首帧 SpawnBombEffect(192, 0.384, 210)
    circle = b.clear_boxes[0]
    assert circle.size.y == pytest.approx(192.0)
    assert circle.growth == pytest.approx(0.384) and circle.lifetime == 210
    assert b.damage_boxes[0].size.x == 0.0  # 首帧无伤害盒
    b.tick(ctx, BCTX)  # timer==1: 伤害盒 256×256/18 钉在 startPos
    box = b.damage_boxes[0]
    assert box.size == Vec2(256.0, 256.0) and box.lifetime == 18
    assert box.pos == Vec2(100.0, 300.0)
    assert circle.lifetime == 209 and circle.size.y == pytest.approx(192.384)
    # 跑完 190 帧: 移速复位, 清弹圆比 bomb 多活 20 帧
    ticks = 1
    while b.is_in_use:
        b.tick(ctx, BCTX)
        ticks += 1
    assert ticks == 190 and b.move_speed_multiplier == 1.0
    assert circle.active and circle.lifetime == 20
    assert circle.size.y == pytest.approx(192.0 + 0.384 * 190)
    # bomb 结束后 UpdateBombProjectiles 仍每帧推进清弹盒 (Player.cpp:2231)
    b.tick(ctx, BCTX)
    assert circle.lifetime == 19 and b.drain_applied == 0


# ---- MarisaA 非集中: 星尘 (BombData.cpp:690-770) ----


def test_marisa_a_unfocused() -> None:
    ctx = _ctx()
    b = _started(character=2)
    assert b.duration == 200 and b.invulnerability_timer == 250
    assert b.cherry_drain == 150  # 30000/200=150; min 8000/200=40
    # 8 星从玩家以 2px/帧 向 8 方向
    for i in range(8):
        assert b.sub_info[i].pos == BCTX.player_pos
    assert b.sub_info[0].vel == Vec2(2.0, 0.0)
    assert b.sub_info[2].vel.x == pytest.approx(0.0, abs=1e-9)
    assert b.sub_info[2].vel.y == pytest.approx(2.0)
    b.tick(ctx, BCTX)  # timer==1 (%3!=0): 移动 + 伤害盒/清弹圆
    assert b.sub_info[0].pos == Vec2(102.0, 300.0)
    box = b.damage_boxes[0]
    assert box.size == Vec2(128.0, 128.0) and box.lifetime == 8
    assert box.pos == Vec2(102.0, 300.0)
    star_clear = [c for c in b.clear_boxes if c.size.y == pytest.approx(96.0)]
    assert len(star_clear) == 8  # 每星一个 SpawnBombEffect(96, 0, 0)
    _tick_through(b, ctx, BCTX, 3)  # timer==3 (%3==0): 停一拍
    assert b.damage_boxes[0].size.x == 0.0
    assert not any(c.active for c in b.clear_boxes)
    assert b.sub_info[0].pos == Vec2(106.0, 300.0)  # 移动不停
    ticks = 0
    while b.is_in_use:
        b.tick(ctx, BCTX)
        ticks += 1
    assert ticks == 197  # 已 tick 3 帧; 共 200


# ---- MarisaA 集中: 银河 (BombData.cpp:779-891) ----


def test_marisa_a_focused_spawn() -> None:
    ctx = _ctx(fixed=True)
    b = _started(character=2, focus=True, fixed=True)
    assert b.duration == 260 and b.invulnerability_timer == 310
    assert b.cherry_drain == 120  # 33000/260=126→120; min 9000/260=34→30
    assert b.move_speed_multiplier == pytest.approx(0.4)
    # 首帧 (timer==0) 即放 i=0: rng=0.5 → 角 -1.5707964, 初速 -5 (向下), 加速 0.24 向上
    sub = b.sub_info[0]
    assert sub.state == 1
    assert sub.vel.x == pytest.approx(0.0, abs=1e-5)
    assert sub.vel.y == pytest.approx(4.76)  # -5 起, 当帧 +0.24
    assert sub.accel_vec.y == pytest.approx(-0.24)
    assert sub.pos.x == pytest.approx(100.0) and sub.pos.y == pytest.approx(305.0)
    box = b.damage_boxes[0]
    assert box.size == Vec2(128.0, 128.0) and box.lifetime == 12
    assert b.sub_info[1].state == 0
    _tick_through(b, ctx, BCTX, 6)  # timer==6 放第二颗 (每 6 帧)
    assert b.sub_info[1].state == 1
    _tick_through(b, ctx, BCTX, 7)  # timer==7 不放
    assert b.sub_info[2].state == 0


def test_marisa_a_focused_damage_cap_and_despawn() -> None:
    ctx = _ctx(fixed=True)
    b = _started(character=2, focus=True, fixed=True)
    # 累计伤害 >=80 → 该星停刷伤害盒 (BombData.cpp:874-880)
    b.damage_boxes[0].damage = 80
    b.tick(ctx, BCTX)
    assert b.damage_boxes[0].size.x == 0.0
    assert b.damage_boxes[0].lifetime == 12  # 残留 lifetime 不清
    # 另起: y<-256 出界消 (rng=0.5 轨道约 93 帧出界)
    b2 = _started(character=2, focus=True, fixed=True)
    _tick_through(b2, ctx, BCTX, 120)
    assert b2.sub_info[0].state == 0
    ticks = 0
    while b2.is_in_use:
        b2.tick(ctx, BCTX)
        ticks += 1
    assert ticks == 260 - 120  # 已 tick 120 帧
    assert b2.move_speed_multiplier == 1.0


# ---- MarisaB 非集中: 旋转激光 (BombData.cpp:952-1048) ----


def test_marisa_b_unfocused() -> None:
    ctx = _ctx()
    b = _started(character=3)
    assert b.duration == 300 and b.invulnerability_timer == 300
    assert b.cherry_drain == 110  # 35000/300=116→110; min 8000/300=26→20
    assert b.move_speed_multiplier == pytest.approx(0.4)
    assert b.start_pos == BCTX.player_pos
    # 3 臂初始角 i*2pi/3 - pi/2
    assert b.sub_info[0].accel == pytest.approx(-math.pi / 2)
    assert b.sub_info[1].accel == pytest.approx(2 * math.tau / 6 - math.pi / 2)
    assert b.sub_info[2].accel == pytest.approx(4 * math.tau / 6 - math.pi / 2)
    assert b.damage_boxes[0].size.x == 0.0  # 首帧无盒
    b.tick(ctx, BCTX)  # timer==1: startPos.x=100<192 → 正转 pi/9000
    d = math.pi / 9000.0
    assert b.sub_info[0].accel == pytest.approx(-math.pi / 2 + d)
    # 每臂 6 盒, offset=32 起每 256/5 一个, 128×128/lifetime=10
    for i in range(3):
        for j in range(6):
            box = b.damage_boxes[i * 6 + j]
            assert box.size == Vec2(128.0, 128.0) and box.lifetime == 10
    box0 = b.damage_boxes[0]
    assert box0.pos.x == pytest.approx(100.0 + 32.0 * math.sin(d), abs=1e-4)
    assert box0.pos.y == pytest.approx(300.0 - 32.0 * math.cos(d), abs=1e-4)
    box1 = b.damage_boxes[1]
    assert box1.pos.y == pytest.approx(300.0 - 83.2 * math.cos(d), abs=1e-4)
    assert b.damage_boxes[18].size.x == 0.0  # 只用 18 个槽
    lasers = [c for c in b.clear_boxes if c.size.y == pytest.approx(64.0)]
    assert len(lasers) == 18  # 每盒一个 SpawnBombEffect(64, 0, 0)
    # startPos 在右半 → 反转
    bctx_r = _bctx(player_pos=Vec2(300.0, 300.0))
    b2 = _started(bctx_r, character=3)
    b2.tick(ctx, bctx_r)
    assert b2.sub_info[0].accel == pytest.approx(-math.pi / 2 - d)
    ticks = 0
    while b.is_in_use:
        b.tick(ctx, BCTX)
        ticks += 1
    assert ticks == 299 and b.move_speed_multiplier == 1.0


# ---- MarisaB 集中: Master Spark (BombData.cpp:1104-1170) ----


def test_marisa_b_focused() -> None:
    ctx = _ctx()
    b = _started(character=3, focus=True)
    assert b.duration == 340 and b.invulnerability_timer == 390
    assert b.cherry_drain == 120  # 41000/340=120; min 10000/340=29→20
    assert b.move_speed_multiplier == pytest.approx(0.2)
    b.tick(ctx, BCTX)  # timer==1 (%4!=0): 全屏纵束
    box = b.damage_boxes[0]
    assert box.size == Vec2(384.0, 300.0)  # 宽 384 × 高 player.y
    assert box.pos == Vec2(192.0, 150.0)  # (192, player.y/2)
    assert box.lifetime == 23
    # SpawnBombProjectile: 线性段 宽 384 高 300 @ (192,150), lifetime=0
    seg = b.clear_boxes[0]
    assert seg.pos_z == pytest.approx(384.0) and seg.size.x == pytest.approx(300.0)
    assert seg.pos == Vec2(192.0, 150.0) and seg.lifetime == 0
    _tick_through(b, ctx, BCTX, 4)  # timer==4 (%4==0): 停一拍
    assert b.damage_boxes[0].size.x == 0.0
    assert not any(c.active for c in b.clear_boxes)
    ticks = 0
    while b.is_in_use:
        b.tick(ctx, BCTX)
        ticks += 1
    assert ticks == 336 and b.move_speed_multiplier == 1.0  # 已 tick 4 帧


# ---- SakuyaA 非集中: 无差别飞刀 (BombData.cpp:1201-1290) ----


def test_sakuya_a_unfocused_spawn() -> None:
    ctx = _ctx(fixed=True)
    b = _started(character=4, fixed=True)
    assert b.duration == 160 and b.invulnerability_timer == 210
    assert b.cherry_drain == 170  # 28000/160=175→170; min 6000/160=37→30
    assert b.start_pos == BCTX.player_pos
    _tick_through(b, ctx, BCTX, 59)
    assert all(b.sub_info[i].state == 0 for i in range(96))  # timer<60 无刀
    b.tick(ctx, BCTX)  # timer==60: 每帧至多 5 把
    for i in range(5):
        assert b.sub_info[i].state == 1
    assert b.sub_info[5].state == 0
    # rng=0.5: 角 0, 初速 8.5, 加速 0.15, 漂移 0; 初始 pos=startPos+24*dir
    sub = b.sub_info[0]
    assert sub.angle == pytest.approx(0.0)
    assert sub.speed == pytest.approx(8.5) and sub.accel == pytest.approx(0.15)
    assert sub.angle_drift == pytest.approx(0.0)
    assert sub.pos == Vec2(124.0, 300.0)
    assert b.damage_boxes[0].damage == 0
    b.tick(ctx, BCTX)  # timer==61: 移动 (speed 8.5+0.15) + 伤害盒
    assert sub.pos.x == pytest.approx(132.65) and sub.pos.y == pytest.approx(300.0)
    box = b.damage_boxes[0]
    assert box.size == Vec2(24.0, 24.0) and box.lifetime == 10
    assert box.pos.x == pytest.approx(132.65)
    knife_clear = [c for c in b.clear_boxes if c.size.y == pytest.approx(32.0)]
    assert len(knife_clear) >= 5  # 每刀一个 SpawnBombEffect(32, 0, 0)


def test_sakuya_a_unfocused_pin_and_despawn() -> None:
    ctx = _ctx(fixed=True)
    b = _started(character=4, fixed=True)
    _tick_through(b, ctx, BCTX, 79)  # 96 把到 timer 79 已全部 spawn 过
    assert b.sub_info[95].state == 1
    sub = b.sub_info[0]
    # 累计伤害 >=30 → 刀钉住: 不移动不刷盒, damage=999 (BombData.cpp:1261-1272)
    b.damage_boxes[0].damage = 30
    pos_before = sub.pos
    b.tick(ctx, BCTX)
    assert sub.pos == pos_before
    assert b.damage_boxes[0].damage == 999 and b.damage_boxes[0].size.x == 0.0
    # 出界 (IsInBounds 64×64, GameManager.cpp:42-65) → 消失
    sub.pos = Vec2(500.0, 300.0)  # 500-32 > 384
    b.tick(ctx, BCTX)
    assert sub.state == 0
    ticks = 0
    while b.is_in_use:
        b.tick(ctx, BCTX)
        ticks += 1
    assert ticks == 160 - 81  # 已 tick 81 帧


# ---- SakuyaA 集中: 杀人玩偶 停时悬停 (BombData.cpp:1333-1473) ----


def test_sakuya_a_focused_spawn() -> None:
    ctx = _ctx(fixed=True)
    b = _started(BCTX_ENEMY, character=4, focus=True, fixed=True)
    assert b.duration == 250 and b.invulnerability_timer == 290
    assert b.cherry_drain == 110  # 29000/250=116→110; min 6500/250=26→20
    assert b.move_speed_multiplier == pytest.approx(0.3)
    _tick_through(b, ctx, BCTX_ENEMY, 19)
    assert b.sub_info[0].state == 0  # timer<20 无刀
    b.tick(ctx, BCTX_ENEMY)  # timer==20: i%48==0 → i=0 与 i=48 两把
    assert b.sub_info[0].state == 1 and b.sub_info[48].state == 1
    assert b.sub_info[1].state == 0
    sub = b.sub_info[0]
    # rng=0.5: 角 -pi, speed 1.0, accel 0.08, 漂移恒 -0.15707964
    assert sub.angle == pytest.approx(-math.pi)
    assert sub.angle_drift == pytest.approx(-0.15707964)
    # 初始 pos=player+24*dir=(76,300); 当帧 speed 1.08 再移 → (74.92,300)
    assert sub.speed == pytest.approx(1.08)
    assert sub.pos.x == pytest.approx(74.92) and sub.pos.y == pytest.approx(300.0)
    assert sub.sub_timer == 1
    box = b.damage_boxes[0]
    assert box.size == Vec2(24.0, 24.0) and box.lifetime == 22
    # timer 114 放最后两把 (i=47,95), 共 96
    _tick_through(b, ctx, BCTX_ENEMY, 114)
    assert b.sub_info[95].state == 1


def test_sakuya_a_focused_hover_and_aim() -> None:
    ctx = _ctx(fixed=True)
    b = _started(BCTX_ENEMY, character=4, focus=True, fixed=True)
    _tick_through(b, ctx, BCTX_ENEMY, 49)  # sub_timer 已到 30 边界前
    sub = b.sub_info[0]
    assert sub.sub_timer == 30
    pos_before = sub.pos
    b.tick(ctx, BCTX_ENEMY)  # sub_timer==30 → 停时悬停: vel=0, 只转角
    assert sub.vel == Vec2(0.0, 0.0) and sub.pos == pos_before
    # 漂移 -0.157/帧; -pi-0.157 经 AddNormalizeAngle 绕回 (-pi, pi]
    assert sub.angle == pytest.approx(math.pi - 0.15707964)
    _tick_through(b, ctx, BCTX_ENEMY, 89)
    b.tick(ctx, BCTX_ENEMY)  # sub_timer==70 → 瞄 positionOfLastEnemyHit, speed=14
    assert sub.speed == pytest.approx(14.08)  # 14 + accel 0.08
    assert sub.vel.x > 0.0  # 敌在右 (276 > pos.x≈7.7)
    assert sub.vel.y == pytest.approx(0.0, abs=1e-3)


def test_sakuya_a_focused_pin_and_lifecycle() -> None:
    ctx = _ctx(fixed=True)
    b = _started(BCTX_ENEMY, character=4, focus=True, fixed=True)
    _tick_through(b, ctx, BCTX_ENEMY, 20)
    sub = b.sub_info[0]
    # 命中 (damage != 0) → 刀钉住: 不移动不刷盒, damage=999 (BombData.cpp:1439-1451)
    b.damage_boxes[0].damage = 22
    pos_before = sub.pos
    b.tick(ctx, BCTX_ENEMY)
    assert sub.pos == pos_before
    assert b.damage_boxes[0].damage == 999 and b.damage_boxes[0].size.x == 0.0
    ticks = 0
    while b.is_in_use:
        b.tick(ctx, BCTX_ENEMY)
        ticks += 1
    assert ticks == 250 - 21
    assert b.move_speed_multiplier == 1.0


# ---- SakuyaB 非集中: 完美方阵 停时 (BombData.cpp:1502-1598) ----


def test_sakuya_b_unfocused() -> None:
    ctx = _ctx()
    b = _started(character=5)
    assert b.duration == 160 and b.invulnerability_timer == 260
    assert b.cherry_drain == 160  # 26000/160=162→160; min 5500/160=34→30
    assert b.move_speed_multiplier == pytest.approx(2.0)
    # 停时: 首帧 + timer 60/120 各一次 StopBulletMovement
    assert b.events.count(EVENT_STOP_BULLET_MOVEMENT) == 1
    _tick_through(b, ctx, BCTX, 29)
    assert all(b.sub_info[i].state == 0 for i in range(4))
    b.tick(ctx, BCTX)  # timer==30: 4 方阵视觉锚点激活; 30%4!=0 无伤害盒
    assert all(b.sub_info[i].state == 1 for i in range(4))
    assert b.damage_boxes[0].size.x == 0.0
    _tick_through(b, ctx, BCTX, 32)  # timer==32 (%4==0): 全场伤害盒
    box = b.damage_boxes[0]
    assert box.pos == Vec2(192.0, 224.0)
    assert box.size == Vec2(352.0, 416.0) and box.lifetime == 3
    ticks = 32  # 已 tick 到 timer 32
    b.events.clear()
    while b.is_in_use:
        b.tick(ctx, BCTX)
        ticks += 1
    assert ticks == 160
    # timer 60/120 的停时事件
    assert b.events.count(EVENT_STOP_BULLET_MOVEMENT) == 2
    assert b.move_speed_multiplier == 1.0
    # 结束帧 SpawnBombEffect(player, 800, 0, 0)
    assert b.clear_boxes[0].pos == BCTX.player_pos
    assert b.clear_boxes[0].size.y == pytest.approx(800.0)
    assert b.clear_boxes[0].lifetime == 0


# ---- SakuyaB 集中: 私人方阵 追踪领域 (BombData.cpp:1633-1724) ----


def test_sakuya_b_focused_init_and_track() -> None:
    ctx = _ctx()
    b = _started(character=5, focus=True)
    assert b.duration == 300 and b.invulnerability_timer == 420
    assert b.cherry_drain == 90  # 29000/300=96→90; min 6000/300=20
    assert b.move_speed_multiplier == 1.5
    # 首帧即有: 领域 96 清弹圆 + 伤害盒 160×160/lifetime=1 @ sub0.pos
    assert b.sub_info[0].state == 1 and b.sub_info[1].state == 1
    assert b.clear_boxes[0].size.y == pytest.approx(96.0)
    box = b.damage_boxes[0]
    assert box.size == Vec2(160.0, 160.0) and box.lifetime == 1
    assert box.pos == BCTX.player_pos
    # 追踪: 玩家移开后领域以 (playerPos-pos)/1700 加速 (伤害盒慢一拍, 取移动前 pos)
    bctx2 = _bctx(player_pos=Vec2(200.0, 200.0))
    b.tick(ctx, bctx2)
    accel = Vec2(100.0 / 1700.0, -100.0 / 1700.0)
    sub = b.sub_info[0]
    assert sub.vel.x == pytest.approx(accel.x) and sub.vel.y == pytest.approx(accel.y)
    assert sub.pos.x == pytest.approx(100.0 + accel.x)
    assert sub.pos.y == pytest.approx(300.0 + accel.y)
    assert b.damage_boxes[0].pos == BCTX.player_pos  # 慢 sub 一拍
    # timer 40/100 停时
    _tick_through(b, ctx, bctx2, 100)
    assert b.events.count(EVENT_STOP_BULLET_MOVEMENT) == 2


def test_sakuya_b_focused_end_clear_box_quirk() -> None:
    ctx = _ctx()
    b = _started(character=5, focus=True)
    ticks = 0
    while b.is_in_use:
        b.tick(ctx, BCTX)
        ticks += 1
    assert ticks == 300 and b.move_speed_multiplier == 1.0
    # 结束: SpawnBombEffect(800,0,0) 落在 0 槽后被覆写为线性段
    # (192,224) 宽448×高512, size.y=800 残留 (BombData.cpp:1646-1655, ZUN quirk)
    box0 = b.clear_boxes[0]
    assert box0.pos == Vec2(192.0, 224.0)
    assert box0.pos_z == pytest.approx(448.0)
    assert box0.size.x == pytest.approx(512.0) and box0.size.y == pytest.approx(800.0)
    assert box0.lifetime == 0
    # pos_z != 0 → 判定走线性段 (448×512), 而非 800 圆
    assert box0.hits(Vec2(192.0, 224.0), Vec2(8.0, 8.0))
    assert box0.hits(Vec2(192.0 + 227.0, 224.0), Vec2(8.0, 8.0))  # 227<228
    assert not box0.hits(Vec2(192.0 + 300.0, 224.0), Vec2(8.0, 8.0))  # 圆内段外
    # 下一帧 UpdateBombProjectiles 清零 (lifetime<=0)
    b.tick(ctx, BCTX)
    assert not box0.active


# ---------------------------------------------------------------------------
# world 集成 smoke (needs_data): 触发/消弹/伤害/结算链 + 决死窗 + 结界破分支
# ---------------------------------------------------------------------------


def _compose_world(character: int, difficulty: int = 2) -> Th07World:
    """seed=42 组一个一面世界; 夹具续命看长程流程。"""
    w = compose_world(compose(), character=character, difficulty=difficulty, seed=42)
    w.th07.lives = 99.0
    return w


@needs_data
def test_bomb_chain_smoke() -> None:
    """魔理沙B 集中 Master Spark: 触发 → 消弹转道具 → by_bomb 伤害 → 结束全链。"""
    w = _compose_world(character=3)
    log: list = []
    w.subscribers.append(log.append)
    hold = frozenset({Button.SHOT, Button.FOCUS})
    for _ in range(300):  # 站桩让敌/弹上场
        w.tick(InputFrame(held=hold))
    # 人工铺一环弹在自机周围(模拟 ECL 发弹, 保证消弹链可观测)
    w.bullets.ring(w.player.pos, 12, 0.5, FrameContext(w.rng), aimed=False)
    bombs_before = w.th07.bombs
    rank_before = w.th07.rank
    w.tick(InputFrame(held=hold, pressed=frozenset({Button.BOMB})))
    assert w.bomb.is_in_use and w.bomb.is_focus
    assert w.th07.bombs == bombs_before - 1 and w.th07.bombs_used == 1
    assert w.th07.rank < rank_before  # DecreaseSubrank(200)
    assert w.player.state == PlayerState.INVULNERABLE
    assert w.player.invulnerability_timer > 0
    for _ in range(400):
        w.tick(InputFrame(held=hold))
    kinds = Counter(type(e).__name__ for e in log)
    assert kinds["BombStarted"] == 1 and kinds["BombEnded"] == 1
    # 铺的环全被 Master Spark 线性段清掉, 逐颗产事件
    assert kinds["BombClearedBullet"] >= 12
    # 消弹转道具: 弹消点(出生即吸附)被收集
    assert kinds["ItemCollected"] > 0 or len(w.items.items) > 0
    # bomb 盒伤害链 + 结算入账
    assert any(e.by_bomb for e in log if isinstance(e, EnemyDamaged))
    assert w.globals.score > 0
    assert not w.bomb.is_in_use and w.bomb.move_speed_multiplier == 1.0


@needs_data
def test_deathbomb_smoke() -> None:
    """决死B: 死亡窗口内按 bomb → 消耗一枚代替丢残机, 死亡结算链不触发。"""
    w = _compose_world(character=0)
    log: list = []
    w.subscribers.append(log.append)
    for _ in range(5):  # 出生推进
        w.tick(InputFrame())
    w.player.state = PlayerState.DEAD
    w.player.respawn_timer = 15
    lives_before = w.th07.lives
    bombs_before = w.th07.bombs
    w.tick(InputFrame(pressed=frozenset({Button.BOMB})))
    assert w.bomb.is_in_use
    assert w.player.state == PlayerState.INVULNERABLE  # 决死B 成立
    assert w.th07.lives == lives_before  # 残机不扣
    assert w.th07.bombs == bombs_before - 1
    assert w.player.respawn_timer == min(15 + 6, w.player.initial_respawn_timer)
    assert not [e for e in log if isinstance(e, PlayerDeathSettled)]


@needs_data
def test_bomb_key_breaks_border_first() -> None:
    """有结界时按 bomb 键 = 主动破结界 (Player.cpp:1686-1692), 不触发炸弹。"""
    w = _compose_world(character=0)
    for _ in range(5):
        w.tick(InputFrame())
    w.player.border.ready_border()
    bombs_before = w.th07.bombs
    w.tick(InputFrame(pressed=frozenset({Button.BOMB})))
    assert not w.bomb.is_in_use
    assert w.th07.bombs == bombs_before
    assert w.player.border.has_border == BorderState.NONE
    # 破裂无敌 40 当帧被 border.tick 递减 (Player.cpp:1699-1701)
    assert w.player.border.border_invulnerability_time == 39
    assert len(w.border_boxes) == 1  # 全屏清弹圆已登记
    assert 33 in w.frame_sounds  # 结界破音 (se_bonus)
