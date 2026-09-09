"""弹场测试: aim 模式分布 / 命令接入 / exFlags 更新器 / 弹型表 / 事件流。

数值权威: th07/src/th07/BulletManager.cpp (SpawnSingleBullet / RunCommands /
UpdateBullet* / OnUpdate), 移植自 old/tests/test_bullets.py 按新接口改写。
"""

from __future__ import annotations

import math

from touhou.engine import (
    Aim,
    Bullet,
    BulletCollisionSystem,
    BulletCommand,
    BulletDespawned,
    BulletField,
    BulletGraze,
    BulletHit,
    BulletMovementSystem,
    BulletSpawned,
    BulletState,
    BulletTypeSpec,
    Burst,
    CmdFlag,
    DespawnCause,
    FrameContext,
    Pipeline,
    Rng,
    Slot,
    World,
    rank_lerp,
    rank_lerp_int,
    step_bullet,
    tick_frame,
)
from touhou.utils.math import Vec2, angle_to

P = Vec2(100, 100)  # 玩家占位

# 机制测试用的合成弹型表(数值形状仿 th07 表: 8/14/16/32px 档 + 出生态
# T 档 10/16/32/24; 作品真实表的对源断言在作品侧测试)
_TEST_SPECS: tuple[BulletTypeSpec, ...] = (
    BulletTypeSpec(0x200, 8.0, 8.0, Vec2(4, 4), 5, spawn_t=(10, 16, 32)),  # 0: 8px
    BulletTypeSpec(0x201, 16.0, 16.0, Vec2(6, 6), 3, spawn_t=(10, 16, 32)),  # 1: 16px
    BulletTypeSpec(0x202, 14.0, 16.0, Vec2(4, 4), 4, spawn_t=(10, 16, 32)),  # 2
    BulletTypeSpec(0x203, 16.0, 16.0, Vec2(6, 6), 3, spawn_t=(10, 16, 32)),  # 3
    BulletTypeSpec(0x204, 14.0, 16.0, Vec2(4, 4), 4, spawn_t=(10, 16, 32)),  # 4
    BulletTypeSpec(0x205, 14.0, 16.0, Vec2(4, 4), 4, spawn_t=(10, 16, 32)),  # 5
    BulletTypeSpec(0x206, 14.0, 16.0, Vec2(4, 4), 4, spawn_t=(10, 16, 32)),  # 6
    BulletTypeSpec(0x207, 32.0, 32.0, Vec2(10, 10), 2, spawn_t=(32, 32, 32)),  # 7
    BulletTypeSpec(0x208, 32.0, 32.0, Vec2(5, 5), 1, spawn_t=(32, 32, 32)),  # 8
    BulletTypeSpec(0x209, 32.0, 32.0, Vec2(8, 8), 2, spawn_t=(32, 32, 32)),  # 9
    BulletTypeSpec(0x2A8, 8.0, 8.0, Vec2(4, 4), 5, spawn_t=(24, 24, 24)),  # 10: T=24
)


def _ctx(seed: int = 0) -> FrameContext:
    return FrameContext(Rng(seed))


def _mk(
    angle: float = 0.0, speed: float = 3.0, pos: Vec2 = Vec2(100, 100)
) -> BulletState:
    return BulletState(pos=pos, angle=angle, speed=speed)


# ======================================================================
# aim 模式 (SpawnSingleBullet 的 switch; arm=x, ring=y)
# ======================================================================
def test_spread_odd_symmetric() -> None:
    b = Burst(Vec2(0, 0), 0.5, Aim.SPREAD_AIMED, 3, 1, 2.0, 2.0, 0.2)
    got = [b.angle_speed(x, 0, Rng(0))[0] for x in range(3)]
    # 奇数颗: 0, -step, +step ((x+1)//2, 奇下标取负)
    assert got == [0.5, 0.5 - 0.2, 0.5 + 0.2]


