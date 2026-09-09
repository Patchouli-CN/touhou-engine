"""炸弹场测试: 触发门槛/盒推进/判定几何/清弹事件/结束事件。

数值权威: Player.cpp:1658-1755 (UpdateBombProjectiles/UpdateBorderAndBombState/
CheckBombGraze/SpawnBomb*); 语义移植自 old/touhou/engine/bomb_base.py,
用例改写自 old/tests/test_bomb_base.py(结算 delta 透出改为 BombStarted 事件)。
"""

from __future__ import annotations

import msgspec

from touhou.engine import (
    BOMB_DURATION_PLACEHOLDER,
    BOMB_RESPAWN_PENALTY,
    ITEM_POINT_BULLET,
    Aim,
    BombClearedBullet,
    BombContext,
    BombEnded,
    BombField,
    BombStarted,
    BulletDespawned,
    BulletField,
    Burst,
    ClearBox,
    DamageBox,
    DespawnCause,
    FrameContext,
    Rng,
)
from touhou.utils.math import Vec2


class StubBomb(BombField[BombContext]):
    """最小机体炸弹: 首帧设 10 帧持续 + 一个伤害盒, 每帧计时, 到时结束。"""

    cost_calls: list[bool] = msgspec.field(default_factory=list)

    def _calc(self, ctx: FrameContext, bctx: BombContext) -> None:
        if self.timer == 0:
            self.duration = 10
            self.invulnerability_timer = 10
            self.damage_boxes[0] = DamageBox(self.start_pos, Vec2(40.0, 40.0), 5)
        self.timer += 1
        if self.timer >= self.duration:
            self.is_in_use = False

    def _tick_resource_cost(self, in_use: bool) -> None:
        self.cost_calls.append(in_use)


class BareBomb(BombField[BombContext]):
    """不布置任何盒的炸弹(_calc 空操作) —— 用于占位 duration 测试。"""

    def _calc(self, ctx: FrameContext, bctx: BombContext) -> None:
        pass


def _ctx() -> FrameContext:
    return FrameContext(Rng(0))


def _collect(ctx: FrameContext) -> list:
    got: list = []
    ctx.events.subscribe(got.append)
    return got


BCTX = BombContext(player_pos=Vec2(100.0, 300.0))


def _start_kw(**overrides):
    kw = dict(
        focus=False,
        bombs_remaining=3.0,
        respawn_timer=30,
        border_invulnerability_time=0,
        bomb_pressed=True,
    )
    kw.update(overrides)
    return kw


def _start(**overrides) -> StubBomb:
    ctx = _ctx()
    b = StubBomb()
    assert b.try_start(ctx, BCTX, **_start_kw(**overrides))
    return b


# ---- 触发门槛 (try_start) ----
def test_start_gating() -> None:
    b = StubBomb()
    ctx = _ctx()
    assert not b.try_start(ctx, BCTX, **_start_kw(bomb_pressed=False))
    assert not b.try_start(ctx, BCTX, **_start_kw(bombs_remaining=0.0))
    assert not b.try_start(ctx, BCTX, **_start_kw(respawn_timer=0))
    assert not b.try_start(ctx, BCTX, **_start_kw(border_invulnerability_time=5))
    assert not b.is_in_use  # 全部拒绝, 未触发


def test_start_success_state_and_event() -> None:
    ctx = _ctx()
    got = _collect(ctx)
    b = StubBomb()
    assert b.try_start(ctx, BCTX, **_start_kw(focus=True))
    assert b.is_in_use and b.is_focus
    assert b.start_pos == BCTX.player_pos
    # start() 当帧已跑一次 calc: duration 由占位 999 被机体设定为 10
    assert b.duration == 10 and b.invulnerability_timer == 10 and b.timer == 1
    assert len(b.damage_boxes) == 112 and len(b.sub_info) == 128
    ctx.events.flush()
    ev = [e for e in got if isinstance(e, BombStarted)]
    assert ev and ev[0].focus and ev[0].x == 100.0


def test_no_double_start_while_in_use() -> None:
    b = _start()
    assert not b.try_start(_ctx(), BCTX, **_start_kw())


def test_respawn_penalty_constant() -> None:
    """决死窗罚常量: respawnTimer += 6 封顶 initial (Player.cpp:1750-1754)。

    由作品订阅 BombStarted 后应用; 常量在 engine。
    """
    assert BOMB_RESPAWN_PENALTY == 6


# ---- 每帧盒推进 (UpdateBombProjectiles) ----
def test_tick_clears_damage_box_width_each_frame() -> None:
    b = _start()
    assert b.damage_boxes[0].size.x == 40.0  # start 当帧 calc 布置
    b.tick(_ctx(), BCTX)  # 帧首清零; stub calc 仅首帧布置
    assert b.damage_boxes[0].size.x == 0.0


