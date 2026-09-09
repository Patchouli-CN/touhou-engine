"""自机弹测试: 射击发生器(fire 周期/entry 链/弹池) + 弹道推进 + 伤害结算。

数值权威: th07 Player.cpp (SpawnBullets/UpdateFireBulletTimer/UpdateShots/
CalcDamageToEnemy); 语义移植自 old/touhou/games/th07/player.py 的作品无关段。
"""

from __future__ import annotations

import math

from touhou.engine import (
    FIRE_CYCLE,
    FrameContext,
    PlayerShot,
    Rng,
    ShotField,
    ShotFired,
    ShotTimer,
)
from touhou.schemas.shot_data import ShotData, ShotEntry, ShotLevel
from touhou.utils.math import Vec2


def _ctx() -> FrameContext:
    return FrameContext(Rng(0))


def _collect(ctx: FrameContext) -> list:
    got: list = []
    ctx.events.subscribe(got.append)
    return got


def _entry(**kw) -> ShotEntry:
    base = dict(
        fire_interval=4,
        fire_offset=0,
        offset=(0.0, 0.0),
        hitbox=(6.0, 6.0),
        angle=-math.pi / 2,
        speed=8.0,
        damage=5,
        option=0,
        bullet_state2=0,
        fire_cb=0,
        update_cb=0,
        draw_cb=0,
        hit_cb=0,
    )
    base.update(kw)
    return ShotEntry(**base)


def _shot_data(*entries: ShotEntry) -> ShotData:
    return ShotData(
        3.0,
        30,
        2.0,
        48.0,
        4.0,
        16.0,
        0.0,
        100.0,
        4.0,
        1.7,
        2.0,
        1.5,
        [ShotLevel(0, list(entries))],
    )


def _field(*entries: ShotEntry, **kw) -> ShotField:
    kw.setdefault("shot_data", _shot_data(*entries))
    kw.setdefault("firing", True)
    return ShotField(**kw)


# ======================================================================
# 射击发生器 (UpdateFireBulletTimer / SpawnBullets)
# ======================================================================
def test_fire_cycle_spawns_on_interval() -> None:
    """FireBulletTimer 从 -1 置 0 启动; fire_interval=4 → 每 4 帧一发。"""
    ctx = _ctx()
    got = _collect(ctx)
    f = _field(_entry())
    for _ in range(9):
        f.fire_pass(ctx)
    alive = f.shots()
    # fire_time 0/4/8 各一发
    assert len(alive) == 3
    ctx.events.flush()
    assert len([ev for ev in got if isinstance(ev, ShotFired)]) == 3


def test_fire_offset_gating() -> None:
    """fire_time % interval != offset → 当帧不发射 (DefaultFireBulletCallback)。"""
    f = _field(_entry(fire_interval=4, fire_offset=2))
    for _ in range(2):
        f.fire_pass(_ctx())  # fire_time 0, 1: 0%4!=2, 1%4!=2
    assert not f.shots()
    f.fire_pass(_ctx())  # fire_time 2: 2%4==2 → 发
    assert len(f.shots()) == 1


def test_fire_timer_rolls_and_restarts() -> None:
    """到 fire_cycle 归 -1, 持续按住下帧从 0 重启; 松开/死亡也归 -1。"""
    f = _field(_entry())
    for _ in range(FIRE_CYCLE):
        f.fire_pass(_ctx())
    assert f.fire_time == -1
    f.fire_pass(_ctx())  # 仍按住 → 重启
    assert f.fire_time == 1
    f.player_state = 2  # DEAD
    f.fire_pass(_ctx())
    assert f.fire_time == -1


def test_no_fire_when_dead_or_not_firing() -> None:
    f = _field(_entry())
    f.firing = False
    f.fire_pass(_ctx())
    assert f.fire_time == -1 and not f.shots()
    f.firing = True
    f.player_state = 1  # SPAWNING
    f.fire_pass(_ctx())
    assert f.fire_time == -1 and not f.shots()


