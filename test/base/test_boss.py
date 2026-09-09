"""Boss 场测试: 生命阈值/阶段/符卡计时/失败/收取判定骨架。

数值权威: EclManager.cpp:658-752 (BeginSpellcard) / :755-849 (EndSpellcard) /
:2241-2257 (捕获分衰减) + EnemyManager.cpp:373-525 (HandleLifeCallback/
HandleTimerCallback); 用例改写自 old/tests/game_test/th07/test_th07_boss.py
(樱点惩罚/擦弹加成公式/符卡分值表内容属作品概念, 不搬)。
"""

from __future__ import annotations

from touhou.engine import (
    BossField,
    BossPhaseChanged,
    FrameContext,
    Rng,
    SpellcardBegan,
    SpellcardEnded,
    SpellcardFailed,
)

SCORES = (2_000_000, 2_200_000)  # 注入的分值表(形状对齐 g_SpellcardScore 即可)


def _ctx() -> FrameContext:
    return FrameContext(Rng(0))


def _collect(ctx: FrameContext) -> list:
    got: list = []
    ctx.events.subscribe(got.append)
    return got


def _boss(**kw) -> BossField:
    kw.setdefault("spellcard_scores", SCORES)
    return BossField(**kw)


# ---- 生命阈值 / 阶段 ----
def test_life_threshold_switches_phase() -> None:
    ctx = _ctx()
    got = _collect(ctx)
    b = _boss()
    b.set_life(1000)
    b.life_thresholds = [(800, 1), (400, 2)]
    b.life = 900
    assert b.check_life_threshold(ctx) == 0  # 未跌破
    b.life = 700
    assert b.check_life_threshold(ctx) == 1  # 跌破 800 → 阶段1
    assert b.life == 800 and b.phase == 1  # 钉住生命
    b.life = 300
    assert b.check_life_threshold(ctx) == 2
    ctx.events.flush()
    evs = [e for e in got if isinstance(e, BossPhaseChanged)]
    assert len(evs) == 2 and evs[0].phase == 1 and evs[0].callback == 1


def test_apply_damage_clamps_at_zero() -> None:
    b = _boss()
    b.set_life(500)
    b.apply_damage(70)
    assert b.life == 430
    b.apply_damage(9999)
    assert b.life == 0


# ---- 符卡 ----
def test_begin_and_capture_on_time() -> None:
    ctx = _ctx()
    got = _collect(ctx)
    b = _boss()
    b.begin_spellcard(ctx, 0, 60 * 60)
    assert b.is_active == 1 and b.is_capturing
    assert b.capture_score == SCORES[0]
    assert b.score_drain_rate == SCORES[0] // 70  # 2000000//70=28571
    assert b.end_spellcard(ctx) is True
    assert b.is_active == 0 and b.spellcard_idx == -1
    ctx.events.flush()
    assert any(isinstance(e, SpellcardBegan) and e.spellcard_idx == 0 for e in got)
    ended = [e for e in got if isinstance(e, SpellcardEnded)]
    assert ended and ended[0].captured and not ended[0].timed_out
    assert ended[0].score == SCORES[0]


def test_fail_on_bomb() -> None:
    """mark_bombed (Player.cpp:1745-1749): 不算捕获, usedBomb=isActive。"""
    ctx = _ctx()
    got = _collect(ctx)
    b = _boss()
    b.begin_spellcard(ctx, 0, 60 * 60)
    b.mark_bombed()
    assert not b.is_capturing and b.capture_score == 0 and b.used_bomb
    b.end_spellcard(ctx)
    ctx.events.flush()
    ended = [e for e in got if isinstance(e, SpellcardEnded)]
    assert ended and not ended[0].captured and ended[0].score == 0


def test_capture_score_decays_linearly() -> None:
    """每帧由基础分重算: captureScore = base - timer*drain/60, 向下取整 10。"""
    b = _boss()
    b.begin_spellcard(_ctx(), 0, 60 * 60)  # base=2000000, drain=28571
    prev = b.capture_score
    for _ in range(4200):  # 推进到 时间限制+10秒
        b.tick(_ctx())
        expect = max(0, int(SCORES[0] - b.timer * 28571 / 60.0))
        if expect > 0:
            expect -= expect % 10
        assert b.capture_score == expect
        assert b.capture_score <= prev  # 单调不增
        prev = b.capture_score
    assert b.capture_score < 100  # int 截断余量, 实际衰减到底


def test_timeout_fails_capture() -> None:
    """超时(on_timeout): 非 survival → is_active=2 + 捕获失败 + SpellcardFailed。"""
    ctx = _ctx()
    got = _collect(ctx)
    b = _boss()
    b.set_life(1000)
    b.begin_spellcard(ctx, 0, 600, timeout_sub=5)
    for _ in range(600):
        b.tick(ctx)
    b.on_timeout(ctx)
    assert b.is_active == 2 and not b.is_capturing and b.capture_score == 0
    assert b.timer_callback_threshold == 600  # 阈值登记在 begin 时一并写入
    assert b.end_spellcard(ctx) is True
    ctx.events.flush()
    assert any(isinstance(e, SpellcardFailed) and e.spellcard_idx == 0 for e in got)
    ended = [e for e in got if isinstance(e, SpellcardEnded)]
    assert ended and ended[0].timed_out and not ended[0].captured


def test_timeout_survival_keeps_capture() -> None:
    """Survival 符卡超时不掉 is_capturing, 无失败事件, is_active 不置 2。"""
    ctx = _ctx()
    got = _collect(ctx)
    b = _boss()
    b.is_survival_spellcard = True
    b.begin_spellcard(ctx, 0, 600, timeout_sub=5)
    for _ in range(600):
        b.tick(ctx)
    assert b.capture_score == SCORES[0]  # survival 不衰减
    b.on_timeout(ctx)
    assert b.is_active == 1 and b.is_capturing
    b.end_spellcard(ctx)
    ctx.events.flush()
    assert not [e for e in got if isinstance(e, SpellcardFailed)]
    ended = [e for e in got if isinstance(e, SpellcardEnded)]
    assert ended and ended[0].captured and ended[0].score == SCORES[0]


def test_seconds_remaining_display() -> None:
    b = _boss()
    b.begin_spellcard(_ctx(), 0, 600)
    for _ in range(60):
        b.tick(_ctx())
    assert b.seconds_remaining == 9  # (600-60)/60


def test_graze_bonus_accumulates_into_capture_score() -> None:
    """擦弹加成(公式是作品概念, 订阅方算好喂入)计入收取分。"""
    ctx = _ctx()
    got = _collect(ctx)
    b = _boss()
    b.begin_spellcard(ctx, 0, 60 * 60)
    for _ in range(600):
        b.tick(ctx)
    b.add_graze_bonus(2500)
    b.add_graze_bonus(2900)
    b.end_spellcard(ctx)
    ctx.events.flush()
    expect = int(SCORES[0] - 600 * 28571 / 60.0)
    expect -= expect % 10
    ended = [e for e in got if isinstance(e, SpellcardEnded)]
    assert ended and ended[0].score == expect + 5400


def test_end_without_spellcard_is_noop() -> None:
    b = _boss()
    assert b.end_spellcard(_ctx()) is False
