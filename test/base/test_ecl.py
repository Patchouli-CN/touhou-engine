"""ECL 解析的合成字节流测试(不依赖真实游戏数据)。"""

from __future__ import annotations

import struct

import msgspec
import pytest

from touhou.exceptions import ParseError
from touhou.schemas.ecl import (
    BeginSpellcard,
    BeginSpellcardV800,
    EclFile,
    ImmFloat,
    ImmInt,
    RunExIns,
    SetCanBeDamaged,
    SetFloat,
    SetInt,
    SetMoveAnm,
    SpawnBulletPattern,
    SubEnd,
    TlEndV800,
    TlSpawn,
    TlSpawnAt,
    VarRef,
    decode_instr,
    encode_instr,
    parse_ecl,
)
from touhou.schemas.ecl.decode import _TABLES


def _instr(
    time: int, op: int, words: tuple[int, ...] = (), *, skip: int = 0xFF, mask: int = 0
) -> bytes:
    size = 12 + 4 * len(words)
    return struct.pack("<IhhBBH", time, op, size, 0, skip, mask) + struct.pack(
        f"<{len(words)}I", *(w & 0xFFFFFFFF for w in words)
    )


def _f32(v: float) -> int:
    return struct.unpack("<I", struct.pack("<f", v))[0]


def _build_v0(subs: list[bytes], timelines: list[bytes] | None = None) -> bytes:
    """造一个 v0 .ecl: 头 + sub 偏移表 + sub 指令流 + 时间轴。"""
    timelines = timelines or []
    header_size = 68 + 4 * len(subs)
    body = bytearray()
    sub_offs = []
    p = header_size
    for s in subs:
        sub_offs.append(p)
        body += s
        p += len(s)
    tl_offs = [0] * 16
    for i, tl in enumerate(timelines):
        tl_offs[i] = p
        body += tl
        p += len(tl)
    return (
        struct.pack("<hh", len(subs), len(timelines))
        + struct.pack("<16i", *tl_offs)
        + struct.pack(f"<{len(subs)}i", *sub_offs)
        + bytes(body)
    )


def test_operand_views() -> None:
    """ParamMask 位决定操作数是立即数还是变量引用; 存储目标未置位 = None。"""
    ins = decode_instr(_instr(5, 4, (10000, 42), mask=0b01), 0)
    assert ins == SetInt(
        offset=0, time=5, skip_difficulty=0xFF, dest=VarRef(10000), value=ImmInt(42)
    )
    ins = decode_instr(_instr(5, 4, (7, 42), mask=0b10), 0)
    assert isinstance(ins, SetInt)
    assert ins.dest is None and ins.value == VarRef(42)
    # float 目标的变量 id 按 f32 值形式存(10004.0f)
    ins = decode_instr(_instr(0, 5, (_f32(10004.0), _f32(1.5)), mask=0b01), 0)
    assert isinstance(ins, SetFloat)
    assert ins.dest == VarRef(10004) and ins.value == ImmFloat(1.5)
    # f32 可变参: 置位 → VarRef(int(f)), 未置位 → ImmFloat
    ins = decode_instr(_instr(0, 5, (0, _f32(10004.0)), mask=0b10), 0)
    assert isinstance(ins, SetFloat)
    assert ins.value == VarRef(10004)


def test_packed_fields() -> None:
    """半字/字节级字段: 弹幕 sprite 两个可变参 i16 半字 + raw flags。"""
    w0 = (3 & 0xFFFF) | (6 << 16)
    words = (w0, 2, 1, _f32(2.0), _f32(1.0), 0, _f32(0.5), 516)
    ins = decode_instr(_instr(60, 64, words, mask=0b0111), 0)
    assert isinstance(ins, SpawnBulletPattern)
    assert ins.aim_mode == 0
    assert ins.sprite == VarRef(3) and ins.sprite_offset == VarRef(6)
    assert ins.count1 == VarRef(2) and ins.flags == 516
    # 字节字段
    ins = decode_instr(_instr(0, 103, (1,)), 0)
    assert ins == SetCanBeDamaged(0, 0, 0xFF, 1)
    # v0 SetMoveAnm: 5 个 i16 打包在 3 字里
    ins = decode_instr(_instr(0, 96, (10 | (11 << 16), 12 | (13 << 16), 14)), 0)
    assert isinstance(ins, SetMoveAnm)
    assert ins.scripts == (10, 11, 12, 13, 14)


