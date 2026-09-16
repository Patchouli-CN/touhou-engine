"""TouhouWorld: 一部作品对局世界的统一入口(窗口 / headless 事件流)。

窗口模式经注册表解析作品的窗口 App(assembly.app, WindowApp 契约), apis 不
import games.*; 观战模式(auto_input 为 callable)由 apis 组世界并包 Game
门面, 经 WindowApp.run_game 的 world/input_source 缝注入(策略拿到的观测面
与自建 ``Game(...)`` 一致)。
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Generic, Literal, TypeVar, overload

from ..engine import InputFrame
from .basic import (
    Game,
    GameEvent,
    GamePhase,
    Input,
    _resolve_assembly,
    _resolve_ids,
)

#: auto_input 接受固定 Input 或 game -> Input 策略
InputSource = Input | Callable[[Game], Input]

_H = TypeVar("_H", bound=bool)  # TouhouWorld 的 headless 字面量参数(类型级)


class TouhouWorldEventStream:
    """headless 世界的事件流——``TouhouWorld.run()``(headless=True) 的返回值。

    迭代即驱动: 每取一个事件, 世界按 ``policy``(缺省为世界的 ``auto_input``;
    ``auto_input`` 是 callable 时直接作流的默认 policy)推进到下一个事件。
    终局自动收尾(GAME_OVER 等价续关菜单选 No, ENDING 自动看完), 流到总结算
    (RESULT)时迭代结束。

    用法::

        stream = tw.run()
        for event in stream:
            ...
        print(stream.result)      # 迭代结束后可读总结算 dict
        stream.policy = lambda game: Input(...)   # 中途接管输入(如 AI)
    """

    def __init__(
        self, world: TouhouWorld, policy: Callable[[Game], Input] | None = None
    ) -> None:
        self._world = world
        self.policy = policy
        self._done = False

    @property
    def game(self) -> Game:
        """流正在驱动的对局门面。"""
        return self._world.game

    @property
    def result(self) -> dict | None:
        """总结算数据(流结束后非 None)。"""
        return self._world.game.result

    def __iter__(self) -> Iterator[GameEvent]:
        g = self.game
        while not self._done:
            if self.policy is not None:
                inp = self.policy(g)
            else:
                default = self._world.auto_input
                inp = default(g) if callable(default) else default
            yield from g.step(inp)
            ph = g.phase
            if ph == GamePhase.RESULT:
                self._done = True
            elif ph == GamePhase.GAME_OVER:
                g.finalize_game_over()  # headless 无续关 UI, 等价选 No
            elif ph == GamePhase.ENDING:
                g.finish_ending()


class TouhouWorld(Generic[_H]):
    """一部作品对局世界的统一入口(不传 ``game=`` 用框架默认作品)。典型用法::

        tw = TouhouWorld(character="ReimuA", difficulty="Normal", headless=True)
        stream = tw.run()                # headless: 返回 TouhouWorldEventStream
        for event in stream:             # 迭代即驱动世界, 终局自动收尾
            ...

        tw2 = TouhouWorld(headless=False)
        tw2.run()                        # 非 headless: 弹出游戏窗口, 阻塞至关窗

    ``game`` 参数(None = 框架默认作品)经注册表解析作品装配; 未注册名报带已
    注册名单的 KeyError。``data_path`` 覆盖注册表登记的资源包路径。

    需要 AI 介入时给 ``stream.policy`` 赋一个 ``game -> Input`` 的函数, 或直接
    用 ``tw.game.step(your_input)`` 自己逐帧驱动。

    ``auto_input`` 接受固定 ``Input`` 或 ``game -> Input`` 策略: headless 下
    callable 直接作事件流的默认 policy; 非 headless 下 callable 进入**观战
    模式** —— 窗口照开但跳过标题菜单直接进游戏, 每帧输入来自策略(角色/难度/
    残机/种子以 TouhouWorld 自身属性为准), Esc 随时中止(暂停/续关菜单仍走
    键盘)::

        tw = TouhouWorld(headless=False, auto_input=my_policy)
        tw.run()   # 看 AI 打游戏
    """

    # headless 字面量进泛型参数: run() 返回类型随之为 Stream / None(mypy 精确收窄)
    @overload
    def __init__(
        self: TouhouWorld[Literal[True]],
        character: str | int | None = None,
        difficulty: str | int | None = None,
        lives: int | None = None,
        *,
        headless: Literal[True],
        stage: int = 1,
        game: str | None = None,
        seed: int | None = None,
        auto_input: InputSource | None = None,
        data_path: str | None = None,
    ) -> None: ...
    @overload
    def __init__(
        self: TouhouWorld[Literal[False]],
        character: str | int | None = None,
        difficulty: str | int | None = None,
        lives: int | None = None,
        headless: Literal[False] = False,
        stage: int = 1,
        *,
        game: str | None = None,
        seed: int | None = None,
        auto_input: InputSource | None = None,
        data_path: str | None = None,
        scale: int | None = None,
        renderer: str | None = None,
    ) -> None: ...
    @overload
    def __init__(
        self,
        character: str | int | None = None,
        difficulty: str | int | None = None,
        lives: int | None = None,
        headless: bool = False,
        stage: int = 1,
        *,
        game: str | None = None,
        seed: int | None = None,
        auto_input: InputSource | None = None,
        data_path: str | None = None,
        scale: int | None = None,
        renderer: str | None = None,
    ) -> None: ...
    def __init__(
        self,
        character: str | int | None = None,
        difficulty: str | int | None = None,
        lives: int | None = None,
        headless: bool = False,
        stage: int = 1,
        *,
        game: str | None = None,
        seed: int | None = None,
        auto_input: InputSource | None = None,
        data_path: str | None = None,
        scale: int | None = None,
        renderer: str | None = None,
    ) -> None:
        self.assembly = _resolve_assembly(game, data_path)
        self.game_name = self.assembly.name
        self.character = character
        self.difficulty = difficulty
        self.lives = lives
        self.headless = headless
        self.stage = stage
        self.seed = seed
        self.scale = scale
        self.renderer = renderer
        self.auto_input: InputSource = (
            auto_input if auto_input is not None else Input(shoot=True, advance=True)
        )
        self._game: Game | None = None
        if headless:
            self._game = self._make_game()

    def _make_game(self) -> Game:
        return Game(
            character=self.character,
            difficulty=self.difficulty,
            stage=self.stage,
            game=self.game_name,
            data_path=self.assembly.resources.data_path,
            seed=self.seed,
            lives=self.lives,
        )

    @property
    def game(self) -> Game:
        """Headless 对局门面(非 headless 模式 run() 后才有观战局门面)。"""
        if self._game is None:
            self._game = self._make_game()
        return self._game

    @property
    def events(self) -> TouhouWorldEventStream:
        """Headless 事件流(等价于 headless 模式调 run())。"""
        return TouhouWorldEventStream(self)

    def stream(
        self, policy: Callable[[Game], Input] | None = None
    ) -> TouhouWorldEventStream:
        """带输入策略的事件流(等价 run() 后设置 stream.policy)。"""
        return TouhouWorldEventStream(self, policy)

    @overload
    def run(self: TouhouWorld[Literal[True]]) -> TouhouWorldEventStream: ...
    @overload
    def run(self: TouhouWorld[Literal[False]]) -> None: ...
    @overload
    def run(self) -> TouhouWorldEventStream | None: ...
    def run(self) -> TouhouWorldEventStream | None:
        """headless=True: 返回事件流(迭代即驱动); headless=False: 弹窗阻塞到关窗。"""
        if self.headless:
            return TouhouWorldEventStream(self)

        app_cls = self.assembly.app
        if app_cls is None:
            raise ValueError(
                f"作品 {self.game_name!r} 未登记窗口层, 只能 headless 运行"
            )
        app = app_cls()
        # auto_input 是 callable(逐帧策略)时进入观战模式: 跳过标题直进一局,
        # 每帧输入来自策略(观测面 = 包住同一世界的 Game 门面); 否则完整流程
        policy = self.auto_input if callable(self.auto_input) else None
        if policy is None:
            app.run_app(
                self.assembly, seed=self.seed, scale=self.scale, renderer=self.renderer
            )
            return None

        # 观战: apis 侧组世界(注册表装配契约)并包门面, 经 run_game 的
        # world/input_source 缝注入; Esc/暂停/续关菜单仍走键盘
        character_id, difficulty_id = _resolve_ids(
            self.assembly, self.character, self.difficulty
        )
        world_cls = self.assembly.world
        if world_cls is None:
            raise ValueError(f"作品 {self.game_name!r} 未登记世界, 无法开局")
        params: dict = {
            "character": character_id,
            "difficulty": difficulty_id,
            "stage_no": self.stage,
            "seed": self.seed,
        }
        if self.lives is not None:
            params["life_count"] = self.lives - 1  # 同 Game.__init__ 的折算
        world = world_cls.compose(self.assembly, **params)
        game = Game._from_world(self.assembly, world)
        self._game = game

        def source(_w: object) -> InputFrame:
            return game._to_frame(policy(game))

        app.run_game(
            self.assembly,
            seed=self.seed,
            scale=self.scale,
            renderer=self.renderer,
            world=world,
            input_source=source,
        )
        return None