def test_fire_suppressed_keeps_timer_but_no_spawn() -> None:
    """fire_suppressed(旧机体炸弹中不发射的通用化): 计时照走不发射。"""
    f = _field(_entry())
    f.fire_suppressed = True
    for _ in range(5):
        f.fire_pass(_ctx())
    assert not f.shots()
    assert f.fire_time == 5


def test_spawn_uses_entry_geometry_and_focus_data() -> None:
    """init_shot: 发射点 = player_pos + offset, 速度角/伤害/判定盒来自 entry。"""
    ctx = _ctx()
    f = _field(_entry(offset=(3.0, -8.0), damage=7), player_pos=Vec2(100, 300))
    f.fire_pass(ctx)
    b = f.shots()[0]
    assert b.pos == Vec2(103, 292)
    assert b.velocity == Vec2.from_angle(-math.pi / 2, 8.0)
    assert b.damage == 7 and b.hitbox == (6.0, 6.0)
    # focus 时用 shot_data_focus
    f2 = _field(_entry(damage=9), focus=True)
    f2.shot_data_focus = _shot_data(_entry(damage=3))
    f2.fire_pass(_ctx())
    assert f2.shots()[0].damage == 3


def test_spawn_from_option_position() -> None:
    """entry.option>0 时从子机位置发射(子机位置由作品同步进 options)。"""
    f = _field(_entry(option=1), options=[Vec2(168, 400)])
    f.fire_pass(_ctx())
    assert f.shots()[0].pos == Vec2(168, 400)


def test_custom_fire_handler_dispatched() -> None:
    """注册的 fire_cb 走作品 handler; 未注册走默认。"""
    calls: list[int] = []

    def fire(field: ShotField, entry: ShotEntry, shot: PlayerShot, ctx) -> bool:
        calls.append(entry.fire_cb)
        return False  # 不发射

    f = _field(_entry(fire_cb=5), _entry(fire_cb=0))
    f.fire_handlers = {5: fire}
    f.fire_pass(_ctx())
    assert calls == [5]
    assert len(f.shots()) == 1  # 仅默认 cb 那条发射


# ======================================================================
# 弹道推进 (UpdateShots)
# ======================================================================
def test_step_moves_and_kills_out_of_bounds() -> None:
    f = _field(_entry())
    f.fire_pass(_ctx())
    b = f.shots()[0]
    y0 = b.pos.y
    f.step(_ctx())
    assert b.pos.y == y0 - 8.0
    while b.bullet_state != 0:
        f.step(_ctx())
    assert b.timer > 0  # 飞出版顶被消


def test_dead_player_detaches_persistent_slots() -> None:
    """玩家 DEAD: 持续弹槽全部脱钩消弹 (UpdateShots 首段)。"""
    f = ShotField(player_state=2)
    shot = PlayerShot(bullet_state=1)
    f.timers[0] = ShotTimer(timer=100, shot=shot)
    f.step(_ctx())
    assert f.timers[0].shot is None and shot.bullet_state == 0


def test_timer_slot_release_cap_when_not_firing() -> None:
    """未射击(fire_time<0)时槽计时压到 50 (PERSIST_RELEASE_CAP)。"""
    f = ShotField()
    shot = PlayerShot(bullet_state=1, bullet_state2=4)  # 激光型不出屏
    f.timers[1] = ShotTimer(timer=999, shot=shot)
    f.step(_ctx())
    assert f.timers[1].timer == 50
    # 归零当帧脱钩
    f.timers[1].timer = 1
    f.step(_ctx())
    assert f.timers[1].timer == 0 and f.timers[1].shot is None


def test_update_handler_can_kill_shot() -> None:
    def upd(field: ShotField, shot: PlayerShot, ctx) -> bool:
        return True  # 立即消弹

    f = _field(_entry())
    f.update_handlers = {0: upd}
    f.fire_pass(_ctx())
    assert len(f.shots()) == 1
    f.step(_ctx())
    assert not f.shots()


# ======================================================================
# 命中敌人 (CalcDamageToEnemy, §A.6)
# ======================================================================
def _enemy_box() -> tuple[Vec2, tuple[float, float]]:
    return Vec2(192, 100), (48.0, 48.0)


