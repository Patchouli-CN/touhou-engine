"""真 th08.dat 的 ECL 冒烟测试(needs_data, 仅本地跑)。

条目带 edz 内层加密, 解析前一律先过 try_decrypt_signed; v800 布局。
"""

from __future__ import annotations

import msgspec

from touhou.engine import open_archive
from touhou.games.th08.ecl_table import ECL_INSTR_SET, parse_ecl
from touhou.schemas.archive import (
    load_entry,
    try_decrypt_signed,
)
from touhou.schemas.ecl import (
    EclInstr,
    SubEnd,
    TlInstr,
    decode_instr,
    encode_instr,
)

from .conftest import DATA, needs_data

pytestmark = needs_data


def _load_ecls() -> list[tuple[str, object]]:
    arc = open_archive(DATA)
    names = sorted(e.name for e in arc.entries if e.name.endswith(".ecl"))
    return [(n, parse_ecl(try_decrypt_signed(load_entry(arc, n)))) for n in names]


def test_ecl_parse_all_v800() -> None:
    """全部 ecldata*.ecl: sub/时间轴全量 decode, 指令表覆盖率核查。"""
    files = _load_ecls()
    assert files
    seen: set[str] = set()
    for name, f in files:
        assert f.subs, name
        for sub in f.subs:
            assert all(isinstance(i, EclInstr) for i in sub.instrs), name
            assert isinstance(sub.instrs[-1], SubEnd), name
            seen.update(type(i).__name__ for i in sub.instrs)
        for tl in f.timelines:
            assert all(isinstance(i, TlInstr) for i in tl), name
    print(f"\necl instr classes seen: {len(seen)}")


def test_ecl_encode_self_consistent() -> None:
    """Decode → encode → decode 自洽。"""
    for name, f in _load_ecls():
        for sub in f.subs:
            for ins in sub.instrs:
                again = decode_instr(
                    encode_instr(ins, instrs=ECL_INSTR_SET), 0, instrs=ECL_INSTR_SET
                )
                assert again == msgspec.structs.replace(ins, offset=0), (name, ins)
