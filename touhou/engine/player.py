"""自机: PlayerField 状态机(出生/无敌/死亡重生) + 高低速移动 + 判定/擦弹。

射击发生器与自机弹在 shots.py; 弹种参数(.sht)/判定半径/移速由作品经组合根
注入或每帧同步。死亡结算内容(power 罚/掉 P/资源罚)是作品概念: 本模块只产
PlayerDied/PlayerDeathSettled/PlayerRespawned 事件, 作品订阅后自行入账。
"""

from __future__ import annotations

from enum import IntEnum

import msgspec

from ..utils.math import Vec2
from .bullets.field import GRAZE_EXPAND
from .context import FrameContext
from .core import System, World
from .events import Event
from .input import Button, InputFrame
from .shots import ShotField

# ---- 状态机/判定关键常量(数值出处 th07 Player.cpp, 弹幕 STG 通用) ----
RESPAWN_INVULN = 240  # 重生无敌帧数
SPAWN_INVULN = 120  # 出生 invulnerabilityTimer(AddedCallback)
SPAWN_TICKS = 30  # Respawn 触发阈值(invulnerabilityTimer>=30)
BULLET_GRACE_PERIOD = 60  # 重生后每帧清弹信号的帧数

_SCREEN_W = 384.0
_SCREEN_H = 448.0


class PlayerState(IntEnum):
    """玩家状态机(Player.hpp PlayerState 的通用四态; 数值序勿改, 序列化依赖)。"""

    ALIVE = 0
    SPAWNING = 1
    DEAD = 2
    INVULNERABLE = 3


class PlayerDied(Event, frozen=True, tag="player_died"):
    """玩家被弹/体术命中死亡(结算/音效/扣残机由作品订阅)。"""

    x: float
    y: float


class PlayerDeathSettled(Event, frozen=True, tag="player_death_settled"):
    """死亡倒计时归零(UpdateDeath; power 罚/掉落/资源罚由作品订阅实现)。"""

    x: float
    y: float


class PlayerRespawned(Event, frozen=True, tag="player_respawned"):
    """重生完成(DEAD→INVULNERABLE + 240 无敌 + 60 帧清弹信号期)。"""

    x: float
    y: float


class PlayerGrazed(Event, frozen=True, tag="player_grazed"):
    """擦弹一次(敌人体术路径; 敌弹擦弹见 bullets 的 BulletGraze)。"""

    x: float
    y: float


class PlayerGraceClear(Event, frozen=True, tag="player_grace_clear"):
    """重生清弹期每帧一条(订阅方清全场敌弹, 旧 RemoveAllBullets(0))。"""


