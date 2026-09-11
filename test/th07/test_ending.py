"""th07 结局文件测试: 结局文件名映射 + 真实 .end 解析/播放(needs_data)。

改写自 old/tests/game_test/th07/test_th07_ending.py 与
test_th07_stage_transition.py 的 .end 段。
"""

from __future__ import annotations

from touhou.engine import open_archive
from touhou.engine.ending import EndingPlayer
from touhou.games.th07.ending import ending_path, load_ending
from touhou.schemas.archive import load_entry
from touhou.schemas.ending import Load, parse_end

from .conftest import DATA, needs_data


def test_ending_path_mapping() -> None:
    """end{char}{shot}.end / bad 按自机共用 end{char}0b.end (Ending.cpp:499-505)。"""
    assert ending_path(0, bad=False) == "end00.end"
    assert ending_path(5, bad=False) == "end21.end"
    assert ending_path(2, bad=True) == "end10b.end"
    assert ending_path(5, bad=True) == "end20b.end"


def _archive():
    return open_archive(DATA, format_name="pbg4")


@needs_data
def test_real_end_files_parse() -> None:
    """真实 end00/end10/end20b: 全部能解出文本与背景段。"""
    arc = _archive()
    for path in ("end00.end", "end10.end", "end20b.end"):
        f = parse_end(load_entry(arc, path))
        assert f.segments and sum(len(s.lines) for s in f.segments) >= 5
        assert any(s.bg for s in f.segments)


@needs_data
def test_real_ending_and_staff_roll() -> None:
    """end00.end 全程 + @F staff00.end staff roll: 文本/CG/滚动/音乐事件全通。"""
    arc = _archive()
    ending = load_ending(arc, character=0, bad=False)
    assert Load("staff00.end") in ending.ops
    p = EndingPlayer(ending.ops, loader=lambda name: load_entry(arc, name))
    saw_face = False
    saw_staff_bg = False
    saw_ending_no = False
    frames = 0
    while not p.done and frames < 60000:
        p.tick()
        saw_face = saw_face or bool(p.faces)
        saw_staff_bg = saw_staff_bg or p.bg_name == "staff00.jpg"
        saw_ending_no = saw_ending_no or any("ＥＮＤＩＮＧ" in t.text for t in p.texts)
        frames += 1
    assert p.done  # staff00.end 的 @z
    assert saw_ending_no  # end00.end 的 "ＥＮＤＩＮＧ　Ｎｏ．４" 行
    assert saw_face and saw_staff_bg  # staff roll: CG 立绘 + staff00.jpg
    plays = [n for k, n in p.music_events if k == "play"]
    assert plays == ["th07_14.mid", "th07_15.mid"]  # 结局曲 → staff 曲
    assert ("fadeout", 5) in p.music_events  # @M5


@needs_data
def test_real_bad_ending_also_has_staff_roll() -> None:
    """Bad ending (end00b.end): 末尾同样 @F 接 staff roll (原版如此)。"""
    arc = _archive()
    ending = load_ending(arc, character=0, bad=True)
    assert Load("staff00.end") in ending.ops
    p = EndingPlayer(ending.ops, loader=lambda name: load_entry(arc, name))
    frames = 0
    saw_staff_bg = False
    while not p.done and frames < 60000:
        p.tick()
        saw_staff_bg = saw_staff_bg or p.bg_name == "staff00.jpg"
        frames += 1
    assert p.done and saw_staff_bg
