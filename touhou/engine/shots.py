"""自机弹: PlayerShot 弹池/持续弹槽 + 射击发生器(fire 周期/entry 链) + 伤害结算。

弹种参数(.sht 解析出的 ShotData)与特色回调(homing/激光/missile 等)由作品
经组合根注入: fire/update/hit 回调表 + trail_damage_cbs; engine 只实现
DefaultFireBulletCallback 与通用弹道/命中语义 (Player.cpp §A.1/A.5/A.6)。
"""

from __future__ import annotations

from collections.abc import Callable

import msgspec

from ..schemas.shot_data import ShotData, ShotEntry
from ..utils.math import Vec2
from .context import FrameContext
from .core import System, World
from .events import Event

SHOT_POOL_SIZE = 96  # Player.bullets[96]
SHOT_HISTORY = 16  # posHistory[16]
PERSIST_RELEASE_CAP = 50  # 松开射击(fireBulletTimer<0)时槽计时压到 50
FIRE_CYCLE = 30  # 射击总周期(fireTime 0..29 滚动, §A.5)

_HISTORY_SENTINEL = Vec2(-999.0, 0.0)
_SCREEN_W = 384.0
_SCREEN_H = 448.0


class ShotFired(Event, frozen=True, tag="shot_fired"):
    """一颗自机弹发射(sound_idx<0 = 无发弹音; 音效由作品订阅播放)。"""

    x: float
    y: float
    sound_idx: int


class PlayerShot(msgspec.Struct):
    """一颗自机弹(§A.1 PlayerBullet): 池化复用, bullet_state==0 为空位。

    hitbox 为全宽/全高(判定按 pos ± hitbox/2)。回调字段存 .sht 里的索引,
    分派表在 ShotField(fire/update/hit handlers)。
    """

    pos: Vec2 = msgspec.field(default_factory=Vec2.zero)
    velocity: Vec2 = msgspec.field(default_factory=Vec2.zero)
    offset: Vec2 = msgspec.field(default_factory=Vec2.zero)  # orb/laser 相对发射点偏移
    pos_history: list[Vec2] = msgspec.field(
        default_factory=lambda: [_HISTORY_SENTINEL] * SHOT_HISTORY
    )
    hitbox: tuple[float, float] = (6.0, 6.0)  # 全宽/全高(C++ hitboxSize.x/y)
    speed: float = 0.0
    angle: float = 0.0
    timer: int = 0  # 存活帧数(ZunTimer)
    damage: int = 1
    bullet_state: int = 0  # 0=死 1=活 2=命中爆炸(穿透弹仍继续判定, 见 iter_hits)
    bullet_state2: int = 0  # 3=穿透(命中不减速) 4/5=激光型(奇偶帧减半伤害)
    timer_idx: int = 0  # 占用的 timers 槽(0/1/2)
    option_id: int = 0  # 发射该弹的 option(0=本体 1/2=子机)
    trail_length: int = 0  # 拖尾长度(拖尾段伤害见 iter_hits)
    anm_file_idx: int = 0
    update_cb: int = 0
    draw_cb: int = 0
    hit_cb: int = 0
    entry: ShotEntry | None = None  # 发射它的射击条目


class ShotTimer(msgspec.Struct):
    """持续弹槽(§A.1 PlayerBulletTimer): 每槽一个 orb/laser 持续弹。"""

    timer: int = 0
    shot: PlayerShot | None = None


FireHandler = Callable[["ShotField", ShotEntry, PlayerShot, FrameContext], bool]
UpdateHandler = Callable[["ShotField", PlayerShot, FrameContext], bool]
HitHandler = Callable[["ShotField", PlayerShot, FrameContext], bool]