def test_spellcard_text() -> None:
    """符卡名: word1 起 48 字节 XOR 0xAA, NUL 截断。"""
    name = "幻符「華眩つ躑躅」".encode("shift_jis")
    enc = bytes(b ^ 0xAA for b in name).ljust(48, b"\xaa")
    words = ((7 & 0xFFFF) | (118 << 16),) + struct.unpack("<12I", enc)
    ins = decode_instr(_instr(0, 90, words), 0)
    assert isinstance(ins, BeginSpellcard)
    assert ins.gui_id == 7 and ins.spellcard_idx == 118
    assert ins.name == "幻符「華眩つ躑躅」"


def test_ex_ins_rest_payload() -> None:
    ins = decode_instr(_instr(0, 121, (3, 0xDEADBEEF)), 0)
    assert isinstance(ins, RunExIns)
    assert ins.idx == ImmInt(3) and ins.args == (0xDEADBEEF,)


def test_terminator_and_unknown() -> None:
    ins = decode_instr(_instr(0xFFFFFFFF, -1), 0)
    assert isinstance(ins, SubEnd) and ins.time == 0xFFFFFFFF
    with pytest.raises(ParseError):
        decode_instr(_instr(0, 127), 0)  # v0 编号表没有 127
    with pytest.raises(ParseError):
        decode_instr(_instr(0, 4, (1,)), 0)  # SetInt 布局 2 字, 实给 1 字
    with pytest.raises(ParseError):
        decode_instr(_instr(0, 4, (1, 2, 3)), 0)  # 多给也报错
    with pytest.raises(ParseError):
        decode_instr(_instr(0, 4, (1, 2)), 0, version=0x999)


def test_spec_matches_class_fields() -> None:
    """两张 opcode 表的字段规格与指令类声明字段逐一对应(防手滑)。"""
    base_fields = {"offset", "time", "skip_difficulty"}
    for version, table in _TABLES.items():
        for op, entry in table.items():
            if entry.cls in (BeginSpellcard, BeginSpellcardV800):
                continue  # 定制编解码, 无字段规格
            declared = {
                f.name: f.required
                for f in msgspec.structs.fields(entry.cls)
                if f.name not in base_fields
            }
            covered = {a.name for a in entry.args} | set(entry.consts)
            missing = {n for n, req in declared.items() if req and n not in covered}
            extra = covered - set(declared)
            assert not missing and not extra, (
                version,
                op,
                entry.cls.__name__,
                missing,
                extra,
            )


def _sample_instrs() -> list[tuple[int, bytes]]:
    """两版本各采样一族代表性指令(字节级手造)。"""
    out: list[tuple[int, bytes]] = []
    out.append((0, _instr(5, 4, (10000, 42), mask=0b01)))  # SetInt
    out.append((0, _instr(0, 5, (_f32(10004.0), _f32(1.5)), mask=0b01)))  # SetFloat
    out.append((0, _instr(0, 2, (20, 100))))  # Jump raw
    out.append((0, _instr(0, 28, (1, 2, -8, 50))))  # JumpIfEq
    out.append(
        (
            0,
            _instr(
                0,
                64,
                (3 | (6 << 16), 2, 1, _f32(2.0), _f32(1.0), 0, _f32(0.5), 516),
                mask=0b0001_0011,
            ),
        )
    )
    out.append(
        (
            0,
            _instr(
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
            ),
        )
    )
    out.append(
        (
            0,
            _instr(
                0,
                90,
                ((7 & 0xFFFF) | (118 << 16),) + struct.unpack("<12I", b"\xaa" * 48),
            ),
        )
    )
    out.append((0, _instr(0, 121, (3, 9))))
    out.append((0, _instr(0xFFFFFFFF, -1)))
    out.append((0x800, _instr(0, 10, (10000, 5), mask=0b01)))  # AddAssign
    out.append(
        (
            0x800,
            _instr(
                0,
                39,
                (_f32(10016.0), _f32(1.0), _f32(2.0), _f32(3.0), _f32(4.0)),
                mask=0b01,
            ),
        )
    )  # Dist
    out.append((0x800, _instr(0, 56, (10, 11, 12, 13, 14, 15))))  # SetMoveAnmV800
    out.append((0x800, _instr(0, 63, (_f32(192.0), _f32(224.0)))))  # SetPosV800
    out.append(
        (
            0x800,
            _instr(
                0,
                122,
                ((1 & 0xFFFF) | (5 << 16), 9999)
                + struct.unpack("<12I", b"\xaa" * 48)
                + struct.unpack("<12I", b"\xbb" * 48)
                + struct.unpack("<32I", b"\xcc" * 128),
            ),
        )
    )
    out.append((0x800, _instr(0, 176, (77,))))  # SetLastSpellFlags rest
    return out


