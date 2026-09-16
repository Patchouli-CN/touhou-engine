"""对局结束链 scene 测试: 续关菜单 / 结局画面 / 结算画面(headless)。

驱动法同既有 scene 测试(SDL dummy + 假输入帧); 世界用真数据 compose_world,
结局/GameOver 用 apply_next_level/game_over 夹具直置(同 test_result_flow)。
"""

from __future__ import annotations

from touhou.engine import Button, InputFrame, open_archive
from touhou.engine.score_store import ScoreStore
from touhou.games.th07 import result as result_flow
from touhou.games.th07.compose import compose
from touhou.games.th07.msg import apply_next_level
from touhou.games.th07.replay import ReplayRecorder, load_replay, save_replay
from touhou.games.th07.view.ending import EndingScene
from touhou.games.th07.view.game_scene import GameScene
from touhou.games.th07.view.music import BgmPlayer
from touhou.games.th07.view.name_entry import NameEntry
from touhou.games.th07.view.result import ResultScene
from touhou.games.th07.world import Th07World, compose_world

from .conftest import DATA, needs_data

SPELLCARD_COUNT = 141
_IDLE = InputFrame()


def _press(*btns: Button) -> InputFrame:
    s = frozenset(btns)
    return InputFrame(held=s, pressed=s)


def _make(stage: int = 1, difficulty: int = 1, character: int = 0) -> Th07World:
    """跳关夹具: 直接组一个指定面的世界(独立内存成绩库)。"""
    return compose_world(
        compose(),
        character=character,
        difficulty=difficulty,
        stage_no=stage,
        seed=42,
        store=ScoreStore(spellcard_count=SPELLCARD_COUNT),
    )


# ---- NameEntry 字表输入(纯逻辑, 无需数据) ----


def test_name_entry_move_skip_and_wrap() -> None:
    """字表移动: ±16 回绕/行内回绕/跳过 93 号空格调 (ResultScreen.cpp:1204-1263)。"""
    e = NameEntry.create("PLAYER", has_lsnm=False)
    assert e.selected == 0 and e.name == "PLAYER  " and e.cursor == 0
    e.move(Button.DOWN)  # 0 → 16 ('a')
    assert e.selected == 16
    e.move(Button.UP)  # 16 → 0
    assert e.selected == 0
    e.move(Button.UP)  # 0 → 80 回绕
    assert e.selected == 80
    e.selected = 77
    e.move(Button.DOWN)  # 77+16=93 是空格 → 再 +16 → 109-96=13
    assert e.selected == 13
    e.selected = 0
    e.move(Button.LEFT)  # 行首左移 → 行尾 15
    assert e.selected == 15
    e.move(Button.RIGHT)  # 行尾右移 → 回 0
    assert e.selected == 0


def test_name_entry_confirm_delete_end() -> None:
    """写字/退格/END 完成; 输满 8 字自动跳 END (:1283-1286)。"""
    e = NameEntry.create("", has_lsnm=False)
    e.confirm()  # 写 'A'
    assert e.name == "A       " and e.cursor == 1
    e.delete()
    assert e.name == "        " and e.cursor == 0
    e.delete()  # 退到顶不再退
    assert e.cursor == 0
    for _ in range(8):
        assert not e.confirm()
    assert e.cursor == 8 and e.selected == 95  # 自动跳 END
    e.confirm()  # 输满后继续写 = 改写末槽 (:1266)
    assert e.cursor == 8
    e.selected = 95
    assert e.confirm()  # END → 完成
    # 有 LSNM 时光标直接停 END (:1194-1197)
    assert NameEntry.create("PLAYER", has_lsnm=True).selected == 95


# ---- 续关菜单(GameScene 子态) ----


@needs_data
def test_retry_menu_quit_goes_result() -> None:
    """GameOver 冻结开菜单, 默认选中 No, 确认 → finalize_game_over → done。"""
    w = _make(1, 1)
    scene = GameScene(w, on_exit=lambda: None)
    w.game_over = True
    scene.step(_IDLE)  # tick 出 game_over 冻结帧 → 菜单进场
    assert scene._retry is not None and not scene.done
    frame, snap = w.frame, scene.snapshot()
    assert snap.sprites  # 冻结帧沿用死亡前画面(menuBackground 截屏语义)
    scene.step(_IDLE)  # INIT 帧
    for _ in range(30):
        scene.step(_IDLE)  # 世界冻结: 帧不走, 覆层在
    assert w.frame == frame
    assert len(scene.snapshot().sprites) > len(snap.sprites)
    assert scene._retry is not None and scene._retry._state == 2  # 默认 No (:891 怪癖)
    scene.step(_press(Button.SHOT))  # 确认 No
    assert w.result is None  # 20 帧离场中
    for _ in range(21):
        scene.step(_IDLE)
    assert scene._retry is None and scene.done
    assert w.result is not None and not w.result["cleared"]


