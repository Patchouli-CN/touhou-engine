"""Replay 列表画面(主菜单第 3 项)+ 回放 scene。

列表 = MainMenu 的 SELECT_REPLAY 态(OnUpdateSelectReplay/DrawReplayMenu 逐行对照,
MainMenu.cpp:1947-2344), 与主菜单共享同一 MenuVmSet; 子态: 0 INIT → 1 录像列表 →
2 选面 → 3 选回放模式 → 起播; 取消一路退回, 4 离场回主菜单(光标停 3)。
回放 scene 从 StageMark 起播喂输入驱动 world; 快进/对话加速按 ReplayManager.cpp。
"""

from __future__ import annotations

from collections.abc import Callable

from ....engine import Event, InputFrame, SceneSnapshot, TextDraw
from ....engine.input import Button
from .. import result as result_flow
from ..replay import ReplayEntry, StageMark, Th07Replay, decode_input, load_inputs
from ..world import Th07World
from .bg3d import StageBg
from .fx import GameFx
from .menu_vms import SE_BACK, SE_MOVE, SE_SELECT, MenuScene, MenuVmSet
from .music import TITLE_BGM, BgmPlayer, StageBgm
from .scene import Scene

_BG_SELECT = "select00.jpg"  # MainMenu.cpp:1963

# 列表/舞台文字(MainMenu.cpp:50-99 g_StageReplayStrings/g_DifficultyStrings/
# g_CharacterAndShottypeReplayStrings)
_STAGE_STRINGS = (
    "Stage1  ",
    "Stage2  ",
    "Stage3  ",
    "Stage4  ",
    "Stage5  ",
    "Stage6  ",
    "Extra   ",
)
_PHANTASM_STRING = "Phantasm"
_DIFF_STRINGS = ("Easy    ", "Normal  ", "Hard    ", "Lunatic ", "Extra   ", "Phantasm")
_CHAR_STRINGS = ("ReimuA ", "ReimuB ", "MarisaA", "MarisaB", "SakuyaA", "SakuyaB")
_HEADER = "No.   Name       Date  Player   Rank"  # MainMenu.cpp:2237-2239
_STAGE_HEADER = "Stage    LastScore"  # MainMenu.cpp:2277-2279

# VM 索引(:2236-2283): 表头 134/行 135..149(一页 15)/处理落ち率 133/
# 舞台表头 150/舞台行 151..157/回放模式 158..160
_VM_SLOWDOWN = 133
_VM_HEADER = 134
_VM_ROW = 135
_VM_STAGE_HEADER = 150
_VM_STAGE_ROW = 151
_VM_MODE = 158
_PAGE_SIZE = 15  # :2047
_MAX_FILES = 60  # 编号槽 15 + 自由档 45 (:1974/:2003)

_WHITE = (255, 255, 255, 255)  # 0xffffffff (:2251)
_GRAY = (128, 128, 128, 255)  # 0xff808080 (:2255)
_WHITE_DIM = (255, 255, 255, 96)  # 0x60ffffff 模式选择中 (:2300)
_GRAY_DIM = (128, 128, 128, 96)  # 0x60808080 (:2304)
_TEXT_SIZE = 15


def _ascii_text(text: str, x: float, y: float, rgba: tuple[int, int, int, int]):
    """Ascii 文字 + 黑影(原版字库烘焙描边近似, 同选面页)。"""
    return (
        TextDraw(text, x + 1, y + 1, _TEXT_SIZE, (0, 0, 0, rgba[3])),
        TextDraw(text, x, y, _TEXT_SIZE, rgba),
    )


