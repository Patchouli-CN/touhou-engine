"""scene runner 与 GameScene 的 headless 测试(SDL dummy 由 conftest 钉死)。"""

from __future__ import annotations

from touhou.engine import Event, InputFrame, RenderBackend, SceneSnapshot
from touhou.engine.input import Button
from touhou.games.th07.view.game_scene import GameScene
from touhou.games.th07.view.scene import Scene, run_scenes

from .conftest import needs_data

_IDLE = InputFrame()


class _StubBackend(RenderBackend):
    """脚本化输入的后端替身: 喂完输入序列后返回 None(窗口关闭)。"""

    def __init__(self, inputs: list[InputFrame | None]) -> None:
        self._inputs = list(inputs)
        self.rendered = 0
        self.sounds: list[int] = []
        self.closed = False

    def open(self, *, title: str, scale: int = 1) -> None:
        pass

    def frame(
        self, events: tuple[Event, ...], snapshot: SceneSnapshot
    ) -> InputFrame | None:
        self.rendered += 1
        return self._inputs.pop(0) if self._inputs else None

    def play_sounds(self, ids: list[int]) -> None:
        self.sounds.extend(ids)

    def close(self) -> None:
        self.closed = True


class _FakeScene(Scene):
    """计步 scene: 走 n 帧后 done, 每帧攒一个 SE。"""

    def __init__(self, steps: int, nxt: Scene | None = None) -> None:
        super().__init__()
        self._steps = steps
        self._nxt = nxt
        self.entered = 0
        self.exited = 0
        self._sounds: list[int] = []

    def on_enter(self) -> None:
        self.entered += 1

    def on_exit(self) -> None:
        self.exited += 1

    def step(self, inp: InputFrame) -> None:
        self._steps -= 1
        self._sounds.append(7)
        if self._steps <= 0:
            self.done = True

    def snapshot(self) -> SceneSnapshot:
        return SceneSnapshot(0)

    def drain_sounds(self) -> list[int]:
        out, self._sounds = self._sounds, []
        return out

    def next_scene(self) -> Scene | None:
        return self._nxt


def test_runner_scene_chain_and_sounds() -> None:
    """A(2 帧)→B(1 帧)→None: enter/exit 次序、SE 透传、backend 关闭。"""
    b = _FakeScene(1)
    a = _FakeScene(2, b)
    backend = _StubBackend([_IDLE] * 10)
    run_scenes(a, backend, title="t", scale=1)
    assert (a.entered, a.exited) == (1, 1)
    assert (b.entered, b.exited) == (1, 1)
    assert backend.rendered >= 3
    assert backend.sounds == [7, 7, 7]  # A×2 + B×1
    assert backend.closed


def test_runner_quit_on_window_close() -> None:
    """Backend 返回 None(窗口关闭)立即退出, 未 done 的 scene 不走 on_exit。"""
    a = _FakeScene(100)
    backend = _StubBackend([None])
    run_scenes(a, backend, title="t", scale=1)
    assert a.exited == 0
    assert backend.closed


@needs_data
def test_game_scene_tick_pause_and_result() -> None:
    """真一面: step 推进世界; Esc 暂停冻结; result 出现即 done + on_result。"""
    from touhou.games.th07.compose import compose
    from touhou.games.th07.world import Th07World, compose_world

    world = compose_world(compose(), seed=42)
    results: list[Th07World] = []
    scene = GameScene(world, on_exit=lambda: None, on_result=results.append)
    frame0 = scene.snapshot().frame
    scene.step(_IDLE)
    assert scene.snapshot().frame == frame0 + 1
    # Esc 暂停: 世界不走, 快照不换
    scene.step(InputFrame(pressed=frozenset({Button.PAUSE})))
    assert scene.paused
    snap = scene.snapshot()
    scene.step(_IDLE)
    assert scene.snapshot() is snap
    scene.step(InputFrame(pressed=frozenset({Button.PAUSE})))
    assert not scene.paused
    # 结算出炉 → done + 回调 + 留给装配处的出口
    world.result = {"score": 1}
    scene.step(_IDLE)
    assert scene.done
    assert results == [world]
    assert scene.next_scene() is None