def test_spread_even_half_step() -> None:
    b = Burst(Vec2(0, 0), 0.0, Aim.SPREAD_ABSOLUTE, 4, 1, 2.0, 2.0, 0.2)
    got = [b.angle_speed(x, 0, Rng(0))[0] for x in range(4)]
    # 偶数颗: ±step/2, ±3step/2
    for want, g in zip((0.1, -0.1, 0.3, -0.3), got, strict=True):
        assert abs(g - want) < 1e-9


def test_ring_aimed_and_ring_rotation_per_layer() -> None:
    b = Burst(Vec2(0, 0), 1.0, Aim.RING_AIMED, 4, 2, 3.0, 1.0, 0.1)
    a0, s0 = b.angle_speed(0, 0, Rng(0))
    a1, _ = b.angle_speed(1, 0, Rng(0))
    a2, s1 = b.angle_speed(0, 1, Rng(0))
    assert abs(a0 - 1.0) < 1e-9
    assert abs(a1 - (1.0 + math.tau / 4)) < 1e-9
    # 第二层整体多转 ring*angle2, 速度按 ring/count2 向 speed_b 插值
    assert abs(a2 - (1.0 + 0.1)) < 1e-9
    assert s0 == 3.0 and abs(s1 - 2.0) < 1e-9


def test_ring_shift_adds_half_step_no_layer_term() -> None:
    b = Burst(Vec2(0, 0), 0.0, Aim.RING_SHIFT_ABSOLUTE, 4, 2, 2.0, 2.0, 0.3)
    a0, _ = b.angle_speed(0, 0, Rng(0))
    a1, _ = b.angle_speed(1, 0, Rng(0))
    a_ring1, _ = b.angle_speed(0, 1, Rng(0))
    assert abs(a0 - math.pi / 4) < 1e-9
    assert abs(a1 - (math.pi / 4 + math.tau / 4)) < 1e-9
    # 源码里 shifted 环没有 y*angle2 项
    assert abs(a_ring1 - a0) < 1e-9


def test_angle_random_in_range() -> None:
    rng = Rng(42)
    b = Burst(Vec2(0, 0), 1.0, Aim.ANGLE_RANDOM, 8, 1, 2.0, 2.0, 0.3)
    for x in range(8):
        a, s = b.angle_speed(x, 0, rng)
        assert 0.3 <= a < 1.0  # [angle2, angle1)
        assert s == 2.0


def test_ring_speed_random() -> None:
    rng = Rng(42)
    b = Burst(Vec2(0, 0), 0.0, Aim.RING_SPEED_RANDOM, 4, 1, 5.0, 1.0, 0.0)
    for x in range(4):
        a, s = b.angle_speed(x, 0, rng)
        assert abs(a - x * math.tau / 4) < 1e-9
        assert 1.0 <= s < 5.0


def test_random_angle_and_speed() -> None:
    rng = Rng(42)
    b = Burst(Vec2(0, 0), 2.0, Aim.RANDOM, 8, 1, 6.0, 2.0, -1.0)
    seen = set()
    for x in range(8):
        a, s = b.angle_speed(x, 0, rng)
        assert -1.0 <= a < 2.0
        assert 2.0 <= s < 6.0
        seen.add(a)
    assert len(seen) > 1  # 确实随机


# ======================================================================
# rank 插值 (EnemyManager.hpp BulletRank*Inner)
# ======================================================================
def test_rank_lerp_endpoints() -> None:
    assert rank_lerp(1.0, 3.0, 0) == 1.0
    assert rank_lerp(1.0, 3.0, 32) == 3.0
    assert rank_lerp_int(0, 5, 0) == 0
    assert rank_lerp_int(0, 5, 32) == 5


def test_rank_lerp_int_truncates_toward_zero() -> None:
    assert rank_lerp_int(1, 4, 16) == 2  # 16*3/32=1.5 → 1
    assert rank_lerp_int(5, 0, 16) == 3  # 16*(-5)/32=-2.5 → C++ 截断 -2 (非 floor -3)