class ReplayListScene(MenuScene):
    """录像列表画面: SELECT_REPLAY 态(子态 0/1/2/3/4 照抄 :1956-2225)。

    on_watch(entry, mark, mode) → 回放 scene(起播: MainMenu.cpp:2182-2201);
    on_exit() → 主菜单(光标停 3, :2216-2217)。删除功能原版没有, 不做。
    """

    def __init__(
        self,
        vm_set: MenuVmSet,
        entries: list[ReplayEntry],
        *,
        on_watch: Callable[[ReplayEntry, StageMark, int], Scene],
        on_exit: Callable[[], Scene],
        music: BgmPlayer | None = None,
    ) -> None:
        super().__init__()
        self._mv = vm_set
        self._entries = entries[:_MAX_FILES]
        self._on_watch = on_watch
        self._on_exit = on_exit
        self._music = music
        self._next: Scene | None = None
        self._substate = 0
        self._input_delay = 0
        self._state_timer = 0
        self._chosen = 0
        self._selected_stage = 0
        self._frame = 0

    # ---- 录像/面槽查询 ----
    def _entry(self) -> ReplayEntry:
        return self._entries[self._chosen]

    def _marks(self) -> dict[int, StageMark]:
        return {m.stage_no: m for m in self._entry().replay.stages}

    def _slot_stage_no(self, slot: int) -> int:
        """面槽 0..6 → stage_no; 槽 6 = Extra/Phantasm 共用(ReplayManager.cpp:55-58)。"""
        if slot < 6:
            return slot + 1
        return 7 if self._entry().replay.difficulty == 4 else 8

    def _slot_has_data(self, slot: int) -> bool:
        return self._slot_stage_no(slot) in self._marks()

    # ---- Scene 接口 ----
    def on_enter(self) -> None:
        """进列表: 回放回来重载标题 BGM(MainMenu.cpp:233-245), 主菜单进来不重启。"""
        if self._music is not None:
            self._music.ensure(TITLE_BGM)

    def step(self, inp: InputFrame) -> None:
        self._update_input(inp)
        if self._substate == 0:
            self._update_init()
        elif self._substate == 1:
            self._update_list()
        elif self._substate == 2:
            self._update_stage_select()
        elif self._substate == 3:
            self._update_mode_select()
        elif self._substate == 4 and self._input_delay >= 30:  # :2213-2219 离场
            self._next = self._on_exit()
            self.done = True
            return
        self._mv.execute()
        self._input_delay += 1
        self._state_timer += 1
        self._frame += 1

    def snapshot(self) -> SceneSnapshot:
        sprites = self._mv.sprites(_BG_SELECT)
        return SceneSnapshot(self._frame, tuple(sprites), self._texts())

    def next_scene(self) -> Scene | None:
        return self._next

    # ---- 子态 0: INIT (:1958-2044) ----
    def _update_init(self) -> None:
        if self._state_timer == 0:
            self._mv.interrupt_all(14)  # :1968
            self.cursor = 0
            self._input_delay = 0
            self._mv.cur_desc = None  # :1972 该页没有说明文字
        if self._state_timer >= 30:  # :2039-2043 滑入 30 帧后才吃输入
            self._substate = 1
            self._input_delay = 0

    # ---- 子态 1: 录像列表 (:2045-2120) ----
    def _update_list(self) -> None:
        mv = self._mv
        n = len(self._entries)
        self._move_cursor_vertical(n)
        if n > _PAGE_SIZE:
            if self._move_edge(Button.LEFT):  # :2049-2057 翻页 ±15
                self.cursor = (self.cursor - _PAGE_SIZE) % n
                self._sounds.append(SE_MOVE)
            if self._move_edge(Button.RIGHT):
                self.cursor = (self.cursor + _PAGE_SIZE) % n
                self._sounds.append(SE_MOVE)
        self._chosen = self.cursor  # :2068
        if self._input_delay < 10:  # :2069-2072 输入门
            return
        if self._confirm_pressed():
            if n == 0:
                return  # :2076-2079 空列表 confirm 当帧不再查取消
            self._sounds.append(SE_SELECT)
            self._substate = 2
            mv.interrupt_all(15)  # :2083
            mv.vms[_VM_ROW + self._chosen % _PAGE_SIZE].vm.pending_interrupt = 17
            self.cursor = 0
            while not self._slot_has_data(self.cursor):
                self.cursor += 1  # :2100-2110 落到第一个有数据的面槽
            return
        if self._cancel_pressed():
            self._sounds.append(SE_BACK)
            self._substate = 4
            self._input_delay = 0
            mv.interrupt_all(16)  # :2118

    # ---- 子态 2: 选面 (:2121-2172; 确认/取消原版无 SE) ----
    def _update_stage_select(self) -> None:
        mv = self._mv
        moved = self._move_cursor_vertical(7)
        if moved < 0:
            while not self._slot_has_data(self.cursor):  # :2125-2134 跳过空槽
                self.cursor -= 1
                if self.cursor < 0:
                    self.cursor = 6
        elif moved > 0:
            while not self._slot_has_data(self.cursor):  # :2138-2147
                self.cursor += 1
                if self.cursor >= 7:
                    self.cursor = 0
        self._selected_stage = self.cursor  # :2149
        if self._confirm_pressed():
            mv.interrupt_all(19)  # :2152
            mv.vms[_VM_ROW + self._chosen % _PAGE_SIZE].vm.pending_interrupt = 17
            self._substate = 3
            self.cursor = 0
            for i in range(3):
                mv.vms[_VM_MODE + i].vm.pending_interrupt = 21  # :2156-2158
            mv.vms[_VM_MODE].vm.pending_interrupt = 20  # :2159
            return
        if self._cancel_pressed():
            self._substate = 1  # :2162-2170
            self._state_timer = 0
            mv.interrupt_all(14)
            self.cursor = self._chosen

    # ---- 子态 3: 选回放模式 (:2173-2212; replayStage 0/1/2) ----
    def _update_mode_select(self) -> None:
        mv = self._mv
        if self._move_cursor_vertical(3):
            for i in range(3):
                mv.vms[_VM_MODE + i].vm.pending_interrupt = 21  # :2177-2179
            mv.vms[_VM_MODE + self.cursor].vm.pending_interrupt = 20  # :2180
        if self._confirm_pressed():
            # 起播(:2182-2201): 机体/难度/面由录像决定; :2198 StopAudio
            mark = self._marks()[self._slot_stage_no(self._selected_stage)]
            if self._music is not None:
                self._music.stop()
            self._next = self._on_watch(self._entry(), mark, self.cursor)
            self.done = True
            return
        if self._cancel_pressed():
            self._substate = 2  # :2203-2210
            self._state_timer = 0
            self.cursor = self._selected_stage
            mv.interrupt_all(15)
            mv.vms[_VM_ROW + self._chosen % _PAGE_SIZE].vm.pending_interrupt = 17

    # ---- 画面 (DrawReplayMenu, MainMenu.cpp:2230-2344) ----
    def _texts(self) -> tuple[TextDraw, ...]:
        mv = self._mv
        out: list[TextDraw] = []
        pos = mv.vms[_VM_HEADER].vm.pos
        out += _ascii_text(_HEADER, pos[0], pos[1], _WHITE)
        page = self._chosen - self._chosen % _PAGE_SIZE  # :2240
        for i in range(page, min(page + _PAGE_SIZE, len(self._entries))):
            r = self._entries[i].replay
            # "%s %8s  %6s %7s  %8s" (:2259-2265)
            line = (
                f"{self._entries[i].label} {r.name:>8}  {r.date:>6}"
                f" {_CHAR_STRINGS[r.character]:>7}  {_DIFF_STRINGS[r.difficulty]:>8}"
            )
            pos = mv.vms[_VM_ROW + i % _PAGE_SIZE].vm.pos
            out += _ascii_text(
                line, pos[0], pos[1], _WHITE if i == self._chosen else _GRAY
            )
        if self._substate in (2, 3) and self._entries:
            out += self._stage_texts(self._entries[self._chosen].replay)
        return tuple(out)

    def _stage_texts(self, replay: Th07Replay) -> list[TextDraw]:
        """选面/选模式中的处理落ち率 + Stage/LastScore 表(:2267-2340)。"""
        mv = self._mv
        marks = {m.stage_no: m for m in replay.stages}
        out: list[TextDraw] = []
        pos = mv.vms[_VM_SLOWDOWN].vm.pos
        out += _ascii_text(f"       {replay.slowdown:2.3f}%", pos[0], pos[1], _WHITE)
        pos = mv.vms[_VM_STAGE_HEADER].vm.pos
        out += _ascii_text(_STAGE_HEADER, pos[0], pos[1], _WHITE)
        for i in range(7):
            stage_no = self._slot_stage_no(i)
            name = (
                _STAGE_STRINGS[i]
                if i < 6 or replay.difficulty <= 4
                else _PHANTASM_STRING
            )
            mark = marks.get(stage_no)
            line = (
                f"{name} {mark.score:9d}0" if mark is not None else f"{name} ----------"
            )
            if self._substate == 2:
                color = _WHITE if i == self._selected_stage else _GRAY
            else:
                color = _WHITE_DIM if i == self._selected_stage else _GRAY_DIM
            pos = mv.vms[_VM_STAGE_ROW + i].vm.pos
            out += _ascii_text(line, pos[0], pos[1], color)
        return out


