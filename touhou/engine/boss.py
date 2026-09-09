"""Boss: BossField 血条/阶段/符卡计时/失败/收取判定的骨架语义。

符卡分值表由作品注入(spellcard_scores); 收取分入账/名簿登记/超时资源罚/
清场清弹等后果全走事件订阅, engine 只做状态机与衰减数学
(EclManager.cpp BeginSpellcard/EndSpellcard/:2241-2257, EnemyManager.cpp
HandleLifeCallback/HandleTimerCallback 的作品无关段)。
"""

from __future__ import annotations

import msgspec

from .context import FrameContext
from .core import System, World
from .events import Event


class SpellcardBegan(Event, frozen=True, tag="spellcard_began"):
    """符卡宣言(BeginSpellcard; 宣言演出/立绘由作品订阅)。"""

    boss_id: int
    spellcard_idx: int
    time_limit: int  # 帧


class SpellcardEnded(Event, frozen=True, tag="spellcard_ended"):
    """符卡结束(EndSpellcard): captured=收取, timed_out=超时失败。

    score = captureScore+grazeBonusScore (代码值, 仅 captured 时有义);
    入账/名簿由作品订阅。非超时结束时作品侧另行清弹清敌
    (旧 despawn_bullets/remove_all_enemies (8000,*) 信号)。
    """

    boss_id: int
    spellcard_idx: int
    captured: bool
    timed_out: bool
    score: int = 0


class SpellcardFailed(Event, frozen=True, tag="spellcard_failed"):
    """超时失败记账(非 survival 符卡计时到点; 清弹/资源罚由作品订阅)。"""

    boss_id: int
    spellcard_idx: int


class BossPhaseChanged(Event, frozen=True, tag="boss_phase_changed"):
    """生命阈值跌破, 阶段切换(callback=登记的回调标识, 0 起; 清场由作品订阅)。"""

    boss_id: int
    phase: int
    life: float
    callback: int