# ======================================================================
# 命令系统接入: 执行顺序 + spawn 即跑一次 RunCommands
# ======================================================================
def test_field_step_runs_commands_before_movement() -> None:
    f = BulletField()
    cmd = BulletCommand(CmdFlag.TARGET_ANGLE, speed=-2.0, angle=0.0, duration=60)
    f.fire(
        Burst(
            Vec2(100, 100),
            0.0,
            Aim.SPREAD_ABSOLUTE,
            1,
            1,
            3.0,
            3.0,
            0.0,
            commands=(cmd,),
        ),
        _ctx(),
    )
    b = f.alive()[0]
    f.step(_ctx())
    # 命令先跑: 速度 3→1 后再位移 → x=101 (若先位移则是 103)
    assert b.speed == 1.0
    assert b.pos.x == 101.0


def test_spawn_runs_run_commands_immediately() -> None:
    f = BulletField()
    f.fire(
        Burst(
            P,
            0.0,
            Aim.SPREAD_ABSOLUTE,
            1,
            1,
            3.0,
            3.0,
            0.0,
            commands=(BulletCommand(CmdFlag.BURST),),
        ),
        _ctx(),
    )
    b = f.alive()[0]
    assert b.ex_flags & CmdFlag.BURST  # SpawnSingleBullet 末尾的 RunCommands
    f.step(_ctx())
    # 爆发首帧 k=5: vel = (5+3) 向右, pos.x += 8
    assert b.pos.x == 108.0


def test_spawn_delay_survives_offscreen_until_delay_ends() -> None:
    f = BulletField()
    cmd = BulletCommand(CmdFlag.SPAWN_DELAY, duration=30)
    f.fire(
        Burst(
            Vec2(-50, 100),
            0.0,
            Aim.SPREAD_ABSOLUTE,
            1,
            1,
            1.0,
            1.0,
            0.0,
            commands=(cmd,),
        ),
        _ctx(),
    )
    for _ in range(29):
        f.step(_ctx())
    assert len(f) == 1  # 延迟期间出界不销毁(仍在移动)
    f.step(_ctx())
    assert len(f) == 0  # 延迟耗尽, 出界销毁


def test_fire_sets_more_flags_and_type_size() -> None:
    f = BulletField(type_specs=_TEST_SPECS)
    f.fire(
        Burst(P, 0.0, Aim.RING_ABSOLUTE, 2, 1, 2.0, 2.0, 0.0, sprite=8, flags=0x200),
        _ctx(),
    )
    b = f.alive()[0]
    assert b.more_flags == 0x200
    assert b.size == Vec2(32.0, 32.0)  # 弹型 8 = 32px 刀弹


# ======================================================================
# exFlags 更新器(逐一对应 UpdateBullet*)
# ======================================================================
def test_dir_change_relative_slows_then_turns() -> None:
    b = _mk(angle=0.0, speed=3.0)
    # ZUN quirk: cmd.speed 进状态槽 angle(转向量), cmd.angle 进 speed(新速度)
    b.add_command(
        BulletCommand(CmdFlag.DIR_CHANGE, speed=1.0, angle=2.0, duration=10, loop=1)
    )
    for _ in range(5):
        step_bullet(b, P)
    # 刹停中: cur = 3 - 4*3/10 = 1.8
    assert abs(b.vel.length - 1.8) < 1e-9
    for _ in range(6):
        step_bullet(b, P)
    assert abs(b.angle - 1.0) < 1e-9  # 相对转向 += 1.0
    assert b.speed == 2.0  # 恢复目标速度
    assert not (b.ex_flags & CmdFlag.DIR_CHANGE)  # loop=1 跑完清位


def test_dir_change_absolute_sets_angle() -> None:
    b = _mk(angle=0.5, speed=3.0)
    b.add_command(
        BulletCommand(CmdFlag.DIR_CHANGE_ABS, speed=1.0, angle=2.0, duration=10, loop=1)
    )
    for _ in range(11):
        step_bullet(b, P)
    assert abs(b.angle - 1.0) < 1e-9  # 绝对角 = st.angle(=cmd.speed), 不是 0.5+1.0
    assert b.speed == 2.0


