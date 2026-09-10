"""Music Room: MusicRoom.cpp 的 scene 化(独立 chain 对象, 不是 MainMenu 的菜单态)。

曲目表/光标/翻页/评论显示逐行对照 MusicRoom.cpp(ProcessInput/OnUpdate/OnDraw);
曲名与评论来自封包内 musiccmt.txt; 实际发声不做(BGM 链留待后续单, hook 点见注释)。
"""

from __future__ import annotations

from collections.abc import Callable

from ....engine import InputFrame, SceneSnapshot, SpriteDraw, TextDraw
from ....engine.anm import AnmBank, AnmMachine, build_bank
from ....engine.input import Button
from ....engine.rng import Rng
from ....schemas.anm import parse_anm
from ....schemas.archive import Archive, load_entry
from ....schemas.musiccmt import TrackDescriptor, parse_musiccmt
from .menu_vms import MenuScene
from .scene import Scene

_BG = "music.jpg"  # LoadSurface("data/result/music.jpg") (MusicRoom.cpp:243)
_MUSIC_ANM = "music00.anm"  # MusicRoom.cpp:248
_TEXT_ANM = "text.anm"
_MUSICCMT = "musiccmt.txt"  # MusicRoom.cpp:257

_VISIBLE = 10  # 一屏 10 首(MusicRoom.cpp:200)
_DESC_COUNT = 8  # descriptionSprites[8] (MusicRoom.hpp:51)
_INPUT_GATE = 8  # waitFramesCounter>=8 才吃输入(MusicRoom.cpp:35-38)

_MAIN_SCRIPT = 0  # ANM_SCRIPT_MUSIC(0x900) ↔ music00.anm 链式键 0
_TITLE_SCRIPT_FIRST = 1  # ANM_SCRIPT_MUSIC_TITLE(0x901)+i ↔ 链式键 1+i
_DESC_SCRIPT_FIRST = 7  # ANM_SCRIPT_TEXT_MUSIC_DESC(0x707)+i ↔ text.anm 链式键 7+i

_TITLE_X = 93.0  # MusicRoom.cpp:207
_TITLE_Y0 = 84.0  # (i+1-listingOffset)*18 + 104 - 20 (MusicRoom.cpp:208-209)
_TITLE_STEP = 18.0
_ARROW_X = _TITLE_X - 60.0  # 光标字符 0x7F(MusicRoom.cpp:212-216)
_NUMBER_X = _TITLE_X - 45.0  # "%2d."(MusicRoom.cpp:218-220)
_FONT_SIZE = 15

_TITLE_RGB = (192, 224, 255)  # 0xc0e0ff 曲名烘焙色(MusicRoom.cpp:352-354)
_TITLE_SHADOW_RGB = (48, 32, 128)  # 0x302080
_DESC_RGB = (255, 224, 192)  # 0xffe0c0 评论烘焙色(MusicRoom.cpp:123-125)
_DESC_SHADOW_RGB = (48, 0, 0)  # 0x300000

_ARROW = "→"  # C++ 画 ascii 字库 0x7F 号字形(MusicRoom.cpp:195,216)


def _load_tracks(archive: Archive | None) -> list[TrackDescriptor]:
    """从封包读 musiccmt.txt 解析曲目表(AddedCallback, MusicRoom.cpp:257-347)。"""
    if archive is None:
        return []
    try:
        return parse_musiccmt(load_entry(archive, _MUSICCMT))
    except KeyError:
        return []


def _load_bank(archive: Archive | None, name: str, anm_version: int) -> AnmBank | None:
    if archive is None:
        return None
    try:
        return build_bank(
            parse_anm(
                load_entry(archive, name), version=anm_version, flat_layout=False
            ),
            flat_layout=False,
        )
    except (KeyError, ValueError):
        return None


def _modulate(rgb: tuple[int, int, int], vm_color: list[int]) -> tuple[int, int, int]:
    """烘焙色 × VM 顶点色(D3D 调制, 选中白 255 / 未选灰 128)。"""
    return (
        rgb[0] * vm_color[0] // 255,
        rgb[1] * vm_color[1] // 255,
        rgb[2] * vm_color[2] // 255,
    )


