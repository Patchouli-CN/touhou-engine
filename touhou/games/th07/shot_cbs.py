"""th07 六机体 exotic 自机弹回调: fire/update/hit handlers + ShotField 注册口。

行为逐条平移 old/touhou/games/th07/player.py 的 _fire_orb/_fire_homing/
_fire_rotating_orb/_update_homing/_update_orb_laser/_update_player_laser/
_on_missile_hit; 回调索引与真实 .sht 核对(g_ShtFireFuncs 等数组下标)。
"""

from __future__ import annotations

import math

import msgspec

from ...engine.context import FrameContext
from ...engine.shots import SHOT_HISTORY, PlayerShot, ShotField
from ...schemas.shot_data import ShotEntry
from ...utils.math import Vec2, normalize_angle_diff
from .player import OptionMachine, OptionState

# ---- 回调索引(old player.py:75-92; 数组 0 号位 NULL 由 engine 回落 default) ----
FIRE_ORB_UNFOCUSED = 2  # 占 timers[fire_offset] 槽的持续弹(要求 UNFOCUSED)
FIRE_ORB_FOCUSED = 3  # 同上(要求 FOCUSED, 槽计时 999, trail_length=fire_interval)
FIRE_HOMING = 4  # 咲夜A: 发射后朝索敌目标重定向, 速度×1.5
FIRE_ROTATING_ORB = 5  # 咲夜B: 发射角 = option_angle + entry.angle + pi/2

UPDATE_HOMING = 1  # 灵梦A: 40 帧内朝最后命中敌转向(cap 10), 否则 +0.3333
UPDATE_HOMING_FOCUSED = 2  # 同上, cap 18 / +0.6
UPDATE_UPWARD_ACCEL = 3  # 魔理沙A 导弹: velocity.y -= rand(0..0.1) + 0.27
UPDATE_ORB_LASER = 4  # 魔理沙B 非 focus: 跟随子机的锁版激光
UPDATE_PLAYER_LASER = 5  # 魔理沙B focus: 跟随本体的拖尾激光

HIT_MISSILE = 1  # 魔理沙A 导弹: 首中爆炸变形, 之后隔帧伤害
# HIT_PARTICLES=2 纯视觉(SpawnHitParticles), 逻辑空壳不注册

HOMING_STEER_FRAMES = 40  # homing 转向窗口(timer < 40, old player.py:96)
PERSIST_DIALOG_BOMB_CAP = 20  # 对话/炸弹中持续弹剩余计时压到 20 (old player.py:97)

#: 咲夜索敌角度窗(Targeting.homing_window 用, old engine/enemies.py:114-115)
SAKUYA_HOMING_WINDOW = (-2.0943952, -1.0471976)

# OnMissileHit: anmFileIdx → (爆炸后判定盒全宽/全高, 爆炸速度) (old player.py:101-110)
MISSILE_BLAST = {
    1089: (32.0, 4.0),
    1090: (42.0, 4.0),
    1091: (48.0, 4.0),
    1092: (56.0, 4.0),
    1093: (48.0, 6.0),
    1094: (64.0, 6.0),
    1095: (80.0, 6.0),
    1096: (96.0, 6.0),
}

_HISTORY_SENTINEL = Vec2(-999.0, 0.0)


