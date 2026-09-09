"""anm 解析的合成字节流测试(不依赖真实游戏数据)。"""

from __future__ import annotations

import struct

import pytest

from touhou.exceptions import ParseError
from touhou.schemas.anm import AnmFile, decode_texture, parse_anm, sprite_image
from touhou.schemas.anm_script import (
    Anchor3,
    DecJump,
    ExitHide,
    Fade,
    InterpPos,
    Jump,
    JumpIfEqFloat,
    Nop,
    SetActiveSprite,
    SetScrollVelX,
    SetTranslation,
    Wait,
    decode_script,
)


def _instr(op: int, time: int = 0, flags: int = 0, words: bytes = b"") -> bytes:
    """编一条指令: 头 8 字节 + 参数区原始字节。"""
    return struct.pack("<hHhH", op, 8 + len(words), time, flags) + words


def _i(*vals: int) -> bytes:
    return struct.pack(f"<{len(vals)}i", *vals)


def _f(*vals: float) -> bytes:
    return struct.pack(f"<{len(vals)}f", *vals)


def _build_entry(
    *,
    width: int = 2,
    height: int = 2,
    fmt: int = 3,
    version: int = 2,
    name: bytes = b"test.anm",
    sprites: list[tuple[int, float, float, float, float]] = (),
    scripts: dict[int, bytes] = {},
    texture: tuple[int, int, int, bytes] | None = (3, 2, 2, b""),
    color_key: int = 0,
) -> bytes:
    """造一个单 entry 的 .anm(纹理像素缺省补零)。"""
    ntex = texture
    if ntex is not None:
        tfmt, tw, th, pixels = ntex
        bpp = {1: 4, 2: 2, 3: 2, 4: 3, 5: 2}[tfmt]
        pixels = pixels or bytes(tw * th * bpp)
    # 布局: 64B 头 + sprite 偏移表 + 脚本表 + sprite 记录 + 脚本 + 名字 + 纹理
    header_size = 64
    spr_table = header_size
    scr_table = spr_table + 4 * len(sprites)
    p = scr_table + 8 * len(scripts)
    spr_offs = []
    body = bytearray()
    for sid, x, y, w, h in sprites:
        spr_offs.append(p)
        rec = struct.pack("<iffff", sid, x, y, w, h)
        body += rec
        p += len(rec)
    scr_offs = []
    for sid, code in scripts.items():
        scr_offs.append((sid, p))
        body += code
        p += len(code)
    name_off = p
    body += name + b"\0"
    p += len(name) + 1
    tex_off = 0
    if ntex is not None:
        tex_off = p
        body += struct.pack("<6hi", 0x4854, 0, 0, ntex[0], ntex[1], ntex[2], 0)
        body += pixels
    header = struct.pack(
        "<13i",
        len(sprites),
        len(scripts),
        0,
        width,
        height,
        fmt,
        color_key,
        name_off,
        0,
        0,
        version,
        0,
        tex_off,
    )
    header += bytes([1 if ntex is not None else 0]) + b"\0\0\0"  # hasData + pad
    header += struct.pack("<i", 0)  # nextOffset
    header += b"\0\0\0\0"
    assert len(header) == 64
    out = bytearray(header)
    for so in spr_offs:
        out += struct.pack("<i", so)
    for sid, so in scr_offs:
        out += struct.pack("<2i", sid, so)
    out += body
    return bytes(out)


def test_decode_texture_formats() -> None:
    """5 种纹理格式的解码数学逐像素核对。"""
    assert decode_texture(1, 1, 1, bytes([10, 20, 30, 40])) == bytes([30, 20, 10, 40])
    assert decode_texture(2, 1, 1, struct.pack("<H", 0x8000)) == bytes([0, 0, 0, 255])
    assert decode_texture(2, 1, 1, struct.pack("<H", 0x7C00)) == bytes([255, 0, 0, 0])
    assert decode_texture(3, 1, 1, struct.pack("<H", 0xFFFF)) == bytes(
        [255, 255, 255, 255]
    )
    assert decode_texture(3, 1, 1, struct.pack("<H", 0x07E0)) == bytes([0, 255, 0, 255])
    assert decode_texture(4, 1, 1, bytes([1, 2, 3])) == bytes([3, 2, 1, 255])
    assert decode_texture(5, 1, 1, struct.pack("<H", 0xF123)) == bytes(
        [17, 34, 51, 255]
    )
    with pytest.raises(ParseError):
        decode_texture(9, 1, 1, b"\0")


def test_decode_script_typed_union() -> None:
    """指令 decode 成强类型对象, int/float 视图按字段注解各取所需。"""
    code = (
        _instr(3, words=_i(5))
        + _instr(6, time=2, words=_f(1.5, -2.0, 3.25))
        + _instr(15, words=_i(128, 30))
        + _instr(32, words=_i(20, 4) + _f(10.0, 20.0, 30.0))
        + _instr(68, time=3, words=_f(1.5, 2.5) + _i(24, 7))
        + _instr(80, words=_f(0.5))
        + _instr(22)
        + _instr(79, words=_i(3))
        + _instr(4, words=_i(8, 99))
        + _instr(5, words=_i(10000, 8, 0))
        + _instr(-1)
    )
    instrs = decode_script(code, 0)
    assert instrs == [
        SetActiveSprite(time=0, flags=0, sprite=5),
        SetTranslation(time=2, flags=0, x=1.5, y=-2.0, z=3.25),
        Fade(time=0, flags=0, alpha=128, duration=30),
        InterpPos(time=0, flags=0, duration=20, ease=4, x=10.0, y=20.0, z=30.0),
        JumpIfEqFloat(time=3, flags=0, x=1.5, y=2.5, dest=24, set_time=7),
        SetScrollVelX(time=0, flags=0, v=0.5),
        Anchor3(time=0, flags=0),
        Wait(time=0, flags=0, frames=3),
        Jump(time=0, flags=0, dest=8, set_time=99),
        DecJump(time=0, flags=0, var=10000, dest=8, set_time=0),
        ExitHide(time=0, flags=0),
    ]


