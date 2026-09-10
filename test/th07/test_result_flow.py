"""th07 结局/续关/总结算链集成测试(needs_data)。

改写自 old/tests/game_test/th07/test_th07_stage_transition.py 与
test_th07_result_flow.py; 对照 Gui.cpp NEXT_LEVEL / Ending.cpp /
AsciiManager.cpp RetryMenu。
"""

from __future__ import annotations

from touhou.engine import Button, FrameContext, InputFrame
from touhou.engine.score_store import ScoreStore
from touhou.games.th07.compose import compose
from touhou.games.th07.msg import apply_next_level, apply_stage_results
from touhou.games.th07.result import (
    continue_available,
    continue_play,
    final_result,
    finalize_game_over,
    finish_ending,
)
from touhou.games.th07.world import Th07World, compose_world
from touhou.schemas.archive import load_entry, open_archive
from touhou.schemas.ending import parse_end

from .conftest import DATA, needs_data

pytestmark = needs_data

SPELLCARD_COUNT = 141  # th07 符卡总数


def _make(stage: int = 1, difficulty: int = 1, character: int = 0) -> Th07World:
    """跳关夹具: 直接组一个指定面的世界(独立内存成绩库)。"""
    return compose_world(
        compose(),
        character=character,
        difficulty=difficulty,
        stage_no=stage,
        seed=42,
        store=ScoreStore(spellcard_count=SPELLCARD_COUNT),
    )


def _shoot(i: int) -> InputFrame:
    return InputFrame(held=frozenset({Button.SHOT}))


def _stage_results(w: Th07World) -> None:
    """帧外调 apply_stage_results(add_score 要帧上下文; 正常路径在 tick 内)。"""
    w.ctx = FrameContext(w.rng, None)
    apply_stage_results(w)
    w.ctx = None


# ---- 6 面 → 结局 → 总结算 ----


def test_stage6_clear_goes_ending_then_result() -> None:
    """6 面 NEXT_LEVEL → 结局(冻结) → finish_ending → 总结算 + CLRD/入榜。"""
    w = _make(6, 1)
    _stage_results(w)  # msg STAGERESULTS 先行(结算面板)
    assert w.stage_results is not None and w.stage_results.all_clear
    apply_next_level(w)  # msg NEXT_LEVEL → enter_ending
    assert not w.pending_next_level  # 6 面不换关
    assert w.ending is not None and w.result is None
    # ReimuA 无续关 → 正常结局 end00.end
    arc = open_archive(DATA, format_name="pbg4")
    assert w.ending == parse_end(load_entry(arc, "end00.end"))
    assert w.stage_results is None  # 结算面板随结局撤下
    frame = w.frame
    w.tick(_shoot(0))
    assert w.frame == frame  # 结局期间游戏冻结
    finish_ending(w)
    r = w.result
    assert r is not None and r["cleared"] and r["clear_percent"] == 100.0
    assert r["stage"] == 6 and r["difficulty"] == 1 and r["character"] == 0
    assert w.cleared and w.ending is None
    assert w.store.clrd[0]["without_retries"][1] == 6  # CLRD: 通过 6 面
    assert w.store.plst["clear_count"] == 1
    assert len(w.store.entries(1, 0)) == 1  # 已入榜(内存)
    # 结算幂等: 再调 final_result 不重复入榜
    assert final_result(w, cleared=True) is r
    assert len(w.store.entries(1, 0)) == 1
    w.tick(_shoot(1))
    assert w.frame == frame  # 通关后游戏冻结


def test_stage6_ending_bad_on_retry() -> None:
    """numRetries!=0 → bad ending (Ending.cpp:499-505)。"""
    w = _make(6, 1)
    w.th07.num_retries = 1
    apply_next_level(w)
    arc = open_archive(DATA, format_name="pbg4")
    assert w.ending == parse_end(load_entry(arc, "end00b.end"))


def test_stage6_next_level_repeat_swallowed() -> None:
    """结局已进(result/ending 在)时重复 NEXT_LEVEL 被吞掉。"""
    w = _make(6, 1)
    apply_next_level(w)
    ending = w.ending
    apply_next_level(w)
    assert w.ending is ending and w.result is None


# ---- 7/8 面(Extra·Phantasm) → 直接总结算 ----


def test_stage7_extra_clear_goes_result_directly() -> None:
    """7 面(Extra) NEXT_LEVEL → 直接总结算, 不进结局。"""
    w = _make(7, 4)
    assert w.th07.lives == 2.0  # C: difficulty>=4 → lifeCount=2
    _stage_results(w)
    assert w.stage_results is not None and w.stage_results.penalty_line is None
    apply_next_level(w)
    assert w.ending is None
    assert w.cleared and w.result is not None and w.result["cleared"]
    assert w.result["stage"] == 7


def test_stage8_phantasm_clear_goes_result_directly() -> None:
    w = _make(8, 5)
    apply_next_level(w)
    assert w.cleared and w.result is not None and w.result["stage"] == 8


# ---- 续关(GameOver) ----


