"""std 解析的合成字节流测试(不依赖真实游戏数据)。"""

from __future__ import annotations

import struct

import pytest

from touhou.exceptions import ParseError
from touhou.schemas.stage import parse_std
from touhou.schemas.stage_script import (
    CamFov,
    CamPos,
    FogInterp,
    Jump,
    PosKey,
    SetFog,
    WaitLabel,
)

_HEADER = 1168


def _instr(frame: int, op: int, args: bytes = b"\x00" * 12) -> bytes:
    assert len(args) == 12
    return struct.pack("<ihh", frame, op, 20) + args


def _build(
    *,
    title: bytes = b"test stage",
    bgm_names: tuple[bytes, ...] = (b"bgm a", b"", b"", b""),
    bgm_paths: tuple[bytes, ...] = (b"bgm/x.mid", b"", b"", b""),
    objects: bytes = b"",
    num_objects: int = 0,
    object_offsets: tuple[int, ...] = (),
    instances: bytes = struct.pack("<h", -1) + b"\x00" * 14,
    script: bytes = struct.pack("<ihh", -1, 0, 20) + b"\x00" * 12,
    quad_count: int = 0,
) -> bytes:
    """造一个 .std: 1168 头 + 偏移表 + 物件区 + 实例表 + 脚本。"""
    header = bytearray(_HEADER)
    faces_off = _HEADER + num_objects * 4 + len(objects)
    script_off = faces_off + len(instances)
    struct.pack_into("<hhII", header, 0, num_objects, quad_count, faces_off, script_off)
    header[16 : 16 + len(title)] = title
    for i, name in enumerate(bgm_names):
        header[144 + i * 128 : 144 + i * 128 + len(name)] = name
    for i, path in enumerate(bgm_paths):
        header[656 + i * 128 : 656 + i * 128 + len(path)] = path
    table = b"".join(struct.pack("<i", o) for o in object_offsets)
    return bytes(header) + table + objects + instances + script


def _object(
    oid: int = 1, z: int = 2, quads: list[tuple[int, int]] | None = None
) -> bytes:
    """造一个 StdRawObject + quad 链(quads = (anm_script, size) 列表)。"""
    out = bytearray()
    out += struct.pack("<Hbb", oid, z, 0)
    out += struct.pack("<3f", 1.0, 2.0, 3.0)
    out += struct.pack("<3f", 10.0, 20.0, 30.0)
    for anm_script, _ in quads or []:
        out += struct.pack("<4h", 0, 28, anm_script, 0)
        out += struct.pack("<3f", 0.0, 0.0, 0.0)
        out += struct.pack("<2f", 0.0, 0.0)
    out += struct.pack("<4h", -1, 0, 0, 0) + b"\x00" * 20  # quad 链终止
    return bytes(out)


def test_parse_header_and_names() -> None:
    std = parse_std(_build())
    assert std.title == "test stage"
    assert std.bgm_names == ("bgm a", "", "", "")
    assert std.main_bgm == "bgm/x.mid"
    assert std.quad_count == 0
    assert std.objects == [] and std.instances == [] and std.script == []


def test_parse_objects_and_instances() -> None:
    obj_off = _HEADER + 4  # 偏移表(1 项)之后
    obj = _object(oid=7, z=1, quads=[(5, 28), (6, 28)])
    inst = struct.pack("<hh", 0, 0) + struct.pack("<3f", 4.0, 5.0, 6.0)
    inst += struct.pack("<h", -1) + b"\x00" * 14
    std = parse_std(
        _build(
            objects=obj,
            num_objects=1,
            object_offsets=(obj_off,),
            instances=inst,
            quad_count=2,
        )
    )
    assert std.quad_count == 2
    o = std.objects[0]
    assert o.id == 7 and o.z_level == 1
    assert o.pos == (1.0, 2.0, 3.0) and o.size == (10.0, 20.0, 30.0)
    assert len(o.quads) == 2
    assert o.quads[0].type == 0 and o.quads[0].anm_script == 5
    assert o.quads[1].anm_script == 6
    assert len(std.instances) == 1
    assert std.instances[0].object_idx == 0
    assert std.instances[0].pos == (4.0, 5.0, 6.0)


def test_parse_script_instructions() -> None:
    script = b"".join(
        [
            _instr(0, 0, struct.pack("<3f", 1.5, -2.5, 3.0)),
            _instr(10, 1, struct.pack("<iff", 0x3F00FF00, 100.0, 900.0)),
            _instr(20, 2, struct.pack("<i", 30) + b"\x00" * 8),
            _instr(30, 4, struct.pack("<2i", 7, 40) + b"\x00" * 4),
            _instr(50, 5, struct.pack("<3f", 0.0, 1.0, 2.0)),
            _instr(60, 11, struct.pack("<f", 0.5) + b"\x00" * 8),
            _instr(70, 31, struct.pack("<i", 2) + b"\x00" * 8),
            struct.pack("<ihh", -1, 0, 20) + b"\x00" * 12,
        ]
    )
    std = parse_std(_build(script=script))
    seq = std.script
    assert len(seq) == 7
    pk = seq[0]
    assert isinstance(pk, PosKey) and (pk.x, pk.y, pk.z) == (1.5, -2.5, 3.0)
    fog = seq[1]
    assert isinstance(fog, SetFog)
    assert fog.color == 0x3F00FF00 and fog.near == 100.0 and fog.far == 900.0
    fi = seq[2]
    assert isinstance(fi, FogInterp) and fi.duration == 30
    jp = seq[3]
    assert isinstance(jp, Jump) and (jp.instr_idx, jp.time) == (7, 40)
    cp = seq[4]
    assert isinstance(cp, CamPos) and (cp.x, cp.y, cp.z) == (0.0, 1.0, 2.0)
    fv = seq[5]
    assert isinstance(fv, CamFov) and fv.fov == 0.5
    wl = seq[6]
    assert isinstance(wl, WaitLabel) and wl.label == 2 and wl.frame == 70


def test_extended_opcodes() -> None:
    """扩展 opcode 32-34 的参数布局。"""
    script = b"".join(
        [
            _instr(0, 32, struct.pack("<3f", 1.0, 2.0, 3.0)),
            _instr(1, 33, struct.pack("<i", 4) + b"\x00" * 8),
            _instr(2, 34, struct.pack("<i", 9) + b"\x00" * 8),
            struct.pack("<ihh", -1, 0, 20) + b"\x00" * 12,
        ]
    )
    seq = parse_std(_build(script=script)).script
    assert type(seq[0]).__name__ == "CameraOffset"
    assert type(seq[1]).__name__ == "CameraMotionMode"
    assert type(seq[2]).__name__ == "BgScript3"


def test_errors() -> None:
    with pytest.raises(ParseError):
        parse_std(b"\x00" * 100)
    # 未知脚本 opcode
    bad = _instr(0, 99) + struct.pack("<ihh", -1, 0, 20) + b"\x00" * 12
    with pytest.raises(ParseError):
        parse_std(_build(script=bad))
