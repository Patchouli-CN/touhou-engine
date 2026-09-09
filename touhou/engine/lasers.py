"""激光: 三态机(SPAWNING/ACTIVE/DESPAWNING) + 旋转局部坐标命中/擦激光判定。"""

from __future__ import annotations

import math
from enum import IntEnum

import msgspec

from ..utils.math import Vec2, angle_to
from .context import FrameContext
from .core import System, World
from .events import Event

#: 同时在场的激光上限 (BulletManager 激光数组容量)
LASER_CAP = 64
#: 擦激光盒外扩像素
LASER_GRAZE_EXPAND = 48.0
#: 擦激光节流: 每 12 帧允许一次
LASER_GRAZE_PERIOD = 12


class LaserState(IntEnum):
    """激光三态。"""

    SPAWNING = 0  # 出现(窄命中)
    ACTIVE = 1  # 全宽命中
    DESPAWNING = 2  # 消散


class LaserSpawned(Event, frozen=True, tag="laser_spawned"):
    """一条激光入场。"""

    x: float
    y: float
    angle: float
    width: float
    color: int = 0


class LaserGraze(Event, frozen=True, tag="laser_graze"):
    """擦到激光(盒外扩 48px, 每 12 帧节流一次, 每帧最多一条)。"""

    x: float
    y: float


class LaserHit(Event, frozen=True, tag="laser_hit"):
    """激光命中候选(每帧最多一条, 生死结算由作品订阅)。"""

    x: float
    y: float


class Laser(msgspec.Struct):
    """一条激光。"""

    pos: Vec2
    angle: float
    width: float = 8.0
    speed: float = 0.0
    start_time: int = 0  # 出现完成帧
    hitbox_start_time: int = 0
    duration: int = 0  # 全宽保持帧
    end_time: int = 0  # 消散完成帧
    hitbox_end_time: int = 0
    start_length: float = 0.0  # 长度上限(0=不限)
    flags: int = 0
    color: int = 0
    hide_warning: bool = False

    state: LaserState = LaserState.SPAWNING
    offset_a: float = 0.0
    offset_b: float = 0.0
    target_width: float = 8.0
    timer: int = 0
    in_use: bool = True

    def __post_init__(self) -> None:
        self.target_width = self.width
        if self.start_time == 0:
            self.state = LaserState.ACTIVE

    # ---- 每帧 ----
    def step(self, dt: float = 1.0) -> None:
        """推进一帧: 几何(长度增长/超长销毁) + 三态迁移。"""
        self._geometry(dt)
        if self.state == LaserState.SPAWNING:
            if self.timer >= self.start_time:
                self.timer = 0
                self.state = LaserState.ACTIVE
        elif self.state == LaserState.ACTIVE:
            if self.timer >= self.duration:
                self.timer = 0
                self.state = LaserState.DESPAWNING
                if self.end_time == 0:
                    self.in_use = False
        elif self.state == LaserState.DESPAWNING:
            if self.timer >= self.end_time:
                self.in_use = False
        self.timer += 1

    def _geometry(self, dt: float) -> None:
        self.offset_b += self.speed * dt
        if self.start_length and self.offset_b - self.offset_a > self.start_length:
            self.offset_a = self.offset_b - self.start_length
        self.offset_a = max(0.0, self.offset_a)
        if self.offset_a >= 640:  # 超长销毁
            self.in_use = False

    # ---- 几何访问器 ----
    @property
    def hitbox(self) -> tuple[Vec2, Vec2]:
        """返回 (center, half_size) 的激光命中盒(局部坐标)。"""
        half_w = self.width / 2
        length = self.offset_b - self.offset_a
        center = Vec2(self.offset_a + length / 2, 0)
        return center, Vec2(length / 2, half_w)

    def graze_frame(self) -> bool:
        """本帧是否允许擦激光(每 12 帧一次)。"""
        return self.timer % LASER_GRAZE_PERIOD == 0

    def localize(self, world: Vec2) -> Vec2:
        """把世界坐标旋到激光局部坐标(激光沿 +x, 原点在 pos)。"""
        relative = world - self.pos
        return relative.rotated(-self.angle)


def laser_hits_player(
    laser: Laser,
    player_pos: Vec2,
    player_r: float,
    graze_extra: float = LASER_GRAZE_EXPAND,
    can_graze: bool = True,
) -> tuple[bool, bool]:
    """返回 (命中判定点?, 擦激光?); laser 需在 ACTIVE/命中时段。"""
    center, half = laser.hitbox
    local = laser.localize(player_pos)

    def aabb(center_: Vec2, half_: Vec2, point: Vec2) -> bool:
        return (
            abs(point.x - center_.x) <= half_.x and abs(point.y - center_.y) <= half_.y
        )

    hit = aabb(Vec2(center.x, center.y), Vec2(half.x, half.y + player_r), local)
    graze = False
    if not hit and can_graze:
        gx, gy = half.x + graze_extra, half.y + graze_extra + player_r
        graze = aabb(Vec2(center.x, center.y), Vec2(gx, gy), local)
    return hit, graze


