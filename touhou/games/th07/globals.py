"""th07 的全局计数状态: 樱点四元组/动态难度/对局计数(纯数据 + 入账方法)。

分数本体在 engine GlobalsField(score/gui_score); 本结构是 th07 专属计数
(GameManager.cpp 的 cherry/rank 段), 事件化计分走 GlobalsField, 计数变化
由 world 直接改写(结算语义出处 old/touhou/games/th07/globals.py)。
"""

from __future__ import annotations

import msgspec

#: cherryMax 相对 cherryStart 的上限(GameManager::IncreaseCherryMax)
CHERRY_MAX_RANGE = 9999990
#: cherryPlus 相对 cherryStart 的上限, 达到即触发森罗结界(GameManager::AddCherryPlus)
CHERRY_PLUS_RANGE = 50000

#: 动态难度表 g_RankArray[difficulty] = (初始rank, minRank, maxRank)
RANK_TABLE = (
    (16, 12, 20),  # Easy
    (16, 10, 32),  # Normal
    (16, 10, 32),  # Hard
    (16, 10, 32),  # Lunatic
    (16, 15, 16),  # Extra
    (16, 15, 16),  # Phantasm
)


class Th07Globals(msgspec.Struct):
    """一局游戏的 th07 专属计数(残机/炸弹/火力/樱点/rank/擦弹/符卡等)。"""

    # ---- 残机/炸弹/火力 ----
    lives: float = 3.0
    bombs: float = 2.0
    power: float = 0.0
    power_overflow: int = 0  # 满火力后小 P 计分计数(查 FULL_POWER_SCORE_BONUS)
    # ---- 樱点 ----
    cherry: int = 0
    cherry_max: int = 0
    cherry_plus: int = 0
    cherry_start: int = 0  # 本关樱点 baseline
    # ---- 动态难度(0..32 scale) ----
    rank: int = 16
    min_rank: int = 10
    max_rank: int = 32
    subrank: int = 0
    # ---- 计数 ----
    deaths: int = 0
    bombs_used: float = 0.0
    graze_in_stage: int = 0
    graze_in_total: int = 0
    spell_cards_captured: int = 0
    point_items_collected_this_stage: int = 0
    point_items_collected_for_extend: int = 0
    extends_from_point_items: int = 0
    next_needed_point_items_for_extend: int = 50

    def initialize_rank(self, difficulty: int) -> None:
        """按难度初始化 rank(GameManager::InitializeRank / g_RankArray)。"""
        self.rank, self.min_rank, self.max_rank = RANK_TABLE[difficulty]
        self.subrank = 0

    # ---- 樱点(GameManager::AddCherry/AddCherryPlus/IncreaseCherryMax) ----
    def add_cherry(self, x: int) -> None:
        """Cherry += x, 封顶 cherryMax。"""
        self.cherry = min(self.cherry + x, self.cherry_max)

    def add_cherry_plus(self, x: int) -> bool:
        """Cherry 与 cherryPlus 同时累加; 返回是否触达结界上限(cherryStart+50000)。"""
        self.cherry = min(self.cherry + x, self.cherry_max)
        if x > 0:
            self.cherry_plus = min(
                self.cherry_plus + x, self.cherry_start + CHERRY_PLUS_RANGE
            )
        return self.cherry_plus >= self.cherry_start + CHERRY_PLUS_RANGE

    def increase_cherry_max(self, x: int) -> None:
        """CherryMax += x, 封顶 cherryStart+9999990。"""
        self.cherry_max = min(self.cherry_max + x, self.cherry_start + CHERRY_MAX_RANGE)

    def subtract_cherry_drain(self, drain: int) -> None:
        """炸弹樱点消耗, 封底 cherryStart(PlayerBombInfo::SubtractCherryDrain)。"""
        if self.cherry - self.cherry_start >= drain:
            self.cherry -= drain
        else:
            self.cherry = self.cherry_start

    # ---- 动态难度 ----
    def increase_subrank(self, x: int) -> None:
        """GameManager::IncreaseSubrank: 每满 100 升 1 rank, 封顶 maxRank。"""
        self.subrank += x
        while 100 <= self.subrank:
            self.rank += 1
            self.subrank -= 100
        if self.rank > self.max_rank:
            self.rank = self.max_rank

    def decrease_subrank(self, x: int) -> None:
        """GameManager::DecreaseSubrank: 每欠 100 降 1 rank, 封底 minRank。"""
        self.subrank -= x
        while self.subrank < 0:
            self.rank -= 1
            self.subrank += 100
        if self.rank < self.min_rank:
            self.rank = self.min_rank
