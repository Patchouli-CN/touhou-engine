"""th07(v0)ECL 指令集的合成字节流测试: 表项规格核查/符卡/打包字段/时间轴解码。"""

from __future__ import annotations

import struct
from typing import get_args

import msgspec

from touhou.engine.ecl import HANDLERS
from touhou.games.th07.ecl_handlers import ECL_EXTRA_HANDLERS
from touhou.games.th07.ecl_instrs import (
    BeginSpellcard,
    Instruction,
    SetCanBeDamaged,
    SetMoveAnm,
    SpawnLaserPattern,
)
from touhou.games.th07.ecl_table import ECL_INSTR_SET, parse_ecl
from touhou.games.th07.ecl_timeline import TL_HANDLERS, TimelineInstr, TlSpawn
from touhou.schemas.ecl import VarRef, decode_instr, encode_instr


def _instr(
    time: int, op: int, words: tuple[int, ...] = (), *, skip: int = 0xFF, mask: int = 0
) -> bytes:
    size = 12 + 4 * len(words)
    return struct.pack("<IhhBBH", time, op, size, 0, skip, mask) + struct.pack(
        f"<{len(words)}I", *(w & 0xFFFFFFFF for w in words)
    )


def _f32(v: float) -> int:
    return struct.unpack("<I", struct.pack("<f", v))[0]


def test_handler_registry_covers_union() -> None:
    """th07 指令 union = 共享 HANDLERS + v0 专属绑定, 无漏网分派。"""
    assert set(get_args(Instruction)) == set(HANDLERS) | set(ECL_EXTRA_HANDLERS)
    assert set(get_args(TimelineInstr)) == set(TL_HANDLERS)


def test_spec_matches_class_fields() -> None:
    """v0 表的字段规格与指令类声明字段逐一对应(防手滑)。"""
    base_fields = {"offset", "time", "skip_difficulty"}
    for op, entry in ECL_INSTR_SET.entries.items():
        if entry.cls is BeginSpellcard:
            continue  # 定制编解码, 无字段规格
        declared = {
            f.name: f.required
            for f in msgspec.structs.fields(entry.cls)
            if f.name not in base_fields
        }
        covered = {a.name for a in entry.args} | set(entry.consts)
        missing = {n for n, req in declared.items() if req and n not in covered}
        extra = covered - set(declared)
        assert not missing and not extra, (op, entry.cls.__name__, missing, extra)


def test_spellcard_text() -> None:
    """符卡名: word1 起 48 字节 XOR 0xAA, NUL 截断。"""
    name = "幻符「華眩つ躑躅」".encode("shift_jis")
    enc = bytes(b ^ 0xAA for b in name).ljust(48, b"\xaa")
    words = ((7 & 0xFFFF) | (118 << 16),) + struct.unpack("<12I", enc)
    raw = _instr(0, 90, words)
    ins = decode_instr(raw, 0, instrs=ECL_INSTR_SET)
    assert isinstance(ins, BeginSpellcard)
    assert ins.gui_id == 7 and ins.spellcard_idx == 118
    assert ins.name == "幻符「華眩つ躑躅」"
    assert encode_instr(ins, instrs=ECL_INSTR_SET) == raw


def test_byte_and_packed_fields() -> None:
    """字节字段(SetCanBeDamaged)与 5×i16 打包(SetMoveAnm)。"""
    ins = decode_instr(_instr(0, 103, (1,)), 0, instrs=ECL_INSTR_SET)
    assert ins == SetCanBeDamaged(0, 0, 0xFF, 1)
    ins = decode_instr(
        _instr(0, 96, (10 | (11 << 16), 12 | (13 << 16), 14)), 0, instrs=ECL_INSTR_SET
    )
    assert isinstance(ins, SetMoveAnm)
    assert ins.scripts == (10, 11, 12, 13, 14)


def test_laser_v0_roundtrip() -> None:
    raw = _instr(
        0,
        82,
        (
            5 | (2 << 16),
            _f32(0.1),
            _f32(2.0),
            0,
            0,
            0,
            _f32(16.0),
            10,
            60,
            20,
            0,
            30,
            4,
        ),
        mask=0b0000_0010,
    )
    ins = decode_instr(raw, 0, instrs=ECL_INSTR_SET)
    assert isinstance(ins, SpawnLaserPattern)
    assert ins.sprite_offset == VarRef(2) and not ins.moving
    assert encode_instr(ins, instrs=ECL_INSTR_SET) == raw


def test_parse_file_and_timeline() -> None:
    """整文件: v0 布局 + v0 时间轴(TlSpawn 字段逐项)。"""
    sub0 = _instr(0, 4, (10000, 42), mask=1) + _instr(10, 1) + _instr(0xFFFFFFFF, -1)
    header_size = 68 + 4
    tl = (
        struct.pack("<hhhh", 0, 0, 0, 32)
        + struct.pack("<6I", _f32(192.0), _f32(64.0), 0, 100, 1, 2000)
        + struct.pack("<hhhh", -1, 0, 0, 8)
    )
    data = (
        struct.pack("<hh", 1, 1)
        + struct.pack("<16i", header_size + len(sub0), *([0] * 15))
        + struct.pack("<i", header_size)
        + sub0
        + tl
    )
    f = parse_ecl(data)
    assert f.version == 0
    assert [type(i).__name__ for i in f.subs[0].instrs] == ["SetInt", "Stop", "SubEnd"]
    spawn, end = f.timelines[0]
    assert isinstance(spawn, TlSpawn)
    assert spawn.sub_id == 0 and spawn.x == 192.0 and spawn.life == 100
    assert end.time == -1