def test_dir_change_aim_at_player() -> None:
    b = _mk(angle=0.0, speed=3.0, pos=Vec2(100, 100))
    b.add_command(
        BulletCommand(
            CmdFlag.DIR_CHANGE_AIM, speed=0.25, angle=2.0, duration=10, loop=1
        )
    )
    player = Vec2(100, 200)  # 正下方
    for _ in range(10):
        step_bullet(b, player)
    # 转向角在回速瞬间按当时位置算 AngleToPlayer
    want = angle_to(b.pos, player) + 0.25
    step_bullet(b, player)
    assert abs(b.angle - want) < 1e-9


def test_dir_change_loops_before_clearing() -> None:
    b = _mk(angle=0.0, speed=3.0)
    b.add_command(
        BulletCommand(CmdFlag.DIR_CHANGE, speed=0.5, angle=2.0, duration=10, loop=2)
    )
    for _ in range(11):
        step_bullet(b, P)
    assert b.ex_flags & CmdFlag.DIR_CHANGE  # 第一次转向后仍在(loop=2)
    for _ in range(10):
        step_bullet(b, P)
    assert not (b.ex_flags & CmdFlag.DIR_CHANGE)
    assert abs(b.angle - 1.0) < 1e-9  # 转了两次 0.5


def test_bounce_left_wall_and_count_exhaustion() -> None:
    b = _mk(angle=math.pi, speed=2.0, pos=Vec2(-9, 100))  # 已出左界(16px 弹)
    b.add_command(BulletCommand(CmdFlag.BOUNCE, speed=-1.0, duration=1))
    step_bullet(b, P)
    # 左右反弹: angle = -angle - pi → 0; 速度取回弹速度(负→沿用当前)
    assert abs(b.angle) < 1e-9 and b.vel.x > 0
    assert b.speed == 2.0
    assert not (b.ex_flags & (CmdFlag.BOUNCE | CmdFlag.BOUNCE_NO_FLOOR))  # 1 次用尽


def test_bounce_floor_only_with_floor_flag() -> None:
    # BOUNCE(0x400): 底边也弹
    b = _mk(angle=math.pi / 2, speed=2.0, pos=Vec2(200, 457))
    b.add_command(BulletCommand(CmdFlag.BOUNCE, speed=-1.0, duration=3))
    step_bullet(b, P)
    assert abs(b.angle - (-math.pi / 2)) < 1e-9  # 向下 → 向上
    assert b.ex_flags & CmdFlag.BOUNCE  # 次数未尽, 位保留
    # BOUNCE_NO_FLOOR(0x800): 底边不弹
    b2 = _mk(angle=math.pi / 2, speed=2.0, pos=Vec2(200, 457))
    b2.add_command(BulletCommand(CmdFlag.BOUNCE_NO_FLOOR, speed=-1.0, duration=3))
    step_bullet(b2, P)
    assert abs(b2.angle - math.pi / 2) < 1e-9  # 角度不变(仍向下)
    assert b2.speed == 2.0  # 但回弹速度已重置


def test_offscreen_grace_128_frames_for_commanded_bullets() -> None:
    f = BulletField()
    # 普通弹出界立即销毁
    f.fire(
        Burst(Vec2(-50, 100), math.pi, Aim.SPREAD_ABSOLUTE, 1, 1, 2.0, 2.0, 0.0), _ctx()
    )
    f.step(_ctx())
    assert len(f) == 0
    # 带转向命令的弹出界宽限 128 帧
    cmd = BulletCommand(CmdFlag.DIR_CHANGE, speed=0.1, angle=1.0, duration=500)
    f.fire(
        Burst(
            Vec2(-50, 100),
            math.pi,
            Aim.SPREAD_ABSOLUTE,
            1,
            1,
            2.0,
            2.0,
            0.0,
            commands=(cmd,),
        ),
        _ctx(),
    )
    for _ in range(127):
        f.step(_ctx())
    assert len(f) == 1
    f.step(_ctx())
    assert len(f) == 0


# ======================================================================
# 出生态 (BulletManager.cpp:255-283 出生 / :1022-1047 每帧)
# 帧数 = etama spawn 特效脚本时长 T+1; 合成表 T 档: 弹型 0-6 → 10/16/32,
# 弹型 7-9 → 32, 弹型 10 → 24
# ======================================================================


