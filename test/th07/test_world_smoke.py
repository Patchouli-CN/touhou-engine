"""th07 一面 headless 冒烟(needs_data): 组合根世界跑 N 帧, 关键事件序列/结算断言 + 确定性。"""

from __future__ import annotations

from collections import Counter

from touhou.engine import Button, InputFrame
from touhou.engine.boss import SpellcardBegan, SpellcardEnded
from touhou.engine.enemies import EnemySpawned
from touhou.engine.events import Event
from touhou.games.th07.compose import compose
from touhou.games.th07.world import Th07World, compose_world

from .conftest import needs_data

pytestmark = needs_data


def _wiggle(i: int) -> InputFrame:
    """射击 + 40 帧周期左右扫(喂移动输入, 同时覆盖道具落点)。"""
    held = {Button.SHOT}
    if (i // 40) % 2 == 0:
        held.add(Button.RIGHT)
    else:
        held.add(Button.LEFT)
    return InputFrame(held=frozenset(held))


def _shoot_only(i: int) -> InputFrame:
    """站桩按住射击(火力直线上行, 集中打 boss)。"""
    return InputFrame(held=frozenset({Button.SHOT}))


def _run(
    frames: int, difficulty: int, input_of, *, lives: float | None = None
) -> tuple[Th07World, list[Event]]:
    """seed=42 组一个一面世界跑 frames 帧, 返回 (世界, 事件流)。"""
    w = compose_world(compose(), character=0, difficulty=difficulty, seed=42)
    if lives is not None:
        w.th07.lives = lives  # 夹具续命(看长程流程; 结算逻辑与残机数无关)
    log: list[Event] = []
    w.subscribers.append(log.append)
    for i in range(frames):
        w.tick(input_of(i))
    return w, log


def _counts(log: list[Event]) -> Counter[str]:
    return Counter(type(e).__name__ for e in log)


def test_stage_one_smoke() -> None:
    """一面 3600 帧(Normal): 刷怪/弹幕/射击/命中/掉落收集全通, 残机打空冻结。"""
    w, log = _run(3600, 1, _wiggle)
    c = _counts(log)
    spawns = [e for e in log if isinstance(e, EnemySpawned)]
    # 开幕波次(真机时间轴): 首架 sub1 + 前 10 架 sub3 开幕妖精
    assert [e.sub_id for e in spawns[:11]] == [1] + [3] * 10
    assert len(spawns) == 144
    assert c["ShotFired"] > 0  # 自机射击
    assert c["BulletSpawned"] > 0  # 敌弹发射
    assert c["EnemyDamaged"] > 0 and c["EnemyDied"] > 0  # 命中结算
    assert c["ItemCollected"] > 0  # 掉落收集
    assert c["BulletGraze"] > 0  # 擦弹
    assert w.globals.score > 0  # 得分入账
    assert w.player.pos.x != 192.0  # 移动输入生效(出生 x=192)
    # 中超 boss 建档(ecldata1 出场于 2667 帧前后)
    assert w.boss is not None and w.boss.boss_id == 0
    # 3 残机打空: 死亡结算/重生各 4 次, GameOver 后画面冻结(帧号停走)
    assert c["PlayerDied"] == 4 and c["PlayerDeathSettled"] == 4
    assert c["PlayerRespawned"] == 4
    assert w.th07.lives == 0.0 and w.game_over
    assert w.frame == 3023


def test_spellcard_lifecycle() -> None:
    """Hard 7500 帧(站桩): 中超符卡宣言 → 击破收场(中弹过 → 未捕获)入账。"""
    w, log = _run(7500, 2, _shoot_only, lives=99.0)
    began = [e for e in log if isinstance(e, SpellcardBegan)]
    ended = [e for e in log if isinstance(e, SpellcardEnded)]
    assert began == [SpellcardBegan(boss_id=0, spellcard_idx=0, time_limit=2280)]
    assert ended == [
        SpellcardEnded(boss_id=0, spellcard_idx=0, captured=False, timed_out=False)
    ]
    assert w.th07.spell_cards_captured == 0  # 符卡中死过, 不算捕获
    assert w.globals.score > 0
    assert _counts(log)["ScoreChanged"] > 0  # 计分事件流在出
    # 中超击破后时间轴推进到尾王前置对话(msg 接线后对话门控停轴, 尾王尚未入场)
    assert w.boss is None
    assert w.msg_active


def test_deterministic_replay() -> None:
    """同种子同输入两遍: 事件流逐条一致, 终态分数一致。"""
    w1, log1 = _run(3600, 1, _wiggle)
    w2, log2 = _run(3600, 1, _wiggle)
    assert [type(e).__name__ for e in log1] == [type(e).__name__ for e in log2]
    assert log1 == log2
    assert w1.globals.score == w2.globals.score
    assert w1.frame == w2.frame
