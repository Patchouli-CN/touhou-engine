"""弹场: 弹型模板/Burst 发散/Bullet 数据 + BulletField 状态容器与判定, 事件从这产。"""

from __future__ import annotations

import math
from enum import IntEnum

import msgspec

from ...utils.math import Vec2, angle_to, normalize_angle_diff
from ..context import FrameContext
from ..events import Event, EventStream
from ..rng import Rng
from .commands import (
    OFFSCREEN_GRACE,
    OFFSCREEN_GRACE_FRAMES,
    SCREEN_H,
    SCREEN_W,
    BulletCommand,
    BulletState,
)

#: 擦弹判定弹盒外扩像素 (CheckGraze, 出处 old/touhou/engine/player_base.py:51)
GRAZE_EXPAND = 20.0


class Aim(IntEnum):
    """敌弹的瞄准/发散方式, 值对应 BulletAimMode (BulletManager.hpp)。"""

    SPREAD_AIMED = 0  # 扇形, 对准玩家
    SPREAD_ABSOLUTE = 1  # 扇形, 绝对角
    RING_AIMED = 2  # 环形, 对准玩家
    RING_ABSOLUTE = 3  # 环形, 绝对角
    RING_SHIFT_AIMED = 4  # 环形错半格, 对准玩家
    RING_SHIFT_ABSOLUTE = 5  # 环形错半格, 绝对角
    ANGLE_RANDOM = 6  # 角度随机(速度按层插值)
    RING_SPEED_RANDOM = 7  # 环形 + 速度随机
    RANDOM = 8  # 角度+速度全随机


# ---- rank 插值 (EnemyManager.hpp BulletRank*Inner) ----
def rank_lerp(low: float, high: float, scale: float) -> float:
    """弹速插值: scale*(high-low)/32 + low。scale=subrank/rank, 0..32。"""
    return scale * (high - low) / 32 + low


