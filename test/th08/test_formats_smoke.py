"""真 th08.dat 的格式冒烟测试(needs_data, 仅本地跑)。

th08 差异点: msg 文本 XOR 0x77 / sht 扩展布局 / thbgm game id 0x800。
"""

from __future__ import annotations

from touhou.engine import open_archive
from touhou.schemas.archive import (
    load_entry,
    try_decrypt_signed,
)
from touhou.schemas.msg import Dialogue, MsgInstr, parse_msg
from touhou.schemas.musiccmt import parse_musiccmt
from touhou.schemas.shot_data import parse_sht
from touhou.schemas.stage import parse_std
from touhou.schemas.stage_script import StdInstr
from touhou.schemas.thbgm import THBGM_HEADER_SIZE, check_thbgm_header, parse_fmt

from .conftest import DATA, needs_data

pytestmark = needs_data

THBGM_DAT = DATA.with_name("thbgm.dat")


def test_msg_parse_all_xor() -> None:
    """全部 msg*.dat(text_xor=0x77): 指令 union 全通, 对话文本可解码。"""
    arc = open_archive(DATA)
    names = [e.name for e in arc.entries if e.name.startswith("msg")]
    assert names
    saw_dialogue = False
    for name in names:
        f = parse_msg(try_decrypt_signed(load_entry(arc, name)), text_xor=0x77)
        for msg in f.messages:
            assert all(isinstance(i, MsgInstr) for i in msg)
            for i in msg:
                if isinstance(i, Dialogue) and i.text.strip():
                    saw_dialogue = True
    assert saw_dialogue


def test_std_parse_all() -> None:
    """全部 stage*.std(含 opcode 32-34 扩展覆盖核查)。"""
    arc = open_archive(DATA)
    names = [e.name for e in arc.entries if e.name.endswith(".std")]
    assert names
    seen_ops: set[str] = set()
    for name in names:
        std = parse_std(try_decrypt_signed(load_entry(arc, name)))
        assert std.objects, name
        assert all(isinstance(i, StdInstr) for i in std.script), name
        seen_ops.update(type(i).__name__ for i in std.script)
    # 报告扩展指令是否被真实数据用到(结果打在外层摘要里)
    print(f"\nstd instrs seen: {sorted(seen_ops)}")


def test_sht_parse_all_extended() -> None:
    arc = open_archive(DATA)
    names = [e.name for e in arc.entries if e.name.endswith(".sht")]
    assert names
    for name in names:
        sht = parse_sht(try_decrypt_signed(load_entry(arc, name)), extended=True)
        assert sht.levels, name
        assert sht.speed > 0, name
        for lv in sht.levels:
            assert lv.entries, name
        # 末档链哨兵是 4 字节截断记录(同基础布局), 不入列
        for lv in sht.levels[:-1]:
            assert lv.entries[-1].fire_interval < 0, name


def test_musiccmt_parse() -> None:
    arc = open_archive(DATA)
    tracks = parse_musiccmt(try_decrypt_signed(load_entry(arc, "musiccmt.txt")))
    assert len(tracks) >= 15
    for t in tracks:
        assert t.title


def test_thbgm_fmt_and_header() -> None:
    arc = open_archive(DATA)
    tracks = parse_fmt(try_decrypt_signed(load_entry(arc, "thbgm.fmt")))
    assert len(tracks) >= 15
    for t in tracks.values():
        assert t.name.endswith(".wav")
        assert 0 <= t.intro_length < t.total_length
    if THBGM_DAT.exists():
        header = THBGM_DAT.read_bytes()[:THBGM_HEADER_SIZE]
        assert check_thbgm_header(header, game_id=0x800)