class ShotField(msgspec.Struct):
    """自机弹场状态容器: 弹池 + 持续弹槽 + 射击发生器 + 作品注入面。

    作品侧每帧同步(PlayerSystem 代同步或作品自管): player_pos/focus/firing/
    player_state(=PlayerState 整数值)/bomb_active/dialog_active/fire_suppressed
    (旧 MarisaB 炸弹中不发射的通用化)/options(子机位置, entry.option>0 用)/
    power(火力档查表)。构造注入: shot_data/shot_data_focus(.sht) 与回调表。
    """

    pool: list[PlayerShot] = msgspec.field(
        default_factory=lambda: [PlayerShot() for _ in range(SHOT_POOL_SIZE)]
    )
    timers: list[ShotTimer] = msgspec.field(
        default_factory=lambda: [ShotTimer() for _ in range(3)]
    )
    # 各槽当前生效的 ShotEntry(C++ shtEntries[4], 换 entry 时中断旧持续弹)
    sht_entries: list[ShotEntry | None] = msgspec.field(
        default_factory=lambda: [None] * 4
    )
    shot_data: ShotData | None = None
    shot_data_focus: ShotData | None = None
    fire_handlers: dict[int, FireHandler] = msgspec.field(default_factory=dict)
    update_handlers: dict[int, UpdateHandler] = msgspec.field(default_factory=dict)
    hit_handlers: dict[int, HitHandler] = msgspec.field(default_factory=dict)
    # 有拖尾段伤害的 update_cb 集合(旧: update_cb==UPDATE_PLAYER_LASER 特判)
    trail_damage_cbs: frozenset[int] = frozenset()
    fire_time: int = -1  # fireBulletTimer: -1=未射击, 0..fire_cycle-1 滚动
    fire_cycle: int = FIRE_CYCLE
    power: float = 0.0
    player_pos: Vec2 = Vec2(_SCREEN_W / 2, _SCREEN_H - 64)
    focus: bool = False
    firing: bool = False
    player_state: int = 0  # PlayerState 整数值(0=ALIVE 1=SPAWNING 2=DEAD 3=INVULN)
    bomb_active: bool = False  # 炸弹中(持续弹压计时/伤害 /3)
    dialog_active: bool = False  # 对话框中(持续弹压计时)
    fire_suppressed: bool = False  # 压制发射(作品同步, 如特定机体炸弹中)
    options: list[Vec2] = msgspec.field(default_factory=list)  # 子机位置(作品同步)

    def shots(self) -> list[PlayerShot]:
        """存活自机弹视图(渲染迭代; 写 bullet_state=0 消弹)。"""
        return [b for b in self.pool if b.bullet_state != 0]

    # ---- 射击调度(UpdateFireBulletTimer / SpawnBullets, §A.5) ----
    def fire_pass(self, ctx: FrameContext) -> None:
        """fireBulletTimer: 按住射击从 -1 置 0 启动, 每帧推进, fire_cycle 帧滚动。

        到顶或 DEAD/SPAWNING 归 -1(下次按下从 0 重启); fire_suppressed 时
        计时照走但不发射 (UpdateFireBulletTimer 的机体抑制分支通用化)。
        player_state 1=SPAWNING 2=DEAD。
        """
        if self.firing and self.fire_time < 0 and self.player_state not in (1, 2):
            self.fire_time = 0  # StartFireBulletTimer(HandlePlayerInputs)
        if self.fire_time < 0:
            return
        if not self.fire_suppressed:
            self._spawn_bullets(ctx)
        self.fire_time += 1
        if self.fire_time >= self.fire_cycle or self.player_state in (1, 2):
            self.fire_time = -1

    def _spawn_bullets(self, ctx: FrameContext) -> None:
        """SpawnBullets: 每个空弹位顺次尝试 entry 链, 一个弹位一帧至多发射一条。"""
        sd = self.shot_data_focus if self.focus else self.shot_data
        if sd is None:
            return
        level = sd.level_for_power(self.power)
        entries = [e for e in level.entries if e.fire_interval >= 0]
        ei = 0
        for shot in self.pool:  # 找第一个 bullet_state==0 的空位
            if ei >= len(entries):
                return
            if shot.bullet_state != 0:
                continue
            while ei < len(entries):
                entry = entries[ei]
                ei += 1
                if self._fire_entry(entry, shot, ctx):
                    shot.bullet_state = 1
                    shot.entry = entry
                    shot.update_cb = entry.update_cb
                    shot.draw_cb = entry.draw_cb
                    shot.hit_cb = entry.hit_cb
                    break

    def _fire_entry(
        self, entry: ShotEntry, shot: PlayerShot, ctx: FrameContext
    ) -> bool:
        """Fire 回调分派(g_ShtFireFuncs): 未注册的 cb 走 DefaultFireBulletCallback。"""
        handler = self.fire_handlers.get(entry.fire_cb)
        if handler is not None:
            return handler(self, entry, shot, ctx)
        return self._fire_default(entry, shot, ctx)

    def _fire_default(
        self, entry: ShotEntry, shot: PlayerShot, ctx: FrameContext
    ) -> bool:
        """DefaultFireBulletCallback: 周期/偏移门控, 到点从 entry 初始化弹。"""
        if self.fire_time % entry.fire_interval != entry.fire_offset:
            return False
        self.init_shot(entry, shot, ctx)
        return True

    def init_shot(self, entry: ShotEntry, shot: PlayerShot, ctx: FrameContext) -> None:
        """从 entry 初始化弹(不含回调专属字段); 发弹音产 ShotFired 事件。"""
        origin = (
            self.player_pos if entry.option == 0 else self.options[entry.option - 1]
        )
        shot.pos = origin + Vec2(*entry.offset)
        shot.hitbox = entry.hitbox
        shot.angle = entry.angle
        shot.speed = entry.speed
        shot.velocity = Vec2.from_angle(entry.angle, entry.speed)
        shot.timer = 0
        shot.bullet_state2 = entry.bullet_state2
        shot.damage = entry.damage
        shot.anm_file_idx = entry.anm_file_idx
        # 自机弹发弹音 (Player.cpp:116-119, SpawnBullets 的 shtEntry->soundIdx)
        ctx.events.emit(ShotFired(shot.pos.x, shot.pos.y, entry.sound_idx))

    # ---- 每帧(UpdateShots, §A.5): 持续弹槽清理 + 活弹逐帧更新 ----
    def step(self, ctx: FrameContext) -> None:
        """推进一帧: 槽计时/脱钩 → update 回调 → 位移 → 出屏消弹。

        旧实现的子机状态机驱动槽清理(focus 切态时中断对应槽)属作品侧:
        作品 system 在本步进前自行清 timers 槽 (旧 _update_shots 首段)。
        """
        # 玩家死亡: 持续弹全部脱钩消弹
        if self.player_state == 2:  # PlayerState.DEAD
            for ts in self.timers:
                if ts.shot is not None:
                    ts.shot.bullet_state = 0
                    ts.shot = None
        # 槽计时: 0<timer<999 每帧递减; 未射击时压到 50; 归零脱钩
        for ts in self.timers:
            if ts.shot is None:
                continue
            if 0 < ts.timer < 999:
                ts.timer -= 1
            if self.fire_time < 0 and ts.timer > PERSIST_RELEASE_CAP:
                ts.timer = PERSIST_RELEASE_CAP
            if ts.timer == 0:
                ts.shot = None
        for shot in self.pool:
            if shot.bullet_state == 0:
                continue
            handler = self.update_handlers.get(shot.update_cb)
            if handler is not None and handler(self, shot, ctx):
                shot.bullet_state = 0
                continue
            shot.pos = shot.pos + shot.velocity
            if shot.bullet_state2 not in (4, 5) and _shot_out_of_bounds(shot):
                shot.bullet_state = 0
            shot.timer += 1

    # ---- 命中敌人(CalcDamageToEnemy, §A.6) ----
    def iter_hits(
        self,
        enemy_center: Vec2,
        enemy_size: tuple[float, float],
        ctx: FrameContext,
        *,
        bomb_active: bool | None = None,
    ) -> list[tuple[PlayerShot, int]]:
        """对一个敌人(center ± size/2)逐发结算本帧伤害, 返回 (shot, damage) 列表。

        有副作用, 每帧每敌人至多调用一次:
        - 非激光弹命中后 bullet_state=2(爆炸); bullet_state2!=3 才速度/8(穿透不减速);
        - bullet_state2 4/5(激光型)只在 timer%2==0 出伤害;
        - hit 回调(如 missile 隔帧)返回 True 则跳过当帧伤害;
        - bomb 中伤害 max(damage//3, 1)(bomb_active 缺省取 self.bomb_active);
        - trail_damage_cbs 命中的弹, pos_history 拖尾段各算 1 点伤害
          (对照 C++ UpdatePlayerLaser 写 bombDamageBoxes[96+i] lifetime=1)。

        简化: C++ 开头 `!invulnerabilityTimer.HasTicked()` 的 0 伤害守卫依赖
        ZunTimer 暂停语义(current==previous), 整数计时模型下恒为已 tick, 故省略。
        """
        bomb = self.bomb_active if bomb_active is None else bomb_active
        ex, ey = enemy_size[0] / 2, enemy_size[1] / 2
        out: list[tuple[PlayerShot, int]] = []
        for shot in self.pool:
            if shot.bullet_state == 0:
                continue
            # 只结算活弹; 爆炸(state==2)后仅穿透弹(bs2==3)继续判定
            if shot.bullet_state != 1 and shot.bullet_state2 != 3:
                continue
            if not _aabb_intersect(
                shot.pos, shot.hitbox[0] / 2, shot.hitbox[1] / 2, enemy_center, ex, ey
            ):
                continue
            if shot.bullet_state2 in (4, 5) and shot.timer % 2 != 0:
                continue
            handler = self.hit_handlers.get(shot.hit_cb)
            if handler is not None and handler(self, shot, ctx):
                continue
            dmg = shot.damage if not bomb else max(shot.damage // 3, 1)
            if shot.bullet_state2 not in (4, 5):
                shot.bullet_state = 2
                if shot.bullet_state2 != 3:
                    shot.velocity = shot.velocity / 8.0
            out.append((shot, dmg))
        # 拖尾历史段(每段 1 点, 无奇偶减半)
        for shot in self.pool:
            if shot.bullet_state == 0 or shot.update_cb not in self.trail_damage_cbs:
                continue
            for i in range(min(shot.trail_length, SHOT_HISTORY)):
                hp = shot.pos_history[i]
                if hp.x < -900.0:
                    break
                if _aabb_intersect(
                    hp, shot.hitbox[0] / 2, shot.hitbox[1] / 2, enemy_center, ex, ey
                ):
                    out.append((shot, 1))
        return out

    def calc_damage_to_enemy(
        self,
        enemy_center: Vec2,
        enemy_size: tuple[float, float],
        ctx: FrameContext,
        *,
        bomb_active: bool | None = None,
    ) -> int:
        """iter_hits 的求和封装(一帧对一个敌人的总伤害)。"""
        return sum(
            d
            for _, d in self.iter_hits(
                enemy_center, enemy_size, ctx, bomb_active=bomb_active
            )
        )


class ShotMovementSystem(System[World]):
    """MOVEMENT 槽: 自机弹推进(UpdateShots) → 射击发生器(fire_pass)。

    顺序对齐旧 OnUpdate (UpdateShots → UpdateFireBulletTimer): 当帧新生的弹
    不动, 下一帧才开始位移。
    """

    def __init__(self, field: ShotField) -> None:
        self.field = field

    def tick(self, world: World, ctx: FrameContext) -> None:
        self.field.step(ctx)
        self.field.fire_pass(ctx)


def _shot_out_of_bounds(b: PlayerShot) -> bool:
    """弹中心±半宽完全离开版面(GameManager::IsInBounds; 判定盒近似精灵尺寸)。"""
    hx, hy = b.hitbox[0] / 2, b.hitbox[1] / 2
    return (
        b.pos.x + hx < 0.0
        or b.pos.x - hx > _SCREEN_W
        or b.pos.y + hy < 0.0
        or b.pos.y - hy > _SCREEN_H
    )


def _aabb_intersect(
    c1: Vec2, hx1: float, hy1: float, c2: Vec2, hx2: float, hy2: float
) -> bool:
    """两 AABB(中心+半宽) 是否相交(边相接算相交, 同 C++ 的 > 判定)。"""
    return not (
        c1.x - hx1 > c2.x + hx2
        or c1.y - hy1 > c2.y + hy2
        or c1.x + hx1 < c2.x - hx2
        or c1.y + hy1 < c2.y - hy2
    )
