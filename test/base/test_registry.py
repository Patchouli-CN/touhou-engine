"""TouhouRegistry: 登记装饰器、重名防线与 create_game 组装。"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from touhou.engine import (
    GameAssembly,
    GameData,
    ResourcePaths,
    SaveSemantics,
    TouhouRegistry,
)
from touhou.engine.core import World

_GAME = "test99"


@pytest.fixture(autouse=True)
def _isolate_registry() -> Iterator[None]:
    """注册表是进程级全局: 用例前后快照/还原各维度表, 免测试间串味。"""
    saved = {
        name: dict(value)
        for name, value in vars(TouhouRegistry).items()
        if name.startswith("_registry_")
    }
    yield
    for name, value in saved.items():
        setattr(TouhouRegistry, name, value)


class _FakeApp:
    """登记测试用的假窗口 App。"""

    def run_app(
        self,
        assembly: object,
        *,
        seed: int | None = None,
        scale: int | None = None,
    ) -> None:
        """完整流程入口(测试替身, 空实现)。"""

    def run_game(
        self,
        assembly: object,
        *,
        character: int = 0,
        difficulty: int = 1,
        stage_no: int = 1,
        seed: int | None = None,
        scale: int | None = None,
    ) -> object:
        """直进一局入口(测试替身, 空实现)。"""
        return assembly


def _register(game: str = _GAME, **overrides: object) -> None:
    kwargs: dict[str, object] = {
        "title": "测试作品",
        "data": GameData(
            characters=("甲",),
            difficulties=("E",),
            character_sht={0: ("a.sht", "b.sht")},
        ),
        "resources": ResourcePaths(
            data_path="x.dat",
            archive_format="fake",
            stage_file="stage{n}.std",
            ecl_file="ecl{n}.ecl",
            msg_file="msg{n}.dat",
        ),
        "anm_version": 2,
    }
    kwargs.update(overrides)
    TouhouRegistry.register(game, **kwargs)  # type: ignore[arg-type]


def test_create_game_assembles_registered_pieces() -> None:
    """登记齐的作品能组装成装配, 世界走装饰器。"""

    @TouhouRegistry.world(_GAME)
    class _FakeWorld(World):
        """登记测试用的假世界。"""

    _register()
    assembly = TouhouRegistry.create_game(_GAME)
    assert assembly.name == _GAME
    assert assembly.title == "测试作品"
    assert assembly.world is _FakeWorld
    assert assembly.anm_version == 2
    assert assembly.save == SaveSemantics()
    assert _GAME in TouhouRegistry.registered_games()


def test_register_carries_save_semantics() -> None:
    """存档语义按作品登记, 不登记则落默认。"""
    _register(save=SaveSemantics(score_file="score.dat"))
    assert TouhouRegistry.create_game(_GAME).save.score_file == "score.dat"


def test_create_game_missing_pieces_raises() -> None:
    """缺维度的作品 fail fast, 报缺失清单。"""
    with pytest.raises(KeyError, match="未登记齐"):
        TouhouRegistry.create_game("test98_nothing")


def test_duplicate_registration_rejected() -> None:
    """同维度重名登记 fail fast, 不静默覆盖。"""
    _register()
    with pytest.raises(ValueError, match="重名登记被拒"):
        _register()


def test_duplicate_world_rejected() -> None:
    """世界同作品重名登记 fail fast。"""

    @TouhouRegistry.world(_GAME)
    class _FirstWorld(World):
        """先登记的假世界。"""

    with pytest.raises(ValueError, match="重名登记被拒"):

        @TouhouRegistry.world(_GAME)
        class _SecondWorld(World):
            """后登记的假世界, 应被拒。"""


def test_world_compose_contract_called_through_registry() -> None:
    """装配入口按契约调用注册表登记的 world 类, 开局参数经此传入。"""
    calls: list[dict] = []

    @TouhouRegistry.world(_GAME)
    class _ComposableWorld(World):
        """登记测试用的可装配假世界。"""

        @classmethod
        def compose(cls, assembly: GameAssembly, **params: object) -> World:
            """记录开局参数并造出这一局。"""
            calls.append(params)
            return cls(frame=7)

    _register()
    assembly = TouhouRegistry.create_game(_GAME)
    assert assembly.world is _ComposableWorld
    built = assembly.world.compose(assembly, character=3)
    assert built.frame == 7
    assert calls == [{"character": 3}]


def test_app_decorator_binds_window_app() -> None:
    """窗口 App 走装饰器登记; 未登记的作品只能 headless。"""
    _register()
    assert TouhouRegistry.create_game(_GAME).app is None

    @TouhouRegistry.app(_GAME)
    class _App(_FakeApp):
        """登记测试用的假窗口 App。"""

    assert TouhouRegistry.create_game(_GAME).app is _App


def test_duplicate_app_rejected() -> None:
    """窗口 App 同作品重名登记 fail fast。"""

    @TouhouRegistry.app(_GAME)
    class _FirstApp(_FakeApp):
        """先登记的假窗口 App。"""

    with pytest.raises(ValueError, match="重名登记被拒"):

        @TouhouRegistry.app(_GAME)
        class _SecondApp(_FakeApp):
            """后登记的假窗口 App, 应被拒。"""


def test_ecl_host_decorator_lands_in_assembly() -> None:
    """ECL 宿主走装饰器登记, create_game 把它作为装配字段。"""
    _register()
    assert TouhouRegistry.create_game(_GAME).ecl_host is None

    @TouhouRegistry.ecl_host(_GAME)
    class _Host:
        """登记测试用的假 ECL 宿主。"""

    assert TouhouRegistry.create_game(_GAME).ecl_host is _Host


def test_duplicate_ecl_host_rejected() -> None:
    """ECL 宿主同作品重名登记 fail fast。"""

    @TouhouRegistry.ecl_host(_GAME)
    class _FirstHost:
        """先登记的假 ECL 宿主。"""

    with pytest.raises(ValueError, match="重名登记被拒"):

        @TouhouRegistry.ecl_host(_GAME)
        class _SecondHost:
            """后登记的假 ECL 宿主, 应被拒。"""
