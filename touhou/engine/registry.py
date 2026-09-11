"""注册表: 作品组件的声明式绑定与统一装配。

登记方向单向: 作品包 import 本模块并登记(@TouhouRegistry.world("thNN") 等),
注册表不反向 import 作品包; 入口负责 import 作品包触发登记。同维度重名登记
fail fast, 防静默覆盖。

装饰器只给"框架按作品名解析、要拿到类去实例化"的接缝(world/ecl_host/app);
表/路径/名单/参数走 register(game, ...)。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

from .assembly import (
    GameAssembly,
    GameData,
    ResourcePaths,
    SaveSemantics,
    WindowApp,
    check_assembly,
)
from .core import World

_Comp = TypeVar("_Comp", bound=type)


class TouhouRegistry:
    """组装东方STG游戏组件的注册表。"""

    _registry_world: dict[str, type[World]] = {}
    _registry_ecl_host: dict[str, type] = {}
    _registry_app: dict[str, type[WindowApp]] = {}
    _registry_title: dict[str, str] = {}
    _registry_data: dict[str, GameData] = {}
    _registry_resources: dict[str, ResourcePaths] = {}
    _registry_anm_version: dict[str, int] = {}
    _registry_save: dict[str, SaveSemantics] = {}

    @classmethod
    def _claim(cls, registry: dict, game: str, kind: str) -> None:
        """确认该维度未被占, 已被占抛 ValueError。"""
        if game in registry:
            raise ValueError(f"作品 {game!r} 的 {kind} 已登记, 重名登记被拒")

    @classmethod
    def _declare(cls, registry: dict, kind: str, game: str) -> Callable[[_Comp], _Comp]:
        """造一个"声明即登记"的类装饰器, 同维度重名 fail fast。"""

        def register_decorator(component: _Comp) -> _Comp:
            cls._claim(registry, game, kind)
            registry[game] = component
            return component

        return register_decorator

    @classmethod
    def world(cls, game: str) -> Callable[[type[World]], type[World]]:
        """声明一个作品的世界。"""
        return cls._declare(cls._registry_world, "world", game)

    @classmethod
    def ecl_host(cls, game: str) -> Callable[[_Comp], _Comp]:
        """声明一个作品的 ECL 宿主回调类。"""
        return cls._declare(cls._registry_ecl_host, "ecl_host", game)

    @classmethod
    def app(cls, game: str) -> Callable[[type[WindowApp]], type[WindowApp]]:
        """声明一个作品的窗口 App 类。"""
        return cls._declare(cls._registry_app, "app", game)

    @classmethod
    def register(
        cls,
        game: str,
        *,
        title: str,
        data: GameData,
        resources: ResourcePaths,
        anm_version: int,
        save: SaveSemantics | None = None,
    ) -> None:
        """登记一部作品的装配数据(类形态的组件走各自的装饰器)。"""
        for registry, kind in (
            (cls._registry_title, "title"),
            (cls._registry_data, "data"),
            (cls._registry_resources, "resources"),
            (cls._registry_anm_version, "anm_version"),
        ):
            cls._claim(registry, game, kind)
        cls._registry_title[game] = title
        cls._registry_data[game] = data
        cls._registry_resources[game] = resources
        cls._registry_anm_version[game] = anm_version
        if save is not None:
            cls._claim(cls._registry_save, game, "save")
            cls._registry_save[game] = save

    @classmethod
    def registered_games(cls) -> tuple[str, ...]:
        """已登记装配件的作品名单。"""
        return tuple(sorted(cls._registry_title))

    @classmethod
    def create_game(cls, game: str) -> GameAssembly:
        """组装并创建一个完整的作品(作品包由调用方 import, 登记在 import 时发生)。"""
        missing = [
            kind
            for kind, registry in (
                ("title", cls._registry_title),
                ("data", cls._registry_data),
                ("resources", cls._registry_resources),
                ("anm_version", cls._registry_anm_version),
            )
            if game not in registry
        ]
        if missing:
            raise KeyError(
                f"作品 {game!r} 未登记齐: 缺 {', '.join(missing)}"
                f"(已登记: {', '.join(cls.registered_games())})"
            )
        assembly = GameAssembly(
            name=game,
            title=cls._registry_title[game],
            data=cls._registry_data[game],
            resources=cls._registry_resources[game],
            anm_version=cls._registry_anm_version[game],
            save=cls._registry_save.get(game, SaveSemantics()),
            world=cls._registry_world.get(game),
            app=cls._registry_app.get(game),
            ecl_host=cls._registry_ecl_host.get(game),
        )
        check_assembly(assembly)
        return assembly
