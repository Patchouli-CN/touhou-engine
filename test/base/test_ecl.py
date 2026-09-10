"""ECL 解析机制的合成字节流测试(合成 opcode 表注入, 不依赖作品表/真实数据)。"""

from __future__ import annotations

import struct

import pytest

from touhou.exceptions import ParseError
from touhou.schemas.ecl import (
    EclFile,
    ImmFloat,
    ImmInt,
    Jump,
    JumpIfEq,
    Nop,
    RunExIns,
    SetFloat,
    SetInt,
    SpawnBulletPattern,
    Stop,
    SubEnd,
    TlInstr,
    VarRef,
    build_instr_set,
    decode_instr,
    encode_instr,
    parse_ecl,
)
from touhou.schemas.ecl.spec import _A, _bullet, _cond, _Entry

_SYNTH = build_instr_set(
    {
        0: _Entry(Nop, (_A("rest", 0, "rest"),)),
        1: _Entry(Stop),
        2: _Entry(Jump, (_A("dest", 0, "ri"), _A("set_time", 1, "ri"))),
        4: _Entry(SetInt, (_A("dest", 0, "int_t"), _A("value", 1, "int"))),
        5: _Entry(SetFloat, (_A("dest", 0, "float_t"), _A("value", 1, "float"))),
        28: _cond(JumpIfEq, False),
        121: _Entry(RunExIns, (_A("idx", 0, "int"), _A("args", 1, "rest"))),
        **{64 + i: _bullet(i) for i in range(9)},
    }
)


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
    ins = decode_instr(_instr(5, 4, (10000, 42), mask=0b01), 0, instrs=_SYNTH)
    assert ins == SetInt(
        offset=0, time=5, skip_difficulty=0xFF, dest=VarRef(10000), value=ImmInt(42)
    )
    ins = decode_instr(_instr(5, 4, (7, 42), mask=0b10), 0, instrs=_SYNTH)
    assert isinstance(ins, SetInt)
    assert ins.dest is None and ins.value == VarRef(42)
    # float 目标的变量 id 按 f32 值形式存(10004.0f)
    ins = decode_instr(
        _instr(0, 5, (_f32(10004.0), _f32(1.5)), mask=0b01), 0, instrs=_SYNTH
    )
    assert isinstance(ins, SetFloat)
    assert ins.dest == VarRef(10004) and ins.value == ImmFloat(1.5)
    # f32 可变参: 置位 → VarRef(int(f)), 未置位 → ImmFloat
    ins = decode_instr(_instr(0, 5, (0, _f32(10004.0)), mask=0b10), 0, instrs=_SYNTH)
    assert isinstance(ins, SetFloat)
    assert ins.value == VarRef(10004)


def test_packed_fields() -> None:
    """半字级字段: 弹幕 sprite 两个可变参 i16 半字 + raw flags。"""
    w0 = (3 & 0xFFFF) | (6 << 16)
    words = (w0, 2, 1, _f32(2.0), _f32(1.0), 0, _f32(0.5), 516)
    ins = decode_instr(_instr(60, 64, words, mask=0b0111), 0, instrs=_SYNTH)
    assert isinstance(ins, SpawnBulletPattern)
    assert ins.aim_mode == 0
    assert ins.sprite == VarRef(3) and ins.sprite_offset == VarRef(6)
    assert ins.count1 == VarRef(2) and ins.flags == 516


def test_ex_ins_rest_payload() -> None:
    ins = decode_instr(_instr(0, 121, (3, 0xDEADBEEF)), 0, instrs=_SYNTH)
    assert isinstance(ins, RunExIns)
    assert ins.idx == ImmInt(3) and ins.args == (0xDEADBEEF,)


def test_terminator_and_unknown() -> None:
    ins = decode_instr(_instr(0xFFFFFFFF, -1), 0, instrs=_SYNTH)
    assert isinstance(ins, SubEnd) and ins.time == 0xFFFFFFFF
    with pytest.raises(ParseError):
        decode_instr(_instr(0, 127), 0, instrs=_SYNTH)  # 合成表没有 127
    with pytest.raises(ParseError):
        decode_instr(
            _instr(0, 4, (1,)), 0, instrs=_SYNTH
        )  # SetInt 布局 2 字, 实给 1 字
    with pytest.raises(ParseError):
        decode_instr(_instr(0, 4, (1, 2, 3)), 0, instrs=_SYNTH)  # 多给也报错