class BossField(msgspec.Struct):
    """一个 boss 的血条/阶段/符卡状态; 与敌人本体的生命同步由作品接线。"""

    boss_id: int = 0
    life: float = 0.0
    max_life: float = 0.0
    is_active: int = 0  # 0=无符卡 1=进行中 2=超时失败
    phase: int = 0
    # (阈值, 阶段切换回调标识); 阈值按生命降序
    life_thresholds: list[tuple[float, int]] = msgspec.field(default_factory=list)
    # 超时回调 (ECL_SET_TIMER_CALLBACK_THRESHOLD/SUB)
    timer_callback_threshold: int = -1  # 帧; -1=无
    timer_callback_sub: int = 0
    seconds_remaining: int = 0  # 剩余秒显示(boss_id==0 时每帧更新)
    # 符卡
    spellcard_idx: int = -1
    spellcard_face: int = 0  # 宣言立绘 sprite 下标(不透明, 透出用)
    spellcard_time_limit: int = 0  # 帧
    is_capturing: bool = False
    is_survival_spellcard: bool = False
    capture_score: int = 0  # 代码值
    graze_bonus_score: int = 0  # 代码值(擦弹加成, 作品经 add_graze_bonus 喂入)
    score_drain_rate: int = 0
    used_bomb: bool = False
    timer: int = 0
    # 符卡分值表(作品级注入; 空 = 未配置)
    spellcard_scores: tuple[int, ...] = ()

    # ---- 生命阈值 / 阶段 ----
    def set_life(self, life: float) -> None:
        """设当前/最大生命(血条两端)。"""
        self.life = self.max_life = life

    def apply_damage(self, damage: int) -> None:
        """扣血(订阅 EnemyDamaged 后调用), 下限 0。"""
        self.life -= damage
        if self.life <= 0:
            self.life = 0

    def check_life_threshold(self, ctx: FrameContext) -> int:
        """HandleLifeCallback (EnemyManager.cpp:373-428): 跌破阈值钉生命切阶段。

        返回命中的回调标识(0=无); 清场等后果由作品订阅 BossPhaseChanged。
        """
        for i, (threshold, cb) in enumerate(self.life_thresholds):
            if self.life < threshold:
                self.life = threshold  # 钉住生命
                self.phase = i + 1
                # 清掉已触发的阈值与超时回调
                self.life_thresholds = self.life_thresholds[i + 1 :]
                self.timer_callback_threshold = -1
                ctx.events.emit(
                    BossPhaseChanged(self.boss_id, self.phase, self.life, cb)
                )
                return cb
        return 0

    # ---- 符卡 ----
    def begin_spellcard(
        self, ctx: FrameContext, idx: int, time_limit: int, timeout_sub: int = 0
    ) -> None:
        """BeginSpellcard (EclManager.cpp:658-752)。"""
        self.spellcard_idx = idx
        self.spellcard_time_limit = time_limit
        self.is_active = 1
        self.is_capturing = True
        self.capture_score = self.spellcard_scores[idx]
        self.graze_bonus_score = 0
        # scoreDrainRate 为 int: captureScore / (threshold/60 + 10)
        self.score_drain_rate = self.capture_score // (time_limit // 60 + 10)
        self.used_bomb = False
        self.timer = 0
        # C++ 中 threshold/sub 由 ECL 单独设置; 这里一并登记方便超时状态机使用
        self.set_timer_callback(time_limit, timeout_sub)
        ctx.events.emit(SpellcardBegan(self.boss_id, idx, time_limit))

    def set_timer_callback(self, threshold: int, sub: int) -> None:
        """ECL_SET_TIMER_CALLBACK_THRESHOLD(114)/SUB(115): 超时阈值(帧)与回调。"""
        self.timer_callback_threshold = threshold
        self.timer_callback_sub = sub

    def tick(self, ctx: FrameContext) -> None:
        """每帧: 计时 + 剩余秒显示 + 捕获分线性衰减 (EclManager.cpp:2241-2257)。

        非 survival 符卡每帧由基础分重算:
        captureScore = SpellcardScore[idx] - timer*scoreDrainRate/60, 向下取整到 10;
        到 (时间限制+10) 秒时衰减到 0。
        """
        if not self.is_active:
            return
        self.timer += 1
        if self.boss_id == 0 and self.timer_callback_threshold >= 0:
            self.seconds_remaining = (self.timer_callback_threshold - self.timer) // 60
        if (
            self.is_capturing
            and self.spellcard_idx >= 0
            and not self.is_survival_spellcard
        ):
            score = int(
                self.spellcard_scores[self.spellcard_idx]
                - self.timer * self.score_drain_rate / 60.0
            )
            if score > 0:
                score -= score % 10
            self.capture_score = max(0, score)

    # ---- 捕获判定 ----
    def mark_bombed(self) -> None:
        """玩家用弹 (Player.cpp:1745-1749): 不算捕获, usedBomb=isActive。"""
        self.capture_score = 0
        self.is_capturing = False
        self.used_bomb = bool(self.is_active)

    def mark_death(self) -> None:
        """玩家死亡/结界破裂 (Player.cpp:1782-1783, 2175-2176): 捕获失败。"""
        self.capture_score = 0
        self.is_capturing = False

    def on_timeout(self, ctx: FrameContext) -> None:
        """超时失败记账(订阅 EnemyTimerCallback 后调用)。

        非 survival 符卡: is_active=2 + 捕获失败 + 产 SpellcardFailed;
        survival 符卡超时不掉捕获 (旧 handle_timer_callback 的 survival 分支)。
        """
        if self.is_active != 1 or self.is_survival_spellcard:
            return
        self.is_active = 2
        self.is_capturing = False
        self.capture_score = 0
        ctx.events.emit(SpellcardFailed(self.boss_id, self.spellcard_idx))

    def add_graze_bonus(self, score: int) -> None:
        """累加擦弹加成(代码值; 加成公式是作品概念, 由订阅方算好传入)。"""
        self.graze_bonus_score += score

    def end_spellcard(self, ctx: FrameContext) -> bool:
        """EndSpellcard (EclManager.cpp:755-849): 有进行中的符卡则收尾并产事件。"""
        idx = self.spellcard_idx
        ended = bool(self.is_active)
        if self.is_active == 1:
            captured = self.is_capturing
            ctx.events.emit(
                SpellcardEnded(
                    self.boss_id,
                    idx,
                    captured,
                    False,
                    self.capture_score + self.graze_bonus_score if captured else 0,
                )
            )
        elif self.is_active == 2:
            ctx.events.emit(SpellcardEnded(self.boss_id, idx, False, True, 0))
        self.is_active = 0
        self.spellcard_idx = -1
        return ended

    @property
    def alive(self) -> bool:
        """符卡进行中且血未空。"""
        return bool(self.is_active) and self.life > 0


class BossSystem(System[World]):
    """LOGIC 槽: boss 计时/捕获分衰减/剩余秒显示(可多挂, 一个 BossField 一台)。"""

    def __init__(self, *fields: BossField) -> None:
        self.fields = fields

    def tick(self, world: World, ctx: FrameContext) -> None:
        for f in self.fields:
            f.tick(ctx)