def _spawn_one(
    flag: int,
    *,
    sprite: int = 1,
    speed: float = 2.0,
    angle: float = math.pi / 2,
    pos: Vec2 = Vec2(192, 100),
    commands: tuple[BulletCommand, ...] = (),
) -> tuple[BulletField, Bullet]:
    f = BulletField(type_specs=_TEST_SPECS)
    f.fire(
        Burst(
            pos,
            angle,
            Aim.RING_ABSOLUTE,
            1,
            1,
            speed,
            speed,
            0.0,
            sprite=sprite,
            flags=flag,
            commands=commands,
        ),
        _ctx(),
    )
    return f, f.alive()[0]


def test_spawn_fast_pos_rollback_and_speed_curve() -> None:
    """flags=2 (SPAWNING_FAST): 出生回退 + 减速曲线 + 转变帧序。"""
    # 出生 pos -= vel*4; 10 帧 vel/2; 第 11 帧转 NORMAL 并当帧落入正常分支(+vel/2+vel)
    f, b = _spawn_one(2)
    assert b.spawn_state == 2
    assert b.pos.distance(Vec2(192, 92)) < 1e-9  # 100 - 2*4
    for _ in range(10):
        f.step(_ctx())
    assert b.spawn_state == 2 and b.pos.distance(Vec2(192, 102)) < 1e-9
    f.step(_ctx())  # 转变帧: +2/2 后转 NORMAL, 再 +2
    assert b.spawn_state == 0
    assert b.pos.distance(Vec2(192, 105)) < 1e-9
    assert b.age == 1  # timer1 从转变帧起计(出生态 timer2 冻结, C++ --/++ 抵消)


def test_spawn_normal_and_slow_divisors() -> None:
    """flags=4 → vel/2.5 共 16 帧, 第 17 帧转变; flags=8 → vel/3 共 32 帧, 33 帧转变。"""
    f4, b4 = _spawn_one(4)
    for _ in range(16):
        f4.step(_ctx())
    assert b4.spawn_state == 4 and abs(b4.pos.y - (92 + 16 * 0.8)) < 1e-9
    f4.step(_ctx())
    assert b4.spawn_state == 0 and abs(b4.pos.y - (92 + 17 * 0.8 + 2)) < 1e-9
    f8, b8 = _spawn_one(8)
    for _ in range(32):
        f8.step(_ctx())
    assert b8.spawn_state == 8 and abs(b8.pos.y - (92 + 32 * (2 / 3))) < 1e-6
    f8.step(_ctx())
    assert b8.spawn_state == 0 and abs(b8.pos.y - (92 + 33 * (2 / 3) + 2)) < 1e-6


def test_spawn_big_bullets_share_t32() -> None:
    """弹型 7-9 三态共用 t=32 脚本: flags=2 也是 33 帧转变。"""
    f, b = _spawn_one(2, sprite=7)
    for _ in range(32):
        f.step(_ctx())
    assert b.spawn_state == 2
    f.step(_ctx())
    assert b.spawn_state == 0


def test_spawn_light_bullet_t24() -> None:
    """弹型 10 (光弹) 三态共用 t=24 脚本: 25 帧转变。"""
    f, b = _spawn_one(2, sprite=10)
    for _ in range(24):
        f.step(_ctx())
    assert b.spawn_state == 2
    f.step(_ctx())
    assert b.spawn_state == 0


def test_spawn_state_runs_no_command_updaters() -> None:
    """出生态不跑 exFlags 更新器: BURST 附加速度在出生态冻结, 转变帧才开始。"""
    cmd = BulletCommand(CmdFlag.BURST)
    f, b = _spawn_one(2, commands=(cmd,))
    # SpawnSingleBullet 末尾的 RunCommands 已激活 BURST, 但出生态不跑更新器
    assert b.ex_flags & CmdFlag.BURST
    v0 = b.vel
    f.step(_ctx())
    assert b.vel == v0  # 冻结
    for _ in range(10):
        f.step(_ctx())  # 到转变帧
    assert b.spawn_state == 0
    # 转变帧起 BURST 更新器跑: vel = angle 方向 (5+speed)*1
    assert b.vel != v0