def test_bomb_ends_after_duration_and_hook_called() -> None:
    ctx = _ctx()
    got = _collect(ctx)
    b = _start()
    alive = [b.tick(ctx, BCTX) for _ in range(8)]
    assert all(alive)
    assert not b.tick(ctx, BCTX)  # 第 9 帧 calc 置 is_in_use=False
    # 资源消耗 hook: 进行中每帧 True, 结束后 False
    assert b.cost_calls == [True] * 9
    assert not b.tick(ctx, BCTX)  # 已结束仍推进清弹盒, 返回 False
    assert b.cost_calls[-1] is False
    ctx.events.flush()
    assert len([e for e in got if isinstance(e, BombEnded)]) == 1  # 只在拉灭帧产一次


def test_clear_box_tick_and_growth() -> None:
    c = ClearBox(Vec2(100, 100), Vec2(0.0, 16.0), 3, ITEM_POINT_BULLET, growth=2.0)
    assert c.active
    c.tick()
    assert c.lifetime == 2 and c.size.y == 18.0
    c.tick()
    c.tick()
    assert c.lifetime == 0
    c.tick()  # lifetime<=0 → 清零
    assert c.size.y == 0.0 and c.pos_z == 0.0 and not c.active


# ---- 判定几何 ----
def test_damage_to_and_hits() -> None:
    b = _start()
    total = b.damage_to(Vec2(100.0, 300.0), Vec2(10.0, 10.0))  # 盒中心重叠
    assert total == 5  # lifetime 即每帧伤害
    assert b.damage_boxes[0].damage == 5  # 累计
    assert b.hits(Vec2(100.0, 300.0), Vec2(10.0, 10.0))
    assert not b.hits(Vec2(500.0, 300.0), Vec2(10.0, 10.0))
    assert b.damage_to(Vec2(500.0, 300.0), Vec2(10.0, 10.0)) == 0


def test_check_bomb_graze_circle_and_segment() -> None:
    b = StubBomb()
    # 圆: dist² < size.y²
    b.clear_boxes.append(ClearBox(Vec2(100, 100), Vec2(0.0, 30.0), 5, 6))
    assert b.check_bomb_graze(Vec2(110, 100), Vec2(4, 4)) == 2
    assert b.item_type == 6  # 透出命中盒的掉落类型
    assert b.check_bomb_graze(Vec2(200, 100), Vec2(4, 4)) == 0
    # 线性段: 宽=pos_z, 高=size.x
    b.clear_boxes.append(ClearBox(Vec2(300, 100), Vec2(20.0, 0.0), 5, 8, pos_z=40.0))
    assert b.check_bomb_graze(Vec2(310, 100), Vec2(4, 4)) == 2
    assert b.item_type == 8
    assert b.check_bomb_graze(Vec2(310, 200), Vec2(4, 4)) == 0


def test_duration_placeholder_constant() -> None:
    """触发时占位 duration (Player.cpp:1736) = 999, 由机体 calc 首帧覆盖。"""
    b = BareBomb()
    b.start(_ctx(), BCTX, focus=False)
    assert b.duration == BOMB_DURATION_PLACEHOLDER == 999


# ---- 清弹盒消弹 (clear_bullets) ----
def test_clear_bullets_despawns_and_emits_per_bullet() -> None:
    """命中清弹盒的敌弹: 产 BombClearedBullet(转道具订阅点) + BulletDespawned。"""
    ctx = _ctx()
    got = _collect(ctx)
    bombs = StubBomb()
    bombs.clear_boxes.append(ClearBox(Vec2(192, 100), Vec2(0.0, 50.0), 5, 6))
    bullets = BulletField()
    bullets.fire(
        Burst(Vec2(192, 100), 0.0, Aim.RING_ABSOLUTE, 2, 1, 2.0, 2.0, 0.0), ctx
    )
    bullets.fire(
        Burst(Vec2(192, 400), 0.0, Aim.RING_ABSOLUTE, 1, 1, 2.0, 2.0, 0.0), ctx
    )
    assert len(bullets) == 3
    n = bombs.clear_bullets(bullets, ctx)
    assert n == 2 and len(bullets) == 1
    ctx.events.flush()
    cleared = [e for e in got if isinstance(e, BombClearedBullet)]
    assert len(cleared) == 2 and all(e.item_type == 6 for e in cleared)
    despawned = [
        e
        for e in got
        if isinstance(e, BulletDespawned) and e.cause == DespawnCause.CLEARED
    ]
    assert len(despawned) == 2