@needs_data
def test_retry_menu_continue_resumes_same_world() -> None:
    """选 Yes → continue_play 原世界接着打(不重建), 分数清零/残机回满。"""
    w = _make(1, 1)
    scene = GameScene(w, on_exit=lambda: None)
    w.game_over = True
    w.globals.score = w.globals.gui_score = 1234560
    scene.step(_IDLE)
    scene.step(_IDLE)  # INIT
    for _ in range(30):
        scene.step(_IDLE)
    scene.step(_press(Button.UP))  # No → Yes
    scene.step(_press(Button.SHOT))  # 确认 Yes
    for _ in range(31):
        scene.step(_IDLE)
    assert scene._retry is None and not scene.done
    assert not w.game_over and w.th07.num_retries == 1
    assert w.globals.score == 1  # C: score = guiScore = numRetries
    frame = w.frame
    scene.step(_IDLE)
    assert w.frame == frame + 1  # 世界恢复推进


@needs_data
def test_retry_menu_music_pause_unpause() -> None:
    """菜单开 → BGM 暂停(AUDIO_PAUSE); 续关 → 恢复(:853/:1007, 仅 WAV 音源)。"""
    arc = open_archive(DATA, format_name="pbg4")
    music = BgmPlayer(arc, DATA.with_name("thbgm.dat"))
    w = _make(1, 1)
    w.archive = arc
    scene = GameScene(w, on_exit=lambda: None, music=music)
    assert music.current  # 关头主曲已起(GameManager.cpp:782)
    w.game_over = True
    scene.step(_IDLE)
    assert music.paused
    scene.step(_IDLE)
    for _ in range(30):
        scene.step(_IDLE)
    scene.step(_press(Button.UP))
    scene.step(_press(Button.SHOT))
    for _ in range(31):
        scene.step(_IDLE)
    assert not music.paused and music.current


@needs_data
def test_extra_game_over_no_retry_menu() -> None:
    """Extra (difficulty>=4) 无续关: game_over 直接结算 (:840-846), 不开菜单。"""
    w = _make(7, 4)
    scene = GameScene(w, on_exit=lambda: None)
    w.game_over = True
    scene.step(_IDLE)
    assert scene._retry is None and scene.done
    assert w.result is not None and not w.result["cleared"]


# ---- 结局画面 ----


class _RecBgm(BgmPlayer):
    """录音 BgmPlayer: 不碰 mixer, 只记 play/fadeout 调用。"""

    def __init__(self) -> None:
        super().__init__(None)
        self.log: list[tuple[str, object]] = []

    def play(self, name: str) -> None:
        self.log.append(("play", name))

    def fadeout(self, seconds: float) -> None:
        self.log.append(("fadeout", seconds))


@needs_data
def test_ending_scene_plays_then_finish() -> None:
    """结局逐帧播(文本/音乐事件), 确认跳过 → finish_ending → 结算出炉 → done。"""
    w = _make(6, 1)
    apply_next_level(w)  # msg NEXT_LEVEL → enter_ending
    assert w.ending is not None
    music = _RecBgm()
    sentinel = object()
    scene = EndingScene(w, music=music, on_done=lambda _w: sentinel)  # type: ignore[arg-type]
    for _ in range(350):
        scene.step(_IDLE)
    assert not scene.done
    assert scene.snapshot().texts  # 文本行已出(实测首行 ~302 帧)
    assert ("play", "th07_14.mid") in music.log  # @m 结局曲 (Ending.cpp:300-301)
    scene.step(_press(Button.SHOT))  # 确认跳过整段
    assert scene.done
    r = w.result
    assert r is not None and r["cleared"] and w.ending is None
    # 跳过=排空全部指令: staff roll 的 @m/@M 事件也都消费
    assert ("play", "th07_15.mid") in music.log
    assert ("fadeout", 5) in music.log
    assert scene.next_scene() is sentinel


@needs_data
def test_ending_scene_snapshot_layers() -> None:
    """结局快照: frame 递增, 文本行随播放出现。"""
    w = _make(6, 1)
    apply_next_level(w)
    scene = EndingScene(w, on_done=lambda _w: None)
    scene.step(_IDLE)
    assert scene.snapshot().frame == 1
    for _ in range(400):
        scene.step(_IDLE)
    assert scene.snapshot().texts  # 结局文本已逐行显示


# ---- 结算画面 ----


