"""BGM 链测试(SDL dummy 由 conftest 钉死; 断言调用链/逻辑态, 不断言真出声)。

BgmPlayer 单测用造出来的 thbgm.dat 头/fmt/std 字节 + monkeypatch 的 load_entry;
StageBgm 用记录仪替身; needs_data 用真 thbgm.dat/std/.mid 取轨断言。
"""

from __future__ import annotations

import struct
from types import SimpleNamespace

import pygame
import pytest

from touhou.engine import Event, InputFrame, RenderBackend, SceneSnapshot
from touhou.engine.input import Button
from touhou.engine.msg import MsgMusicChange, MsgMusicFadeout
from touhou.games.th07.config import MUSIC_MIDI, MUSIC_OFF, MUSIC_WAV
from touhou.games.th07.view import music as music_mod
from touhou.games.th07.view.music import TITLE_BGM, BgmPlayer, StageBgm, _stem
from touhou.games.th07.view.scene import Scene, run_scenes
from touhou.schemas.thbgm import (
    FMT_ENTRY_SIZE,
    THBGM_MAGIC,
    THBGM_VERSION,
    build_wav,
    parse_fmt,
)

from .conftest import DATA, needs_data

_IDLE = InputFrame()
_GAME_ID = 0x700


# ----  fixture 字节 ----
def _fmt_bytes(entries: list[tuple[str, int, int, int]]) -> bytes:
    """造 thbgm.fmt: (曲名, start, intro, total), 2ch/44100/16bit。"""
    out = b""
    for name, start, intro, total in entries:
        out += name.encode("latin-1").ljust(16, b"\0")
        out += struct.pack("<iIii", start, 0, intro, total)
        out += struct.pack("<HHIIHH", 1, 2, 44100, 176400, 4, 16)
        out += b"\0" * (FMT_ENTRY_SIZE - 48)
    return out + b"\0" * FMT_ENTRY_SIZE  # 空条目终止


def _thbgm_file(tmp_path) -> object:
    path = tmp_path / "thbgm.dat"
    path.write_bytes(
        struct.pack("<4sIII", THBGM_MAGIC, THBGM_VERSION, _GAME_ID, 0)
        + b"\1" * 200000  # fmt 里的假 PCM 区间
    )
    return path


def _std_bytes(*paths: str) -> bytes:
    """造 .std 头: 只填 bgm 名/路径槽; 实例表/脚本各放一个终止哨兵。"""
    buf = bytearray(1168)
    struct.pack_into("<hhII", buf, 0, 0, 0, 1000, 1004)
    struct.pack_into("<h", buf, 1000, -1)  # 实例表 id<0 终止
    struct.pack_into("<i", buf, 1004, -1)  # 脚本 frame==-1 哨兵
    for i, p in enumerate(paths):
        buf[144 + i * 128 : 144 + i * 128 + len(p)] = p.encode("cp932")
        buf[656 + i * 128 : 656 + i * 128 + len(p)] = p.encode("cp932")
    return bytes(buf)


def _patch_load(monkeypatch: pytest.MonkeyPatch, files: dict[str, bytes]) -> None:
    monkeypatch.setattr(music_mod, "load_entry", lambda arc, name: files[name])


class _Rec:
    """BgmPlayer 记录仪替身(Scene/驱动接线断言用)。"""

    def __init__(self, *args, mode: int = MUSIC_WAV, **kwargs) -> None:
        self.mode = mode
        self.current = ""
        self.log: list[tuple] = []
        self.polls = 0

    def set_mode(self, mode: int) -> None:
        self.mode = mode

    def play(self, name: str) -> None:
        self.current = _stem(name)
        self.log.append(("play", self.current))

    def ensure(self, name: str) -> None:
        if self.current != _stem(name):
            self.play(name)

    def stop(self) -> None:
        self.current = ""
        self.log.append(("stop",))

    def fadeout(self, seconds: float) -> None:
        self.current = ""
        self.log.append(("fadeout", seconds))

    def pause(self) -> None:
        self.log.append(("pause",))

    def unpause(self) -> None:
        self.log.append(("unpause",))

    def poll(self) -> None:
        self.polls += 1


