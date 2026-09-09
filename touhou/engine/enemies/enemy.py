"""Enemy: 一台 EclMachine 挂载成的敌人实例, 战斗字段与生命周期回调在这。

机器只认移动/生命周期; 判定盒/标志位/掉落等 C Enemy 字段由作品宿主
(enemy_config 指令)写进本结构, 伤害/体术管线在 field.py。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import msgspec

from ..context import FrameContext
from ..ecl.machine import EclMachine
from ..ecl.state import Vec3
from ..events import Event

if TYPE_CHECKING:
    from .field import EnemyField


# ---- 敌人事件(得分/掉落/特效等反应由作品订阅; 掉落号/击坠分是不透明整数) ----
class EnemySpawned(Event, frozen=True, tag="enemy_spawned"):
    """一个敌人入场(时间轴/生敌指令经宿主回调生成)。"""

    enemy_id: int
    x: float
    y: float
    sub_id: int


class EnemyDamaged(Event, frozen=True, tag="enemy_damaged"):
    """一个敌人本帧受了伤(raw_damage>0 才产; 结算口径见 enemies.damage)。

    raw_damage = graze 追加后、70 封顶与作品修正前的原始伤害(作品算分/算
    资源用它); damage = 实际扣血。by_bomb 区分自机弹路径与 bomb 盒路径
    (旧实现的分路径结算, 见 field.py 注记)。
    """

    enemy_id: int
    x: float
    y: float
    raw_damage: int
    damage: int
    is_boss: bool
    by_bomb: bool = False


class EnemyDied(Event, frozen=True, tag="enemy_died"):
    """一个敌人被击坠(life<=0 && canDie; death_type 0/1/2)。

    scored=False = death_type 2 阶段击破(C 无 AddScore); score/item_drop
    是生敌时登记的不透明值, 入账/掉落由作品订阅实现。
    """

    enemy_id: int
    x: float
    y: float
    is_boss: bool
    scored: bool
    score: int
    item_drop: int


class EnemyDespawned(Event, frozen=True, tag="enemy_despawned"):
    """一个敌人脚本结束离场(非击坠; 击坠见 EnemyDied)。"""

    enemy_id: int
    x: float
    y: float
    is_boss: bool


class EnemyEscaped(Event, frozen=True, tag="enemy_escaped"):
    """death_type 3: boss 离场(不计分不掉落, 继续跑死亡 sub)。"""

    enemy_id: int
    x: float
    y: float


class EnemyLifeCallback(Event, frozen=True, tag="enemy_life_callback"):
    """生命阈值回调触发(已钉生命并切 sub; 作品侧据此切阶段/清弹幕)。"""

    enemy_id: int
    sub_id: int


class EnemyTimerCallback(Event, frozen=True, tag="enemy_timer_callback"):
    """超时回调触发(已切 sub; 符卡失败/清弹/资源罚由作品订阅实现)。"""

    enemy_id: int
    sub_id: int


class Enemy(msgspec.Struct):
    """一个敌人: ECL 机 + 战斗状态; 回调/死亡语义对照 EnemyManager.cpp OnUpdate。"""

    machine: EclMachine
    enemy_id: int = 0
    active: bool = True
    died_by_kill: bool = False  # 击坠置位(区别脚本 despawn), 事件只产一次
    # ---- 战斗字段(C enemyTemplate, 作品宿主经 enemy_config 写入) ----
    hitbox_size: Vec3 = msgspec.field(default_factory=lambda: Vec3(12.0, 12.0, 12.0))
    graze_size: Vec3 = msgspec.field(default_factory=Vec3)  # x>0 时追加一次判定
    is_boss: int = 0
    can_die: int = 1
    is_hittable: int = 1
    can_be_damaged: int = 1
    has_no_collision: int = 0
    has_contact_hitbox: int = 1
    is_projectile: int = 0
    invisible_on_bomb: int = 0
    death_type: int = 0  # 0 正常击坠 1 计分续跑 2 阶段击破不计分 3 离场
    score: int = 100  # 不透明击坠分(语义在作品侧, 击坠时随事件透出)
    item_drop: int = -1  # 不透明掉落号(同上)
    anm_idx: int = -1  # 未 SET_ANM 时 <0: 无贴图敌人失去碰撞
    freeze_ecl_during_bombs: int = 0
    # ---- 回调登记(SetLifeCallback/SetTimerCallback/SetDeathCallback 系) ----
    life_callback_threshold: list[int] = msgspec.field(default_factory=lambda: [-1] * 4)
    life_callback_sub: list[int] = msgspec.field(default_factory=lambda: [-1] * 4)
    timer_callback_threshold: int = -1
    timer_callback_sub: int = -1
    death_callback_sub: int = -1
    # ---- 拖尾(SetTrail): [flags, count, interval, ...], history[0]=当前 pos ----
    trail: list[int] = msgspec.field(default_factory=lambda: [0] * 5)
    trail_history: list[Vec3] = msgspec.field(default_factory=list)

    @property
    def pos2(self) -> tuple[float, float]:
        """屏幕坐标 (x, y)。"""
        p = self.machine.enemy.pos
        return (p.x, p.y)

    # ---- 每帧 (EnemyManager::OnUpdate: RunEcl → 回调段; 伤害在 EnemyField) ----
    def step(self, field: EnemyField, ctx: FrameContext) -> None:
        """推进一帧: 冻结检查 → ECL 步进 → 拖尾/碰撞标志 → 生命/超时回调。"""
        st = self.machine.enemy
        if self.freeze_ecl_during_bombs and field.frozen:
            # C: timer-- 后 goto 循环尾, 尾部 timer++ 抵消 → 净不变;
            # invincibilityTimer 照减 (EnemyManager.cpp:658-663, 1096-1100)
            if st.invincibility_timer > 0:
                st.invincibility_timer -= 1
            return
        if not self.machine.step():
            self.active = False
            x, y = self.pos2
            ctx.events.emit(EnemyDespawned(self.enemy_id, x, y, bool(self.is_boss)))
            return
        # EnemyManager.cpp:682-696: trail 历史每帧右移(在 disableMovement 之外)
        if self.trail[0] != 0:
            self._shift_trail_history()
        # EnemyManager.cpp:697-700: 无贴图敌人失去碰撞(只置位不清位);
        # 逻辑层以 anm_idx<0 (未 SET_ANM) 近似 primaryVm.sprite==NULL
        if self.anm_idx < 0:
            self.has_no_collision = 1
        self._handle_life_callback(field, ctx)
        if self.active:
            self._handle_timer_callback(field, ctx)

    # ---- 击坠 (EnemyManager.cpp:943 OnUpdate: life<=0 && canDie) ----
    def kill(self, field: EnemyField, ctx: FrameContext) -> None:
        """生命归零的死亡分支; death_type 语义逐条对齐 C case 0/1/2/3。"""
        first = not self.died_by_kill
        self.died_by_kill = True
        st = self.machine.enemy
        dt = self.death_type
        self.life_callback_threshold = [-1] * 4
        self.timer_callback_threshold = -1
        st.periodic_callback_sub = -1
        x, y = self.pos2
        if dt == 3:
            # boss 离场(escape): 不计分不掉落, 钉 life=1 继续跑死亡 sub
            st.life = 1
            self.can_be_damaged = 0
            self.death_type = 0
            self._run_death_callback(field)
            if first:
                ctx.events.emit(EnemyEscaped(self.enemy_id, x, y))
            return
        if dt == 1:
            # 计分后 canDie=0 继续跑死亡 sub (C case 1 goto END_BOSS 落进 case 2)
            self.can_die = 0
            st.life = 0
            self._run_death_callback(field)
            if first:
                self._emit_died(ctx, x, y, scored=True)
            return
        if dt == 2:
            # 阶段击破: 不计分, 保持 active, 跑死亡回调(回调通常 SET_LIFE 复活)
            st.life = 0
            self._run_death_callback(field)
            if first:
                self._emit_died(ctx, x, y, scored=False)
            return
        self.active = False
        self._run_death_callback(field)  # C: active=0 后死亡回调照样 CallEclSub
        if first:
            self._emit_died(ctx, x, y, scored=True)

    def _emit_died(
        self, ctx: FrameContext, x: float, y: float, *, scored: bool
    ) -> None:
        ctx.events.emit(
            EnemyDied(
                self.enemy_id,
                x,
                y,
                bool(self.is_boss),
                scored,
                self.score,
                self.item_drop,
            )
        )

    # ---- 内部 ----
    def _shift_trail_history(self) -> None:
        """EnemyManager.cpp:682-696: enemyHistory 右移, [0]=当前 pos。"""
        n = self.trail[1]  # trailCount
        h = self.trail_history
        if len(h) < n:
            # C Initialize: 全部 pos.x=-999 哨兵 (EnemyManager.hpp:299-302)
            h.extend(Vec3(-999.0, 0.0, 0.0) for _ in range(n - len(h)))
        for j in range(n - 1, 0, -1):
            h[j] = h[j - 1]
        h[0] = self.machine.enemy.pos.copy()

    def _callback_reset(self, field: EnemyField) -> None:
        """回调切换时的公共复位 (C: shootInterval/stackDepth 等)。"""
        st = self.machine.enemy
        st.shoot_interval = 0
        self.machine.stack.clear()
        field.enemy_callback_reset(self)  # 作品侧复位(弹幕参数等)

    def _rerun_ecl(self, field: EnemyField, ctx: FrameContext) -> None:
        """回调后的 goto HUH: 当帧重跑一次主循环。"""
        if not self.machine.rerun():
            self.active = False
            x, y = self.pos2
            ctx.events.emit(EnemyDespawned(self.enemy_id, x, y, bool(self.is_boss)))

    def _handle_life_callback(self, field: EnemyField, ctx: FrameContext) -> None:
        """Enemy::HandleLifeCallback: 跌破阈值 → 钉生命 + 切 sub + 清场。"""
        st = self.machine.enemy
        for i in range(4):
            t = self.life_callback_threshold[i]
            if t < 0 or st.life >= t:
                continue
            st.life = t
            sub = self.life_callback_sub[i]
            self.life_callback_threshold[i] = -1
            self.timer_callback_threshold = -1
            st.periodic_callback_sub = -1
            self.machine.call_sub(sub)
            self._callback_reset(field)
            field.clear_field(self, ctx)  # 杀光非 boss 敌
            ctx.events.emit(EnemyLifeCallback(self.enemy_id, sub))
            self._rerun_ecl(field, ctx)
            return

    def _handle_timer_callback(self, field: EnemyField, ctx: FrameContext) -> None:
        """Enemy::HandleTimerCallback: 超时 → 切 sub; 符卡失败等后果由作品订阅事件。"""
        st = self.machine.enemy
        if (
            self.timer_callback_threshold < 0
            or st.timer < self.timer_callback_threshold
        ):
            return
        # 若还有更高的生命阈值, 钉生命并清掉(不触发其回调)
        best, best_i = 0, -1
        for i in range(4):
            t = self.life_callback_threshold[i]
            if t >= 0 and t > best:
                best, best_i = t, i
        if best > 0:
            st.life = best
            self.life_callback_threshold[best_i] = -1
        sub = self.timer_callback_sub
        self.machine.call_sub(sub)
        self.timer_callback_threshold = -1
        self.timer_callback_sub = self.death_callback_sub
        st.timer = 0
        ctx.events.emit(EnemyTimerCallback(self.enemy_id, sub))
        st.periodic_callback_sub = -1
        self._callback_reset(field)
        self._rerun_ecl(field, ctx)

    def _run_death_callback(self, field: EnemyField) -> None:
        """死亡回调 sub (复位后 CallEclSub, 后续帧由 machine.step 继续跑)。"""
        if self.death_callback_sub < 0:
            return
        sub = self.death_callback_sub
        self.death_callback_sub = -1
        self._callback_reset(field)
        self.machine.call_sub(sub)
