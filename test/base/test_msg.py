"""msg 解析的合成字节流测试(不依赖真实游戏数据)。"""

from __future__ import annotations

import struct

import pytest

from touhou.exceptions import ParseError
from touhou.schemas.msg import (
    AllowSkip,
    ConfigureAllPortraits,
    Delete,
    Dialogue,
    MsgFile,
    Music,
    Pause,
    ShowPortrait,
    ShowSelection,
    ShowTopText,
    Switch,
    TextIntroduce,
    parse_msg,
)


def _instr(time: int, op: int, args: bytes = b"") -> bytes:
    return struct.pack("<HBB", time, op, len(args)) + args


def _build(*messages: list[bytes]) -> bytes:
    """造一个 msg 文件: 头 + 偏移表 + 指令流(每条消息自带 Delete 结尾)。"""
    n = len(messages)
    offsets = []
    body = bytearray()
    p = 4 + 4 * n
    for msg in messages:
        offsets.append(p)
        for ins in msg:
            body += ins
            p += len(ins)
    return struct.pack(f"<{1 + n}i", n, *offsets) + bytes(body)


def test_parse_dialogue_and_control() -> None:
    text = "妖々夢".encode("shift_jis") + b"\x00"
    msg = [
        _instr(0, 1, struct.pack("<hh", 0, 3)),
        _instr(10, 3, struct.pack("<hh", 1, 0) + text),
        _instr(20, 5, struct.pack("<hB", 0, 3)),
        _instr(30, 4, struct.pack("<i", 60)),
        _instr(40, 7, struct.pack("<i", 5)),
        _instr(50, 13, b"\x01"),
        _instr(60, 0),
    ]
    f = parse_msg(_build(msg))
    assert len(f.messages) == 1
    seq = f.messages[0]
    assert isinstance(seq[0], ShowPortrait)
    assert (seq[0].portrait_idx, seq[0].anm_script_idx) == (0, 3)
    dia = seq[1]
    assert isinstance(dia, Dialogue)
    assert (dia.color, dia.line, dia.text) == (1, 0, "妖々夢")
    assert dia.time == 10
    sw = seq[2]
    assert isinstance(sw, Switch) and (sw.idx, sw.interrupt) == (0, 3)
    pause = seq[3]
    assert isinstance(pause, Pause) and pause.duration == 60
    mus = seq[4]
    assert isinstance(mus, Music) and mus.music_idx == 5
    sk = seq[5]
    assert isinstance(sk, AllowSkip) and sk.skippable == 1
    assert isinstance(seq[6], Delete)


def test_multiple_messages_offsets() -> None:
    f = parse_msg(
        _build([_instr(0, 4, struct.pack("<i", 10)), _instr(5, 0)], [_instr(0, 0)])
    )
    assert len(f.messages) == 2
    assert len(f.messages[0]) == 2 and len(f.messages[1]) == 1


def test_text_xor_roundtrip() -> None:
    """加密文本(text_xor=0x77)解析还原; 不带参数则读到乱码字节。"""
    plain = "永夜抄".encode("shift_jis") + b"\x00"
    enc = bytes(b ^ 0x77 for b in plain)
    data = _build([_instr(0, 3, struct.pack("<hh", 0, 0) + enc), _instr(1, 0)])
    f = parse_msg(data, text_xor=0x77)
    dia = f.messages[0][0]
    assert isinstance(dia, Dialogue)
    assert dia.text == "永夜抄"
    f0 = parse_msg(data)
    dia0 = f0.messages[0][0]
    assert isinstance(dia0, Dialogue)
    assert dia0.text != "永夜抄"


def test_extended_opcodes() -> None:
    """扩展 opcode 15-22 的参数布局。"""
    msg = [
        _instr(0, 15, struct.pack("<5i", 2, 10, -1, 20, 30)),
        _instr(1, 19, "表題".encode("shift_jis") + b"\x00"),
        _instr(2, 21, struct.pack("<i", 120)),
        _instr(3, 0),
    ]
    seq = parse_msg(_build(msg)).messages[0]
    cap = seq[0]
    assert isinstance(cap, ConfigureAllPortraits)
    assert cap.portrait_idx == 2 and cap.sprites == (10, -1, 20, 30)
    top = seq[1]
    assert isinstance(top, ShowTopText) and top.text == "表題"
    sel = seq[2]
    assert isinstance(sel, ShowSelection) and sel.duration == 120


def test_text_introduce() -> None:
    msg = [
        _instr(0, 8, struct.pack("<hh", 2, 1) + "一面".encode("shift_jis") + b"\x00"),
        _instr(1, 0),
    ]
    seq = parse_msg(_build(msg)).messages[0]
    intro = seq[0]
    assert isinstance(intro, TextIntroduce)
    assert (intro.color, intro.line, intro.text) == (2, 1, "一面")


def test_errors() -> None:
    with pytest.raises(ParseError):
        parse_msg(b"\x01\x02")
    with pytest.raises(ParseError):
        parse_msg(struct.pack("<i", 99999))
    # 偏移越界
    with pytest.raises(ParseError):
        parse_msg(struct.pack("<2i", 1, 9999) + _instr(0, 0))
    # 缺 Delete 终止
    with pytest.raises(ParseError):
        parse_msg(_build([_instr(0, 4, struct.pack("<i", 10))]))
    # 未知 opcode
    with pytest.raises(ParseError):
        parse_msg(_build([_instr(0, 99), _instr(1, 0)]))
    # 参数截断
    with pytest.raises(ParseError):
        parse_msg(_build([_instr(0, 4, b"\x01"), _instr(1, 0)]))


def test_msgfile_struct_shape() -> None:
    f = parse_msg(_build([_instr(0, 0)]))
    assert isinstance(f, MsgFile)
    assert f.messages[0][0].time == 0
