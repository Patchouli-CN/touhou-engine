"""th08 弹型表测试 —— 表数值抽样对 th08-ref/etama.anm 源 + 注入点 + 逐弹碰撞盒。

表数值出处见 games/th08/data.py 弹型表头注释(g_BulletSpriteScripts
BulletManager.cpp:299-322 / AddedCallback 判定树 :1624-1701 / 本机 th08.dat
etama.anm 实测脚本时长)。world 接线用例打 @needs_data(真实 th08.dat)。
"""

from __future__ import annotations

import math

from touhou.engine.bullets import Aim, Bullet, BulletWorld, Burst
from touhou.games.th08.data import BULLET_TYPE_SPECS
from touhou.games.th08.world import ImperishableNight, _bullet_box
from touhou.utils import Vec2

from .conftest import needs_data

P = Vec2(192, 100)


def _fire_one(
    w: BulletWorld, sprite: int, flags: int = 0, speed: float = 2.0
) -> Bullet:
    w.fire(
        Burst(
            P,
            math.pi / 2,
            Aim.RING_ABSOLUTE,
            1,
            1,
            speed,
            speed,
            0.0,
            sprite=sprite,
            flags=flags,
        )
    )
    return w.alive()[-1]


# ---- 表数值抽样(对 th08-ref 源) ----
def test_table_shape_21_slots() -> None:
    assert len(BULLET_TYPE_SPECS) == 21
    # 活动脚本号 = g_BulletSpriteScripts[i].scripts[0] (BulletManager.cpp:299-322)
    assert [s.anm_file_idx for s in BULLET_TYPE_SPECS] == [
        0,
        1,
        2,
        3,
        4,
        5,
        6,
        7,
        8,
        9,
        25,
        106,
        107,
        108,
        109,
        110,
        111,
        112,
        113,
        114,
        115,
    ]


def test_table_spot_values() -> None:
    s0 = BULLET_TYPE_SPECS[0]  # 8px → (4,4,bucket5), spawn 脚本 18/19/20
    assert (s0.width, s0.height) == (8.0, 8.0)
    assert (s0.graze_size, s0.collision_type, s0.spawn_t) == (
        Vec2(4, 4),
        5,
        (10, 15, 30),
    )
    s1 = BULLET_TYPE_SPECS[1]  # 16px 默认档 → (6,6,bucket3)
    assert (s1.graze_size, s1.collision_type) == (Vec2(6, 6), 3)
    s5 = BULLET_TYPE_SPECS[5]  # 判定树 case 5 无 break 落 106 → bucket4
    assert (s5.graze_size, s5.collision_type) == (Vec2(4, 4), 4)
    s7 = BULLET_TYPE_SPECS[7]  # 32px 默认档 → (10,10,bucket1), 脚本 24 三态共用
    assert (s7.graze_size, s7.collision_type, s7.spawn_t) == (
        Vec2(10, 10),
        1,
        (30, 30, 30),
    )
    s10 = BULLET_TYPE_SPECS[10]  # 64px 大玉 → (24,24,bucket0), 脚本 27 → T=24
    assert (s10.height, s10.graze_size, s10.collision_type, s10.spawn_t) == (
        64.0,
        Vec2(24, 24),
        0,
        (24, 24, 24),
    )
    s14 = BULLET_TYPE_SPECS[14]  # 脚本 109: 实测 32x31 → (8,8,bucket1)
    assert (s14.width, s14.height) == (32.0, 31.0)
    assert (s14.graze_size, s14.collision_type) == (Vec2(8, 8), 1)
    s20 = BULLET_TYPE_SPECS[20]  # 脚本 115 → (5,5,bucket2)
    assert (s20.graze_size, s20.collision_type) == (Vec2(5, 5), 2)


# ---- 注入点 ----
def test_engine_default_without_injection() -> None:
    """空表注入: 全弹型 16px 默认尺寸 + 无出生态(引擎不持有任何作品的表)。"""
    w = BulletWorld()
    b = _fire_one(w, sprite=8, flags=2)
    assert b.size == Vec2(16, 16)
    assert b.spawn_state == 0


def test_th08_table_injected_sizes() -> None:
    w = BulletWorld(type_specs=BULLET_TYPE_SPECS)
    assert _fire_one(w, 0).size == Vec2(8.0, 8.0)
    assert _fire_one(w, 10).size == Vec2(64.0, 64.0)
    assert _fire_one(w, 11).size == Vec2(16.0, 16.0)  # 弹型 11-20 不再掉默认
    assert _fire_one(w, 20).size == Vec2(32.0, 32.0)
    assert _fire_one(w, 99).size == Vec2(16, 16)  # 表外仍回落 16px


def test_th08_spawn_state_restored_for_types_11_to_20() -> None:
    """弹型 11-20 出生态不再丢失: flags=2 → SPAWNING_FAST, 帧数 = T+1。"""
    w = BulletWorld(type_specs=BULLET_TYPE_SPECS)
    b = _fire_one(w, 15, flags=2)  # 脚本 24 → T=30 → 31 帧转变
    assert b.spawn_state == 2
    assert b.pos.distance(Vec2(192, 92)) < 1e-9  # 出生 pos -= vel*4
    for _ in range(30):
        w.step()
    assert b.spawn_state == 2
    w.step()
    assert b.spawn_state == 0


def test_th08_spawn_fast_normal_slow_frames() -> None:
    """弹型 1 (脚本 21/22/23 → T=10/15/30): 11/16/31 帧转变。"""
    for flag, frames in ((2, 11), (4, 16), (8, 31)):
        w = BulletWorld(type_specs=BULLET_TYPE_SPECS)
        b = _fire_one(w, 1, flags=flag)
        assert b.spawn_state == flag
        for _ in range(frames - 1):
            w.step()
        assert b.spawn_state == flag
        w.step()
        assert b.spawn_state == 0


# ---- 逐弹碰撞盒(world 判定管线消费) ----
def test_bullet_box_per_type() -> None:
    w = BulletWorld(type_specs=BULLET_TYPE_SPECS)
    assert _bullet_box(_fire_one(w, 0), w) == (4.0, 4.0)
    assert _bullet_box(_fire_one(w, 10), w) == (24.0, 24.0)
    assert _bullet_box(_fire_one(w, 9), w) == (8.0, 8.0)
    # 未知弹型回落世界均匀半径 ×2
    assert _bullet_box(_fire_one(w, 99), w) == (7.0, 7.0)


# ---- world 接线(真实数据) ----
@needs_data
def test_world_bullets_use_th08_table() -> None:
    g = ImperishableNight(character=0, difficulty=1)
    assert g.bullets.type_specs is BULLET_TYPE_SPECS
