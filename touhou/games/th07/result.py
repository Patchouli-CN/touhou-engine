"""th07 的结局/续关/总结算链: 6 面结局进出、GameOver 续关语义、通关入账。

移植 old/touhou/games/th07/world.py 的 _enter_ending/finish_ending/
continue_available/continue_play/finalize_game_over/final_result; C++ 出处
随各函数单行注释(Gui.cpp NEXT_LEVEL / AsciiManager.cpp RetryMenu /
ResultScreen.cpp)。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ...engine.score_store import make_highscore_record
from .ending import generic_ending, load_ending
from .results import RunStats, clear_percent, rating

if TYPE_CHECKING:
    from .world import Th07World  # 仅类型检查期(运行时本模块被 world/msg 引用)


# ---- 结局(6 面通关) ----


def enter_ending(w: Th07World) -> None:
    """6 面通关 → 结局 (Gui.cpp NEXT_LEVEL currentStage==6 → curState=9)。

    结局文件 (Ending.cpp:499-505): numRetries!=0 → bad ending, 否则按机体
    正常结局; 资源缺失退化为通用通关画面。游戏画面冻结, view 看完调
    finish_ending() 进总结算。
    """
    # 出处 old/touhou/games/th07/world.py:1227 (_enter_ending)
    w.globals.snap_gui_score()  # NEXT_LEVEL: guiScore 对齐真实分
    w.stage_results = None
    assert w.archive is not None
    try:
        w.ending = load_ending(w.archive, w.character, bad=w.th07.num_retries > 0)
    except (KeyError, ValueError, OSError):
        w.ending = generic_ending()


def finish_ending(w: Th07World) -> None:
    """结局看完(view 确认) → 总结算 (Ending 结束 → ResultScreen)。"""
    # 出处 old/touhou/games/th07/world.py:1252
    if w.ending is None:
        return
    w.ending = None
    w.cleared = True
    w.result = final_result(w, cleared=True)


# ---- 续关(GameOver) ----


def continue_available(w: Th07World) -> bool:
    """续关菜单是否可出现 (AsciiManager.cpp:839-846 的门控: 次数尽/Extra 跳过)。"""
    # 出处 old/touhou/games/th07/world.py:1261
    return (
        w.game_over
        and w.result is None
        and w.difficulty < 4
        and w.th07.num_retries < w.max_retries
    )


def finalize_game_over(w: Th07World) -> None:
    """续关菜单选 No (RetryMenu case 4 → curState=6 ResultScreen): 进结算。"""
    # 出处 old/touhou/games/th07/world.py:1273
    if w.game_over and w.result is None:
        w.result = final_result(w, cleared=False)


def continue_play(w: Th07World) -> None:
    """续关(retry 菜单 Yes, AsciiManager.cpp:955-976)。

    当场复活接着玩(玩家已重生, 不重来本关)。重置清单:
    numRetries++; score 清零(C: guiScore=numRetries→score=guiScore);
    残机回开局数; bomb 回满; power=0; cherry=cherryStart;
    grazeInStage/本关点道具/奖残进度清零。保留: grazeInTotal/rank/
    deaths/bombsUsed/spellCardsCaptured/已过面进度。
    """
    # 出处 old/touhou/games/th07/world.py:1283
    if not continue_available(w):
        return
    g = w.th07
    g.num_retries += 1
    w.globals.gui_score = g.num_retries  # C: guiScore = numRetries (≈0)
    w.globals.gui_score_difference = 0
    w.globals.score = w.globals.gui_score  # C: score = guiScore
    g.lives = float(w.initial_lives)
    g.bombs = w.initial_bombs
    g.power = 0.0
    g.cherry = g.cherry_start
    g.graze_in_stage = 0
    g.point_items_collected_this_stage = 0
    g.point_items_collected_for_extend = 0
    g.extends_from_point_items = 0
    g.next_needed_point_items_for_extend = 50
    w.game_over = False
    w.result = None
    w.result_cache = None


# ---- 总结算(通关/GameOver) ----


def final_result(
    w: Th07World,
    *,
    cleared: bool = False,
    slow_percent: float = 0.0,
    name: str | None = None,
) -> dict:
    """结算: 汇总 globals → 评级 + 入榜 + 写 store(内存), 返回结算数据(view 消费)。

    slow_percent: 固定 60fps 下恒 0(无减速统计), 参数仅留接口。
    name: 入榜记录名; None = 带出 LSNM(store.last_name)。
    幂等: 一局只结算一次(重复调用返回缓存, 不重复入榜/计数);
    落盘由调用方(view 结算画面确认时)负责。
    """
    # 出处 old/touhou/games/th07/world.py:1891
    if w.result_cache is not None:
        return w.result_cache
    if name is None:
        name = w.store.last_name
    g = w.th07
    w.globals.snap_gui_score()  # CutChain: 显示分对齐真实分
    stats = RunStats(
        score=w.globals.score,
        difficulty=w.difficulty,
        deaths=float(g.deaths),
        bombs_used=g.bombs_used,
        retries=g.num_retries,
        spellcards_captured=g.spell_cards_captured,
        graze_total=g.graze_in_total,
        # 点道具: 已过关面的累计 + 本关(换关入账前关, 终面用当前值)
        point_items_collected=(
            w.point_items_prev_stages + g.point_items_collected_this_stage
        ),
        cleared=cleared,
        clear_percent=1.0 if cleared else clear_percent(w.frame / 60.0),
        play_time_frames=w.frame,
    )
    rank_value = rating(stats, slow_percent=slow_percent)
    rec = make_highscore_record(
        w.globals.score,
        w.character,
        w.difficulty,
        w.stage_no,
        name=name,
        num_retries=g.num_retries,
    )
    pos = w.store.insert_score(rec)
    if cleared:
        # CLRD: currentStage-1 = 通过的面数, 取 max (GameManager.cpp 过关时)
        w.store.record_clear(w.character, w.difficulty, w.stage_no, g.num_retries)
    w.store.record_run_end(
        w.character,
        w.difficulty,
        score=w.globals.score,
        frames=w.frame,
        cleared=cleared,
        num_retries=g.num_retries,
    )
    w.result_cache = {
        "score": w.globals.score,
        "rating": round(rank_value, 1),
        "rank": pos,
        "cleared": cleared,
        "clear_percent": stats.clear_percent * 100.0,
        "difficulty": w.difficulty,
        "character": w.character,
        "stage": w.stage_no,
        "name": name,
        "retries": g.num_retries,
        "deaths": g.deaths,
        "bombs": int(g.bombs_used),
        "spellcards": g.spell_cards_captured,
        "graze": g.graze_in_total,
        "point_items": stats.point_items_collected,
        "slow_percent": slow_percent,
        "high_score": w.store.high_score(w.difficulty, w.character),
    }
    return w.result_cache