def test_spawn_state_no_offscreen_despawn_no_hit() -> None:
    """出生态不做出界判定, 也不参与命中/擦弹。"""
    # 向上高速: 普通弹早已出界消弹, 出生态弹(弹型 7, T=32)仍在场
    f, b = _spawn_one(2, sprite=7, speed=20.0, angle=-math.pi / 2)
    f2, b2 = _spawn_one(0, sprite=7, speed=20.0, angle=-math.pi / 2)
    for _ in range(19):  # 19 帧后 y=180-10*19=-10 < -8 → 普通弹出界
        f.step(_ctx())
        f2.step(_ctx())
    assert b2.dead
    assert not b.dead and b.spawn_state == 2
    # 命中: 出生态弹即使罩住玩家也不算
    f3, b3 = _spawn_one(2, pos=Vec2(100, 100), speed=0.0)
    f3.player_pos = Vec2(100, 100)
    ctx = _ctx()
    got: list = []
    ctx.events.subscribe(got.append)
    f3.check_player(ctx)
    ctx.events.flush()
    assert not [e for e in got if isinstance(e, BulletHit)]
    for _ in range(11):
        f3.step(ctx)
    f3.check_player(ctx)
    ctx.events.flush()
    assert [e for e in got if isinstance(e, BulletHit)]


# ======================================================================
# 判定半径物化 (fire 时把 BulletField.bullet_radius 写到 Bullet.hitbox)
# ======================================================================
def test_bullet_hitbox_materialized_from_field() -> None:
    f = BulletField()
    f.fire(Burst(P, 0.0, Aim.RING_ABSOLUTE, 4, 1, 2.0, 2.0, 0.1, sprite=0), _ctx())
    assert [b.hitbox for b in f.alive()] == [f.bullet_radius] * 4
    # 世界半宽改动后, 新生成的弹携带新值; 已生成的保持生成时的值
    f.bullet_radius = 5.0
    f.fire(Burst(P, 0.0, Aim.RING_ABSOLUTE, 2, 1, 2.0, 2.0, 0.1, sprite=7), _ctx())
    assert sorted({b.hitbox for b in f.alive()}) == [3.5, 5.0]


def test_bullet_default_hitbox() -> None:
    # 直接构造(不经 fire)给与世界字段默认一致的 3.5
    assert Bullet(pos=Vec2(0, 0), angle=0.0, speed=1.0).hitbox == 3.5


# ======================================================================
# screenClearTime (BulletManager.cpp:289-292 / :480 / :1205-1207)
# ======================================================================
def test_screen_clear_time_suppresses_new_bullets() -> None:
    f = BulletField()
    f.screen_clear_time = 10
    n = f.fire(Burst(P, 0.0, Aim.RING_ABSOLUTE, 8, 1, 2.0, 2.0, 0.0), _ctx())
    assert n == 0 and len(f) == 0
    # 带 0x1000 moreFlag 的弹不受窗口压制
    n = f.fire(
        Burst(P, 0.0, Aim.RING_ABSOLUTE, 8, 1, 2.0, 2.0, 0.0, flags=0x1000), _ctx()
    )
    assert n == 8 and len(f) == 8
    # 窗口每帧递减, 10 帧后恢复正常生成
    for _ in range(10):
        f.step(_ctx())
    assert f.screen_clear_time == 0
    n = f.fire(Burst(P, 0.0, Aim.RING_ABSOLUTE, 4, 1, 2.0, 2.0, 0.0), _ctx())
    assert n == 4


def test_screen_clear_time_rng_still_consumed() -> None:
    """窗口内被压制的弹仍按原样消耗 RNG(C 是出生后置 DESPAWN, 随机数已抽)。"""
    f = BulletField()
    f.screen_clear_time = 10
    ctx = _ctx()
    g0 = ctx.rng.gen
    f.fire(Burst(P, 1.0, Aim.ANGLE_RANDOM, 4, 1, 2.0, 2.0, 0.5), ctx)
    used = ctx.rng.gen - g0
    f2 = BulletField()
    ctx2 = _ctx()
    g1 = ctx2.rng.gen
    f2.fire(Burst(P, 1.0, Aim.ANGLE_RANDOM, 4, 1, 2.0, 2.0, 0.5), ctx2)
    assert used == ctx2.rng.gen - g1 == 4 * 2  # unit()=u32=2×u16, 每颗一抽


