"""真 th07.dat 的剩余格式冒烟测试(needs_data, 仅本地跑)。"""

from __future__ import annotations

from touhou.schemas.archive import load_entry, open_archive
from touhou.schemas.msg import Dialogue, MsgInstr, parse_msg
from touhou.schemas.musiccmt import parse_musiccmt
from touhou.schemas.shot_data import parse_sht
from touhou.schemas.sound import SOUND_EFFECTS
from touhou.schemas.stage import parse_std
from touhou.schemas.stage_script import StdInstr
from touhou.schemas.thbgm import THBGM_HEADER_SIZE, check_thbgm_header, parse_fmt

from .conftest import DATA, needs_data

pytestmark = needs_data

#: thbgm.dat 与 th07.dat 同目录(高音质 BGM 流)
THBGM_DAT = DATA.with_name("thbgm.dat")


def test_msg_parse_all() -> None:
    """全部 msgN.dat: 指令 union 全通, 至少一条 Dialogue 有日文文本。"""
    arc = open_archive(DATA)
    names = [e.name for e in arc.entries if e.name.startswith("msg")]
    assert len(names) == 8
    saw_dialogue = False
    for name in names:
        f = parse_msg(load_entry(arc, name))
        assert f.messages, name
        for msg in f.messages:
            assert all(isinstance(i, MsgInstr) for i in msg)
            for i in msg:
                if isinstance(i, Dialogue) and i.text.strip():
                    saw_dialogue = True
    assert saw_dialogue


def test_std_parse_all() -> None:
    """全部 stageN.std: 物件/实例/脚本指令 union 全通。"""
    arc = open_archive(DATA)
    names = [e.name for e in arc.entries if e.name.endswith(".std")]
    assert len(names) == 8
    for name in names:
        std = parse_std(load_entry(arc, name))
        assert std.title, name
        assert std.objects, name
        assert all(isinstance(i, StdInstr) for i in std.script), name
        assert std.main_bgm, name


def test_sht_parse_all() -> None:
    """全部 .sht: 条目链非空, 非末档链以哨兵收尾(末档哨兵是截断记录, 不入列)。"""
    arc = open_archive(DATA)
    names = [e.name for e in arc.entries if e.name.endswith(".sht")]
    assert len(names) == 12
    for name in names:
        sht = parse_sht(load_entry(arc, name))
        assert sht.levels, name
        assert sht.speed > 0, name
        for lv in sht.levels:
            assert lv.entries, name
        for lv in sht.levels[:-1]:
            assert lv.entries[-1].fire_interval < 0, name


def test_musiccmt_parse() -> None:
    arc = open_archive(DATA)
    tracks = parse_musiccmt(load_entry(arc, "musiccmt.txt"))
    assert len(tracks) >= 15
    for t in tracks:
        assert t.path.startswith("bgm/")
        assert t.title


def test_thbgm_fmt_and_header() -> None:
    arc = open_archive(DATA)
    tracks = parse_fmt(load_entry(arc, "thbgm.fmt"))
    assert len(tracks) >= 15
    for t in tracks.values():
        assert t.name.endswith(".wav")
        assert 0 <= t.intro_length < t.total_length
        assert t.sample_rate == 44100
    if THBGM_DAT.exists():
        header = THBGM_DAT.read_bytes()[:THBGM_HEADER_SIZE]
        assert check_thbgm_header(header, game_id=0x700)


def test_sound_effects_wavs_exist() -> None:
    """SE 表引用的 wav 全在包里。"""
    arc = open_archive(DATA)
    names = {e.name for e in arc.entries}
    for se in SOUND_EFFECTS:
        assert se.file_name in names, se.file_name
