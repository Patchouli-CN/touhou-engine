"""Music Room 状态机/光标/翻页/评论显示的 headless 测试(无数据: VM 无脚本, 状态机照跑)。"""

from __future__ import annotations

from touhou.engine import InputFrame
from touhou.engine.input import Button
from touhou.games.th07.view.musicroom import MusicRoomScene
from touhou.games.th07.view.scene import Scene
from touhou.schemas.musiccmt import TrackDescriptor

from .conftest import needs_data

_IDLE = InputFrame()


def _press(*btns: Button) -> InputFrame:
    s = frozenset(btns)
    return InputFrame(held=s, pressed=s)


def _hold(*btns: Button) -> InputFrame:
    return InputFrame(held=frozenset(btns))


def _tracks(n: int = 12, comment_lines: int = 2) -> list[TrackDescriptor]:
    return [
        TrackDescriptor(
            f"bgm/th07_{i + 1:02d}.mid",
            f"曲{i + 1}",
            tuple(f"评论{i + 1}-{j + 1}" for j in range(comment_lines)),
        )
        for i in range(n)
    ]


class _Marker(Scene):
    """next_scene 落点标记。"""

    def step(self, inp: InputFrame) -> None:
        pass

    def snapshot(self):
        raise NotImplementedError

    def next_scene(self):
        return None


def _scene(tracks: list[TrackDescriptor] | None = None, **kwargs) -> MusicRoomScene:
    marker = _Marker()
    scene = MusicRoomScene(
        None,
        tracks=_tracks() if tracks is None else tracks,
        on_exit=lambda: marker,
        **kwargs,
    )
    scene._marker = marker
    return scene


def _step(scene: MusicRoomScene, inp: InputFrame = _IDLE, n: int = 1) -> None:
    for _ in range(n):
        scene.step(inp)


def _enter(scene: MusicRoomScene) -> None:
    """8 帧输入门 + 开门帧(MusicRoom.cpp:35-38)。"""
    _step(scene, _IDLE, 9)


# ---- 输入门 ----
def test_input_gate_8_frames() -> None:
    """进场 waitFramesCounter>=8 才吃输入(MusicRoom.cpp:35-38)。"""
    scene = _scene()
    _step(scene, _press(Button.UP), 8)
    assert scene.cursor == 0  # 门内输入全挡
    assert not scene._enable_input
    scene.step(_IDLE)  # 开门帧
    assert scene._enable_input
    scene.step(_press(Button.UP))
    assert scene.cursor == 11


def test_first_frame_sets_interrupts() -> None:
    """首帧(wait==0): 光标行 interrupt 1, 其余 2, 评论 VM 全 1(MusicRoom.cpp:17-33)。"""
    scene = _scene()
    scene.step(_IDLE)
    assert scene._title_vms[0].pending_interrupt == 1
    assert scene._title_vms[1].pending_interrupt == 2
    assert all(m.pending_interrupt == 1 for m in scene._desc_vms)


# ---- 光标与翻页 ----
def test_cursor_up_wraps_to_last_with_offset() -> None:
    """0 上绕到末曲, listingOffset=num-10(MusicRoom.cpp:51-66)。"""
    scene = _scene()
    _enter(scene)
    scene.step(_press(Button.UP))
    assert scene.cursor == 11
    assert scene.listing_offset == 2


def test_cursor_down_scrolls_page() -> None:
    """光标出窗翻页 listingOffset=cursor-9; 绕回顶部 offset=0(MusicRoom.cpp:79-93)。"""
    scene = _scene()
    _enter(scene)
    _step(scene, _press(Button.DOWN), 10)
    assert scene.cursor == 10
    assert scene.listing_offset == 1
    scene.step(_press(Button.DOWN))
    assert (scene.cursor, scene.listing_offset) == (11, 2)
    scene.step(_press(Button.DOWN))
    assert (scene.cursor, scene.listing_offset) == (0, 0)


def test_cursor_up_scrolls_back() -> None:
    """向上出窗 listingOffset=cursor(MusicRoom.cpp:63-66)。"""
    scene = _scene()
    _enter(scene)
    _step(scene, _press(Button.DOWN), 11)
    scene.step(_press(Button.UP))
    assert (scene.cursor, scene.listing_offset) == (10, 2)  # 未出窗 offset 不动
    scene.cursor = 1
    scene.listing_offset = 1
    scene.step(_press(Button.UP))
    assert (scene.cursor, scene.listing_offset) == (0, 0)


def test_no_eighth_repeat() -> None:
    """按住方向不重复触发(C++ 用 WAS_PRESSED_RAW, 无 eighth)。"""
    scene = _scene()
    _enter(scene)
    scene.step(_press(Button.DOWN))
    _step(scene, _hold(Button.DOWN), 60)
    assert scene.cursor == 1


