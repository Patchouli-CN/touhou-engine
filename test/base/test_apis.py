"""apis 层的作品无关机制(stub 作品): Input 映射/命令队列/worker/事件映射。

只用注册表登记的 stub 作品, 不 import games.*; 真数据端到端冒烟在
test/th07/test_apis.py。
"""

from __future__ import annotations

from collections.abc import Iterator

import msgspec
import pytest

from touhou.apis import Game, GameEventKind, Input
from touhou.engine import (
    GameData,
    GlobalsField,
    InputFrame,
    ResourcePaths,
    SceneSnapshot,
    TouhouRegistry,
    World,
)
from touhou.engine.boss import SpellcardBegan, SpellcardEnded
from touhou.engine.context import FrameContext
from touhou.engine.core import Pipeline, tick_frame
from touhou.engine.events import Event
from touhou.engine.rng import Rng

_GAME = "test98"


class _StubWorld(World):
    """最小鸭子世界: tick 走 tick_frame(空管线), 帧内把预置事件发进事件流。"""

    stage_no: int = 1
    game_over: bool = False
    cleared: bool = False
    ending: object | None = None
    result: dict | None = None
    subscribers: list = msgspec.field(default_factory=list)
    globals: GlobalsField = msgspec.field(default_factory=GlobalsField)
    scripted: list[Event] = msgspec.field(default_factory=list)  # 下一帧要发的事件
    counters: dict[str, float] = msgspec.field(default_factory=dict)
    last_input: InputFrame | None = None

    @classmethod
    def compose(cls, assembly: object, **params: object) -> _StubWorld:
        return cls()

    def stats(self) -> dict[str, float]:
        return dict(self.counters)

    def tick(self, input: InputFrame | None = None) -> SceneSnapshot:
        self.last_input = input
        ctx = FrameContext(Rng(0), input)
        for sub in self.subscribers:
            ctx.events.subscribe(sub)
        for ev in self.scripted:
            ctx.events.emit(ev)
        self.scripted.clear()
        return tick_frame(self, Pipeline(), ctx)


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


@pytest.fixture()
def game() -> Game:
    TouhouRegistry.register(
        _GAME,
        title="测试作品",
        data=GameData(
            characters=("甲", "乙"),
            difficulties=("E", "N"),
            character_sht={0: ("a.sht", "b.sht"), 1: ("c.sht", "d.sht")},
        ),
        resources=ResourcePaths(
            data_path="x.dat",
            archive_format="fake",
            stage_file="stage{n}.std",
            ecl_file="ecl{n}.ecl",
            msg_file="msg{n}.dat",
        ),
        anm_version=2,
    )
    TouhouRegistry.world(_GAME)(_StubWorld)
    return Game(character="甲", difficulty="N", game=_GAME)


def test_input_mapping_edges(game: Game) -> None:
    """Input → InputFrame: 按住集 + 按下沿(上帧对比), advance/bomb 强制补沿。"""
    game.step(Input(shoot=True, bomb=True, advance=True))
    first = game._world.last_input
    assert first is not None
    assert {b.value for b in first.held} == {"shot", "bomb"}
    assert {b.value for b in first.pressed} == {"shot", "bomb"}
    game.step(Input(shoot=True))  # 持续按住: shot 不再产沿
    second = game._world.last_input
    assert second is not None
    assert {b.value for b in second.held} == {"shot"}
    assert not second.pressed


def test_name_resolution_and_errors(game: Game) -> None:
    """名单名映射内部 id(大小写不敏感); 非法名/越界下标报 ValueError。"""
    assert Game(character="乙", game=_GAME).assembly.name == _GAME
    with pytest.raises(ValueError, match="不支持"):
        Game(character="丙", game=_GAME)
    with pytest.raises(ValueError, match="越界"):
        Game(character=9, game=_GAME)


def test_command_queue_applied_at_frame_boundary(game: Game) -> None:
    """queue(fn) 的命令在下一帧边界应用, Future 拿到应用结果。"""
    fut = game.queue(lambda w, ctx: setattr(w, "game_over", True))
    assert game._world.game_over is False  # 入队即生效是错的
    game.step()
    assert game._world.game_over is True
    assert fut.result(timeout=5) is None  # setattr 返 None


def test_submit_returns_future(game: Game) -> None:
    """submit(fn) 上 worker 池异步执行, 结果经 Future 回主线程。"""
    fut = game.submit(lambda x, y: x + y, 2, 40)
    assert fut.result(timeout=5) == 42


def test_event_stream_mapping(game: Game) -> None:
    """引擎事件流映射成通用 GameEvent(符卡宣言/收取/未捕获)。"""
    game._world.scripted.append(
        SpellcardBegan(boss_id=0, spellcard_idx=3, time_limit=1800)
    )
    (ev,) = game.step()
    assert ev.kind == GameEventKind.SPELLCARD_BEGIN
    game._world.scripted.append(
        SpellcardEnded(boss_id=0, spellcard_idx=3, captured=True, timed_out=False)
    )
    (ev,) = game.step()
    assert ev.kind == GameEventKind.SPELLCARD_CAPTURED
    game._world.scripted.append(
        SpellcardEnded(boss_id=0, spellcard_idx=4, captured=False, timed_out=True)
    )
    (ev,) = game.step()
    assert ev.kind == GameEventKind.SPELLCARD_END


def test_diff_events_extend_and_game_over(game: Game) -> None:
    """状态差事件: 残机增加 → EXTEND; game_over 边沿 → GAME_OVER。"""
    game._world.counters["lives"] = 3.0
    game.step()  # 基准帧对齐
    game._world.counters["lives"] = 4.0
    kinds = [e.kind for e in game.step()]
    assert GameEventKind.EXTEND in kinds
    game._world.game_over = True
    kinds = [e.kind for e in game.step()]
    assert GameEventKind.GAME_OVER in kinds