def _make_result_world(*, retries: int = 0, ranked: bool = True):
    """stage1 GameOver 结算世界: result 出炉 + 录制器; 返回 (world, recorder)。"""
    w = _make(1, 1)
    w.game_over = True
    w.th07.num_retries = retries
    if not ranked:
        # 塞满榜(10 条高分) → 本局不进榜 (LinkScoreEx >= 10, :1189)
        for k in range(10):
            w.store.insert_score(
                {
                    "score": 9000000 - k,
                    "character": 0,
                    "difficulty": 1,
                    "stage": 1,
                    "name": "HOLDER",
                    "numRetries": 0,
                    "date": "2026-01-01T00:00:00+00:00",
                }
            )
    w.globals.score = w.globals.gui_score = 123450
    result_flow.finalize_game_over(w)
    assert w.result is not None
    recorder = ReplayRecorder(w, name=w.store.last_name)
    return w, recorder


def _drive_result(scene: ResultScene, *, save_replay_flag: bool) -> None:
    """跑完结算全链: 输名(Esc 带过) → 面板确认 → 保存询问 Yes/No → (选槽改名) → 离场。"""
    for _ in range(31):
        scene.step(_IDLE)  # ENTER_NAME 30 帧门
    if scene._state == 10:  # ENTER_NAME
        scene.step(_press(Button.PAUSE))  # Esc = 完成输入 (:1301)
    for _ in range(91):
        scene.step(_IDLE)  # STATS_SHOW 90 帧门
    scene.step(_press(Button.SHOT))  # 面板确认 → STATS_WAIT
    for _ in range(32):
        scene.step(_IDLE)  # STATS_WAIT 30 → SAVE_PROMPT(59) → 60 帧询问出场
    for _ in range(20):
        scene.step(_IDLE)  # SAVE_PROMPT 80 帧门
    if not save_replay_flag:
        scene.step(_press(Button.RIGHT))  # Yes → No
        scene.step(_press(Button.SHOT))
    else:
        scene.step(_press(Button.SHOT))  # Yes → 选槽
        for _ in range(21):
            scene.step(_IDLE)  # 选槽 20 帧门
        scene.step(_press(Button.SHOT))  # 选新槽(无既有文件) → SAVING
        for _ in range(31):
            scene.step(_IDLE)  # 改名 30 帧门
        for _ in range(15):
            scene.step(_press(Button.RIGHT))  # 0 → 15
        for _ in range(5):
            scene.step(_press(Button.DOWN))  # 15 → 95 (END)
        scene.step(_press(Button.SHOT))  # END → 存盘
    for _ in range(62):
        scene.step(_IDLE)  # EXITING 60 帧
    assert scene.done


@needs_data
def test_result_scene_full_chain_with_replay_save(tmp_path) -> None:
    """结算全链: 入榜输名 → 面板 → 选新槽存录像 → 离场; store/录像/出口断言。"""
    w, recorder = _make_result_world()
    assert w.result is not None and w.result["rank"] == 0  # 空榜入榜首
    saved: list[str] = []
    sentinel = object()
    scene = ResultScene(
        w,
        recorder=recorder,
        replay_dir=str(tmp_path),
        on_save=lambda: saved.append("score"),
        on_exit=lambda: sentinel,  # type: ignore[arg-type]
    )
    _drive_result(scene, save_replay_flag=True)
    # 名字 = 默认 LSNM("PLAYER"), 写回榜上记录 + lsnm
    rec = w.store.entries(1, 0)[0]
    assert rec["name"].startswith("PLAYER") and rec["score"] == 123450
    assert w.store.last_name.startswith("PLAYER")
    # 录像存到 tmp 目录(新槽), 名字/分数对
    files = list(tmp_path.glob("*.json"))
    assert len(files) == 1
    replay = load_replay(files[0])
    assert replay.score == 123450 and replay.name.startswith("PLAYER")
    scene.on_exit()
    assert saved == ["score"]
    assert scene.next_scene() is sentinel


@needs_data
def test_result_scene_decline_save_no_replay(tmp_path) -> None:
    """保存询问选 No → 直接离场, 不产录像文件。"""
    w, recorder = _make_result_world()
    scene = ResultScene(
        w,
        recorder=recorder,
        replay_dir=str(tmp_path),
        on_save=lambda: None,
        on_exit=lambda: None,
    )
    _drive_result(scene, save_replay_flag=False)
    assert not list(tmp_path.glob("*.json"))