# ======================================================================
# 出界宽限衰减 (BulletManager.cpp:957-975)
# ======================================================================
def test_offscreen_grace_residual_countdown() -> None:
    cmd = BulletCommand(
        CmdFlag.DIR_CHANGE, speed=0.0, angle=-1000.0, duration=8, loop=1
    )
    f = BulletField(type_specs=_TEST_SPECS)
    f.fire(
        Burst(
            Vec2(192, 20),
            -math.pi / 2,
            Aim.RING_ABSOLUTE,
            1,
            1,
            8.0,
            8.0,
            0.0,
            sprite=0,
            commands=(cmd,),
        ),
        _ctx(),
    )
    b = f.alive()[0]
    for _ in range(9):
        f.step(_ctx())  # 第 9 帧: 转向命令在屏外跑完, ex_flags 清零(残余 oob=5)
    assert not (b.ex_flags & CmdFlag.DIR_CHANGE)
    assert b.out_of_bounds_time == 4  # 清零帧: 5 -> 4
    assert not b.dead and len(f) == 1
    # 残余 outOfBoundsTime 逐帧递减: 再活 4 帧, 归零后的下一帧才销毁
    for _ in range(4):
        f.step(_ctx())
    assert len(f) == 1 and b.out_of_bounds_time == 0
    f.step(_ctx())
    assert len(f) == 0


# ======================================================================
# TARGET_VEL 激活时烘入 effectiveFramerateMultiplier
# (BulletManager.cpp:347-349 激活烘 mult; :703-704 每帧再乘当前 mult)
# ======================================================================
def test_target_vel_bakes_time_scale_at_activation() -> None:
    cmd = BulletCommand(CmdFlag.TARGET_VEL, speed=2.0, angle=0.0, duration=10)
    f = BulletField()
    f.time_scale = 0.25  # 减速中
    f.fire(
        Burst(P, math.pi / 2, Aim.RING_ABSOLUTE, 1, 1, 1.0, 1.0, 0.0, commands=(cmd,)),
        _ctx(),
    )
    b = f.alive()[0]
    # 出生 vel = 1.0*0.25 向下; 激活时 vec3 = 2.0*0.25 = 0.5 向 +x
    assert b.vel.distance(Vec2(0.0, 0.25)) < 1e-9
    f.step(_ctx())  # 更新器: vel += vec3 * 0.25 → +x 0.125 (双重缩放, 照抄 C)
    assert abs(b.vel.x - 0.125) < 1e-9
    assert abs(b.vel.y - 0.25) < 1e-9


# ======================================================================
# 事件流 + 槽位落位
# ======================================================================
def test_fire_and_despawn_emit_events() -> None:
    """Fire 产 BulletSpawned; 出界消弹产 BulletDespawned(cause=OFFSCREEN)。"""
    f = BulletField()
    ctx = _ctx()
    got: list = []
    ctx.events.subscribe(got.append)
    f.fire(
        Burst(Vec2(-50, 100), math.pi, Aim.SPREAD_ABSOLUTE, 2, 1, 2.0, 2.0, 0.0), ctx
    )
    ctx.events.flush()
    spawned = [e for e in got if isinstance(e, BulletSpawned)]
    assert len(spawned) == 2
    assert spawned[0].x == -50.0 and spawned[0].sprite == 0
    f.step(ctx)
    ctx.events.flush()
    despawned = [e for e in got if isinstance(e, BulletDespawned)]
    assert len(despawned) == 2
    assert all(e.cause is DespawnCause.OFFSCREEN for e in despawned)


