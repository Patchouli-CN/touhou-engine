"""全局状态骨架测试: 分数追赶/封顶 + 命名计数器 + 事件。

数值权威: GameManager::OnUpdate(guiScore 追赶) / AddScore / CutChain;
用例改写自 old/tests/test_globals_base.py(固定字段改为计数器组+事件形态)。
"""

from __future__ import annotations

from touhou.engine import (
    GUI_SCORE_INCREMENT_MAX,
    SCORE_MAX,
    CounterChanged,
    FrameContext,
    GlobalsField,
    Rng,
    ScoreChanged,
)


def _ctx() -> FrameContext:
    return FrameContext(Rng(0))


def _collect(ctx: FrameContext) -> list:
    got: list = []
    ctx.events.subscribe(got.append)
    return got


def test_add_score_divides_by_10() -> None:
    ctx = _ctx()
    got = _collect(ctx)
    g = GlobalsField()
    g.add_score(2000, ctx)  # 代码值 2000 → 入账 200
    assert g.score == 200
    g.add_score(15, ctx)  # 整数除法
    assert g.score == 201
    ctx.events.flush()
    evs = [e for e in got if isinstance(e, ScoreChanged)]
    assert evs[0].delta == 200 and evs[1].delta == 1 and evs[1].score == 201


def test_score_capped_at_max() -> None:
    g = GlobalsField(score=SCORE_MAX)
    g.add_score(5000, _ctx())
    g.tick_gui_score()
    assert g.score == SCORE_MAX


def test_gui_score_chases_and_converges() -> None:
    g = GlobalsField()
    g.add_score(32000, _ctx())  # score = 3200
    g.tick_gui_score()
    # 第一帧 inc = 3200>>5 = 100
    assert g.gui_score == 100
    assert g.gui_score_difference == 100
    for _ in range(60):
        g.tick_gui_score()
    assert g.gui_score == g.score == 3200
    assert g.gui_score_difference == 0  # 追上归零


def test_gui_score_increment_min_one() -> None:
    g = GlobalsField(score=1)
    g.tick_gui_score()
    assert g.gui_score == 1  # 差值>>5==0 时最小步进 1


def test_gui_score_increment_capped() -> None:
    g = GlobalsField(score=100_000_000)
    g.tick_gui_score()
    assert g.gui_score == GUI_SCORE_INCREMENT_MAX
    assert g.gui_score_difference == GUI_SCORE_INCREMENT_MAX


def test_snap_gui_score() -> None:
    g = GlobalsField(score=12345)
    g.snap_gui_score()
    assert g.gui_score == 12345 and g.gui_score_difference == 0


def test_counters_carry_events() -> None:
    """计数器组: 作品自定字段语义(残机/bomb/火力), 增减产 CounterChanged。"""
    ctx = _ctx()
    got = _collect(ctx)
    g = GlobalsField()
    assert g.counter("lives") == 0.0  # 未设过为 0
    g.set_counter("lives", 3.0, ctx)
    g.adjust("lives", -1, ctx)
    g.adjust("bombs", 3, ctx)
    assert g.counter("lives") == 2.0 and g.counter("bombs") == 3.0
    ctx.events.flush()
    evs = [e for e in got if isinstance(e, CounterChanged)]
    assert [(e.name, e.delta, e.value) for e in evs] == [
        ("lives", 3.0, 3.0),
        ("lives", -1, 2.0),
        ("bombs", 3, 3.0),
    ]