class PlayerField(msgspec.Struct):
    """自机状态容器: 状态机 + 移动 + 判定/擦弹 + 死亡重生骨架。

    数值(hitbox/graze 半径、四档移速、重生计时初值)由作品按 .sht 注入;
    结界类保命机制走 ``_intercept_hit`` hook(命中时返回 True = 拦截, 不死)。
    """

    pos: Vec2 = Vec2(_SCREEN_W / 2, _SCREEN_H - 64)
    velocity: Vec2 = Vec2.zero()
    focus: bool = False
    firing: bool = False
    state: PlayerState = PlayerState.SPAWNING
    invulnerability_timer: int = SPAWN_INVULN
    respawn_timer: int = 0
    initial_respawn_timer: int = 30  # 决死窗/死亡倒计时初值(.sht 注入)
    bullet_grace_period: int = 0
    dialog_active: bool = False  # 对话框中(射击/炸弹门控 + 持续弹压计时)
    hitbox_radius: float = 2.0  # 判定盒半宽(作品按 .sht 注入, 半宽 = radius/2)
    graze_radius: float = 24.0  # 擦弹盒半宽(同上)
    bounds: tuple[Vec2, Vec2] = msgspec.field(
        default_factory=lambda: (
            Vec2(8, 16),
            Vec2(_SCREEN_W - 8, _SCREEN_H - 16),
        )
    )
    # 四档移速(.sht speed/speedFocus/speedDiagonal/speedDiagonalFocus 注入)
    move_speed: float = 0.0
    move_speed_focus: float = 0.0
    move_speed_diagonal: float = 0.0
    move_speed_diagonal_focus: float = 0.0
    frame: int = 0
    _move: Vec2 = Vec2.zero()

    @property
    def alive(self) -> bool:
        """非 DEAD。"""
        return self.state != PlayerState.DEAD

    # ---- 输入 ----
    def push(self, x: int, y: int, *, focus: bool = False, firing: bool = True) -> None:
        """写入本帧移动/低速/射击输入。"""
        self._move = Vec2(float(x), float(y))
        self.focus = focus
        self.firing = firing

    def push_frame(self, input: InputFrame) -> None:
        """从 InputFrame 写入本帧输入(方向键 + FOCUS/SHOT)。"""
        held = input.held
        self.push(
            int(Button.RIGHT in held) - int(Button.LEFT in held),
            int(Button.DOWN in held) - int(Button.UP in held),
            focus=Button.FOCUS in held,
            firing=Button.SHOT in held,
        )

    # ---- 每帧(对照 Player::OnUpdate: 状态机 → 移动; 射击在 shots.py) ----
    def step(self, ctx: FrameContext) -> None:
        """推进一帧: 清弹信号 → 状态机(死亡倒计时/出生/无敌) → 移动。"""
        self.frame += 1
        # UpdateState: bulletGracePeriod 内每帧清弹信号
        if self.bullet_grace_period > 0:
            self.bullet_grace_period -= 1
            ctx.events.emit(PlayerGraceClear())
        if self.state == PlayerState.DEAD:
            self._update_death(ctx)
        elif self.state == PlayerState.SPAWNING:
            # Respawn: invulnerabilityTimer>=30 → INVULNERABLE(240)
            # (AddedCallback 给 120>=30, 出生次帧即转入)
            if self.invulnerability_timer >= SPAWN_TICKS:
                self._enter_invulnerable()
        elif self.state == PlayerState.INVULNERABLE:
            self.invulnerability_timer -= 1
            if self.invulnerability_timer <= 0:
                self.invulnerability_timer = 0
                self.state = PlayerState.ALIVE
        # HandlePlayerInputs: DEAD/SPAWNING 不移动
        if self.state not in (PlayerState.DEAD, PlayerState.SPAWNING):
            self._move_player()

    # ---- 死亡/重生(§A.7: Die/UpdateDeath/Respawn) ----
    def die(self, ctx: FrameContext) -> None:
        """死亡: DEAD + 倒计时复位, 产 PlayerDied(音效/结算由作品订阅)。"""
        self.state = PlayerState.DEAD
        self.invulnerability_timer = 0
        self.respawn_timer = self.initial_respawn_timer
        ctx.events.emit(PlayerDied(self.pos.x, self.pos.y))

    def take_hit(self, ctx: FrameContext) -> bool:
        """被弹入口(订阅 BulletHit/LaserHit 后调用): ALIVE 且未被拦截 → 死。"""
        if self.state != PlayerState.ALIVE:
            return False
        if self._intercept_hit(ctx):
            return False
        self.die(ctx)
        return True

    def _intercept_hit(self, ctx: FrameContext) -> bool:
        """命中拦截 hook(结界保命等; 基类不拦截, 作品层覆盖并自产事件)。"""
        return False

    def _update_death(self, ctx: FrameContext) -> None:
        """死亡倒计时: 归零产 PlayerDeathSettled → 重生 → PlayerRespawned。"""
        if self.respawn_timer > 0:
            self.respawn_timer -= 1
            if self.respawn_timer == 0:
                ctx.events.emit(PlayerDeathSettled(self.pos.x, self.pos.y))
                self.respawn()
                ctx.events.emit(PlayerRespawned(self.pos.x, self.pos.y))

    def respawn(self, pos: Vec2 | None = None) -> None:
        """重生: INVULNERABLE + 240 无敌 + 60 帧清弹期(Respawn)。"""
        self.pos = pos or Vec2(_SCREEN_W / 2, _SCREEN_H - 64)
        self._enter_invulnerable()

    def _enter_invulnerable(self) -> None:
        self.state = PlayerState.INVULNERABLE
        self.invulnerability_timer = RESPAWN_INVULN
        self.respawn_timer = self.initial_respawn_timer
        self.bullet_grace_period = BULLET_GRACE_PERIOD

    # ---- 判定/擦弹(§A.7: CheckGraze/CalcKillboxCollision, AABB) ----
    def graze_check(self, center: Vec2, w: float, h: float, ctx: FrameContext) -> bool:
        """擦弹判定: 盒 center±(w,h)/2 外扩 20px 与擦弹盒相交; DEAD/SPAWNING 不擦。"""
        if self.state in (PlayerState.DEAD, PlayerState.SPAWNING):
            return False
        hx, hy = w / 2 + GRAZE_EXPAND, h / 2 + GRAZE_EXPAND
        if not _aabb_intersect(
            center, hx, hy, self.pos, self.graze_radius, self.graze_radius
        ):
            return False
        ctx.events.emit(PlayerGrazed(center.x, center.y))
        return True

    def contact_hit(self, center: Vec2, w: float, h: float, ctx: FrameContext) -> bool:
        """体术命中判定 (CalcKillboxCollision 返回 1 的分支, Player.cpp:1014-1039)。

        盒 center±(w,h)/2 与判定盒相交即命中: ALIVE → 拦截或死, 其余状态
        (无敌/出生/死亡)仅命中无玩家侧效果; 返回是否相交(敌人侧扣血由调用方做)。
        """
        if not _aabb_intersect(
            center, w / 2, h / 2, self.pos, self.hitbox_radius, self.hitbox_radius
        ):
            return False
        if self.state == PlayerState.ALIVE and not self._intercept_hit(ctx):
            self.die(ctx)
        return True

    def hits_killbox(self, center: Vec2, w: float, h: float) -> bool:
        """纯几何: 盒 center±(w,h)/2 是否与判定盒相交(不触发任何状态变化)。"""
        return _aabb_intersect(
            center, w / 2, h / 2, self.pos, self.hitbox_radius, self.hitbox_radius
        )

    # ---- 移动 ----
    def _move_player(self) -> None:
        straight, diagonal = self._current_speeds()
        mv = self._move
        if mv.x and mv.y:
            v = Vec2(mv.x * diagonal, mv.y * diagonal)
        else:
            v = Vec2(mv.x * straight, mv.y * straight)
        self.velocity = v
        self.pos = self.pos + v
        lo, hi = self.bounds
        self.pos = Vec2(
            max(lo.x, min(self.pos.x, hi.x)), max(lo.y, min(self.pos.y, hi.y))
        )

    def _current_speeds(self) -> tuple[float, float]:
        """当前 (直线速度, 斜向速度): 按 focus 取注入值。"""
        if self.focus:
            return self.move_speed_focus, self.move_speed_diagonal_focus
        return self.move_speed, self.move_speed_diagonal


class PlayerSystem(System[World]):
    """LOGIC 槽: 输入 → 状态机/移动; 末尾把自机状态同步给 ShotField(若挂了)。"""

    def __init__(
        self,
        field: PlayerField,
        shots: ShotField | None = None,
        read_input: bool = True,
    ) -> None:
        self.field = field
        self.shots = shots
        self.read_input = read_input

    def tick(self, world: World, ctx: FrameContext) -> None:
        if self.read_input:
            self.field.push_frame(ctx.input)
        self.field.step(ctx)
        if self.shots is not None:
            s, f = self.shots, self.field
            s.player_pos = f.pos
            s.focus = f.focus
            s.firing = f.firing
            s.player_state = int(f.state)


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