def test_roundtrip() -> None:
    """Decode → encode 逐字节还原, 再 decode 得同一对象(合成流)。"""
    samples = [
        _instr(5, 4, (10000, 42), mask=0b01),  # SetInt
        _instr(0, 5, (_f32(10004.0), _f32(1.5)), mask=0b01),  # SetFloat
        _instr(0, 2, (20, 100)),  # Jump raw
        _instr(0, 28, (1, 2, -8, 50)),  # JumpIfEq
        _instr(
            0,
            64,
            (3 | (6 << 16), 2, 1, _f32(2.0), _f32(1.0), 0, _f32(0.5), 516),
            mask=0b0001_0011,
        ),
        _instr(0, 121, (3, 9)),  # RunExIns rest
        _instr(0xFFFFFFFF, -1),
    ]
    for raw in samples:
        ins = decode_instr(raw, 0, instrs=_SYNTH)
        assert encode_instr(ins, instrs=_SYNTH) == raw
        assert decode_instr(encode_instr(ins, instrs=_SYNTH), 0, instrs=_SYNTH) == ins


class _TlProbe(TlInstr, frozen=True, tag="tl_probe"):
    """合成时间轴指令: 记录解码器被调用的偏移。"""


_tl_calls: list[int] = []


def _decode_tl_synth(data: bytes, off: int) -> tuple[TlInstr, ...]:
    _tl_calls.append(off)
    return (_TlProbe(time=-1),)


def test_parse_file_v0() -> None:
    """v0 头/sub 表布局: 偏移表 i32, 时间轴解码器按注入回调。"""
    _tl_calls.clear()
    sub0 = _instr(0, 4, (10000, 42), mask=1) + _instr(10, 1) + _instr(0xFFFFFFFF, -1)
    sub1 = _instr(0xFFFFFFFF, -1)
    f = parse_ecl(
        _build_v0([sub0, sub1], [b"\xff\xff\x04\x00"]),
        version=0,
        instrs=_SYNTH,
        decode_tl=_decode_tl_synth,
    )
    assert isinstance(f, EclFile) and f.version == 0
    assert len(f.subs) == 2
    assert [type(i).__name__ for i in f.subs[0].instrs] == ["SetInt", "Stop", "SubEnd"]
    assert f.subs[0].offset == 68 + 8
    assert len(f.timelines) == 1 and _tl_calls == [68 + 8 + len(sub0) + len(sub1)]


def test_parse_file_v800() -> None:
    """v800 头布局: u32 version 头校验 + 偏移表 u32。"""
    _tl_calls.clear()
    sub0 = _instr(0, 4, (10000, 1), mask=1) + _instr(0xFFFFFFFF, -1)
    header_size = 0x48 + 4
    tl_offs = [0] * 16
    tl_offs[0] = header_size + len(sub0)
    data = (
        struct.pack("<Ihh", 0x800, 1, 1)
        + struct.pack("<16I", *tl_offs)
        + struct.pack("<I", header_size)
        + sub0
        + b"\xff\xff\x04\x00"
    )
    f = parse_ecl(data, version=0x800, instrs=_SYNTH, decode_tl=_decode_tl_synth)
    assert f.version == 0x800
    assert [type(i).__name__ for i in f.subs[0].instrs] == ["SetInt", "SubEnd"]
    assert _tl_calls == [tl_offs[0]]


def test_parse_errors() -> None:
    with pytest.raises(ParseError):
        parse_ecl(b"\x00" * 10, version=0, instrs=_SYNTH, decode_tl=_decode_tl_synth)
    with pytest.raises(ParseError):
        parse_ecl(
            b"\x00" * 100, version=0x999, instrs=_SYNTH, decode_tl=_decode_tl_synth
        )
    bad_magic = struct.pack("<Ihh", 0x700, 0, 0) + b"\x00" * 64
    with pytest.raises(ParseError):
        parse_ecl(bad_magic, version=0x800, instrs=_SYNTH, decode_tl=_decode_tl_synth)