class MusicRoomScene(MenuScene):
    """Music Room: 上下选曲(一屏 10 首滚动), 确认"播放"并刷新该曲评论, 取消回主菜单。

    C++ 无解锁过滤(musiccmt.txt 全曲目列出)也无菜单 SE; 评论跟随的是
    selectedIdx(最近确认的曲), 不随光标移动刷新(MusicRoom.cpp:106-133)。
    """

    def __init__(
        self,
        archive: Archive | None,
        *,
        anm_version: int = 2,
        on_exit: Callable[[], Scene],
        tracks: list[TrackDescriptor] | None = None,
    ) -> None:
        super().__init__()
        self._on_exit = on_exit
        self.tracks = tracks if tracks is not None else _load_tracks(archive)
        self.selected_idx = (
            0  # C++ 初始 0: 进场即显示第 1 首评论(MusicRoom.cpp:366-380)
        )
        self.listing_offset = 0
        self._enable_input = False
        self._wait = 0
        self._frame = 0
        rng = Rng(0)  # view VM 专用, 与 sim 无关
        bank = _load_bank(archive, _MUSIC_ANM, anm_version)
        text_bank = _load_bank(archive, _TEXT_ANM, anm_version)
        self._bank = bank
        scripts = bank.scripts if bank is not None else {}
        self._main_vm = AnmMachine(rng)
        self._main_vm.start(scripts.get(_MAIN_SCRIPT))  # MusicRoom.cpp:254
        self._title_vms: list[AnmMachine] = []
        for i in range(len(self.tracks)):
            m = AnmMachine(rng)
            m.start(scripts.get(_TITLE_SCRIPT_FIRST + i))  # MusicRoom.cpp:350-351
            self._title_vms.append(m)
        desc_scripts = text_bank.scripts if text_bank is not None else {}
        self._desc_vms: list[AnmMachine] = []
        for i in range(_DESC_COUNT):
            m = AnmMachine(rng)
            m.start(desc_scripts.get(_DESC_SCRIPT_FIRST + i))  # MusicRoom.cpp:363-365
            self._desc_vms.append(m)
        # 进场评论 = selectedIdx(0)的评论, 空行槽不显示(MusicRoom.cpp:366-380)
        self._desc_active = (
            self._comment_active(self.tracks[0])
            if self.tracks
            else [False] * _DESC_COUNT
        )

    @staticmethod
    def _comment_active(track: TrackDescriptor) -> list[bool]:
        return [i < len(track.comment) for i in range(_DESC_COUNT)]

    # ---- Scene 接口 ----
    def on_enter(self) -> None:
        """进 Music Room(C++ 不停标题 BGM, 播到首次选曲; BGM 链留待后续单)。"""

    def on_exit(self) -> None:
        """离开 Music Room(曲目停止点 = 主菜单重载标题 BGM, MainMenu.cpp:2658; BGM 链留待)。"""

    def step(self, inp: InputFrame) -> None:
        self._update_input(inp)
        was = self._enable_input
        if not self._enable_input:
            if self._wait == 0:
                self._interrupt_titles()  # CheckInputEnable (MusicRoom.cpp:17-33)
                for m in self._desc_vms:
                    m.pending_interrupt = 1
            if self._wait >= _INPUT_GATE:
                self._enable_input = True
        elif self._process_input():
            self.done = (
                True  # RETURNMENU → CONTINUE_AND_REMOVE_JOB (MusicRoom.cpp:134-138)
            )
        self._wait = 0 if was != self._enable_input else self._wait + 1  # :167-174
        self._main_vm.execute()  # OnUpdate (:175-183)
        for m in self._title_vms:
            m.execute()
        for m in self._desc_vms:
            m.execute()
        self._frame += 1

    def snapshot(self) -> SceneSnapshot:
        sprites = [
            SpriteDraw(_BG, 320.0, 240.0, z=-1.0)
        ]  # CopySurfaceToBackBuffer (:197-198)
        main = self._main_sprite()
        if main is not None:
            sprites.append(main)
        texts: list[TextDraw] = []
        n = len(self.tracks)
        for i in range(self.listing_offset, min(self.listing_offset + _VISIBLE, n)):
            vm = self._title_vms[i]
            if not vm.visible or vm.color[3] <= 0:
                continue
            alpha = vm.color[3]
            y = (i + 1 - self.listing_offset) * _TITLE_STEP + _TITLE_Y0  # :208-209
            plain = (*vm.color[:3], alpha)  # 序号/箭头用 VM 色直出(:206 SetColor)
            if i == self.cursor:
                texts.append(TextDraw(_ARROW, _ARROW_X, y, _FONT_SIZE, plain))
            texts.append(TextDraw(f"{i + 1:>2}.", _NUMBER_X, y, _FONT_SIZE, plain))
            title = self.tracks[i].title
            shadow = (*_modulate(_TITLE_SHADOW_RGB, vm.color), alpha)
            texts.append(TextDraw(title, _TITLE_X + 1, y + 1, _FONT_SIZE, shadow))
            texts.append(
                TextDraw(
                    title,
                    _TITLE_X,
                    y,
                    _FONT_SIZE,
                    (*_modulate(_TITLE_RGB, vm.color), alpha),
                )
            )
        if self.tracks:
            comment = self.tracks[self.selected_idx].comment
            for i, vm in enumerate(self._desc_vms):
                if not self._desc_active[i] or not vm.visible or vm.color[3] <= 0:
                    continue
                alpha = vm.color[3]
                x, y = vm.pos[0], vm.pos[1]  # 站位由 text.anm 脚本定(实测 64,320+16i)
                texts.append(
                    TextDraw(
                        comment[i], x + 1, y + 1, _FONT_SIZE, (*_DESC_SHADOW_RGB, alpha)
                    )
                )
                texts.append(
                    TextDraw(comment[i], x, y, _FONT_SIZE, (*_DESC_RGB, alpha))
                )
        return SceneSnapshot(self._frame, tuple(sprites), tuple(texts))

    def next_scene(self) -> Scene | None:
        return self._on_exit()

    # ---- 输入 (MusicRoom.cpp:44-141 ProcessInput; 无 eighth 重复, 无 SE) ----
    def _process_input(self) -> bool:
        n = len(self.tracks)
        if self._pressed(Button.UP) and n:
            self.cursor -= 1
            if self.cursor < 0:
                self.cursor = n - 1
                self.listing_offset = max(n - _VISIBLE, 0)
            elif self.listing_offset > self.cursor:
                self.listing_offset = self.cursor
            self._interrupt_titles()  # :67-77
        if self._pressed(Button.DOWN) and n:
            self.cursor += 1
            if self.cursor >= n:
                self.cursor = 0
                self.listing_offset = 0
            elif self.listing_offset <= self.cursor - _VISIBLE:
                self.listing_offset = self.cursor - (_VISIBLE - 1)
            self._interrupt_titles()  # :94-104
        if self._confirm_pressed() and n:
            self.selected_idx = self.cursor
            # BGM 播放 hook 点: PlayAudio(track.path) (:106-113) —— music_mode
            # WAV=thbgm.dat 内 .wav / MIDI=.mid / OFF=无声(Supervisor.cpp:1367-1397),
            # preloadBgm 时先 StartBGM("thbgm.dat"); BGM 链留待后续单
            self._desc_active = self._comment_active(self.tracks[self.selected_idx])
            for m in self._desc_vms:
                m.pending_interrupt = 1  # :131
        if self._cancel_pressed():
            # 回主菜单光标停 Music Room(MainMenu.cpp:2630-2631); C++ 此处无 SE
            return True
        return False

    def _interrupt_titles(self) -> None:
        """光标行 interrupt 1(亮), 其余 2(暗)(MusicRoom.cpp:67-77 模式)。"""
        for i, m in enumerate(self._title_vms):
            m.pending_interrupt = 1 if i == self.cursor else 2

    def _main_sprite(self) -> SpriteDraw | None:
        """顶部标题横幅 VM(DrawNoRotation, MusicRoom.cpp:199)。"""
        vm = self._main_vm
        if not vm.visible or vm.active_sprite_idx < 0 or vm.color[3] <= 0:
            return None
        x = vm.pos[0] + vm.offset[0]
        y = vm.pos[1] + vm.offset[1]
        if (
            vm.anchor & 3 and self._bank is not None
        ):  # 左/顶缘 → 中心锚 (AnmManager.cpp:1011-1041)
            slot = self._bank.sprites.get(vm.active_sprite_idx)
            if slot is not None:
                if vm.anchor & 1:
                    x += slot.sprite.w * vm.scale[0] / 2
                if vm.anchor & 2:
                    y += slot.sprite.h * vm.scale[1] / 2
        return SpriteDraw(
            f"{_MUSIC_ANM}:{vm.active_sprite_idx}",
            x,
            y,
            rotation=vm.rotation[2],
            alpha=vm.color[3],
            scale_x=vm.scale[0],
            scale_y=vm.scale[1],
            color=(vm.color[0], vm.color[1], vm.color[2]),
            blend_mode=vm.blend_mode,
        )