def test_move_refreshes_interrupts() -> None:
    """移动后新光标行 interrupt 1, 旧行 2(MusicRoom.cpp:67-77)。"""
    scene = _scene()
    _enter(scene)
    for m in scene._title_vms:
        m.pending_interrupt = 0
    scene.step(_press(Button.DOWN))
    assert scene._title_vms[0].pending_interrupt == 2
    assert scene._title_vms[1].pending_interrupt == 1


# ---- 确认与评论 ----
def test_confirm_sets_selected_and_comment() -> None:
    """确认: selectedIdx=cursor, 评论按该曲非空行刷新 + interrupt 1(MusicRoom.cpp:106-133)。"""
    scene = _scene()
    _enter(scene)
    _step(scene, _press(Button.DOWN), 3)
    scene.step(_press(Button.SHOT))
    assert scene.selected_idx == 3
    assert scene._desc_active == [True, True] + [False] * 6
    assert all(m.pending_interrupt == 1 for m in scene._desc_vms)


def test_comment_follows_selected_not_cursor() -> None:
    """评论跟随最近确认曲, 光标移动不刷新(MusicRoom.cpp:106-133)。"""
    scene = _scene()
    _enter(scene)
    scene.step(_press(Button.SHOT))  # 确认曲 1
    active = list(scene._desc_active)
    _step(scene, _press(Button.DOWN), 5)
    assert scene.selected_idx == 0
    assert scene._desc_active == active


def test_comment_capped_at_8_lines() -> None:
    """评论槽只有 8 个(descriptionSprites[8]), 超出的行不显示。"""
    scene = _scene(tracks=_tracks(2, comment_lines=10))
    _enter(scene)
    scene.step(_press(Button.SHOT))
    assert scene._desc_active == [True] * 8


def test_no_menu_sounds() -> None:
    """Music Room 全程无 SE(C++ ProcessInput 无 PlaySoundSE)。"""
    scene = _scene()
    _enter(scene)
    scene.step(_press(Button.DOWN))
    scene.step(_press(Button.SHOT))
    scene.step(_press(Button.BOMB))
    assert scene.drain_sounds() == []


# ---- 返回 ----
def test_cancel_returns_to_title() -> None:
    """取消(BOMB 或 PAUSE): done + 落到装配的主菜单(MusicRoom.cpp:134-138)。"""
    for btn in (Button.BOMB, Button.PAUSE):
        scene = _scene()
        _enter(scene)
        scene.step(_press(btn))
        assert scene.done
        assert scene.next_scene() is scene._marker


def test_empty_tracks_still_works() -> None:
    """无曲目(缺 musiccmt.txt): 移动/确认无副作用, 取消照常返回。"""
    scene = _scene(tracks=[])
    _enter(scene)
    scene.step(_press(Button.DOWN))
    scene.step(_press(Button.SHOT))
    assert scene.cursor == 0
    assert scene.selected_idx == 0
    scene.step(_press(Button.BOMB))
    assert scene.done


# ---- 真数据: 曲目表/画面 ----
@needs_data
def test_real_data_tracks_and_layout() -> None:
    """真机: 20 曲全列出(C++ 无解锁过滤), 快照 = music.jpg 底 + 横幅 + 曲名/评论。"""
    from touhou.games.th07.compose import DATA_PATH
    from touhou.schemas.archive import open_archive

    archive = open_archive(DATA_PATH, format_name="pbg4")
    scene = MusicRoomScene(archive, on_exit=lambda: _Marker())
    assert len(scene.tracks) == 20
    assert scene.tracks[0].path == "bgm/th07_01.mid"
    assert scene.tracks[0].title.startswith("妖々夢")
    _step(scene, _IDLE, 40)  # 输入门 + 亮暗插值 16 帧跑完
    snap = scene.snapshot()
    assert snap.sprites[0].image == "music.jpg"
    assert any(s.image == "music00.anm:0" for s in snap.sprites)  # 顶部横幅
    texts = [t.text for t in snap.texts]
    assert " 1." in texts and "10." in texts and "11." not in texts  # 一屏 10 首
    assert any(t.startswith("妖々夢") for t in texts)
    assert scene.tracks[0].comment[0] in texts  # 进场即显示第 1 首评论
    # 翻页后显示 11 号曲
    _enter(scene)
    _step(scene, _press(Button.DOWN), 10)
    _step(scene, _IDLE, 20)
    texts = [t.text for t in scene.snapshot().texts]
    assert "11." in texts and " 1." not in texts