class ReplayWatchScene(Scene):
    """看录像: 从 StageMark 起播(组该面世界 → 喂锚点帧 → 灌快照 → 续喂输入)。

    快进: 按住 SKIP(Ctrl) 8 倍速(Gui.cpp:145-148 renderSkipFrames=8);
    对话可跳过段自动 3 倍, 模式 2 非 boss 5 倍(ReplayManager.cpp:87-98);
    模式 1(处理落ち再现)依赖录制帧率, 本引擎无此概念, 视同模式 0(已知偏差)。
    Esc 暂停; 暂停中 X 中断回放(原版 Esc 出暂停菜单选退出, 菜单画面留待, 先近似)。
    回放结束(REPLAY_END)回录像列表(MainMenu.cpp:233-245 直跳 SELECT_REPLAY)。
    """

    playfield_chrome = True

    def __init__(
        self,
        world: Th07World,
        replay: Th07Replay,
        mark: StageMark,
        *,
        mode: int = 0,
        fx: GameFx | None = None,
        music: BgmPlayer | None = None,
        bg: StageBg | None = None,
        on_exit: Callable[[], Scene | None],
    ) -> None:
        super().__init__()
        self.world = world
        self._on_exit = on_exit
        self._mode = mode
        self._fx = fx
        self._music = music
        self._bg = bg
        self._bg_surf = None
        self._bgm = StageBgm(music, world.archive) if music is not None else None
        self._codes = load_inputs(replay)
        self._events: list[Event] = []
        world.subscribers.append(self._events.append)
        if self._bgm is not None:
            world.subscribers.append(self._bgm.on_event)
        # 起播: 喂锚点帧输入拿首帧快照, 再灌快照与原局该帧后状态逐字节对齐
        self._prev_held: frozenset[Button] = frozenset()
        inp = decode_input(self._codes[mark.start_frame], self._prev_held)
        self._prev_held = inp.held
        self._snapshot = world.tick(inp)
        self._fx_sprites: tuple = ()
        self._fx_texts: tuple = ()
        self._step_fx()
        if self._bg is not None:
            self._bg_surf = self._bg.step(world)
        mark.snapshot.apply(world)
        if self._bgm is not None:
            self._bgm.step(world)  # 该面主曲(GameManager.cpp:782, 快照回灌后取帧号)
        self._idx = mark.start_frame + 1
        self._frame_sounds: list[int] = []
        self.paused = False

    def _step_fx(self) -> None:
        """特效层逐 tick 推进(快进时与 sim 同倍率), 产出留待末帧合并。"""
        if self._fx is None:
            return
        sprites, texts = self._fx.step()
        self._fx_sprites = tuple(sprites)
        self._fx_texts = tuple(texts)

    def step(self, inp: InputFrame) -> None:
        if Button.PAUSE in inp.pressed:
            self.paused = not self.paused
            if self._music is not None:
                # 暂停联动 BGM(GameManager.cpp:138-144, 仅 WAV 音源)
                if self.paused:
                    self._music.pause()
                else:
                    self._music.unpause()
        if self.paused:
            self._frame_sounds = []
            if Button.BOMB in inp.pressed:
                self.done = True  # 暂停菜单退出回放(近似)
            return
        steps = 8 if Button.SKIP in inp.held else 1
        if self._mode == 2 and self.world.boss is None:
            steps = max(steps, 5)  # 非 boss 高速再生(ReplayManager.cpp:93-98)
        w = self.world
        if w.msg_active and w.msg_vm is not None and w.msg_vm.dialogue_skippable:
            steps = max(steps, 3)  # 对话自动快进(:87-91)
        executed = 0
        for _ in range(steps):
            if self._idx >= len(self._codes):
                self.done = True  # 输入喂完 = 回放结束(REPLAY_END)
                break
            frame_inp = decode_input(self._codes[self._idx], self._prev_held)
            self._prev_held = frame_inp.held
            self._idx += 1
            self._snapshot = w.tick(frame_inp)
            self._step_fx()
            if self._bgm is not None:
                self._bgm.step(w)
            self._frame_sounds = list(w.frame_sounds)
            executed += 1
            if w.ending is not None:
                result_flow.finish_ending(w)  # 回放不进结局画面(Gui.cpp:1077-1085)
            if w.result is not None:
                self.done = True
                break
        if self._bg is not None and executed:
            self._bg_surf = self._bg.step(w, frames=executed)  # 快进多推少渲

    def on_exit(self) -> None:
        """离开回放停 BGM(GameManager::DeletedCallback, GameManager.cpp:813)。"""
        if self._music is not None:
            self._music.stop()
        if self._bg is not None:
            self._bg.close()

    def snapshot(self) -> SceneSnapshot:
        base = self._snapshot
        if not self._fx_sprites and not self._fx_texts:
            return base
        return SceneSnapshot(
            base.frame,
            base.sprites + self._fx_sprites,
            base.texts + self._fx_texts,
            base.effects,
        )

    @property
    def frame_shakes(self) -> list[tuple[int, int, int]]:
        """本帧震屏事件(runner 同步给后端; 暂停帧不重复消费)。"""
        return [] if self.paused else self.world.frame_shakes

    @property
    def frame_bg(self):  # -> pygame.Surface | None(duck 通道, 不引类型)
        """本帧 3D 背景帧(runner 同步给后端; None = 纯色占位)。"""
        return self._bg_surf

    def events(self) -> tuple[Event, ...]:
        out = tuple(self._events)
        self._events.clear()
        return out

    def drain_sounds(self) -> list[int]:
        out, self._frame_sounds = self._frame_sounds, []
        return out

    def next_scene(self) -> Scene | None:
        return self._on_exit()