def test_roundtrip() -> None:
    """Decode → encode 逐字节还原, 再 decode 得同一对象(合成流)。"""
    for version, raw in _sample_instrs():
        ins = decode_instr(raw, 0, version=version)
        assert encode_instr(ins, version=version) == raw
        assert (
            decode_instr(encode_instr(ins, version=version), 0, version=version) == ins
        )


def test_parse_file_v0() -> None:
    sub0 = _instr(0, 4, (10000, 42), mask=1) + _instr(10, 1) + _instr(0xFFFFFFFF, -1)
    sub1 = _instr(0xFFFFFFFF, -1)
    tl = (
        struct.pack("<hhhh", 0, 0, 0, 32)
        + struct.pack("<6I", _f32(192.0), _f32(64.0), 0, 100, 1, 2000)
        + struct.pack("<hhhh", -1, 0, 0, 8)
    )
    f = parse_ecl(_build_v0([sub0, sub1], [tl]))
    assert isinstance(f, EclFile) and f.version == 0
    assert len(f.subs) == 2
    assert [type(i).__name__ for i in f.subs[0].instrs] == ["SetInt", "Stop", "SubEnd"]
    assert f.subs[0].offset == 68 + 8
    assert len(f.timelines) == 1
    spawn, end = f.timelines[0]
    assert isinstance(spawn, TlSpawn)
    assert spawn.sub_id == 0 and spawn.x == 192.0 and spawn.life == 100
    assert end.time == -1


def test_parse_file_v800() -> None:
    sub0 = _instr(0, 6, (10000, 1), mask=1) + _instr(0xFFFFFFFF, -1)
    header_size = 0x48 + 4
    tl_offs = [0] * 16
    tl_offs[0] = header_size + len(sub0)
    tl = (
        struct.pack("<ihBB", 30, 0, 32, 0xFF)
        + struct.pack("<6I", 5, _f32(192.0), _f32(64.0), 100, 1, 2000)
        + struct.pack("<ihBB", -1, 0, 0, 0)
    )
    data = (
        struct.pack("<Ihh", 0x800, 1, 1)
        + struct.pack("<16I", *tl_offs)
        + struct.pack("<I", header_size)
        + sub0
        + tl
    )
    f = parse_ecl(data, version=0x800)
    assert f.version == 0x800
    assert [type(i).__name__ for i in f.subs[0].instrs] == ["SetInt", "SubEnd"]
    spawn, end = f.timelines[0]
    assert isinstance(spawn, TlSpawnAt) and spawn.difficulty_mask == 0xFF
    assert spawn.sub_id == 5 and spawn.y == 64.0
    assert isinstance(end, TlEndV800)


def test_parse_errors() -> None:
    with pytest.raises(ParseError):
        parse_ecl(b"\x00" * 10)
    with pytest.raises(ParseError):
        parse_ecl(b"\x00" * 100, version=0x999)
    bad_magic = struct.pack("<Ihh", 0x700, 0, 0) + b"\x00" * 64
    with pytest.raises(ParseError):
        parse_ecl(bad_magic, version=0x800)
