"""真 th07.dat 的 ECL 冒烟测试(needs_data, 仅本地跑)。"""

from __future__ import annotations

import msgspec

from touhou.engine import open_archive
from touhou.games.th07.ecl_table import ECL_INSTR_SET, parse_ecl
from touhou.schemas.archive import load_entry
from touhou.schemas.ecl import (
    EclInstr,
    SubEnd,
    TlInstr,
    decode_instr,
    encode_instr,
)

from .conftest import DATA, needs_data

pytestmark = needs_data


def test_ecl_parse_all() -> None:
    """全部 ecldata*.ecl(v0 布局): sub/时间轴全量 decode, 指令表覆盖率核查。"""
    arc = open_archive(DATA, format_name="pbg4")
    names = sorted(e.name for e in arc.entries if e.name.endswith(".ecl"))
    assert names
    seen: set[str] = set()
    for name in names:
        f = parse_ecl(load_entry(arc, name))
        assert f.subs, name
        for sub in f.subs:
            assert all(isinstance(i, EclInstr) for i in sub.instrs), name
            assert isinstance(sub.instrs[-1], SubEnd), name
            seen.update(type(i).__name__ for i in sub.instrs)
        for tl in f.timelines:
            assert all(isinstance(i, TlInstr) for i in tl), name
    print(f"\necl instr classes seen: {len(seen)}")


def test_ecl_encode_self_consistent() -> None:
    """Decode → encode → decode 自洽(真实数据的 unused 头字节/杂散 mask 位不要求还原)。"""
    arc = open_archive(DATA, format_name="pbg4")
    names = sorted(e.name for e in arc.entries if e.name.endswith(".ecl"))
    for name in names:
        f = parse_ecl(load_entry(arc, name))
        for sub in f.subs:
            for ins in sub.instrs:
                again = decode_instr(
                    encode_instr(ins, instrs=ECL_INSTR_SET), 0, instrs=ECL_INSTR_SET
                )
                assert again == msgspec.structs.replace(ins, offset=0), (name, ins)