def rank_lerp_int(low: int, high: int, scale: int) -> int:
    """弹量/射击间隔插值(整数, C++ int 除法向零截断)。"""
    d = scale * (high - low)
    return (d // 32 if d >= 0 else -((-d) // 32)) + low


class BulletTypeSpec(msgspec.Struct, frozen=True):
    """一种敌弹弹型: 判定/擦弹尺寸、碰撞分层与出生态帧数(作品侧注入)。"""

    # 数值出处 BulletManager.cpp AddedCallback + g_BulletTypeInfos;
    # width/height 取 etama.anm 精灵尺寸, spawn_t = 出生特效脚本时长(三档)
    anm_file_idx: int  # etama 活动脚本索引 (g_BulletTypeInfos/scripts[0])
    width: float  # 精灵宽(px)
    height: float  # 精灵高(px) = bulletHeight
    graze_size: Vec2  # 擦弹/命中判定尺寸(collisionSize)
    collision_type: int  # 绘制分层 0..5
    spawn_t: tuple[int, int, int] = (0, 0, 0)  # 出生特效脚本时长 T(0=无出生态)


_DEFAULT_BULLET_SIZE = Vec2(16, 16)

# 出生 pos -= vel*4, 出生态以 vel/2 | vel/2.5 | vel/3 移动
# (BulletManager.cpp:255-283 出生 / :1022-1047 每帧, flags 2/4/8 = SPAWNING_*)
_SPAWN_MOVE_DIV = {2: 2.0, 4: 2.5, 8: 3.0}


def _spawn_state_spec(spec: BulletTypeSpec | None, flags: int) -> tuple[int, int]:
    """Shooter flags/弹型模板 → (spawn_state, 转变帧数); 无出生态返回 (0, 0)。

    spawn_state = 触发的 flag 位(2/4/8, 优先级同 C++ if/elif 链);
    帧数 = 特效脚本 T + 1(第 T+1 次 ExecuteScript 返回 1 → 当帧转 NORMAL)。
    """
    if flags & 2:
        bit, idx = 2, 0
    elif flags & 4:
        bit, idx = 4, 1
    elif flags & 8:
        bit, idx = 8, 2
    else:
        return 0, 0
    if spec is None or spec.spawn_t[idx] == 0:
        return 0, 0
    return bit, spec.spawn_t[idx] + 1


class Burst(msgspec.Struct, frozen=True):
    """一次"按 pattern 发散出的若干弹参数"(对照 EnemyBulletShooter)。

    base_angle: 基准角 —— 非随机模式下相当于 angle1, aimed 模式调用方应传入
    angle_to(发射点, 玩家) + angle1; 随机模式(ANGLE_RANDOM/RANDOM)下即 angle1,
    angle_step 即 angle2(随机区间为 [angle2, angle1))。
    """

    path: Vec2  # 发射起点(通常是敌人位置)
    base_angle: float  # 基准角(见上)
    aim: Aim
    arms: int  # count1: 每次发几颗(环的份数/扇的颗数)
    rings: int  # count2: 几层(环数)
    speed_a: float  # speed1
    speed_b: float  # speed2(层间插值低端/随机低端)
    angle_step: float  # angle2: 层间角差 / 扇间隔
    sprite: int = 0  # 弹型(= type_specs 下标)
    sprite_offset: int = 0  # spriteOffset: 颜色/变体偏移
    commands: tuple[BulletCommand, ...] = ()  # 出生即挂的命令队列
    flags: int = 0  # moreFlags(命令位 + 2/4/8 出生态 + 0x200 音效 + 0x1000 不清屏…)

    def angle_speed(self, arm: int, ring: int, rng: Rng) -> tuple[float, float]:
        """第 (arm, ring) 颗弹的发射角/速度(SpawnSingleBullet 的 switch)。"""
        mode = self.aim
        count1, count2 = self.arms, self.rings
        port = self.base_angle
        if count2 > 1:
            speed = self.speed_a - (self.speed_a - self.speed_b) * ring / count2
        else:
            speed = self.speed_a

        if mode in (Aim.SPREAD_AIMED, Aim.SPREAD_ABSOLUTE):
            # 对称扇: 奇数颗从 0 偏移, 偶数颗错开半步; 奇数下标取负
            if count1 & 1:
                off = self.angle_step * ((arm + 1) // 2)
            else:
                off = self.angle_step * (arm // 2) + self.angle_step * 0.5
            if arm & 1:
                off = -off
            return port + off, speed
        if mode in (Aim.RING_AIMED, Aim.RING_ABSOLUTE):
            return port + arm * math.tau / count1 + ring * self.angle_step, speed
        if mode in (Aim.RING_SHIFT_AIMED, Aim.RING_SHIFT_ABSOLUTE):
            return port + math.pi / count1 + arm * math.tau / count1, speed
        if mode is Aim.ANGLE_RANDOM:
            return rng.in_range(self.angle_step, port), speed
        if mode is Aim.RING_SPEED_RANDOM:
            speed = rng.in_range(self.speed_b, self.speed_a)
            return port + arm * math.tau / count1 + ring * self.angle_step, speed
        # Aim.RANDOM
        return (
            rng.in_range(self.angle_step, port),
            rng.in_range(self.speed_b, self.speed_a),
        )


class Bullet(BulletState):
    """一颗敌弹: 命令状态(基类) + 弹型/出生态/擦弹标记。"""

    sprite: int = 0
    sprite_offset: int = 0  # C bullet->spriteOffset
    # 判定半径(碰撞盒半宽, 观测面用): fire() 把 BulletField.bullet_radius
    # 物化到实例上; 默认 3.5 与字段默认一致
    hitbox: float = 3.5
    state2: int = 0  # C bullet->state2 (ExIns 的每弹标记位)
    age: int = 0
    dead: bool = False
    grazed: bool = False  # 每颗弹只擦一次(由 check_player 置位)
    out_of_bounds_time: int = 0
    # 出生态: 0=NORMAL; 2/4/8 = SPAWNING_FAST/NORMAL/SLOW
    # (C bullet->state; spawn_frames 倒计时 = 特效脚本剩余帧数)
    spawn_state: int = 0
    spawn_frames: int = 0

    def __post_init__(self) -> None:
        # C++ spawn 时 angle = AddNormalizeAngle(bulletAngle, 0)
        self.angle = normalize_angle_diff(self.angle)
        super().__post_init__()

    def step(self) -> None:
        """推进一帧(位移; 命令更新在 BulletField.step 里先于本调用)。"""
        self.pos = self.pos + self.vel
        self.age += 1

    def off_screen(self) -> bool:
        """完全出屏(GameManager::IsInBounds 的否: 以精灵半宽/半高为边距)。"""
        hw, hh = self.size.x / 2.0, self.size.y / 2.0
        return not (
            self.pos.x + hw >= 0.0
            and self.pos.x - hw <= SCREEN_W
            and self.pos.y + hh >= 0.0
            and self.pos.y - hh <= SCREEN_H
        )


# ---- 弹事件(生成/消除/擦弹/命中候选; 得分/消弹特效等反应由作品订阅) ----
class BulletSpawned(Event, frozen=True, tag="bullet_spawned"):
    """一颗弹入场(spawn 特效态也算, 被消弹窗口压制的不产)。"""

    x: float
    y: float
    sprite: int
    angle: float
    speed: float
    spawn_state: int = 0


class DespawnCause(IntEnum):
    """消弹原因。"""

    OFFSCREEN = 1  # 出界(含宽限耗尽/残余递减归零)
    CLEARED = 2  # 清弹(clear)


class BulletDespawned(Event, frozen=True, tag="bullet_despawned"):
    """一颗弹离场。"""

    x: float
    y: float
    sprite: int
    cause: DespawnCause


class BulletGraze(Event, frozen=True, tag="bullet_graze"):
    """擦弹候选: 弹盒外扩 20px 与擦弹盒相交(每颗弹只产一次)。"""

    x: float
    y: float


class BulletHit(Event, frozen=True, tag="bullet_hit"):
    """命中候选: 弹盒与判定盒相交(每帧最多一条, 生死结算由作品订阅)。"""

    x: float
    y: float


class BulletField(msgspec.Struct):
    """弹场状态容器: 弹列表 + 弹型/判定配置(作品数值构造注入, 引擎不持表)。

    player_pos/graze_enabled/hit_enabled 由作品侧每帧同步(旧实现同样是世界层
    每帧赋值 player_pos; enabled 两flag 吸收旧 player 状态/炸弹门控)。
    """

    type_specs: tuple[BulletTypeSpec, ...] = ()  # 空表 = 16px 默认尺寸, 无出生态
    player_pos: Vec2 = Vec2(SCREEN_W / 2, SCREEN_H / 2)
    player_radius: float = 2.0  # 判定盒半宽(作品按 .sht 注入)
    graze_radius: float = 24.0  # 擦弹盒半宽(作品按 .sht 注入)
    graze_enabled: bool = True  # 旧: 玩家 DEAD/SPAWNING 不擦
    hit_enabled: bool = True  # 旧: 炸弹中/非 ALIVE 不命中
    bullet_radius: float = 3.5  # 敌弹判定半宽(擦弹/命中盒 = pos±radius 均匀 AABB)
    # g_Supervisor.effectiveFramerateMultiplier 的弹幕侧: 出生速度/命令更新器的
    # dt 乘它, 位移本身不二次缩放
    time_scale: float = 1.0
    # BulletManager::screenClearTime (:480/:553 置 10, :1205-1207 每帧递减):
    # 窗口期内不带 0x1000 moreFlag 的新弹出生即 DESPAWN (:289-292, 不入场)
    screen_clear_time: int = 0
    _bullets: list[Bullet] = msgspec.field(default_factory=list)

    # ---- 生成 ----
    def fire(self, burst: Burst, ctx: FrameContext) -> int:
        """把一发 Burst 展开成实际子弹(SpawnBulletPattern 双层循环), 返回颗数。"""
        count = 0
        spec = (
            self.type_specs[burst.sprite]
            if 0 <= burst.sprite < len(self.type_specs)
            else None
        )
        size = (
            Vec2(spec.width, spec.height)
            if spec is not None and spec.width > 0
            else _DEFAULT_BULLET_SIZE
        )
        for ring in range(burst.rings):
            for arm in range(burst.arms):
                angle, speed = burst.angle_speed(arm, ring, ctx.rng)
                # BulletManager.cpp:289-292: screenClearTime 窗口内且无 0x1000
                # moreFlag 的弹出生即 DESPAWN(RNG 照原样消耗, 弹体不入场)
                if self.screen_clear_time != 0 and not (burst.flags & 0x1000):
                    continue
                b = Bullet(
                    pos=burst.path,
                    angle=angle,
                    speed=speed,
                    size=size,
                    commands=list(burst.commands),
                    sprite=burst.sprite,
                    sprite_offset=burst.sprite_offset,
                    hitbox=self.bullet_radius,
                )
                if self.time_scale != 1.0:
                    # SpawnSingleBullet: velocity = speed * effectiveFramerateMultiplier
                    b.vel = b.vel * self.time_scale
                # moreFlags = shooter flags; 命令位由 AddCommand 记入(这里补 OR)
                b.more_flags = burst.flags
                for c in b.commands:
                    b.more_flags |= c.type
                # SpawnSingleBullet:255-283: flags 2/4/8 → 出生态 + pos -= vel*4
                # (在 RunCommands 之前, 用出生速度回退)
                st, frames = _spawn_state_spec(spec, burst.flags)
                if st:
                    b.spawn_state = st
                    b.spawn_frames = frames
                    b.pos = b.pos - b.vel * 4.0
                b.run_commands(self.time_scale)  # SpawnSingleBullet 末尾立即跑一次
                self._bullets.append(b)
                ctx.events.emit(
                    BulletSpawned(b.pos.x, b.pos.y, b.sprite, b.angle, b.speed, st)
                )
                count += 1
        return count

    def ring(
        self,
        at: Vec2,
        arms: int,
        speed: float,
        ctx: FrameContext,
        *,
        aimed: bool = True,
        angle_step: float = 0.12,
        speed_b: float | None = None,
    ) -> int:
        """放一环( aimed=对准玩家 )。"""
        port = angle_to(at, self.player_pos) if aimed else 0.0
        return self.fire(
            Burst(
                at,
                port,
                Aim.RING_AIMED if aimed else Aim.RING_ABSOLUTE,
                arms,
                1,
                speed,
                speed_b if speed_b is not None else speed,
                angle_step,
            ),
            ctx,
        )

    def spread(
        self,
        at: Vec2,
        arms: int,
        speed: float,
        spread: float,
        ctx: FrameContext,
        *,
        aimed: bool = True,
        speed_b: float | None = None,
    ) -> int:
        """放一扇( aimed=对准玩家 )。"""
        port = angle_to(at, self.player_pos) if aimed else 0.0
        return self.fire(
            Burst(
                at,
                port,
                Aim.SPREAD_AIMED if aimed else Aim.SPREAD_ABSOLUTE,
                arms,
                1,
                speed,
                speed_b if speed_b is not None else speed,
                spread,
            ),
            ctx,
        )

    # ---- 每帧(MOVEMENT 槽) ----
    def step(self, ctx: FrameContext) -> None:
        """推进全场一帧(OnUpdate: 出生态分支 → 命令 → 更新器 → 位移 → 出界)。"""
        for b in self._bullets:
            if b.spawn_state:
                # 出生态: pos += vel/2 | /2.5 | /3; 倒计时未归 0 本帧到此为止
                # (C++ timer2-- 被 update_timers 的 timer2++ 抵消, 等效 age 冻结)
                b.pos = b.pos + b.vel / _SPAWN_MOVE_DIV[b.spawn_state]
                b.spawn_frames -= 1
                if b.spawn_frames > 0:
                    continue
                b.spawn_state = 0  # switch_break: 转 NORMAL, 当帧落入正常分支
            b.run_commands(self.time_scale)
            b.step_commands(self.player_pos, self.time_scale)
            if b.spawn_delay != 0:
                b.spawn_delay -= 1
            b.step()
            if b.spawn_delay == 0:
                if b.off_screen():
                    if b.ex_flags & OFFSCREEN_GRACE:
                        # 带转向/反弹命令的弹出界后宽限 128 帧(可以回来)
                        b.out_of_bounds_time += 1
                        if b.out_of_bounds_time >= OFFSCREEN_GRACE_FRAMES:
                            b.dead = True
                    elif b.out_of_bounds_time == 0:
                        b.dead = True
                    else:
                        # BulletManager.cpp:968-974: 宽限位已清但 outOfBoundsTime
                        # 还有剩(转向/反弹在屏外跑完)时, 逐帧递减而非立即销毁
                        b.out_of_bounds_time -= 1
                else:
                    b.out_of_bounds_time = 0
        for b in self._bullets:
            if b.dead:
                ctx.events.emit(
                    BulletDespawned(b.pos.x, b.pos.y, b.sprite, DespawnCause.OFFSCREEN)
                )
        self._bullets = [b for b in self._bullets if not b.dead]
        # BulletManager.cpp:1205-1207: screenClearTime 每帧递减
        if self.screen_clear_time != 0:
            self.screen_clear_time -= 1

    # ---- 判定(COLLISION 槽) ----
    def check_player(self, ctx: FrameContext) -> None:
        """逐弹擦弹(每弹一次) + 命中候选(首弹命中出事件即停, 结算由作品订阅)。"""
        # AABB 语义: 弹盒 pos±bullet_radius, 擦弹盒再外扩 GRAZE_EXPAND(CheckGraze);
        # 旧 hits_player 的圆形判定只有旧单测/ demo 用, 真实路径是世界层 AABB
        # (check_killbox, size=(bullet_radius*2, bullet_radius*2)) —— 以此为准
        for b in self._bullets:
            if b.spawn_state:
                continue  # 出生态弹无擦弹/命中(OnUpdate SPAWNING_* 分支不到判定)
            if self.graze_enabled and not b.grazed:
                g = self.bullet_radius + GRAZE_EXPAND + self.graze_radius
                if (
                    abs(b.pos.x - self.player_pos.x) <= g
                    and abs(b.pos.y - self.player_pos.y) <= g
                ):
                    b.grazed = True
                    ctx.events.emit(BulletGraze(b.pos.x, b.pos.y))
            if not self.hit_enabled:
                continue
            h = self.bullet_radius + self.player_radius
            if (
                abs(b.pos.x - self.player_pos.x) <= h
                and abs(b.pos.y - self.player_pos.y) <= h
            ):
                ctx.events.emit(BulletHit(b.pos.x, b.pos.y))
                break  # 旧世界层命中即 break(死亡结算后本帧不再判)

    # ---- 批量操作 ----
    def clear(self, events: EventStream | None = None) -> None:
        """清场(消弹事件可选; 转道具/特效等反应由作品订阅 BulletDespawned)。"""
        if events is not None:
            for b in self._bullets:
                events.emit(
                    BulletDespawned(b.pos.x, b.pos.y, b.sprite, DespawnCause.CLEARED)
                )
        self._bullets.clear()

    def stop_bullet_movement(self) -> None:
        """BulletManager::StopBulletMovement (:1476-1500): 全场活弹速度清零永停。

        C++ 另清 angularVelocity/acceleration; 本模型角速度/加速度在命令槽里,
        speed=0 使后续命令重算出的速度亦为 0, 语义等价。
        """
        for b in self._bullets:
            b.vel = Vec2.zero()
            b.speed = 0.0

    def alive(self) -> list[Bullet]:
        """在场弹列表(内部容器, 别改)。"""
        return self._bullets

    def __len__(self) -> int:
        return len(self._bullets)
