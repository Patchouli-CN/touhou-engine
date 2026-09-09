"""th07 弹型表测试 —— 表数值对源断言(g_BulletTypeInfos + AddedCallback 判定树 +
etama.anm 出生特效脚本时长, 出处注释见 games/th07/data.py 表头)。"""

from __future__ import annotations

from touhou.games.th07.data import (
    BULLET_TYPE_SPECS,
    bullet_active_sprite_idx,
    bullet_sprite_height,
    bullet_type_size,
)
from touhou.utils import Vec2


def test_bullet_type_specs_table() -> None:
    assert len(BULLET_TYPE_SPECS) == 16
    s0 = BULLET_TYPE_SPECS[0]
    assert (s0.anm_file_idx, s0.height, s0.graze_size, s0.collision_type) == (
        0x200,
        8.0,
        Vec2(4, 4),
        5,
    )
    s1 = BULLET_TYPE_SPECS[1]
    assert (s1.graze_size, s1.collision_type) == (Vec2(6, 6), 3)  # 16px 默认档
    s2 = BULLET_TYPE_SPECS[2]
    assert (s2.graze_size, s2.collision_type) == (Vec2(4, 4), 4)  # anm 514 特判
    s7 = BULLET_TYPE_SPECS[7]
    assert (s7.graze_size, s7.collision_type) == (Vec2(10, 10), 2)  # 32px 默认档
    s8 = BULLET_TYPE_SPECS[8]
    assert (s8.graze_size, s8.collision_type) == (Vec2(5, 5), 1)  # anm 520 特判
    s9 = BULLET_TYPE_SPECS[9]
    assert (s9.graze_size, s9.collision_type) == (Vec2(8, 8), 2)  # anm 521 特判
    s10 = BULLET_TYPE_SPECS[10]
    assert (s10.anm_file_idx, s10.height, s10.collision_type) == (0x2A8, 8.0, 5)
    assert BULLET_TYPE_SPECS[11].anm_file_idx == 0  # 11..15 未初始化


def test_bullet_type_specs_spawn_t() -> None:
    """出生特效脚本时长 T(脚本 0x212-0x218/0x2aa): 转变帧 = T+1。"""
    assert BULLET_TYPE_SPECS[0].spawn_t == (10, 16, 32)  # 0x212/0x213/0x214
    for i in range(1, 7):
        assert BULLET_TYPE_SPECS[i].spawn_t == (10, 16, 32)  # 0x215/0x216/0x217
    for i in range(7, 10):
        assert BULLET_TYPE_SPECS[i].spawn_t == (32, 32, 32)  # 0x218 三态共用
    assert BULLET_TYPE_SPECS[10].spawn_t == (24, 24, 24)  # 0x2aa 三态共用
    assert BULLET_TYPE_SPECS[11].spawn_t == (0, 0, 0)  # 未初始化槽无出生态


def test_bullet_type_size_fallback() -> None:
    assert bullet_type_size(8) == Vec2(32.0, 32.0)
    assert bullet_type_size(0) == Vec2(8.0, 8.0)
    assert bullet_type_size(99) == Vec2(16, 16)  # 未知弹型默认 16px


def test_bullet_sprite_helpers() -> None:
    assert bullet_active_sprite_idx(0, 0) == 512
    assert bullet_active_sprite_idx(8, 4) == 636  # 蝶弹
    assert bullet_active_sprite_idx(99, 0) == -1
    # 模板 10 (脚本 0x2a8): offset 0..3 = 64px 大玉, 4+ = 16px
    assert bullet_sprite_height(10, 0) == 64.0
    assert bullet_sprite_height(10, 4) == 16.0
    assert bullet_sprite_height(7, 0) == 32.0
