"""th07 的结算统计与评级 —— 移植 old/touhou/games/th07/results.py(ResultScreen.cpp)。"""

from __future__ import annotations

import msgspec

# 难度权重: {Easy, Normal, Hard, Lunatic, Extra}(Phantasm 复用 Extra)
DIFFICULTY_WEIGHTS = (-30, -10, 20, 30, 30)
# 符卡权重: 每张捕获的分值倍率
SPELLCARD_WEIGHTS = (1, 1.5, 1.5, 2, 2.5)


class RunStats(msgspec.Struct):
    """一局的运行时累计统计(总结算的输入)。"""

    score: int = 0
    difficulty: int = 1  # 0..5
    deaths: float = 0.0  # Miss 数
    bombs_used: float = 0.0
    retries: int = 0  # Continue 数
    spellcards_captured: int = 0
    graze_total: int = 0
    point_items_collected: int = 0
    cleared: bool = False
    clear_percent: float = 0.0  # 通关率(未通关时 <1)
    play_time_frames: int = 0  # 帧计时(用于 slow%)


def rating(stats: RunStats, *, slow_percent: float = 0.0) -> float:
    """综合评价 `rankingProbably`。slow_percent 为减速百分比(0..100)。"""
    d = min(stats.difficulty, 4)  # Phantasm 复用 Extra 权重
    score = stats.score
    r = 0.0

    # 分数段
    if score < 2_000_000:
        r -= 20
    elif score < 200_000_000:
        r += -20 + (score - 2_000_000) / 198_000_000 * 60
    else:
        r += 40
    r += DIFFICULTY_WEIGHTS[d]

    # 通关率
    if stats.cleared:
        r += 70
    else:
        r += stats.clear_percent * 70

    # 续关/死亡/炸弹
    r -= stats.retries * 10
    r += -stats.deaths * 5 + 10
    r += -stats.bombs_used * 2 + 10
    # 符卡
    r += stats.spellcards_captured * SPELLCARD_WEIGHTS[d]

    # 减速(作弊/超减速 → -999)
    if slow_percent < 50:
        r += -70 * slow_percent / 100
    else:
        return -999.0

    # 点道具/擦弹
    r += (
        (0.01 * stats.point_items_collected) if stats.point_items_collected < 800 else 8
    )
    r += (0.0025 * stats.graze_total) if stats.graze_total < 5000 else 12.5
    return r


def clear_percent(stage_seconds: float) -> float:
    """由通关用时换算通关率(基于规格中的时间基准)。"""
    return min(0.99, stage_seconds * 60.0 / 180621.0)