class Th07ShotHooks(msgspec.Struct):
    """exotic 弹回调的外部状态口: 子机状态机引用 + 索敌目标(world 每帧同步)。"""

    options: OptionMachine
    position_of_last_enemy_hit: Vec2 = msgspec.field(
        default_factory=lambda: Vec2(-999.0, -999.0)
    )
    sakuya_target_position: Vec2 = msgspec.field(
        default_factory=lambda: Vec2(-999.0, -999.0)
    )

    def register(self, shots: ShotField) -> None:
        """把 th07 exotic 回调灌进 ShotField 分派表(组合根调一次)。"""
        shots.fire_handlers.update(
            {
                FIRE_ORB_UNFOCUSED: self._fire_orb_unfocused,
                FIRE_ORB_FOCUSED: self._fire_orb_focused,
                FIRE_HOMING: self._fire_homing,
                FIRE_ROTATING_ORB: self._fire_rotating_orb,
            }
        )
        shots.update_handlers.update(
            {
                UPDATE_HOMING: self._update_homing,
                UPDATE_HOMING_FOCUSED: self._update_homing_focused,
                UPDATE_UPWARD_ACCEL: self._update_upward_accel,
                UPDATE_ORB_LASER: self._update_orb_laser,
                UPDATE_PLAYER_LASER: self._update_player_laser,
            }
        )
        shots.hit_handlers.update({HIT_MISSILE: self._on_missile_hit})
        shots.trail_damage_cbs = frozenset({UPDATE_PLAYER_LASER})

    def clear_stale_slots(self, shots: ShotField) -> None:
        """Focus 切态的持续弹槽清理(旧 _update_shots 首段; 每帧弹场步进前调)。"""
        # 出处 old/touhou/games/th07/player.py:576-588
        state = self.options.state
        if state != OptionState.FOCUSED and shots.timers[2].shot is not None:
            shots.timers[2].shot.bullet_state = 0
            shots.timers[2].shot = None
        if state != OptionState.UNFOCUSED:
            for i in (0, 1):
                shot = shots.timers[i].shot
                if shot is not None:
                    shot.bullet_state = 0
                    shots.timers[i].shot = None

    # ---- fire 回调(g_ShtFireFuncs) ----
    def _fire_orb_unfocused(
        self, shots: ShotField, entry: ShotEntry, shot: PlayerShot, ctx: FrameContext
    ) -> bool:
        """FireOrbBulletUnfocused 入口。"""
        return self._fire_orb(shots, entry, shot, ctx, focused=False)

    def _fire_orb_focused(
        self, shots: ShotField, entry: ShotEntry, shot: PlayerShot, ctx: FrameContext
    ) -> bool:
        """FireOrbBulletFocused 入口。"""
        return self._fire_orb(shots, entry, shot, ctx, focused=True)

    def _fire_orb(
        self,
        shots: ShotField,
        entry: ShotEntry,
        shot: PlayerShot,
        ctx: FrameContext,
        *,
        focused: bool,
    ) -> bool:
        """占 timers[fire_offset] 槽的持续弹; 槽占/状态不符不发射, entry 变了中断旧弹。"""
        # 出处 old/touhou/games/th07/player.py:515-544
        slot = entry.fire_offset
        if slot >= len(shots.timers):
            return False
        ts = shots.timers[slot]
        if ts.shot is not None:
            if shots.sht_entries[slot] is not entry:
                # C++ 置 vm.pendingInterrupt(动画退出消弹), 逻辑层直接消弹
                ts.shot.bullet_state = 0
                ts.shot = None
            return False
        need = OptionState.FOCUSED if focused else OptionState.UNFOCUSED
        if self.options.state != need:
            return False
        ts.timer = 999 if focused else entry.fire_interval
        ts.shot = shot
        shot.timer_idx = slot
        shot.option_id = entry.option
        shot.offset = Vec2(*entry.offset)
        shots.init_shot(entry, shot, ctx)
        if focused:
            shot.trail_length = entry.fire_interval
            shot.pos_history = [_HISTORY_SENTINEL] * SHOT_HISTORY
            shot.pos = Vec2(-999.0, shot.pos.y)
        shots.sht_entries[slot] = entry
        return True

    def _fire_homing(
        self, shots: ShotField, entry: ShotEntry, shot: PlayerShot, ctx: FrameContext
    ) -> bool:
        """FireHomingBullet(咲夜A): default 发射后朝索敌目标重定向, 速度×1.5。"""
        # 出处 old/touhou/games/th07/player.py:546-561
        if shots.fire_time % entry.fire_interval != entry.fire_offset:
            return False
        shots.init_shot(entry, shot, ctx)
        tgt = self.sakuya_target_position
        if tgt.x > -100.0:
            angle = normalize_angle_diff(
                math.atan2(tgt.y - shot.pos.y, tgt.x - shot.pos.x)
                + entry.angle
                + math.pi / 2
            )
            shot.velocity = Vec2.from_angle(angle, entry.speed * 1.5)
            shot.angle = angle
        return True

    def _fire_rotating_orb(
        self, shots: ShotField, entry: ShotEntry, shot: PlayerShot, ctx: FrameContext
    ) -> bool:
        """FireRotatingOrbBullet(咲夜B): 发射角 = option_angle + entry.angle + pi/2。"""
        # 出处 old/touhou/games/th07/player.py:563-571
        if shots.fire_time % entry.fire_interval != entry.fire_offset:
            return False
        shots.init_shot(entry, shot, ctx)
        angle = normalize_angle_diff(
            self.options.option_angle + entry.angle + math.pi / 2
        )
        shot.velocity = Vec2.from_angle(angle, entry.speed)
        shot.angle = angle
        return True

    # ---- update 回调(g_ShtUpdateFuncs), True → 弹置 0 ----
    def _update_homing(
        self, shots: ShotField, shot: PlayerShot, ctx: FrameContext
    ) -> bool:
        """UpdateHomingBullet: cap 10 / +0.3333。"""
        return self._steer_homing(shot, cap=10.0, accel=0.33333334)

    def _update_homing_focused(
        self, shots: ShotField, shot: PlayerShot, ctx: FrameContext
    ) -> bool:
        """UpdateHomingBulletFocused: cap 18 / +0.6。"""
        return self._steer_homing(shot, cap=18.0, accel=0.6)

    def _steer_homing(self, shot: PlayerShot, *, cap: float, accel: float) -> bool:
        """40 帧内有目标则每帧重算方向转向(速度 cap), 否则沿当前方向加速到 cap。"""
        # 出处 old/touhou/games/th07/player.py:633-657
        if shot.bullet_state != 1:
            return False
        tgt = self.position_of_last_enemy_hit
        if tgt.x > -100.0 and shot.timer < HOMING_STEER_FRAMES:
            x = tgt.x - shot.pos.x
            y = tgt.y - shot.pos.y
            length = math.hypot(x, y) / (shot.speed / 4.0)
            if length < 1.0:
                length = 1.0
            x = x / length + shot.velocity.x
            y = y / length + shot.velocity.y
            length = math.hypot(x, y)
            if length == 0.0:
                return False  # C++ 此处产生 nan; 逻辑层直接保持原速
            shot.speed = min(max(length, 1.0), cap)
            shot.velocity = Vec2(x * shot.speed / length, y * shot.speed / length)
        elif shot.speed < cap:
            shot.speed += accel
            vlen = shot.velocity.length
            if vlen > 0.0:
                shot.velocity = shot.velocity * (shot.speed / vlen)
        return False

    def _update_upward_accel(
        self, shots: ShotField, shot: PlayerShot, ctx: FrameContext
    ) -> bool:
        """UpdateUpwardAccel(魔理沙A 导弹): 活弹每帧 velocity.y -= rand(0..0.1)+0.27。"""
        # 出处 old/touhou/games/th07/player.py:622-626 (rand 走 ctx.rng, 确定性)
        if shot.bullet_state == 1:
            v = shot.velocity
            shot.velocity = Vec2(v.x, v.y - (ctx.rng.unit() * 0.1 + 0.27))
        return False

    def _update_orb_laser(
        self, shots: ShotField, shot: PlayerShot, ctx: FrameContext
    ) -> bool:
        """UpdateOrbLaser: 跟随子机 options[option_id-1]+offset(仅 x); hitbox 高=子机 y。"""
        # 出处 old/touhou/games/th07/player.py:659-678
        ts = shots.timers[shot.timer_idx]
        if (shots.dialog_active or shots.bomb_active) and (
            ts.timer > PERSIST_DIALOG_BOMB_CAP
        ):
            ts.timer = PERSIST_DIALOG_BOMB_CAP
        if ts.timer <= 0:
            ts.timer = 0
            ts.shot = None
            shot.bullet_state = 0
            return True
        opt = shots.options[shot.option_id - 1]
        shot.pos = Vec2(opt.x + shot.offset.x, opt.y)
        if shots.player_state == 2:  # PlayerState.DEAD
            return True
        shot.hitbox = (shot.hitbox[0], shot.pos.y)
        shot.pos = Vec2(shot.pos.x, shot.pos.y / 2)
        return False

    def _update_player_laser(
        self, shots: ShotField, shot: PlayerShot, ctx: FrameContext
    ) -> bool:
        """UpdatePlayerLaser: 跟随本体; pos_history 每帧右移(拖尾段伤害在 iter_hits)。"""
        # 出处 old/touhou/games/th07/player.py:680-701
        ts = shots.timers[shot.timer_idx]
        if (shots.dialog_active or shots.bomb_active) and (
            ts.timer > PERSIST_DIALOG_BOMB_CAP
        ):
            ts.timer = PERSIST_DIALOG_BOMB_CAP
        if ts.timer <= 0:
            ts.timer = 0
            ts.shot = None
            shot.bullet_state = 0
            return True
        for i in range(SHOT_HISTORY - 1, 0, -1):
            shot.pos_history[i] = shot.pos_history[i - 1]
        shot.pos_history[0] = shot.pos
        if shots.player_state == 2:  # PlayerState.DEAD
            return True
        shot.pos = Vec2(shots.player_pos.x + shot.offset.x, shots.player_pos.y)
        shot.hitbox = (shot.hitbox[0], shots.player_pos.y + 64.0)
        shot.pos = Vec2(shot.pos.x, shot.pos.y / 2 - 32.0)
        return False

    # ---- hit 回调(g_ShtHitFuncs), True → 跳过当帧伤害 ----
    def _on_missile_hit(
        self, shots: ShotField, shot: PlayerShot, ctx: FrameContext
    ) -> bool:
        """OnMissileHit: 爆炸中隔帧跳过+伤害/3(最低 1)+速度×0.88; 首中爆炸变形。"""
        # 出处 old/touhou/games/th07/player.py:711-727 (rand 走 ctx.rng, 确定性)
        if shot.bullet_state == 2:
            if shot.timer % 2 != 0:
                return True
            shot.damage = shot.damage // 3
            if shot.damage == 0:
                shot.damage = 1
            shot.velocity = shot.velocity * 0.88
        else:
            blast = MISSILE_BLAST.get(shot.anm_file_idx)
            if blast is not None:
                angle = ctx.rng.unit() * (math.pi / 2) - 3 * math.pi / 4
                shot.hitbox = (blast[0], blast[0])
                shot.velocity = Vec2.from_angle(angle, blast[1])
        return False
