"""自机场测试: 出生状态机/移动/判定擦弹/死亡重生流程/事件流。

数值权威: th07 Player.cpp (AddedCallback/Respawn/UpdateDeath/HandlePlayerInputs/
CheckGraze/CalcKillboxCollision); 语义移植自 old/touhou/engine/player_base.py,
用例改写自 old/tests/test_player_base.py(死亡结算内容属作品概念, 改为事件断言)。
"""

from __future__ import annotations

from touhou.engine import (
    BULLET_GRACE_PERIOD,
    RESPAWN_INVULN,
    SPAWN_INVULN,
    SPAWN_TICKS,
    FrameContext,
    PlayerDeathSettled,
    PlayerDied,
    PlayerField,
    PlayerGraceClear,
    PlayerGrazed,
    PlayerRespawned,
    PlayerState,
    Rng,
)
from touhou.utils.math import Vec2


def _ctx() -> FrameContext:
    return FrameContext(Rng(0))


def _collect(ctx: FrameContext) -> list:
    got: list = []
    ctx.events.subscribe(got.append)
    return got


def _player(**kw) -> PlayerField:
    kw.setdefault("pos", Vec2(192, 400))
    kw.setdefault("initial_respawn_timer", 30)
    # 注入移速(旧 StubPlayer: 直线 4 斜向 2)
    kw.setdefault("move_speed", 4.0)
    kw.setdefault("move_speed_focus", 1.7)
    kw.setdefault("move_speed_diagonal", 2.0)
    kw.setdefault("move_speed_diagonal_focus", 1.5)
    return PlayerField(**kw)


# ---- 出生状态机 ----
def test_initial_state_is_spawning() -> None:
    p = _player()
    assert p.state == PlayerState.SPAWNING
    assert p.invulnerability_timer == SPAWN_INVULN
    assert p.respawn_timer == 0  # 初值由 _enter_invulnerable 填


def test_spawning_enters_invulnerable() -> None:
    p = _player()
    p.step(_ctx())
    # invulnerabilityTimer>=30 → INVULNERABLE(240) + 60 帧清弹期
    assert p.state == PlayerState.INVULNERABLE
    assert p.invulnerability_timer == RESPAWN_INVULN
    assert p.bullet_grace_period == BULLET_GRACE_PERIOD
    assert p.respawn_timer == 30


def test_invulnerable_counts_down_to_alive() -> None:
    p = _player()
    p.step(_ctx())  # → INVULNERABLE(240)
    p.bullet_grace_period = 0
    for _ in range(RESPAWN_INVULN):
        p.step(_ctx())
    assert p.state == PlayerState.ALIVE
    assert p.invulnerability_timer == 0


def test_bullet_grace_period_emits_clear_event() -> None:
    ctx = _ctx()
    got = _collect(ctx)
    p = _player()
    p.step(ctx)  # 进入 INVULNERABLE, grace=60
    p.step(ctx)
    ctx.events.flush()
    assert any(isinstance(ev, PlayerGraceClear) for ev in got)


# ---- 移动 ----
def test_move_straight_and_bounds_clamp() -> None:
    p = _player()
    p.step(_ctx())  # → INVULNERABLE(可移动)
    p.push(1, 0)
    p.step(_ctx())
    assert p.pos.x == 196.0 and p.pos.y == 400
    for _ in range(100):
        p.step(_ctx())
    assert p.pos.x == 376.0  # 默认 bounds 右缘 384-8


def test_move_diagonal_uses_diagonal_speed() -> None:
    p = _player()
    p.step(_ctx())
    p.push(1, 1)
    p.step(_ctx())
    assert p.pos.x == 194.0 and p.pos.y == 402.0  # 斜向速度 2.0


def test_move_focus_uses_focus_speed() -> None:
    p = _player()
    p.step(_ctx())
    p.push(1, 0, focus=True)
    p.step(_ctx())
    assert p.pos.x == 193.7  # 低速直线 1.7