@needs_data
def test_result_scene_cannot_save_after_retry(tmp_path) -> None:
    """续关过的局 → REPLAY_CANNOT_SAVE (:1362-1365): 无询问, 确认即离场。"""
    w, recorder = _make_result_world(retries=1)
    scene = ResultScene(
        w,
        recorder=recorder,
        replay_dir=str(tmp_path),
        on_save=lambda: None,
        on_exit=lambda: None,
    )
    for _ in range(31):
        scene.step(_IDLE)
    scene.step(_press(Button.PAUSE))  # 名字带过
    for _ in range(91):
        scene.step(_IDLE)
    scene.step(_press(Button.SHOT))  # 面板确认
    for _ in range(33):
        scene.step(_IDLE)  # STATS_WAIT → PROMPT 帧 60 → CANNOT_SAVE
    assert scene._state == 12  # REPLAY_CANNOT_SAVE
    for _ in range(21):
        scene.step(_IDLE)
    scene.step(_press(Button.SHOT))  # 确认 → EXITING
    for _ in range(62):
        scene.step(_IDLE)
    assert scene.done
    assert not list(tmp_path.glob("*.json"))


@needs_data
def test_result_scene_overwrite_existing_slot(tmp_path) -> None:
    """选既有槽 → 覆盖确认 (REPLAY_OVERWRITE) → Yes → 改名存盘覆盖该文件。"""
    w, recorder = _make_result_world()
    old = recorder.finish(w)
    target = save_replay(old, tmp_path / "th7_ud_old.json")
    scene = ResultScene(
        w,
        recorder=recorder,
        replay_dir=str(tmp_path),
        on_save=lambda: None,
        on_exit=lambda: None,
    )
    for _ in range(31):
        scene.step(_IDLE)
    scene.step(_press(Button.PAUSE))
    for _ in range(91):
        scene.step(_IDLE)
    scene.step(_press(Button.SHOT))
    for _ in range(32):
        scene.step(_IDLE)
    for _ in range(20):
        scene.step(_IDLE)
    scene.step(_press(Button.SHOT))  # Yes → 选槽
    for _ in range(21):
        scene.step(_IDLE)
    assert len(scene._slots) == 1  # 既有 1 条 + 末行新槽
    scene.step(_press(Button.SHOT))  # 选槽 0(既有) → 覆盖确认
    assert scene._state == 15  # REPLAY_OVERWRITE
    for _ in range(21):
        scene.step(_IDLE)
    scene.step(_press(Button.SHOT))  # Yes → SAVING
    assert scene._state == 14
    for _ in range(31):
        scene.step(_IDLE)
    for _ in range(15):
        scene.step(_press(Button.RIGHT))
    for _ in range(5):
        scene.step(_press(Button.DOWN))
    scene.step(_press(Button.SHOT))  # END → 存盘
    assert scene._state == 2  # EXITING
    assert list(tmp_path.glob("*.json")) == [target]  # 覆盖原文件, 不新增
    assert load_replay(target).score == 123450


@needs_data
def test_result_scene_not_ranked_skips_enter_name(tmp_path) -> None:
    """未入榜 → 跳过 ENTER_NAME 直进总结算面板 (:1189-1191)。"""
    w, recorder = _make_result_world(ranked=False)
    assert w.result is not None and w.result["rank"] == -1
    scene = ResultScene(
        w,
        recorder=recorder,
        replay_dir=str(tmp_path),
        on_save=lambda: None,
        on_exit=lambda: None,
    )
    assert scene._state == 16  # FINAL_STATS_SHOW
    _drive_result(scene, save_replay_flag=False)


@needs_data
def test_result_scene_practice_enters_save_prompt(tmp_path) -> None:
    """练习局直进录像保存询问(PRACTICE_END→REPLAY_SAVE_PROMPT :2603-2616), Yes 存得出录像。"""
    w = compose_world(
        compose(),
        character=0,
        difficulty=1,
        stage_no=1,
        seed=42,
        store=ScoreStore(spellcard_count=SPELLCARD_COUNT),
        practice=True,
    )
    w.game_over = True
    result_flow.finalize_game_over(w)  # practice: 记 pscr, 不入榜
    assert w.result is not None and w.result["rank"] == -1
    recorder = ReplayRecorder(w, name=w.store.last_name)
    scene = ResultScene(
        w,
        recorder=recorder,
        replay_dir=str(tmp_path),
        on_save=lambda: None,
        on_exit=lambda: None,
        practice=True,
    )
    assert scene._state == 11  # REPLAY_SAVE_PROMPT
    for _ in range(81):
        scene.step(_IDLE)  # 80 帧输入门
    scene.step(_press(Button.SHOT))  # Yes → 选槽
    for _ in range(21):
        scene.step(_IDLE)
    scene.step(_press(Button.SHOT))  # 新槽 → SAVING
    for _ in range(31):
        scene.step(_IDLE)
    for _ in range(15):
        scene.step(_press(Button.RIGHT))
    for _ in range(5):
        scene.step(_press(Button.DOWN))
    scene.step(_press(Button.SHOT))  # END → 存盘
    for _ in range(62):
        scene.step(_IDLE)
    assert scene.done
    files = list(tmp_path.glob("*.json"))
    assert len(files) == 1
    assert load_replay(files[0]).practice
