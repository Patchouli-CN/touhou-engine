"""真 th07.dat 的 schemas 冒烟测试(needs_data, 仅本地跑)。"""

from __future__ import annotations

from touhou.engine import open_archive
from touhou.schemas.anm import parse_anm, sprite_image
from touhou.schemas.anm_script import AnmInstr
from touhou.schemas.archive import load_entry

from .conftest import DATA, needs_data

pytestmark = needs_data


def test_open_archive_pbg4_sniff() -> None:
    """不认格式名时按文件头认成 pbg4。"""
    arc = open_archive(DATA)
    assert arc.format_name == "pbg4"
    assert len(arc.entries) > 100


def test_open_archive_explicit_format() -> None:
    arc = open_archive(DATA, format_name="pbg4")
    assert "ascii.anm" in [e.name for e in arc.entries]


def test_anm_parse_real_file() -> None:
    """真 .anm 条目: entry/sprite/脚本指令 union 全通。"""
    arc = open_archive(DATA, format_name="pbg4")
    anm = parse_anm(load_entry(arc, "ascii.anm"), version=2)
    assert len(anm.entries) >= 1
    assert anm.entries[0].sprites
    assert anm.scripts[0]
    for escr in anm.scripts:
        for instrs in escr.values():
            assert all(isinstance(i, AnmInstr) for i in instrs)
    w, h, rgba = sprite_image(anm, 0)
    assert w > 0 and h > 0 and len(rgba) == w * h * 4


def test_anm_parse_all_entries() -> None:
    """全包 .anm 条目逐一解析(指令表覆盖率的事实核查)。"""
    arc = open_archive(DATA, format_name="pbg4")
    names = [e.name for e in arc.entries if e.name.endswith(".anm")]
    assert names
    for name in names:
        anm = parse_anm(load_entry(arc, name), version=2)
        assert anm.entries, name