def test_decode_script_flags_preserved() -> None:
    """flags(间接变量位标记)原样保留给执行方解释。"""
    (ins,) = decode_script(_instr(3, flags=0b1, words=_i(10000)) + _instr(-1), 0)[:1]
    assert ins == SetActiveSprite(time=0, flags=1, sprite=10000)


def test_decode_script_stops_at_exit_hide() -> None:
    """ExitHide 后的字节不再 decode。"""
    instrs = decode_script(_instr(-1) + _instr(999, words=_i(1)), 0)
    assert instrs == [ExitHide(time=0, flags=0)]


def test_decode_script_nop() -> None:
    """Opcode 0 是真实数据里存在的空转指令(eff08.anm 等)。"""
    assert decode_script(_instr(0, time=60) + _instr(-1), 0) == [
        Nop(time=60, flags=0),
        ExitHide(time=0, flags=0),
    ]


def test_decode_script_unknown_opcode_raises() -> None:
    with pytest.raises(ParseError, match="opcode"):
        decode_script(_instr(999, words=_i(1)), 0)


def test_decode_script_arg_count_mismatch_raises() -> None:
    with pytest.raises(ParseError, match="参数数不符"):
        decode_script(_instr(3, words=_i(1, 2)), 0)


def test_parse_anm_single_entry() -> None:
    """单 entry: 纹理/sprite 缩放/脚本一次解析全。"""
    pixels = struct.pack("<4H", 0xFFFF, 0xF800, 0x07E0, 0x001F)
    code = _instr(3, words=_i(0)) + _instr(-1)
    data = _build_entry(
        sprites=[(0, 0.0, 0.0, 1.0, 1.0), (7, 1.0, 1.0, 1.0, 1.0)],
        scripts={0: code},
        texture=(3, 2, 2, pixels),
    )
    anm = parse_anm(data, version=2)
    assert len(anm.entries) == 1
    e = anm.entries[0]
    assert e.name == "test.anm"
    assert (e.tex_width, e.tex_height) == (2, 2)
    assert e.rgba == bytes(
        [255, 255, 255, 255, 255, 0, 0, 255, 0, 255, 0, 255, 0, 0, 255, 255]
    )
    assert e.sprites[7].x == 1 and e.sprites[7].fx == 1.0
    assert list(anm.scripts[0]) == [0]
    assert anm.scripts[0][0] == [
        SetActiveSprite(time=0, flags=0, sprite=0),
        ExitHide(time=0, flags=0),
    ]
    w, h, rgba = sprite_image(anm, 7)
    assert (w, h) == (1, 1)
    assert rgba == bytes([0, 0, 255, 255])  # 右下角像素


def test_parse_anm_version_mismatch() -> None:
    data = _build_entry(version=2)
    with pytest.raises(ParseError, match="版本不符"):
        parse_anm(data, version=3)


def test_parse_anm_entry_chain() -> None:
    """多 entry 用 nextOffset 链式相连。"""
    e0 = bytearray(_build_entry(name=b"a", scripts={0: _instr(-1)}))
    e1 = _build_entry(name=b"b", scripts={1: _instr(-1)})
    struct.pack_into("<i", e0, 56, len(e0))
    anm = parse_anm(bytes(e0) + e1, version=2)
    assert [e.name for e in anm.entries] == ["a", "b"]
    assert list(anm.scripts[0]) == [0]
    assert list(anm.scripts[1]) == [1]


def test_parse_anm_flat_layout_script_keys() -> None:
    """flat_layout=True 时脚本表键是装载序号, 忽略文件里存的 id。"""
    data = _build_entry(scripts={42: _instr(-1), 77: _instr(-1)})
    assert list(parse_anm(data, version=2).scripts[0]) == [42, 77]
    assert list(parse_anm(data, version=2, flat_layout=True).scripts[0]) == [0, 1]


def test_parse_anm_empty_texture_at_name() -> None:
    """@ 开头名字 → 按 entry 头宽高的全透明空纹理。"""
    data = _build_entry(name=b"@empty", texture=None, width=4, height=3)
    e = parse_anm(data, version=2).entries[0]
    assert e.rgba == bytes(4 * 3 * 4)
    assert (e.tex_width, e.tex_height) == (4, 3)


def test_parse_anm_external_texture_deferred() -> None:
    """外链纹理不注入 loader: rgba=None + name/color_key/format 留给调用方。"""
    data = _build_entry(name=b"data/foo.png", texture=None, color_key=0xFF00FF, fmt=1)
    e = parse_anm(data, version=2).entries[0]
    assert e.rgba is None
    assert (e.name, e.color_key, e.format) == ("data/foo.png", 0xFF00FF, 1)
    with pytest.raises(ParseError, match="外链纹理"):
        sprite_image(AnmFile([e], [{}]), 0)