def test_game_over_waits_for_continue_choice() -> None:
    """难度<4 且次数未尽: game_over 后冻结待选, 选 No 才进结算。"""
    w = _make(1, 1)
    w.game_over = True
    assert continue_available(w)
    frame = w.frame
    w.tick(_shoot(0))
    assert w.result is None and w.frame == frame  # 待续关, 不自动结算
    assert len(w.store.entries(1, 0)) == 0
    finalize_game_over(w)  # RetryMenu 选 No → curState=6
    r = w.result
    assert r is not None and not r["cleared"]
    assert r["clear_percent"] < 100.0 and r["retries"] == 0
    assert len(w.store.entries(1, 0)) == 1


def test_continue_gating() -> None:
    """续关门控 (AsciiManager.cpp:839-846): Extra/次数用尽不进菜单, 直接结算。"""
    # Extra (difficulty>=4): 不可续关
    w = _make(7, 4)
    w.game_over = True
    assert not continue_available(w)
    continue_play(w)  # 无效
    assert w.game_over and w.th07.num_retries == 0
    w.tick(_shoot(0))
    assert w.result is not None and not w.result["cleared"]
    # 次数用尽 (numRetries >= maxRetries): 不可续关
    w2 = _make(1, 1)
    assert w2.max_retries == 3  # plst.total_frames=0 → <7h → 3
    w2.th07.num_retries = w2.max_retries
    w2.game_over = True
    assert not continue_available(w2)
    w2.tick(_shoot(0))
    assert w2.result is not None
    # 用尽前仍可续; 再死则不可续
    w3 = _make(1, 1)
    w3.th07.num_retries = w3.max_retries - 1
    w3.game_over = True
    assert continue_available(w3)
    continue_play(w3)
    assert w3.th07.num_retries == w3.max_retries
    w3.game_over = True
    assert not continue_available(w3)


def test_continue_play_resets_per_source() -> None:
    """续关 Yes 的重置清单 (AsciiManager.cpp:955-976): 分清零/残机回满等, 总量保留。"""
    w = _make(1, 1)
    w.game_over = True
    g = w.th07
    w.globals.score = 1234560
    w.globals.gui_score = 1234560
    g.power = 128.0
    g.cherry = g.cherry_start + 50000
    g.graze_in_stage = 55
    g.graze_in_total = 300
    g.point_items_collected_this_stage = 42
    g.point_items_collected_for_extend = 30
    g.extends_from_point_items = 1
    g.next_needed_point_items_for_extend = 100
    g.bombs = 0.0
    g.deaths = 2
    continue_play(w)
    assert not w.game_over and w.result is None and w.result_cache is None
    assert g.num_retries == 1
    assert w.globals.score == 1 and w.globals.gui_score == 1  # C: = numRetries
    assert g.lives == float(w.initial_lives)
    assert g.bombs == w.initial_bombs
    assert g.power == 0.0
    assert g.cherry == g.cherry_start
    assert g.graze_in_stage == 0
    assert g.point_items_collected_this_stage == 0
    assert g.point_items_collected_for_extend == 0
    assert g.extends_from_point_items == 0
    assert g.next_needed_point_items_for_extend == 50
    # 保留项
    assert g.graze_in_total == 300 and g.deaths == 2
    # 当场复活接着玩(不重开本关): 帧继续前进
    assert w.stage_no == 1
    w.tick(_shoot(0))
    assert w.frame == 1


def test_continue_marks_bad_ending() -> None:
    """续关标记影响结局: 续过关的 6 面通关 → bad ending。"""
    w = _make(6, 1)
    w.game_over = True
    continue_play(w)
    assert w.th07.num_retries == 1
    apply_next_level(w)
    arc = open_archive(DATA, format_name="pbg4")
    assert w.ending == parse_end(load_entry(arc, "end00b.end"))


# ---- 总结算字段 / store 入账 ----


def test_final_result_fields() -> None:
    """结算字段齐全(view 依赖): 分数/难度/各项计数/评级/名次/Slow%。"""
    w = _make(1, 3, character=2)
    r = final_result(w, cleared=False)
    for k in (
        "score",
        "rating",
        "rank",
        "cleared",
        "clear_percent",
        "difficulty",
        "character",
        "stage",
        "name",
        "retries",
        "deaths",
        "bombs",
        "spellcards",
        "graze",
        "point_items",
        "slow_percent",
        "high_score",
    ):
        assert k in r, k
    assert r["difficulty"] == 3 and r["character"] == 2
    assert r["slow_percent"] == 0.0  # 固定 60fps 恒 0
    assert r["name"] == "PLAYER"  # LSNM 缺省
    assert r["rank"] == 0 and r["high_score"] == 100000  # 空榜 → 榜首/底线
    assert w.store.plst["play_count"] == 1  # 开局计数(compose 入账)


def test_catk_recorded_on_real_spellcard() -> None:
    """真实 ECL 符卡 begin/end → catk attempts 入账(捕获 0: 符卡中死过)。"""
    w = _make(1, 2)  # Hard
    w.th07.lives = 99.0  # 夹具续命(看长程流程)
    for i in range(7500):
        w.tick(_shoot(i))
    entry = w.store.catk[0]  # 中超首张符卡(ecldata1 spellcard_idx=0)
    assert entry["attempts"][0] == 1 and entry["attempts"][6] == 1
    assert entry["name"]
    assert entry["successes"][0] == 0  # 符卡中弹过, 未捕获
    assert w.catk_idx is None  # 收场后复位
