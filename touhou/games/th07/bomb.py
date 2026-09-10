"""th07 的炸弹场: BombField 子类(12 套机体 calc 查表分派 + 樱点 drain) + 触发出账常量。

机体 calc 与 drain 公式在同包 bomb_calcs.py; 本模块是世界/测试的引用面。
触发后的计数扣减/决死窗/符卡 used_bomb 由世界层 Th07BombSystem 同步入账
(须先于 PlayerSystem, 见 world.py); BombStarted 订阅只挂音效(settle.py)。
"""

from __future__ import annotations

import msgspec

from ...engine.bomb import BombContext, BombField
from ...engine.context import FrameContext
from ...utils.math import Vec2
from .bomb_calcs import (  # 再导出: 引用面集中回本模块(对齐旧 bomb.py 单一模块)
    BOMB_CALCS,
    BOMB_PARAMS,
    CHAR_MARISA_A,
    CHAR_MARISA_B,
    CHAR_REIMU_A,
    CHAR_REIMU_B,
    CHAR_SAKUYA_A,
    CHAR_SAKUYA_B,
    EVENT_END_PLAYER_SPELLCARD,
    EVENT_REMOVE_ALL_ITEMS,
    EVENT_STOP_BULLET_MOVEMENT,
    BombParams,
    compute_bomb_cherry_drain,
)

__all__ = [
    "BOMB_PARAMS",
    "BOMB_SOUNDS",
    "BOMB_SUBRANK_PENALTY",
    "EVENT_END_PLAYER_SPELLCARD",
    "EVENT_REMOVE_ALL_ITEMS",
    "EVENT_STOP_BULLET_MOVEMENT",
    "SE_BOMB",
    "BombParams",
    "Th07BombContext",
    "Th07BombField",
    "compute_bomb_cherry_drain",
]

BOMB_SUBRANK_PENALTY = 200  # DecreaseSubrank(200) (Player.cpp:1747)

# 炸弹发声音 (BombData.cpp 各 *Calc 的 timer==0 分支; 音效号出处 old schema/sound.py)
SE_BOMB_SAKUYA_A = 5  # se_power0
SE_BOMB_REIMARI = 6  # se_power1
SE_BOMB_MARISA_A_FOCUS = 7  # se_tan00
SE_BOMB_REIMU_A = 13  # se_gun00
SE_BOMB = 14  # se_cat00 (符卡宣告/炸弹横幅, Gui::ShowSpellcard)
SE_BOMB_SAKUMARI = 19  # se_nep00

#: (character, focus) → 炸弹发声音 (旧 world.py:100-113)
BOMB_SOUNDS: dict[tuple[int, bool], int] = {
    (CHAR_REIMU_A, False): SE_BOMB_REIMU_A,  # :180
    (CHAR_REIMU_A, True): SE_BOMB_REIMU_A,  # :374
    (CHAR_REIMU_B, False): SE_BOMB_REIMARI,  # :542
    (CHAR_REIMU_B, True): SE_BOMB_REIMARI,  # :653
    (CHAR_MARISA_A, False): SE_BOMB_REIMARI,  # :737
    (CHAR_MARISA_A, True): SE_BOMB_MARISA_A_FOCUS,  # :866
    (CHAR_MARISA_B, False): SE_BOMB_SAKUMARI,  # :990
    (CHAR_MARISA_B, True): SE_BOMB_SAKUMARI,  # :1117
    (CHAR_SAKUYA_A, False): SE_BOMB_SAKUYA_A,  # :1219
    (CHAR_SAKUYA_A, True): SE_BOMB_SAKUYA_A,  # :1352
    (CHAR_SAKUYA_B, False): SE_BOMB_SAKUMARI,  # :1516
    (CHAR_SAKUYA_B, True): SE_BOMB_SAKUMARI,  # :1658
}


class Th07BombContext(BombContext):
    """bombCalc 的每帧外部输入(th07 扩展: 樱点/追踪目标)。last_enemy_hit x<=-100 → 追玩家。"""

    cherry: float = 0.0
    cherry_start: float = 0.0
    last_enemy_hit: Vec2 = Vec2(-999.0, -999.0)


class Th07BombField(BombField[Th07BombContext]):
    """一次炸弹的生命周期(th07): (character, focus) 查表分派 + 每帧樱点 drain 透出。

    上层每帧另消费 drain_applied(本帧应扣樱点)与 events/shakes(世界层
    Th07BombSystem 消费后清空)。
    """

    character: int = CHAR_REIMU_A
    cherry_drain: int = 0
    drain_applied: int = 0  # 本帧应扣樱点(上层调 subtract_cherry_drain)
    events: list[str] = msgspec.field(default_factory=list)
    shakes: list[tuple[int, int, int]] = msgspec.field(
        default_factory=list
    )  # 震屏(view 数据源)

    def _calc(self, ctx: FrameContext, bctx: Th07BombContext) -> None:
        """按 (character, focus) 查表分派 (g_BombData, BombData.cpp:16-28)。"""
        calc = BOMB_CALCS.get((self.character, self.is_focus))
        if calc is None:  # 12 套已全, 仅防御未知 character
            raise NotImplementedError(
                f"character={self.character} focus={self.is_focus} 炸弹未实现"
            )
        calc(self, ctx, bctx)

    def _tick_resource_cost(self, in_use: bool) -> None:
        """每帧扣樱点 (Player.cpp:1705-1708): 非 bomb 中清零, 否则透出 cherry_drain。"""
        if not in_use:
            self.drain_applied = 0
        else:
            self.drain_applied = self.cherry_drain if self.has_ticked else 0

    def _reset_run_state(self) -> None:
        """start() 时清零樱点消耗/事件/震屏状态。"""
        self.cherry_drain = 0
        self.drain_applied = 0
        self.events = []
        self.shakes = []
