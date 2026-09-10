"""th07 录像: 编解码/存取单元测试 + 逐帧确定性验证(回放可行性的地基)。"""

from __future__ import annotations

import msgspec
import pytest

from touhou.engine import InputFrame, SceneSnapshot
from touhou.engine.globals import GlobalsField
from touhou.engine.input import Button
from touhou.games.th07.bomb import Th07BombField
from touhou.games.th07.compose import compose
from touhou.games.th07.globals import Th07Globals
from touhou.games.th07.player import OptionMachine, Th07PlayerField
from touhou.games.th07.replay import (
    ReplayEntry,
    ReplayRecorder,
    StageMark,
    StageSnapshot,
    Th07Replay,
    decode_input,
    encode_input,
    list_replays,
    load_replay,
    new_replay_path,
    save_replay,
)
from touhou.games.th07.view.game_scene import GameScene
from touhou.games.th07.view.menu_vms import MenuVmSet
from touhou.games.th07.view.replay import ReplayListScene, ReplayWatchScene
from touhou.games.th07.view.scene import Scene
from touhou.games.th07.world import compose_world

from .conftest import needs_data


def _snapshot() -> StageSnapshot:
    """默认场态拼一个可序列化的快照(player 走 asdict 口径)。"""
    player = msgspec.structs.asdict(Th07PlayerField())
    player.pop("on_border_break")
    return StageSnapshot(
        frame=10,
        rng_main=(1, 2),
        rng_ecl=(3, 4),
        th07=Th07Globals(lives=2.0),
        globals=GlobalsField(score=100),
        options=OptionMachine(),
        bomb=Th07BombField(),
        player=player,
        point_items_prev_stages=0,
        rand_spawn_idx=0,
        rand_table_idx=0,
        spellcard_began_frame=-1,
        catk_idx=None,
    )


def _replay() -> Th07Replay:
    return Th07Replay(
        version=1,
        name="TEST",
        date="09/10",
        character=0,
        difficulty=1,
        stage_no=1,
        practice=False,
        seed=42,
        score=1000,
        slowdown=0.0,
        stages=[StageMark(stage_no=1, start_frame=0, score=1000, snapshot=_snapshot())],
        inputs=[[0, 3], [9, 2]],
    )


def test_input_codec_bits_and_pressed_edge() -> None:
    """Held → 码 → held 往返; pressed 沿由上帧推导。"""
    inp = InputFrame(held=frozenset({Button.SHOT, Button.LEFT, Button.PAUSE}))
    code = encode_input(inp)
    prev: frozenset[Button] = frozenset()
    out = decode_input(code, prev)
    assert out.held == frozenset({Button.SHOT, Button.LEFT})  # PAUSE 不进带
    assert out.pressed == out.held  # 上帧空 → 全沿
    out2 = decode_input(code, out.held)
    assert out2.pressed == frozenset()  # 持续按住无新沿
    out3 = decode_input(0, out.held)
    assert out3.held == frozenset() and out3.pressed == frozenset()


def test_save_load_list_roundtrip(tmp_path) -> None:
    """存 → 读 → 列表扫描; 坏文件/旧格式被跳过。"""
    path = save_replay(_replay(), tmp_path / "th7_ud001.json")
    loaded = load_replay(path)
    assert loaded.name == "TEST" and loaded.score == 1000
    assert loaded.stages[0].snapshot.th07.lives == 2.0
    assert loaded.inputs == [[0, 3], [9, 2]]
    # 旧时代 JSON 样例格式(version 字段语义不同/缺字段) → 扫描跳过
    (tmp_path / "th7_udold.json").write_text('{"version": 1, "meta": {}, "inputs": []}')
    (tmp_path / "junk.json").write_text("not json")
    entries = list_replays(tmp_path)
    assert [e.label for e in entries] == ["User "]
    assert entries[0].replay.name == "TEST"
    with pytest.raises(ValueError):
        load_replay(tmp_path / "junk.json")


def test_new_replay_path_unique(tmp_path) -> None:
    """同秒撞名时序号递增。"""
    p1 = new_replay_path(tmp_path)
    p1.write_bytes(b"{}")
    p2 = new_replay_path(tmp_path)
    assert p1.name != p2.name
    assert p1.name.startswith("th7_ud") and p2.name.endswith(".json")