def test_clear_emits_cleared_cause() -> None:
    """clear(events=...) 逐弹产 BulletDespawned(cause=CLEARED)。"""
    f = BulletField()
    ctx = _ctx()
    f.fire(Burst(P, 0.0, Aim.RING_ABSOLUTE, 4, 1, 2.0, 2.0, 0.1), ctx)
    got: list = []
    ctx.events.subscribe(got.append)
    f.clear(ctx.events)
    ctx.events.flush()
    assert len(f) == 0
    despawned = [e for e in got if isinstance(e, BulletDespawned)]
    assert len(despawned) == 4
    assert all(e.cause is DespawnCause.CLEARED for e in despawned)


def test_graze_event_once_per_bullet() -> None:
    """擦弹盒(弹盒外扩 20px + 擦弹半径)相交产 BulletGraze, 每颗弹只擦一次。"""
    f = BulletField()  # bullet_radius=3.5, graze_radius=24 → 半宽 47.5
    ctx = _ctx()
    got: list = []
    ctx.events.subscribe(got.append)
    f.fire(Burst(P, 0.0, Aim.RING_ABSOLUTE, 1, 1, 0.0, 0.0, 0.0), ctx)
    f.player_pos = Vec2(140, 100)  # dx=40: 命中盒(5.5)外, 擦弹盒(47.5)内
    f.check_player(ctx)
    f.check_player(ctx)  # 第二帧同位置不再擦
    ctx.events.flush()
    graze = [e for e in got if isinstance(e, BulletGraze)]
    assert len(graze) == 1
    assert not [e for e in got if isinstance(e, BulletHit)]


def test_hit_event_and_gates() -> None:
    """命中盒(弹半径+判定半径)相交产 BulletHit(每帧一条); 门控位关掉则不判。"""
    f = BulletField()
    ctx = _ctx()
    got: list = []
    ctx.events.subscribe(got.append)
    f.fire(Burst(P, 0.0, Aim.RING_ABSOLUTE, 2, 1, 0.0, 0.0, 0.1), ctx)
    f.player_pos = P
    f.hit_enabled = False  # 旧: 炸弹中/非 ALIVE 不命中
    f.graze_enabled = False  # 旧: 玩家 DEAD/SPAWNING 不擦
    f.check_player(ctx)
    f.hit_enabled = True
    f.check_player(ctx)
    ctx.events.flush()
    hits = [e for e in got if isinstance(e, BulletHit)]
    assert len(hits) == 1  # 门控挡一帧; 命中每帧最多一条
    assert not [e for e in got if isinstance(e, BulletGraze)]


def test_pipeline_slots_movement_then_collision() -> None:
    """管线落位: MOVEMENT 槽推进, COLLISION 槽判定, 事件帧末 flush。"""
    f = BulletField()
    world = World()
    pipe: Pipeline[World] = Pipeline()
    pipe.add(Slot.MOVEMENT, BulletMovementSystem(f))
    pipe.add(Slot.COLLISION, BulletCollisionSystem(f))
    ctx = _ctx()
    got: list = []
    ctx.events.subscribe(got.append)
    f.fire(
        Burst(Vec2(100, 100), math.pi / 2, Aim.SPREAD_ABSOLUTE, 1, 1, 4.0, 4.0, 0.0),
        ctx,
    )
    f.player_pos = Vec2(100, 200)
    tick_frame(world, pipe, ctx)
    b = f.alive()[0]
    assert b.pos.y == 104.0  # movement 槽位移一帧
    # 擦弹盒半宽 47.5: 位移后 dy=96 不擦
    assert not [e for e in got if isinstance(e, (BulletGraze, BulletHit))]
    for _ in range(24):
        tick_frame(world, pipe, ctx)  # y=200 时贴脸
    assert [e for e in got if isinstance(e, BulletHit)]


def test_ring_spread_helpers_aim_at_player() -> None:
    """ring/spread 便捷发射: aimed 时基准角 = angle_to(发射点, 玩家)。"""
    f = BulletField()
    f.player_pos = Vec2(192, 400)
    n = f.ring(Vec2(192, 100), 8, 2.0, _ctx())
    assert n == 8 and len(f) == 8
    b = f.alive()[0]
    assert abs(b.angle - math.pi / 2) < 1e-9  # 正下方
    n = f.spread(Vec2(192, 100), 3, 3.0, 0.2, _ctx())
    assert n == 3
