"""对外公共 API —— 给外部程序(脚本/AI/自定义渲染)用的 Pythonic 门面。

只面向注册表装配(GameAssembly)与作品世界(World 鸭子契约)编程, 不 import
games.*(AST 守护钉死): 作品经 TouhouRegistry 按名解析, 默认作品由作品包
register_default_game 显式声明。线程规矩(架构讨论稿 §2.5):

- sim 状态只有主线程能改: 写操作一律 ``game.queue(fn)`` 命令入队, 帧边界
  统一应用(落地在 engine ``tick_frame`` 的 World.commands drain);
- 重任务 ``game.submit(fn) -> Future`` 上 worker 池, fn 里只能碰传入的
  不可变快照/标量副本;
- 读走快照与标量副本(snapshot()/bullets_array()/各属性), 拿不到 world 本体。
"""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Protocol, cast

import numpy as np

from ..engine import (
    BombStarted,
    BossField,
    BulletField,
    EnemyField,
    Event,
    FrameContext,
    GameAssembly,
    GlobalsField,
    InputFrame,
    ItemField,
    LaserField,
    PlayerDied,
    PlayerField,
    SceneSnapshot,
    SpellcardBegan,
    SpellcardEnded,
    World,
)
from ..engine.context import Command, CommandQueue
from ..engine.events import EventHandler
from ..engine.input import Button
from ..engine.lasers import LaserState
from .events import GameEvent, GameEventKind, GamePhase
from .input import Input
from .resolve import _resolve_assembly, _resolve_ids
from .snapshots import (
    BossSnapshot,
    BulletSnapshot,
    EnemySnapshot,
    ItemSnapshot,
    LaserSnapshot,
    PlayerSnapshot,
    Snapshot,
)

# ---- worker 池(§2.5: 重任务异步; fn 只碰不可变快照) ----
_POOL: ThreadPoolExecutor | None = None


def _pool() -> ThreadPoolExecutor:
    """模块级共享 worker 池(懒建; 线程数保守, 重活排队)。"""
    global _POOL
    if _POOL is None:
        _POOL = ThreadPoolExecutor(max_workers=4, thread_name_prefix="touhou-api")
    return _POOL


class _FnCommand(Command):
    """把 ``fn(world, ctx)`` 可调用包成引擎命令, 应用结果解进 Future。"""

    def __init__(self, fn: Callable[[GameWorld, FrameContext], object]) -> None:
        self._fn = fn
        self.future: Future = Future()

    def apply(self, world: World, ctx: FrameContext) -> None:
        """帧边界执行; 异常进 Future(不抛给 CommandQueue, 免重复记日志)。"""
        try:
            self.future.set_result(self._fn(cast(GameWorld, world), ctx))
        except Exception as e:
            self.future.set_exception(e)


# ---- 作品解析 ----
class GameWorld(Protocol):
    """apis 门面面向的作品世界契约(鸭子满足, 作品世界无需继承/注册)。

    标量资源(残机/火力等)不在这里: 位置由作品自定, 走 stats()/set_stat()
    可选钩子(getattr 探测, 缺失报中文错)。
    """

    frame: int
    stage_no: int
    game_over: bool
    cleared: bool
    ending: object | None
    result: dict | None
    commands: CommandQueue
    subscribers: list[EventHandler]
    globals: GlobalsField
    player: PlayerField
    bullets: BulletField
    enemies: EnemyField
    items: ItemField
    lasers: LaserField
    boss: BossField | None

    def tick(self, input: InputFrame | None = None) -> SceneSnapshot:
        """推进一帧, 返回本帧 SceneSnapshot。"""
        ...


