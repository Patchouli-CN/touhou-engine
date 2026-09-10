"""th08(v800)ECL 指令集的合成字节流测试: 表项规格核查/符卡/专属指令/时间轴解码。"""

from __future__ import annotations

import struct
from typing import get_args

import msgspec

from touhou.engine.ecl import HANDLERS
from touhou.games.th08.ecl_handlers import ECL_EXTRA_HANDLERS
from touhou.games.th08.ecl_instrs import (
    AddAssign,
    BeginSpellcardV800,
    Dist,
    Instruction,
    SetLastSpellFlags,
    SetMoveAnmV800,
    SetPosV800,
)
from touhou.games.th08.ecl_table import ECL_INSTR_SET, parse_ecl
from touhou.games.th08.ecl_timeline import (
    TL_HANDLERS,
    TimelineInstr,
    TlEndV800,
    TlSpawnAt,
)
from touhou.schemas.ecl import ImmFloat, ImmInt, VarRef, decode_instr, encode_instr


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
    """th08 指令 union = 共享 HANDLERS + v800 专属绑定, 无漏网分派。"""
    assert set(get_args(Instruction)) == set(HANDLERS) | set(ECL_EXTRA_HANDLERS)
    assert set(get_args(TimelineInstr)) == set(TL_HANDLERS)


def test_spec_matches_class_fields() -> None:
    """v800 表的字段规格与指令类声明字段逐一对应(防手滑)。"""
    base_fields = {"offset", "time", "skip_difficulty"}
    for op, entry in ECL_INSTR_SET.entries.items():
        if entry.cls is BeginSpellcardV800:
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


def test_spellcard_v800_roundtrip() -> None:
    raw = _instr(
        0,
        122,
        ((1 & 0xFFFF) | (5 << 16), 9999)
        + struct.unpack("<12I", b"\xaa" * 48)
        + struct.unpack("<12I", b"\xbb" * 48)
        + struct.unpack("<32I", b"\xcc" * 128),
    )
    ins = decode_instr(raw, 0, instrs=ECL_INSTR_SET)
    assert isinstance(ins, BeginSpellcardV800)
    assert ins.gui_id == 1 and ins.spellcard_idx == 5 and ins.bonus == 9999
    assert encode_instr(ins, instrs=ECL_INSTR_SET) == raw


def test_v800_exclusive_instrs() -> None:
    """v800 专属布局: 2 操作数自赋值/Dist/6 脚本 anm/xy 位置/rest 载荷。"""
    ins = decode_instr(_instr(0, 10, (10000, 5), mask=0b01), 0, instrs=ECL_INSTR_SET)
    assert ins == AddAssign(0, 0, 0xFF, VarRef(10000), ImmInt(5))
    ins = decode_instr(
        _instr(
            0,
            39,
            (_f32(10016.0), _f32(1.0), _f32(2.0), _f32(3.0), _f32(4.0)),
            mask=0b01,
        ),
        0,
        instrs=ECL_INSTR_SET,
    )
    assert isinstance(ins, Dist)
    assert ins.dest == VarRef(10016) and ins.x2 == ImmFloat(3.0)
    ins = decode_instr(_instr(0, 56, (10, 11, 12, 13, 14, 15)), 0, instrs=ECL_INSTR_SET)
    assert isinstance(ins, SetMoveAnmV800)
    assert ins.scripts == tuple(ImmInt(v) for v in (10, 11, 12, 13, 14, 15))
    ins = decode_instr(
        _instr(0, 63, (_f32(192.0), _f32(224.0))), 0, instrs=ECL_INSTR_SET
    )
    assert ins == SetPosV800(0, 0, 0xFF, ImmFloat(192.0), ImmFloat(224.0))
    raw = _instr(0, 176, (77,))  # SetLastSpellFlags: C 不读的载荷字
    ins = decode_instr(raw, 0, instrs=ECL_INSTR_SET)
    assert ins == SetLastSpellFlags(0, 0, 0xFF, (77,))
    assert encode_instr(ins, instrs=ECL_INSTR_SET) == raw


def test_parse_file_and_timeline() -> None:
    """整文件: v800 布局 + v800 时间轴(TlSpawnAt 难度掩码)。"""
    sub0 = _instr(0, 6, (10000, 1), mask=1) + _instr(0xFFFFFFFF, -1)
    header_size = 0x48 + 4
    tl = (
        struct.pack("<ihBB", 30, 0, 32, 0xFF)
        + struct.pack("<6I", 5, _f32(192.0), _f32(64.0), 100, 1, 2000)
        + struct.pack("<ihBB", -1, 0, 0, 0)
    )
    data = (
        struct.pack("<Ihh", 0x800, 1, 1)
        + struct.pack("<16I", header_size + len(sub0), *([0] * 15))
        + struct.pack("<I", header_size)
        + sub0
        + tl
    )
    f = parse_ecl(data)
    assert f.version == 0x800
    assert [type(i).__name__ for i in f.subs[0].instrs] == ["SetInt", "SubEnd"]
    spawn, end = f.timelines[0]
    assert isinstance(spawn, TlSpawnAt) and spawn.difficulty_mask == 0xFF
    assert spawn.sub_id == 5 and spawn.y == 64.0
    assert isinstance(end, TlEndV800)
