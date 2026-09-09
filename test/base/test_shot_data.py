"""sht 解析的合成字节流测试(不依赖真实游戏数据)。"""

from __future__ import annotations

import struct

import pytest

from touhou.exceptions import ParseError
from touhou.schemas.shot_data import parse_sht


def _entry(
    fi: int,
    fo: int = 0,
    *,
    size: int = 52,
    damage: int = 10,
    option: int = 0,
    bs2: int = 0,
    gauge: int = 0,
    anm: int = 0,
    snd: int = -1,
    cbs: tuple[int, int, int, int] = (0, 0, 0, 0),
) -> bytes:
    out = bytearray()
    out += struct.pack("<hh", fi, fo)
    out += struct.pack("<6f", 1.0, 2.0, 3.0, 4.0, 0.5, 6.0)
    out += struct.pack("<h", damage)
    if size == 56:
        out += struct.pack("<5h", gauge, option, bs2, anm, snd)
    else:
        out += struct.pack("<BB", option, bs2)
        out += struct.pack("<hh", anm, snd)
    out += struct.pack("<4i", *cbs)
    assert len(out) == size
    return bytes(out)


def _build_base(levels: list[tuple[int, list[bytes]]]) -> bytes:
    """基础布局: 52 字节头 + 档表 + 各档条目链。"""
    header = struct.pack("<hH", len(levels), len(levels))
    header += struct.pack("<f", 3.0)  # initialBombs
    header += struct.pack("<i", 12)  # initialRespawnTimer
    header += struct.pack("<10f", 1.0, 2.0, 3.0, 4.0, 0.75, 384.0, 4.0, 2.0, 3.0, 1.5)
    table = bytearray()
    body = bytearray()
    p = 52 + 8 * len(levels)
    for req, entries in levels:
        table += struct.pack("<Ii", p, req)
        for e in entries:
            body += e
            p += len(e)
    return header + bytes(table) + bytes(body)


def _build_ext(levels: list[tuple[int, list[bytes]]]) -> bytes:
    """扩展布局: 0x38 字节头 + 档表 + 56 字节条目链。"""
    header = struct.pack("<HH", 0, len(levels))
    header += struct.pack("<f", 3.0)
    header += struct.pack("<i", 10)
    header += struct.pack("<5f", 1.0, 48.0, 6.0, 32.0, 224.0)
    header += struct.pack("<I", 0)
    header += struct.pack("<5f", 4.5, 2.0, 3.25, 1.75, 5.0)
    assert len(header) == 0x38
    table = bytearray()
    body = bytearray()
    p = 0x38 + 8 * len(levels)
    for req, entries in levels:
        table += struct.pack("<Ii", p, req)
        for e in entries:
            body += e
            p += len(e)
    return header + bytes(table) + bytes(body)


def test_parse_base_layout() -> None:
    entries = [
        _entry(4, 0, damage=12, option=0, cbs=(1, 2, 3, 4)),
        _entry(-1),
    ]
    sht = parse_sht(_build_base([(0, entries), (128, [_entry(-1)])]))
    assert sht.initial_bombs == 3.0
    assert sht.initial_respawn_timer == 12
    assert sht.cherry_penalty_multiplier == 0.75
    assert sht.poc_y == 384.0
    assert sht.speed == 4.0 and sht.speed_focus == 2.0
    assert sht.speed_diagonal == 3.0 and sht.speed_diagonal_focus == 1.5
    assert len(sht.levels) == 2
    lv0 = sht.levels[0]
    assert lv0.required_power == 0 and len(lv0.entries) == 2
    e = lv0.entries[0]
    assert e.fire_interval == 4 and e.fire_offset == 0
    assert e.offset == (1.0, 2.0) and e.hitbox == (3.0, 4.0)
    assert e.angle == 0.5 and e.speed == 6.0
    assert e.damage == 12 and e.option == 0
    assert (e.fire_cb, e.update_cb, e.draw_cb, e.hit_cb) == (1, 2, 3, 4)
    assert e.anm_file_idx == 0 and e.sound_idx == -1
    assert e.gauge_behavior == 0
    assert lv0.entries[-1].fire_interval < 0  # 链尾哨兵也入列
    assert sht.level_for_power(200).required_power == 128
    assert sht.level_for_power(10).required_power == 0


def test_parse_extended_layout() -> None:
    entries = [
        _entry(6, 1, size=56, damage=20, option=2, bs2=3, gauge=7, anm=8, snd=9),
        _entry(-1, size=56),
    ]
    sht = parse_sht(_build_ext([(64, entries)]), extended=True)
    assert sht.initial_bombs == 3.0
    assert sht.initial_respawn_timer == 10
    assert sht.cherry_penalty_multiplier == 0.0
    assert sht.grab_item_radius == 48.0
    assert sht.poc_y == 224.0
    assert sht.speed == 4.5 and sht.speed_focus == 2.0
    assert sht.speed_diagonal == 3.25 and sht.speed_diagonal_focus == 1.75
    assert len(sht.levels) == 1
    e = sht.levels[0].entries[0]
    assert e.fire_interval == 6 and e.fire_offset == 1
    assert e.damage == 20 and e.option == 2 and e.bullet_state2 == 3
    assert e.gauge_behavior == 7
    assert e.anm_file_idx == 8 and e.sound_idx == 9


def test_errors() -> None:
    with pytest.raises(ParseError):
        parse_sht(b"\x00" * 10)
    # 档表截断
    data = struct.pack("<hH", 2, 2) + b"\x00" * 48  # 头够, 档表不足
    with pytest.raises(ParseError):
        parse_sht(data)