class LaserField(msgspec.Struct):
    """激光场状态容器: 激光列表 + 判定配置(作品侧每帧同步玩家相关字段)。"""

    lasers: list[Laser] = msgspec.field(default_factory=list)
    player_pos: Vec2 = Vec2(192, 400)  # 瞄准/判定用
    player_radius: float = 1.0  # 判定点半径(作品按 .sht hitbox/2 注入)
    hit_enabled: bool = True  # 旧: 炸弹中/非 ALIVE 不命中(世界层门控)
    graze_enabled: bool = True

    def spawn(
        self,
        pos: Vec2,
        angle: float,
        ctx: FrameContext,
        *,
        aimed: bool = True,
        width: float = 8.0,
        speed: float = 0.0,
        duration: int = 120,
        start_time: int = 20,
        hitbox_start_time: int = 20,
        end_time: int = 40,
        hitbox_end_time: int = 40,
        start_length: float = 160.0,
        flags: int = 0,
        color: int = 0,
    ) -> Laser | None:
        """生成一条激光(aimed 时按 player_pos 瞄准); 满 64 条返回 None。"""
        if len(self.lasers) >= LASER_CAP:
            return None
        if aimed:
            angle = angle_to(pos, self.player_pos) + angle
        laser = Laser(
            pos=pos,
            angle=angle,
            width=width,
            speed=speed,
            start_time=start_time,
            hitbox_start_time=hitbox_start_time,
            duration=duration,
            end_time=end_time,
            hitbox_end_time=hitbox_end_time,
            start_length=start_length,
            flags=flags,
            color=color,
        )
        # 激光初始长度(来自 shooter 的 endOffset; 之后随 speed 增长)
        laser.offset_b = start_length
        self.lasers.append(laser)
        ctx.events.emit(LaserSpawned(pos.x, pos.y, laser.angle, width, color))
        return laser

    def step(self, dt: float = 1.0) -> None:
        """推进全场一帧, 移除 in_use=False 的。"""
        for lsr in self.lasers:
            if lsr.in_use:
                lsr.step(dt)
        self.lasers = [lsr for lsr in self.lasers if lsr.in_use]

    def check_player(self, ctx: FrameContext) -> None:
        """命中/擦激光判定: 每帧最多产一条 LaserHit 和一条 LaserGraze。"""
        # 旧 check_player 返回 (hit, graze) 两个 bool 由世界层消费, 事件化后
        # 信息面一致(每帧一位); hit 结算(结界挡刀/死亡)由作品订阅
        hit_done = graze_done = False
        for lsr in self.lasers:
            if not lsr.in_use or (hit_done and graze_done):
                continue
            # 只在外观有效且处于命中窗口期间判定
            if lsr.state == LaserState.SPAWNING and lsr.timer < lsr.hitbox_start_time:
                continue
            if lsr.state == LaserState.DESPAWNING and lsr.timer >= lsr.hitbox_end_time:
                continue
            lhit, lgraze = laser_hits_player(
                lsr,
                self.player_pos,
                self.player_radius,
                can_graze=lsr.graze_frame() and self.graze_enabled,
            )
            if lhit and self.hit_enabled and not hit_done:
                ctx.events.emit(LaserHit(self.player_pos.x, self.player_pos.y))
                hit_done = True
            if lgraze and not graze_done:
                ctx.events.emit(LaserGraze(self.player_pos.x, self.player_pos.y))
                graze_done = True

    def remove_all(
        self,
        *,
        skip_flag4: bool = True,
        spawn_items: bool = False,
        spawn_at_pos: bool = False,
    ) -> list[Vec2]:
        """清弹连带激光 (BulletManager.cpp:439-471 激光段 / :524-550 DespawnBullets 段)。

        flags&4 的激光在 skip_flag4=True(RemoveAllBullets param!=10)时豁免;
        state<DESPAWNING 的进 DESPAWNING(timer=0, width=targetWidth);
        spawn_items 时自 startOffset 起沿线每 32px 记一个点(spawn_at_pos 另记
        激光原点, 仅 DespawnBullets 路径), 点位由返回值交给调用方同帧转道具
        (旧实现是 spawn_item 回调, 事件流帧末才投递, 回调又是禁用注入形态);
        hitbox_end_time 清零(含已在 DESPAWNING 的)。
        """
        points: list[Vec2] = []
        for lsr in self.lasers:
            if not lsr.in_use:
                continue
            if skip_flag4 and (lsr.flags & 4):
                continue
            if lsr.state < LaserState.DESPAWNING:
                lsr.state = LaserState.DESPAWNING
                lsr.timer = 0
                lsr.width = lsr.target_width
                if spawn_items:
                    if spawn_at_pos:
                        points.append(lsr.pos)
                    dx, dy = math.cos(lsr.angle), math.sin(lsr.angle)
                    off = lsr.offset_a
                    while lsr.offset_b > off:
                        points.append(Vec2(lsr.pos.x + dx * off, lsr.pos.y + dy * off))
                        off += 32.0
            lsr.hitbox_end_time = 0
        return points

    def clear(self) -> None:
        """清空。"""
        self.lasers.clear()

    def alive(self) -> list[Laser]:
        """在场(有效的)激光列表。"""
        return [lsr for lsr in self.lasers if lsr.in_use]

    def __len__(self) -> int:
        return len(self.alive())


class LaserMovementSystem(System[World]):
    """MOVEMENT 槽: 激光推进(几何 + 三态迁移 + 移除)。"""

    def __init__(self, field: LaserField) -> None:
        self.field = field

    def tick(self, world: World, ctx: FrameContext) -> None:
        self.field.step()


class LaserCollisionSystem(System[World]):
    """COLLISION 槽: 命中/擦激光判定, 产 LaserHit/LaserGraze 事件。"""

    def __init__(self, field: LaserField) -> None:
        self.field = field

    def tick(self, world: World, ctx: FrameContext) -> None:
        self.field.check_player(ctx)