def test_dead_or_spawning_does_not_move() -> None:
    p = _player()
    p.invulnerability_timer = SPAWN_TICKS - 1  # 保持 SPAWNING(不触发转入)
    p.push(1, 0)
    p.step(_ctx())
    assert p.pos.x == 192.0 and p.state == PlayerState.SPAWNING


# ---- 判定/擦弹 ----
def test_contact_hit_alive_dies() -> None:
    ctx = _ctx()
    got = _collect(ctx)
    p = _player(state=PlayerState.ALIVE)
    assert p.contact_hit(p.pos, 4.0, 4.0, ctx) is True
    assert p.state == PlayerState.DEAD
    ctx.events.flush()
    assert any(isinstance(ev, PlayerDied) for ev in got)


def test_contact_hit_miss_and_invulnerable() -> None:
    ctx = _ctx()
    p = _player(state=PlayerState.ALIVE)
    assert p.contact_hit(p.pos + Vec2(100, 0), 4.0, 4.0, ctx) is False
    p.state = PlayerState.INVULNERABLE
    # 无敌中纯相交: 命中登记但不死 (CalcKillboxCollision==1 语义)
    assert p.contact_hit(p.pos, 4.0, 4.0, ctx) is True
    assert p.state == PlayerState.INVULNERABLE


def test_take_hit_state_gate_and_intercept() -> None:
    ctx = _ctx()
    p = _player(state=PlayerState.INVULNERABLE)
    assert p.take_hit(ctx) is False  # 非 ALIVE 不吃弹

    class BorderField(PlayerField):
        """拦截 hook: 命中不破(结界保命的作品语义替身)。"""

        def _intercept_hit(self, ctx: FrameContext) -> bool:
            return True

    p2 = BorderField(
        pos=Vec2(192, 400), state=PlayerState.ALIVE, initial_respawn_timer=30
    )
    assert p2.take_hit(ctx) is False
    assert p2.state == PlayerState.ALIVE  # 被拦截, 不死


def test_graze_geometry_and_gating() -> None:
    ctx = _ctx()
    got = _collect(ctx)
    p = _player(state=PlayerState.ALIVE)
    assert p.graze_check(p.pos + Vec2(30, 0), 4.0, 4.0, ctx) is True  # 24+2+20=46 内
    assert p.graze_check(p.pos + Vec2(100, 0), 4.0, 4.0, ctx) is False
    p.state = PlayerState.DEAD
    assert p.graze_check(p.pos, 4.0, 4.0, ctx) is False  # DEAD 不擦
    ctx.events.flush()
    assert len([ev for ev in got if isinstance(ev, PlayerGrazed)]) == 1


# ---- 死亡→结算→重生 ----
def test_death_settle_and_respawn_cycle() -> None:
    ctx = _ctx()
    got = _collect(ctx)
    p = _player(state=PlayerState.ALIVE)
    p.die(ctx)
    assert p.state == PlayerState.DEAD and p.respawn_timer == 30
    for _ in range(30):
        p.step(ctx)
    ctx.events.flush()
    kinds = [type(ev) for ev in got]
    assert PlayerDied in kinds
    assert PlayerDeathSettled in kinds
    assert PlayerRespawned in kinds
    # 结算事件先于重生事件(同 C++ UpdateDeath 顺序)
    assert kinds.index(PlayerDeathSettled) < kinds.index(PlayerRespawned)
    assert p.state == PlayerState.INVULNERABLE
    assert p.invulnerability_timer == RESPAWN_INVULN


def test_respawn_resets_pos_and_grace() -> None:
    p = _player(state=PlayerState.ALIVE, pos=Vec2(100, 100))
    p.respawn()
    assert p.pos == Vec2(192, 384)  # 版心底部
    assert p.state == PlayerState.INVULNERABLE
    assert p.bullet_grace_period == BULLET_GRACE_PERIOD