@needs_data
def test_determinism_frame_by_frame() -> None:
    """同 seed 同输入两遍一面 3600 帧: 逐帧比对分数/弹数/自机位/樱点/rng。"""

    def scripted(i: int) -> InputFrame:
        held = {Button.SHOT}
        if (i // 40) % 2 == 0:
            held.add(Button.RIGHT)
        else:
            held.add(Button.LEFT)
        if i % 7 < 3:
            held.add(Button.FOCUS)
        pressed = {Button.BOMB} if i in (500, 1500) else set()
        return InputFrame(held=frozenset(held), pressed=frozenset(pressed))

    def run() -> list[tuple]:
        w = compose_world(compose(), character=0, difficulty=1, seed=42)
        trace = []
        for i in range(3600):
            w.tick(scripted(i))
            trace.append(
                (
                    w.globals.score,
                    len(w.bullets),
                    w.player.pos.x,
                    w.player.pos.y,
                    w.th07.cherry,
                    w.th07.lives,
                    w.rng.state(),
                    w.host.rng.state() if w.host is not None else None,
                )
            )
        return trace

    t1, t2 = run(), run()
    assert t1 == t2  # 逐帧全等 → 回放可行性成立


def _probe(w) -> tuple:
    """回放比对探针: 分数/弹数/自机位/樱点/双 rng 状态。"""
    return (
        w.globals.score,
        len(w.bullets),
        w.player.pos.x,
        w.player.pos.y,
        w.th07.cherry,
        w.rng.state(),
        w.host.rng.state() if w.host is not None else None,
    )


def _backend_style_inputs(n: int) -> list[InputFrame]:
    """后端口径输入序列: held 按周期变化, 变化帧带 pressed 沿。"""
    out: list[InputFrame] = []
    prev: frozenset[Button] = frozenset()
    for i in range(n):
        held = {Button.SHOT}
        if (i // 40) % 2 == 0:
            held.add(Button.RIGHT)
        else:
            held.add(Button.LEFT)
        if i % 7 < 3:
            held.add(Button.FOCUS)
        cur = frozenset(held)
        out.append(InputFrame(held=cur, pressed=cur - prev))
        prev = cur
    return out


@needs_data
def test_record_watch_roundtrip(tmp_path) -> None:
    """录 2000 帧 → 存盘读回 → 回放: 逐帧探针与原局全等。"""
    frames = 2000
    w = compose_world(compose(), character=0, difficulty=1, seed=42)
    rec = ReplayRecorder(w, name="TEST")
    scene = GameScene(w, on_exit=lambda: None, recorder=rec)
    probe = [_probe(w)]  # 首帧(init tick)后
    for inp in _backend_style_inputs(frames):
        scene.step(inp)
        probe.append(_probe(w))
    assert rec.frames == frames + 1  # init tick 也算一帧
    loaded = load_replay(save_replay(rec.finish(w), tmp_path / "r.json"))
    assert loaded.seed == 42 and loaded.name == "TEST"

    w2 = compose_world(
        compose(),
        character=loaded.character,
        difficulty=loaded.difficulty,
        stage_no=loaded.stage_no,
        seed=loaded.seed,
    )
    watch = ReplayWatchScene(w2, loaded, loaded.stages[0], on_exit=lambda: None)
    probe2 = [_probe(w2)]
    for _ in range(frames):
        watch.step(InputFrame())
        probe2.append(_probe(w2))
    assert probe == probe2
    watch.step(InputFrame())  # 再步一帧: 无输入可喂 → 回放结束
    assert watch.done


@needs_data
def test_stage_mark_restore_parity(tmp_path) -> None:
    """从二面锚点起播: 快照恢复后 600 帧与原局逐帧全等(快照完整性判官)。"""
    w = compose_world(compose(), character=0, difficulty=1, seed=42)
    w.th07.lives = 99.0  # 夹具续命(打穿一面看换关)
    rec = ReplayRecorder(w, name="T")
    scene = GameScene(w, on_exit=lambda: None, recorder=rec)
    probe = [_probe(w)]
    i = 0
    while w.stage_no == 1 and i < 14000:  # Z 脉冲推对话(同 test_msg_stage1)
        scene.step(
            InputFrame(
                held=frozenset({Button.SHOT}),
                pressed=frozenset({Button.SHOT}) if i % 15 == 0 else frozenset(),
            )
        )
        probe.append(_probe(w))
        i += 1
    assert w.stage_no == 2
    for _ in range(600):  # 换关后再录 600 帧作比对段
        scene.step(
            InputFrame(
                held=frozenset({Button.SHOT}),
                pressed=frozenset({Button.SHOT}) if i % 15 == 0 else frozenset(),
            )
        )
        probe.append(_probe(w))
        i += 1
    loaded = load_replay(save_replay(rec.finish(w), tmp_path / "r.json"))
    mark2 = next(m for m in loaded.stages if m.stage_no == 2)

    w2 = compose_world(
        compose(), character=0, difficulty=1, stage_no=2, seed=loaded.seed
    )
    watch = ReplayWatchScene(w2, loaded, mark2, on_exit=lambda: None)
    probe2 = [_probe(w2)]
    for _ in range(600):
        watch.step(InputFrame())
        probe2.append(_probe(w2))
    base = mark2.start_frame
    assert probe2 == probe[base : base + 601]


def _entry_list(n: int, stages: tuple[int, ...] = (1,)) -> list[ReplayEntry]:
    """N 条合成录像条目; stages 控制有数据的面槽(测空槽跳过)。"""
    marks = [
        StageMark(stage_no=s, start_frame=0, score=1000 * s, snapshot=_snapshot())
        for s in stages
    ]
    out = []
    for i in range(n):
        r = _replay()
        r.stages = marks
        r.name = f"P{i}"
        out.append(ReplayEntry(f"r{i}.json", r))
    return out


class _WatchStub(Scene):
    """on_watch 返回的占位 scene。"""

    def step(self, inp: InputFrame) -> None:
        pass

    def snapshot(self) -> SceneSnapshot:
        return SceneSnapshot(0)

    def next_scene(self) -> Scene | None:
        return None


def _press(b: Button) -> InputFrame:
    return InputFrame(held=frozenset({b}), pressed=frozenset({b}))


class _ListHarness:
    """列表 scene 测试夹具: 记录 on_watch/on_exit 调用。"""

    def __init__(self, entries: list[ReplayEntry]) -> None:
        self.watched: list[tuple[ReplayEntry, StageMark, int]] = []
        self.exited = 0
        self.scene = ReplayListScene(
            MenuVmSet(None),
            entries,
            on_watch=self._watch,
            on_exit=self._exit,
        )

    def _watch(self, entry: ReplayEntry, mark: StageMark, mode: int) -> Scene:
        self.watched.append((entry, mark, mode))
        return _WatchStub()

    def _exit(self) -> Scene:
        self.exited += 1
        return _WatchStub()

    def open(self) -> None:
        """走完 INIT 30 帧 + 列表 10 帧输入门。"""
        for _ in range(41):
            self.scene.step(InputFrame())


def test_replay_list_init_gate_and_move() -> None:
    """INIT 30 帧门挡一切; 移动不门(:2046), 确认/取消门 10 帧(:2069)。"""
    h = _ListHarness(_entry_list(3))
    h.scene.step(_press(Button.DOWN))  # INIT 门内输入无效
    for _ in range(30):
        h.scene.step(InputFrame())
    assert h.scene.cursor == 0
    h.scene.step(_press(Button.DOWN))  # 移动不门, 即开即动
    assert h.scene.cursor == 1
    assert 12 in h.scene.drain_sounds()  # SE_MOVE
    h.scene.step(_press(Button.SHOT))  # 确认门(id<10)仍挡
    assert h.scene._substate == 1
    for _ in range(9):
        h.scene.step(InputFrame())
    h.scene.step(_press(Button.SHOT))  # id>=10 开门
    assert h.scene._substate == 2
    assert 10 in h.scene.drain_sounds()  # SE_SELECT


def test_replay_list_stage_slot_skip_and_watch() -> None:
    """选面跳过无数据槽; 选模式确认起播, 带出正确的锚点与模式。"""
    h = _ListHarness(_entry_list(2, stages=(1, 3)))
    h.open()
    h.scene.step(_press(Button.SHOT))  # 进选面, 光标落槽 0(Stage1)
    assert h.scene._substate == 2 and h.scene.cursor == 0
    h.scene.drain_sounds()  # 清掉列表 confirm 的 SE_SELECT
    h.scene.step(_press(Button.DOWN))  # 槽 1(Stage2)无数据 → 滑到槽 2(Stage3)
    assert h.scene.cursor == 2
    h.scene.step(_press(Button.SHOT))  # 进选模式(确认无 SE)
    assert h.scene._substate == 3 and h.scene.cursor == 0
    assert 10 not in h.scene.drain_sounds()  # 只有刚才移动的 SE_MOVE
    h.scene.step(_press(Button.DOWN))  # 模式 1
    h.scene.step(_press(Button.SHOT))  # 起播
    assert h.scene.done
    entry, mark, mode = h.watched[0]
    assert mark.stage_no == 3 and mode == 1
    assert isinstance(h.scene.next_scene(), _WatchStub)


def test_replay_list_cancel_chain_and_exit() -> None:
    """模式→选面→列表→离场 30 帧回主菜单; 取消 SE 只在列表层。"""
    h = _ListHarness(_entry_list(2))
    h.open()
    h.scene.step(_press(Button.SHOT))  # 选面
    h.scene.step(_press(Button.SHOT))  # 选模式
    h.scene.step(_press(Button.BOMB))  # 取消回选面(无 SE)
    assert h.scene._substate == 2
    h.scene.step(_press(Button.BOMB))  # 取消回列表(无 SE)
    assert h.scene._substate == 1
    assert 11 not in h.scene.drain_sounds()
    h.scene.step(_press(Button.BOMB))  # 取消离场(SE_BACK)
    assert h.scene._substate == 4
    assert 11 in h.scene.drain_sounds()
    for _ in range(30):
        h.scene.step(InputFrame())
    assert h.scene.done and h.exited == 1


def test_replay_list_paging_and_empty() -> None:
    """15 条以上左右翻页(±15); 空列表 confirm 无反应, cancel 可退。"""
    h = _ListHarness(_entry_list(20))
    h.open()
    h.scene.step(_press(Button.RIGHT))
    assert h.scene.cursor == 15
    h.scene.step(_press(Button.RIGHT))  # 15+15=30 >= 20 → 30-20=10(:2061-2064)
    assert h.scene.cursor == 10
    h.scene.step(_press(Button.LEFT))  # 10-15 <0 → +20 = 15(:2052-2055)
    assert h.scene.cursor == 15

    empty = _ListHarness([])
    empty.open()
    empty.scene.step(_press(Button.SHOT))
    assert empty.scene._substate == 1  # confirm 落空
    assert 10 not in empty.scene.drain_sounds()
    empty.scene.step(_press(Button.BOMB))
    assert empty.scene._substate == 4


class _StubBackend:
    """脚本化输入的后端替身: 喂完输入序列后返回 None(窗口关闭)。"""

    def __init__(self, inputs: list) -> None:
        self._inputs = list(inputs)
        self.sounds: list[int] = []
        self.closed = False

    def open(self, *, title: str, scale: int = 1) -> None:
        pass

    def frame(self, events, snapshot):
        return self._inputs.pop(0) if self._inputs else None

    def play_sounds(self, ids: list[int]) -> None:
        self.sounds.extend(ids)

    def close(self) -> None:
        self.closed = True


@needs_data
def test_run_app_replay_chain(tmp_path) -> None:
    """run_app 全链: 主菜单→Replay 列表(空目录)→取消(光标停 3)→Quit。"""
    from touhou.games.th07.view.app import run_app

    idle = InputFrame()
    inputs = (
        [idle] * 11  # 主菜单确认门
        + [_press(Button.DOWN)] * 2  # 0→2(Extra 锁定滑过)→3(Replay)
        + [_press(Button.SHOT)]  # 进录像列表
        + [idle] * 41  # 列表 INIT 30 帧 + 输入门
        + [_press(Button.BOMB)]  # 取消离场
        + [idle] * 30  # 离场 30 帧回主菜单(光标停 3)
        + [idle] * 11  # 主菜单确认门
        + [_press(Button.DOWN)] * 4  # 3→7(Exit)
        + [_press(Button.SHOT)]  # Quit
        + [idle] * 60  # 离场 60 帧后退出
    )
    backend = _StubBackend(inputs)
    run_app(
        compose(),
        seed=42,
        score_path=str(tmp_path / "score.json"),
        config_path=str(tmp_path / "config.json"),
        replay_dir=str(tmp_path / "replays"),
        backend=backend,
    )
    assert not backend._inputs  # 输入序列正好喂完
    assert backend.closed