class Game:
    """一局作品对局的 headless 门面(不传 ``game=`` 用框架默认作品)。

    典型用法::

        game = Game(character="ReimuA", difficulty="Normal", seed=42)
        while game.phase == GamePhase.RUNNING:
            events = game.step(Input(shoot=True))
            if game.frame % 60 == 0:
                snap = game.snapshot()   # 按需, 每帧构造有开销

    ``lives`` 语义 = 开局残机数(内部按作品惯例折算, 如 th07 的 cfg.lifeCount
    变换); ``data_path`` 覆盖注册表登记的资源包路径。
    """

    def __init__(
        self,
        character: str | int | None = None,
        difficulty: str | int | None = None,
        stage: int = 1,
        *,
        game: str | None = None,
        data_path: str | None = None,
        seed: int | None = None,
        lives: int | None = None,
        score_path: str | None = None,
    ) -> None:
        assembly = _resolve_assembly(game, data_path)
        character_id, difficulty_id = _resolve_ids(assembly, character, difficulty)
        world_cls = assembly.world
        if world_cls is None:
            raise ValueError(f"作品 {assembly.name!r} 未登记世界, 无法开局")
        params: dict = {
            "character": character_id,
            "difficulty": difficulty_id,
            "stage_no": stage,
            "seed": seed,
            "score_path": score_path,
        }
        if lives is not None:
            if lives < 1:
                raise ValueError(f"残机数 {lives} 非法(须 >= 1)")
            params["life_count"] = lives - 1  # C++ cfg.lifeCount 惯例(残机-1)
        self._init(assembly, world_cls.compose(assembly, **params))

    def _init(self, assembly: GameAssembly, world: World) -> None:
        """装配门面内部状态(__init__ 与 _from_world 共用)。"""
        self.assembly = assembly
        self.game_name = assembly.name
        self._world: GameWorld = cast(GameWorld, world)  # 鸭子契约, 一处钉型
        self._events: list[Event] = []  # 本帧收集的引擎事件
        self._scene: SceneSnapshot | None = None
        self._prev_held: frozenset[Button] = frozenset()
        self._world.subscribers.append(self._events.append)
        self._prev = self._probe()  # 事件差的基准帧状态(每帧 step 后更新)

    @classmethod
    def _from_world(cls, assembly: GameAssembly, world: World) -> Game:
        """包一个现存世界为 Game 门面(观战模式用, 不重新开局)。

        基准帧状态按现况初始化(事件差从下一次 step 起算)。
        """
        obj = cls.__new__(cls)
        obj._init(assembly, world)
        return obj

    # ---- 逐帧推进 ----
    def _to_frame(self, input: Input) -> InputFrame:
        """Input → InputFrame: 按下沿 = 上帧未按住, advance/bomb 强制补沿。"""
        held = input._held()
        pressed = held - self._prev_held
        if input.advance:
            pressed |= {Button.SHOT}
        if input.bomb:
            pressed |= {Button.BOMB}
        self._prev_held = held
        return InputFrame(held=held, pressed=pressed)

    def step(self, input: Input = Input.none()) -> list[GameEvent]:
        """推进一帧, 返回本帧发生的事件列表(流映射事件在前, 状态差事件在后)。"""
        prev = self._prev
        self._events.clear()
        self._scene = self._world.tick(self._to_frame(input))
        frame = self._world.frame
        out = [
            ev for e in self._events if (ev := self._map_event(e, frame)) is not None
        ]
        now = self._probe()
        self._prev = now
        out += self._diff_events(prev, now)
        return out

    # ---- 事件流映射(引擎 tagged union → 通用类别; 原始事件见 last_events) ----
    def _spellcard_name(self) -> str | None:
        """当前/上一张符卡名(世界透出字段, 无该字段的作品为 None)。"""
        return getattr(self._world, "spellcard_name", None) or None

    def _map_event(self, e: Event, frame: int) -> GameEvent | None:
        if isinstance(e, SpellcardBegan):
            return GameEvent(
                GameEventKind.SPELLCARD_BEGIN, frame, name=self._spellcard_name()
            )
        if isinstance(e, SpellcardEnded):
            kind = (
                GameEventKind.SPELLCARD_CAPTURED
                if e.captured
                else GameEventKind.SPELLCARD_END
            )
            return GameEvent(kind, frame, name=self._spellcard_name())
        if isinstance(e, PlayerDied):
            return GameEvent(GameEventKind.PLAYER_DEATH, frame)
        if isinstance(e, BombStarted):
            return GameEvent(GameEventKind.BOMB_START, frame)
        return None

    # ---- 状态差探测(事件流不覆盖的通用边沿: 奖残/过关/终局) ----
    def _safe_stats(self) -> dict[str, float]:
        """stats() 能力位探测(无钩子的作品回落空表, diff 探测不报错)。"""
        probe = getattr(self._world, "stats", None)
        return dict(probe()) if callable(probe) else {}

    def _probe(self) -> dict:
        w = self._world
        return {
            "lives": self._safe_stats().get("lives", 0.0),
            "stage": getattr(w, "stage_no", 1),
            "game_over": getattr(w, "game_over", False),
            "cleared": getattr(w, "cleared", False),
            "ending": getattr(w, "ending", None) is not None,
        }

    def _diff_events(self, prev: dict, now: dict) -> list[GameEvent]:
        out: list[GameEvent] = []
        frame = self._world.frame
        if now["lives"] > prev["lives"]:
            out.append(GameEvent(GameEventKind.EXTEND, frame))
        if now["stage"] != prev["stage"]:
            out.append(GameEvent(GameEventKind.STAGE_CLEAR, frame, stage=prev["stage"]))
        if now["ending"] and not prev["ending"]:
            out.append(GameEvent(GameEventKind.ENDING_START, frame))
        if now["game_over"] and not prev["game_over"]:
            out.append(GameEvent(GameEventKind.GAME_OVER, frame))
        if now["cleared"] and not prev["cleared"]:
            out.append(GameEvent(GameEventKind.GAME_CLEAR, frame))
        return out

    # ---- 只读状态(标量副本; 读路径不持有 world 本体) ----
    def _stats(self) -> dict[str, float]:
        """stats() 能力位(缺钩子的作品调残机类属性时给中文错)。"""
        probe = getattr(self._world, "stats", None)
        if not callable(probe):
            raise NotImplementedError(
                f"作品 {self.game_name!r} 未提供 stats() 读数钩子"
                f"(apis 观测面能力位, 由作品世界实现)"
            )
        return dict(probe())

    @property
    def frame(self) -> int:
        return self._world.frame

    @property
    def score(self) -> int:
        return self._world.globals.score

    @property
    def lives(self) -> int:
        return int(self._stats()["lives"])

    @property
    def bombs(self) -> int:
        return int(self._stats()["bombs"])

    @property
    def power(self) -> int:
        return int(self._stats()["power"])

    @property
    def graze(self) -> int:
        return int(self._stats()["graze"])

    @property
    def player_pos(self) -> tuple[float, float]:
        """自机坐标 (x, y) —— 标量级便宜读取, 逐帧热循环安全。"""
        p = self._world.player.pos
        return (p.x, p.y)

    @property
    def stage(self) -> int:
        return self._world.stage_no

    @property
    def phase(self) -> GamePhase:
        w = self._world
        if w.result is not None:
            return GamePhase.RESULT
        if w.game_over:
            return GamePhase.GAME_OVER
        if w.ending is not None:
            return GamePhase.ENDING
        if getattr(w, "stage_results", None) is not None:
            return GamePhase.STAGE_CLEAR
        if getattr(w, "msg_active", False):
            return GamePhase.DIALOG
        return GamePhase.RUNNING

    @property
    def result(self) -> dict | None:
        """总结算数据(结算后非 None; 字段由作品实现定义)。"""
        return self._world.result

    @property
    def scene(self) -> SceneSnapshot | None:
        """上一帧的 SceneSnapshot(绘制面; 未 step 过为 None)。"""
        return self._scene

    @property
    def last_events(self) -> tuple[Event, ...]:
        """上一帧的原始引擎事件流(全量, 未映射的类别从这读)。"""
        return tuple(self._events)

    # ---- 终局收尾(作品世界能力位, 缺失报中文错) ----
    def _call_world_hook(self, name: str, purpose: str) -> None:
        hook = getattr(self._world, name, None)
        if not callable(hook):
            raise NotImplementedError(
                f"作品 {self.game_name!r} 未提供 {name}() 钩子({purpose})"
            )
        hook()

    def can_continue(self) -> bool:
        """GameOver 后是否可续关(续关菜单门控)。"""
        hook = getattr(self._world, "can_continue", None)
        return bool(hook()) if callable(hook) else False

    def finalize_game_over(self) -> None:
        """GameOver 后不续关直接进结算(= 续关菜单选 No)。"""
        self._call_world_hook("finalize_game_over", "GameOver 收尾")

    def finish_ending(self) -> None:
        """结局看完 → 总结算(窗口版由确认键触发, headless 由调用方/流收尾)。"""
        self._call_world_hook("finish_ending", "结局收尾")

    # ---- §2.5 机制件: 命令队列(写) + worker 池(重任务) ----
    def queue(self, fn: Callable[[GameWorld, FrameContext], object]) -> Future:
        """写操作入队: fn(world, ctx) 在下一个帧边界统一应用, 返回 Future。

        任意线程可调; 应用顺序 = 入队顺序。模拟冻结(暂停/结算画面)时命令
        滞留到恢复 tick 才应用。
        """
        command = _FnCommand(fn)
        self._world.commands.push(command)
        return command.future

    def submit(
        self, fn: Callable[..., object], /, *args: object, **kwargs: object
    ) -> Future:
        """把重任务(AI 躲弹/图像处理/批量解析)提交到 worker 池异步执行。

        fn 里只能碰传入的不可变快照(snapshot()/bullets_array() 的产出)与
        标量副本, 不许摸 world 本体 —— 异步安全靠这条纪律保证。
        """
        return _pool().submit(fn, *args, **kwargs)

    # ---- 实体快照 ----
    def snapshot(self) -> Snapshot:
        """当前帧实体快照(不可变 msgspec.Struct)。

        每帧都调用有构造开销(全场实体逐个装箱), 建议按需调用; 躲弹等逐帧
        热循环请用 ``bullets_array()`` + ``player_pos``。
        """
        w = self._world
        p = w.player
        player = PlayerSnapshot(
            x=p.pos.x,
            y=p.pos.y,
            state=p.state.name.lower(),
            focus=p.focus,
            invulnerable=p.invulnerability_timer > 0,
            hitbox=p.hitbox_radius,
        )
        boss = None
        if w.boss is not None:
            b = w.boss
            bx = by = 0.0
            boss_enemy = getattr(w, "boss_enemy", None)
            if boss_enemy is not None:
                bx, by = boss_enemy.pos2
            boss = BossSnapshot(
                name=self._spellcard_name() or "",
                x=bx,
                y=by,
                life=b.life,
                max_life=b.max_life,
                spellcard_active=bool(getattr(w, "spellcard_active", lambda: False)()),
            )
        return Snapshot(
            frame=w.frame,
            phase=self.phase,
            player=player,
            boss=boss,
            bullets=tuple(
                BulletSnapshot(
                    x=b.pos.x,
                    y=b.pos.y,
                    angle=b.angle,
                    speed=b.speed,
                    sprite=b.sprite,
                    hitbox=b.hitbox,
                )
                for b in w.bullets.alive()
            ),
            enemies=tuple(
                EnemySnapshot(
                    x=e.pos2[0],
                    y=e.pos2[1],
                    life=int(e.machine.enemy.life),
                    radius=e.hitbox_size.x / 2,
                    is_boss=bool(e.is_boss),
                )
                for e in w.enemies.alive()
            ),
            items=tuple(
                ItemSnapshot(x=i.pos.x, y=i.pos.y, kind=i.kind) for i in w.items.alive()
            ),
            lasers=tuple(
                LaserSnapshot(
                    x=lz.pos.x,
                    y=lz.pos.y,
                    angle=lz.angle,
                    width=lz.width,
                    active=lz.state == LaserState.ACTIVE,
                )
                for lz in w.lasers.lasers
                if lz.in_use
            ),
        )

    # ---- 实体 numpy 快路径(热循环用; 无逐对象装箱) ----
    def bullets_array(self) -> np.ndarray:
        """全场敌弹的 numpy 观测面, 形状 (N, 6), float64。

        列: x, y, vx, vy, hitbox, sprite。vx/vy 取子弹当前速度向量
        (Bullet.vel, 命令作用后的真值)。空场返回 (0, 6)。
        """
        bullets = list(self._world.bullets.alive())
        if not bullets:
            return np.empty((0, 6), dtype=np.float64)
        return np.array(
            [
                (b.pos.x, b.pos.y, b.vel.x, b.vel.y, b.hitbox, float(b.sprite))
                for b in bullets
            ],
            dtype=np.float64,
        )

    def lasers_array(self) -> np.ndarray:
        """在场激光的 numpy 观测面, 形状 (N, 5), float64。

        列: x, y, angle, width, active(1.0=全宽命中态)。空场返回 (0, 5)。
        """
        lasers = [lz for lz in self._world.lasers.lasers if lz.in_use]
        if not lasers:
            return np.empty((0, 5), dtype=np.float64)
        return np.array(
            [
                (
                    lz.pos.x,
                    lz.pos.y,
                    lz.angle,
                    lz.width,
                    1.0 if lz.state == LaserState.ACTIVE else 0.0,
                )
                for lz in lasers
            ],
            dtype=np.float64,
        )