def test_hit_sums_damage_and_explodes_shot() -> None:
    f = ShotField(
        pool=[
            PlayerShot(pos=Vec2(192, 100), damage=10, bullet_state=1),
            PlayerShot(pos=Vec2(500, 100), damage=7, bullet_state=1),  # 脱靶
        ]
    )
    center, size = _enemy_box()
    assert f.calc_damage_to_enemy(center, size, _ctx()) == 10
    assert f.pool[0].bullet_state == 2  # 爆炸态
    assert f.pool[1].bullet_state == 1
    # 爆炸后的非穿透弹不再结算
    assert f.calc_damage_to_enemy(center, size, _ctx()) == 0


def test_penetrating_shot_keeps_judging_without_slowdown() -> None:
    """bullet_state2==3(穿透): 命中不减速, 爆炸后仍继续判定。"""
    b = PlayerShot(
        pos=Vec2(192, 100),
        damage=10,
        bullet_state=1,
        bullet_state2=3,
        velocity=Vec2(0, -8),
    )
    f = ShotField(pool=[b])
    center, size = _enemy_box()
    assert f.calc_damage_to_enemy(center, size, _ctx()) == 10
    assert b.velocity == Vec2(0, -8) and b.bullet_state == 2
    assert f.calc_damage_to_enemy(center, size, _ctx()) == 10  # 再中


def test_laser_type_deals_on_even_frames_only() -> None:
    """bullet_state2 4/5(激光型): 只 timer%2==0 出伤害, 不进爆炸态。"""
    b = PlayerShot(pos=Vec2(192, 100), damage=10, bullet_state=1, bullet_state2=4)
    f = ShotField(pool=[b])
    center, size = _enemy_box()
    assert f.calc_damage_to_enemy(center, size, _ctx()) == 10  # timer=0 偶
    assert b.bullet_state == 1  # 激光型不进爆炸态
    b.timer = 1
    assert f.calc_damage_to_enemy(center, size, _ctx()) == 0


def test_bomb_active_divides_damage_by_3() -> None:
    """Bomb 中伤害 max(damage//3, 1)。"""
    f = ShotField(
        pool=[PlayerShot(pos=Vec2(192, 100), damage=10, bullet_state=1)],
        bomb_active=True,
    )
    center, size = _enemy_box()
    assert f.calc_damage_to_enemy(center, size, _ctx()) == 3
    b2 = PlayerShot(pos=Vec2(192, 100), damage=2, bullet_state=1)
    f.pool.append(b2)
    assert f.calc_damage_to_enemy(center, size, _ctx()) == 1  # 最低 1


def test_hit_handler_skips_frame_damage() -> None:
    """Hit 回调返回 True → 跳过当帧伤害(如 missile 隔帧)。"""
    b = PlayerShot(pos=Vec2(192, 100), damage=10, bullet_state=1, hit_cb=2)
    f = ShotField(pool=[b], hit_handlers={2: lambda field, shot, ctx: True})
    center, size = _enemy_box()
    assert f.calc_damage_to_enemy(center, size, _ctx()) == 0
    assert b.bullet_state == 1  # 未进爆炸态


def test_trail_segments_deal_one_point() -> None:
    """trail_damage_cbs 命中的弹: pos_history 拖尾段各 1 点(无奇偶减半)。"""
    b = PlayerShot(
        pos=Vec2(500, 500),  # 本体脱靶
        damage=10,
        bullet_state=1,
        bullet_state2=4,
        update_cb=7,
        trail_length=3,
        hitbox=(6.0, 6.0),
    )
    b.pos_history[0] = Vec2(192, 100)  # 命中
    b.pos_history[1] = Vec2(500, 500)  # 脱靶
    b.pos_history[2] = Vec2(200, 100)  # 命中
    f = ShotField(pool=[b], trail_damage_cbs=frozenset({7}))
    center, size = _enemy_box()
    assert f.calc_damage_to_enemy(center, size, _ctx()) == 2