@needs_data
def test_run_app_full_chain(tmp_path) -> None:
    """run_app 全链: 标题→难度→机体→装备→进对局→窗口关闭退出。"""
    from touhou.games.th07.compose import compose
    from touhou.games.th07.view.app import run_app

    shot = InputFrame(held=frozenset({Button.SHOT}), pressed=frozenset({Button.SHOT}))
    inputs: list[InputFrame | None] = (
        [_IDLE] * 11
        + [shot]  # Start
        + [_IDLE] * 31
        + [shot]  # 难度 Normal
        + [_IDLE] * 31
        + [shot]  # 机体 灵梦
        + [_IDLE] * 31
        + [shot]  # 装备 A → 进对局
        + [_IDLE] * 30  # 对局跑 30 帧
        + [None]  # 关窗
    )
    backend = _StubBackend(inputs)
    run_app(
        compose(), seed=42, score_path=str(tmp_path / "score.json"), backend=backend
    )
    assert not backend._inputs  # 输入序列正好喂完
    assert backend.closed


@needs_data
def test_run_app_option_chain(tmp_path) -> None:
    """run_app 全链: 主菜单→Option→调残机→返回(光标停 Option)→Quit, 配置落盘。"""
    from touhou.games.th07.compose import compose
    from touhou.games.th07.config import load_config
    from touhou.games.th07.view.app import run_app

    def press(b: Button) -> InputFrame:
        return InputFrame(held=frozenset({b}), pressed=frozenset({b}))

    shot = press(Button.SHOT)
    down = press(Button.DOWN)
    inputs: list[InputFrame | None] = (
        [_IDLE] * 11
        + [down] * 5  # 0→2(Extra 锁定滑过)→3→4→5→6(Option)
        + [shot]  # 进 Option
        + [_IDLE] * 35  # 30 帧转场 + INIT + 4 帧输入门
        + [press(Button.RIGHT)]  # 残机档 2→3
        + [press(Button.UP)]  # 光标 0→8(Exit, 环绕)
        + [shot]  # 回主菜单(光标停 Option=6)
        + [_IDLE] * 11  # 主菜单确认门
        + [down]  # 6→7(Exit)
        + [shot]  # Quit
        + [_IDLE] * 60  # 离场 60 帧后退出
    )
    backend = _StubBackend(inputs)
    config_path = str(tmp_path / "config.json")
    run_app(
        compose(),
        seed=42,
        score_path=str(tmp_path / "score.json"),
        config_path=config_path,
        backend=backend,
    )
    assert not backend._inputs  # 输入序列正好喂完
    assert backend.closed
    cfg = load_config(config_path)
    assert cfg.life_count == 3  # Option 里调的一档落盘
    # SE 序列: 移动 12 ×8(菜单 5 + option 2 + 返回后 1), 确认 10 ×2, 返回 11 ×1
    assert backend.sounds.count(12) == 8
    assert backend.sounds.count(10) == 2
    assert backend.sounds.count(11) == 1


@needs_data
def test_run_app_musicroom_chain(tmp_path) -> None:
    """run_app 全链: 主菜单→Music Room→选曲确认→返回(光标停 Music Room)→Quit。"""
    from touhou.games.th07.compose import compose
    from touhou.games.th07.view.app import run_app

    def press(b: Button) -> InputFrame:
        return InputFrame(held=frozenset({b}), pressed=frozenset({b}))

    down = press(Button.DOWN)
    inputs: list[InputFrame | None] = (
        [_IDLE] * 11
        + [down] * 4  # 0→2(Extra 锁定滑过)→3→4→5(Music Room)
        + [press(Button.SHOT)]  # 进 Music Room
        + [_IDLE] * 9  # 8 帧输入门 + 开门帧(MusicRoom.cpp:35-38)
        + [down]  # 光标 0→1
        + [press(Button.SHOT)]  # 选中曲目(播放 hook, 实际发声留待)
        + [press(Button.BOMB)]  # 回主菜单(光标停 Music Room=5)
        + [_IDLE] * 11  # 主菜单确认门
        + [down] * 2  # 5→6→7(Exit)
        + [press(Button.SHOT)]  # Quit
        + [_IDLE] * 60  # 离场 60 帧后退出
    )
    backend = _StubBackend(inputs)
    run_app(
        compose(),
        seed=42,
        score_path=str(tmp_path / "score.json"),
        config_path=str(tmp_path / "config.json"),
        backend=backend,
    )
    assert not backend._inputs  # 输入序列正好喂完
    assert backend.closed
    # SE: 移动 12 ×6(菜单 4 + 返回后 2), 确认 10 ×2; Music Room 全程无 SE
    assert backend.sounds.count(12) == 6
    assert backend.sounds.count(10) == 2
    assert 11 not in backend.sounds
