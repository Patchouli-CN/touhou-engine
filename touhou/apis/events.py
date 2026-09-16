"""对局阶段与事件类别: GamePhase 枚举 / GameEventKind 常量 / GameEvent。"""

from __future__ import annotations

from enum import Enum

import msgspec


class GamePhase(Enum):
    """对局所处阶段(由内部状态推导)。"""

    RUNNING = "running"  # 正常游玩中
    DIALOG = "dialog"  # 对话中(可移动, 不能射击/Bomb)
    STAGE_CLEAR = "stage_clear"  # 过关结算面板显示中
    ENDING = "ending"  # 结局画面显示中
    GAME_OVER = "game_over"  # 无残机(续关菜单/冻结)
    RESULT = "result"  # 总结算已出(result 可读)


class GameEventKind:
    """通用事件类别(纯字符串常量)。

    只收全系列共有概念; 引擎事件流的其余事件(刷弹/擦弹/道具…)从
    ``Game.last_events`` 读原始 Event 对象, 不逐条映射进本类。
    """

    SPELLCARD_BEGIN = "spellcard_begin"  # name=符卡名
    SPELLCARD_CAPTURED = "spellcard_captured"  # name=符卡名
    SPELLCARD_END = "spellcard_end"  # 未捕获结束(超时/击破失败); name=符卡名
    PLAYER_DEATH = "player_death"
    BOMB_START = "bomb_start"
    EXTEND = "extend"  # 奖残(残机增加)
    STAGE_CLEAR = "stage_clear"  # stage=刚通过的关号
    GAME_OVER = "game_over"
    GAME_CLEAR = "game_clear"  # 通关(总结算)
    ENDING_START = "ending_start"  # 6 面通关进结局


class GameEvent(msgspec.Struct, frozen=True):
    """一帧内发生的事件。name/stage 仅在相关类别时有值。"""

    kind: str
    frame: int
    name: str | None = None
    stage: int | None = None