def _player(
    monkeypatch: pytest.MonkeyPatch, tmp_path, mode: int = MUSIC_WAV
) -> BgmPlayer:
    """Fmt 只收 th07_02.wav 的播放器(dummy 声卡 → 只走逻辑态)。"""
    _patch_load(
        monkeypatch,
        {
            "thbgm.fmt": _fmt_bytes([("th07_02.wav", 16, 1000, 44100 * 4)]),
            "th07_05.mid": b"MThd" + b"\0" * 16,
        },
    )
    return BgmPlayer(object(), _thbgm_file(tmp_path), mode=mode)  # type: ignore[arg-type]


# ---- BgmPlayer: 选曲/模式 ----
def test_stem() -> None:
    assert _stem("bgm/th07_02.mid") == "th07_02"
    assert _stem("bgm\\th07_13b.mid") == "th07_13b"
    assert _stem("th07_01.wav") == "th07_01"
    assert _stem(" ") == ""


def test_mode_off_silence(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    """Off 档: PlayAudio 直接 return(Supervisor.cpp:1392-1394), 永远无声。"""
    p = _player(monkeypatch, tmp_path, mode=MUSIC_OFF)
    p.play("bgm/th07_02.mid")
    p.play("bgm/th07_05.mid")
    assert p.current == "" and p._wav is None


def test_wav_play_and_fallback(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    """WAV 档: fmt 收录曲走 WAV(记 _wav); 未收录回退 MIDI。"""
    p = _player(monkeypatch, tmp_path)
    p.play("bgm/th07_02.mid")  # fmt 里是 th07_02.wav
    assert p.current == "th07_02"
    assert p._wav is not None and p._wav.name == "th07_02.wav"
    assert p._wav_pass_ms == pytest.approx(1000.0)  # 176400B / 176400Bps = 1s
    p.play("bgm/th07_05.mid")  # fmt 未收录 → MIDI
    assert p.current == "th07_05" and p._wav is None


def test_midi_missing_track_silence(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    """WAV/MIDI 都取不到的曲: 静默, current 记空。"""
    p = _player(monkeypatch, tmp_path)
    p.play("bgm/th07_99.mid")
    assert p.current == ""


def test_midi_mode_skips_wav(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    """MIDI 档: 不查 fmt, 直取 .mid。"""
    p = _player(monkeypatch, tmp_path, mode=MUSIC_MIDI)
    p.play("bgm/th07_05.mid")
    assert p.current == "th07_05" and p._wav is None


def test_ensure_dedupe(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    """ensure: 同名曲在播不重启(标题曲重入语义)。"""
    p = _player(monkeypatch, tmp_path)
    p.ensure(TITLE_BGM)
    assert p.current == ""  # fmt/mid 都没 th07_01 → 播不成
    p.play("bgm/th07_05.mid")
    p.ensure("bgm/th07_05.mid")  # 同名 → 不动作
    assert p.current == "th07_05"
    p.ensure("bgm/th07_02.mid")  # 不同名 → 切
    assert p.current == "th07_02"


def test_stop_fadeout_clear(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    p = _player(monkeypatch, tmp_path)
    p.play("bgm/th07_02.mid")
    p.stop()
    assert p.current == "" and p._wav is None and not p.paused
    p.play("bgm/th07_02.mid")
    p.fadeout(4.0)
    assert p.current == "" and p._wav is None


def test_pause_wav_only(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    """原版仅 WAV 音源响应 AUDIO_PAUSE(SoundPlayer.cpp:839-853)。"""
    p = _player(monkeypatch, tmp_path, mode=MUSIC_MIDI)
    p.play("bgm/th07_05.mid")
    p.pause()
    assert not p.paused  # MIDI 档不暂停
    p.set_mode(MUSIC_WAV)
    p.play("bgm/th07_02.mid")
    p.pause()
    assert p.paused
    p.unpause()
    assert not p.paused
    p.stop()
    p.pause()  # 无在播曲 → 不置暂停态
    assert not p.paused


def test_poll_rewind_mock_mixer(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    """WAV 循环段: 段尾/自然播完 → play(0, start=intro)(dsutil.cpp:1071-1112)。"""
    monkeypatch.setenv("SDL_AUDIODRIVER", "stub")  # 绕开 dummy 静音守卫
    calls: list[tuple] = []
    state = {"pos": 0, "busy": True}
    monkeypatch.setattr(pygame.mixer, "get_init", lambda: (44100, -16, 2))
    monkeypatch.setattr(pygame.mixer.music, "load", lambda f: None)
    monkeypatch.setattr(
        pygame.mixer.music,
        "play",
        lambda loops=0, start=0.0: calls.append((loops, start)),
    )
    monkeypatch.setattr(pygame.mixer.music, "get_pos", lambda: state["pos"])
    monkeypatch.setattr(pygame.mixer.music, "get_busy", lambda: state["busy"])
    p = _player(monkeypatch, tmp_path)
    p.play("bgm/th07_02.mid")
    assert calls == [(0, 0.0)]  # 首遍从头播
    track = p._wav
    assert track is not None
    state["pos"] = 3900  # 段尾 30ms 内 → 回卷
    p.poll()
    assert calls[-1] == (0, track.intro_seconds)
    assert p._wav_pass_ms == pytest.approx(track.loop_seconds * 1000.0)
    p.paused = True  # 暂停中 get_busy=False 也不回卷
    state["busy"] = False
    p.poll()
    assert len(calls) == 2
    p.paused = False  # 自然播完兜底回卷
    p.poll()
    assert calls[-1] == (0, track.intro_seconds)


def test_poll_noop_without_audio(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    """Dummy 声卡: poll 不碰 mixer 也不炸。"""
    p = _player(monkeypatch, tmp_path)
    p.play("bgm/th07_02.mid")
    p.poll()  # _audio_ok False → 直接返回


# ---- StageBgm 驱动 ----
def _stage_driver(monkeypatch: pytest.MonkeyPatch) -> tuple[StageBgm, _Rec]:
    _patch_load(
        monkeypatch,
        {
            "stage1.std": _std_bytes("bgm/th07_02.mid", "bgm/th07_03.mid"),
            "stage6.std": _std_bytes("bgm/th07_12.mid", "bgm/th07_13.mid"),
        },
    )
    rec = _Rec()
    return StageBgm(rec, object()), rec  # type: ignore[arg-type]


def test_stage_edge_plays_main_bgm(monkeypatch: pytest.MonkeyPatch) -> None:
    """关号边沿 → 面曲(GameManager.cpp:782); 同关不重复。"""
    drv, rec = _stage_driver(monkeypatch)
    w = SimpleNamespace(stage_no=1, frame=0, frame_bgm=[])
    drv.step(w)
    drv.step(w)
    assert rec.log == [("play", "th07_02")]
    w.stage_no = 2  # 无 std 数据 → 静默
    drv.step(w)
    assert rec.log == [("play", "th07_02")]


def test_msg_music_events(monkeypatch: pytest.MonkeyPatch) -> None:
    """MSG_MUSIC(1) → boss 曲(Gui.cpp:974-980); MSG_FADEOUT_MUSIC → 淡出 4 秒(:1022)。"""
    drv, rec = _stage_driver(monkeypatch)
    w = SimpleNamespace(stage_no=1, frame=0, frame_bgm=[])
    drv.step(w)
    drv.on_event(MsgMusicChange(1))
    drv.on_event(MsgMusicChange(3))  # 空白槽 → 静默
    drv.on_event(MsgMusicFadeout())
    assert rec.log == [("play", "th07_02"), ("play", "th07_03"), ("fadeout", 4.0)]


def test_frame_bgm_commands(monkeypatch: pytest.MonkeyPatch) -> None:
    """ECL 音乐指令(world.frame_bgm): 幽幽子复活曲/3 秒淡出。"""
    drv, rec = _stage_driver(monkeypatch)
    w = SimpleNamespace(stage_no=1, frame=0, frame_bgm=[("play", "bgm/th07_13b.mid")])
    drv.step(w)
    w.frame_bgm = [("fadeout", 3.0)]
    drv.step(w)
    assert rec.log == [
        ("play", "th07_13b"),
        ("play", "th07_02"),  # 关号边沿面曲(首帧)
        ("fadeout", 3.0),
    ]


def test_stage6_delayed_main_bgm(monkeypatch: pytest.MonkeyPatch) -> None:
    """6 面: 关头 StopAudio(GameManager.cpp:786), 300 帧后才起面曲(Gui.cpp:141-144)。"""
    drv, rec = _stage_driver(monkeypatch)
    w = SimpleNamespace(stage_no=6, frame=1000, frame_bgm=[])
    drv.step(w)
    assert rec.log == [("stop",)]
    w.frame = 1000 + 299
    drv.step(w)
    assert rec.log == [("stop",)]
    w.frame = 1000 + 300
    drv.step(w)
    assert rec.log == [("stop",), ("play", "th07_12")]


# ---- scene 接线 ----
class _StubBackend(RenderBackend):
    """脚本化输入的后端替身。"""

    def __init__(self, inputs: list[InputFrame | None]) -> None:
        self._inputs = list(inputs)

    def open(self, *, title: str, scale: int = 1) -> None:
        pass

    def frame(
        self, events: tuple[Event, ...], snapshot: SceneSnapshot
    ) -> InputFrame | None:
        return self._inputs.pop(0) if self._inputs else None

    def play_sounds(self, ids: list[int]) -> None:
        pass

    def close(self) -> None:
        pass


class _TwoFrameScene(Scene):
    """走两帧就 done 的空 scene。"""

    def __init__(self) -> None:
        super().__init__()
        self._n = 2

    def step(self, inp: InputFrame) -> None:
        self._n -= 1
        if self._n <= 0:
            self.done = True

    def snapshot(self) -> SceneSnapshot:
        return SceneSnapshot(0)

    def next_scene(self):
        return None


def test_runner_polls_music_each_frame() -> None:
    """run_scenes 每帧 poll(music) → WAV 循环回卷与 scene 无关。"""
    rec = _Rec()
    run_scenes(
        _TwoFrameScene(), _StubBackend([_IDLE, _IDLE, _IDLE]), title="t", music=rec
    )
    assert rec.polls == 2


def test_title_scene_bgm_hooks() -> None:
    """标题: on_enter 起播标题曲(重入不重启); 开局 on_exit 停, 进子菜单不停。"""
    from touhou.engine.score_store import ScoreStore
    from touhou.games.th07.view.title import MenuMemory, StartRequest, TitleScene

    rec = _Rec()
    scene = TitleScene(None, ScoreStore(), MenuMemory(), music=rec)
    scene.on_enter()
    scene.on_enter()  # ensure 去重
    assert rec.log == [("play", "th07_01")]
    scene.on_exit()  # 无 start_request = 进子画面 → 不停
    assert rec.log == [("play", "th07_01")]
    scene.start_request = StartRequest(character=0, difficulty=1)
    scene.on_exit()  # 开局 → StopAudio(:1778)
    assert rec.log == [("play", "th07_01"), ("stop",)]


def test_musicroom_confirm_plays_track() -> None:
    """Music Room 确认 → PlayAudio(track.path)(MusicRoom.cpp:106-113)。"""
    from touhou.games.th07.view.musicroom import MusicRoomScene
    from touhou.schemas.musiccmt import TrackDescriptor

    rec = _Rec()
    scene = MusicRoomScene(
        None,
        tracks=[TrackDescriptor("bgm/th07_05.mid", "曲", ())],
        on_exit=lambda: None,  # type: ignore[return-value]
        music=rec,
    )
    for _ in range(9):  # 输入门 8 帧
        scene.step(_IDLE)
    shot = InputFrame(held=frozenset({Button.SHOT}), pressed=frozenset({Button.SHOT}))
    scene.step(shot)
    assert rec.log == [("play", "th07_05")]


@needs_data
def test_game_scene_bgm_chain() -> None:
    """真一面 GameScene: 进场面曲 → Esc 暂停联动 → on_exit 停。"""
    from touhou.games.th07.compose import compose
    from touhou.games.th07.view.game_scene import GameScene
    from touhou.games.th07.world import compose_world

    rec = _Rec()
    scene = GameScene(
        compose_world(compose(), seed=42), on_exit=lambda: None, music=rec
    )
    assert rec.log == [("play", "th07_02")]
    pause = InputFrame(pressed=frozenset({Button.PAUSE}))
    scene.step(pause)
    scene.step(pause)
    assert rec.log[-2:] == [("pause",), ("unpause",)]
    scene.on_exit()
    assert rec.log[-1] == ("stop",)


@needs_data
def test_game_scene_ending_music() -> None:
    """6 面通关: 结局点起结局曲(Ending.cpp:300-301)再走总结算。"""
    from touhou.engine import open_archive
    from touhou.games.th07.compose import compose
    from touhou.games.th07.msg import apply_next_level
    from touhou.games.th07.view.game_scene import GameScene
    from touhou.games.th07.world import compose_world
    from touhou.schemas.archive import load_entry
    from touhou.schemas.ending import parse_end

    rec = _Rec()
    w = compose_world(compose(), character=0, difficulty=1, stage_no=6, seed=42)
    scene = GameScene(w, on_exit=lambda: None, music=rec)
    apply_next_level(w)  # msg NEXT_LEVEL → enter_ending
    assert w.ending is not None
    scene.step(_IDLE)
    arc = open_archive(DATA, format_name="pbg4")
    expected = _stem(parse_end(load_entry(arc, "end00.end")).music)
    assert expected
    assert ("play", expected) in rec.log
    assert scene.done  # 结局画面留待: 起播后直接总结算


# ---- needs_data: 真实取轨 ----
@needs_data
def test_real_thbgm_tracks() -> None:
    """真 thbgm.dat: 头校验/fmt 20 曲/取轨字节非空/包 RIFF 格式对头。"""
    from touhou.engine import open_archive
    from touhou.schemas.archive import load_entry
    from touhou.schemas.thbgm import THBGM_HEADER_SIZE, check_thbgm_header

    bgm = DATA.with_name("thbgm.dat")
    assert check_thbgm_header(bgm.read_bytes()[:THBGM_HEADER_SIZE], game_id=_GAME_ID)
    arc = open_archive(DATA, format_name="pbg4")
    tracks = parse_fmt(load_entry(arc, "thbgm.fmt"))
    assert len(tracks) == 20
    t = tracks["th07_02.wav"]
    assert 0 < t.intro_length < t.total_length  # 有循环段信息
    with open(bgm, "rb") as f:
        f.seek(t.start_offset)
        pcm = f.read(t.total_length)
    assert len(pcm) == t.total_length
    wav = build_wav(t, pcm)
    assert wav[:4] == b"RIFF" and wav[8:12] == b"WAVE"
    # 经播放器真实取轨(dummy 声卡 → 逻辑态, 不读 PCM)
    p = BgmPlayer(arc, bgm, mode=MUSIC_WAV)
    p.play("bgm/th07_02.mid")
    assert p.current == "th07_02" and p._wav == t
    # MIDI 档真取 .mid
    p2 = BgmPlayer(arc, bgm, mode=MUSIC_MIDI)
    p2.play("bgm/th07_01.mid")
    assert p2.current == "th07_01"
    assert load_entry(arc, "th07_01.mid")[:4] == b"MThd"


@needs_data
def test_real_stage_bgm_paths() -> None:
    """真 std: 面曲/boss 曲槽位与反编译装载口径一致(GameManager.cpp:778-779)。"""
    from touhou.engine import open_archive
    from touhou.schemas.archive import load_entry
    from touhou.schemas.stage import parse_std

    arc = open_archive(DATA, format_name="pbg4")
    s1 = parse_std(load_entry(arc, "stage1.std"))
    assert s1.bgm_paths[:2] == ("bgm/th07_02.mid", "bgm/th07_03.mid")
    s6 = parse_std(load_entry(arc, "stage6.std"))
    assert s6.bgm_paths[:2] == ("bgm/th07_12.mid", "bgm/th07_13.mid")


@needs_data
def test_run_app_bgm_chain(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    """run_app 全链 BGM 序列: 标题曲 → 开局停 → 一面面曲。"""
    from touhou.games.th07.compose import compose
    from touhou.games.th07.view import app as app_mod
    from touhou.games.th07.view.app import run_app

    created: list[_Rec] = []
    monkeypatch.setattr(
        app_mod,
        "BgmPlayer",
        lambda *a, **k: created.append(_Rec(*a, **k)) or created[-1],
    )
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
        + [_IDLE] * 30
        + [None]  # 关窗
    )
    run_app(
        compose(),
        seed=42,
        score_path=str(tmp_path / "score.json"),
        backend=_StubBackend(inputs),
    )
    assert len(created) == 1
    assert created[0].log == [("play", "th07_01"), ("stop",), ("play", "th07_02")]
