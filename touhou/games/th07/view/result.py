"""对局后结算画面: ResultScreen.cpp RegisterChain type=1 的 scene 化。

链: ENTER_NAME(入榜输名) → FINAL_STATS_SHOW/WAIT(总结算面板) →
REPLAY_SAVE_PROMPT(录像保存询问) → 选槽/覆盖确认/改名 → EXITING → 回标题。
续关过的录像不可存 (:1362-1378 → REPLAY_CANNOT_SAVE); practice 局跳过输名
直进录像保存询问 (PRACTICE_END → REPLAY_SAVE_PROMPT, AddedCallback
:2603-2616)。名字/录像名的字表输入同一份状态机
(HandleResultKeyboard :1133-1317 与 REPLAY_SAVING :1529-1644 同构)。
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from ....engine import InputFrame, SceneSnapshot, SpriteDraw, TextDraw
from ....engine.anm import AnmBank, AnmMachine, build_bank
from ....engine.input import Button
from ....engine.rng import Rng
from ....engine.score_store import ScoreStore
from ....schemas.anm import parse_anm
from ....schemas.archive import Archive, load_entry
from ..replay import (
    ReplayEntry,
    ReplayRecorder,
    list_replays,
    new_replay_path,
    save_replay,
)
from ..world import Th07World
from .menu_vms import SE_BACK, SE_MOVE, SE_SELECT, MenuScene, MenuVm
from .name_entry import NameEntry, name_grid_sprites
from .result_draw import score_rows, slot_rows, stats_lines, vm_sprites
from .scene import Scene

_BG = "result.jpg"  # LoadSurface("data/result/result.jpg") (ResultScreen.cpp:2551)
_RESULT_ANM = "result00.anm"  # ResultScreen.cpp:2556

_VM_COUNT = 41  # vms[41] (ResultScreen.hpp:426)
_VM_PANEL = 16  # 表格面板锚 (:2196)
_VM_PROMPT_YES = 19  # 询问/覆盖确认的 Yes/No 亮暗 (:1381-1395/:1646-1660)
_VM_SLOT_ROW = 25  # 选中槽行 vms[25+chosen] 的 interrupt 16 (:1495-1496)
_VM_STATS = 40  # 总结算面板 (腕前面板, :2028)

# 状态 (ResultScreen.hpp:206-231 ResultScreenState)
_ST_EXITING = 2
_ST_ENTER_NAME = 10
_ST_SAVE_PROMPT = 11
_ST_CANNOT_SAVE = 12
_ST_SELECT_SLOT = 13
_ST_SAVING = 14
_ST_OVERWRITE = 15
_ST_STATS_SHOW = 16
_ST_STATS_WAIT = 17

_MAX_SLOTS = 15  # 原版编号槽 15 (:1455); 本作 = 既有文件(≤14) + 末行新槽


def _load_bank(archive: Archive | None, anm_version: int) -> AnmBank | None:
    if archive is None:
        return None
    try:
        return build_bank(
            parse_anm(
                load_entry(archive, _RESULT_ANM), version=anm_version, flat_layout=False
            ),
            flat_layout=False,
        )
    except (KeyError, ValueError):
        return None


class ResultScene(MenuScene):
    """对局后结算: 入榜输名 + 总结算面板 + 录像选槽保存, 完毕回标题。

    分数在进画面前已入榜(final_result 幂等, result["rank"] = 名次);
    ENTER_NAME 只是把榜上那条的名字改成输入值 (HandleResultKeyboard 的
    curScore.name 就地编辑语义); on_save() 在离场时落盘(DeletedCallback
    WriteScore, :2653-2657)。
    """

    def __init__(
        self,
        world: Th07World,
        *,
        anm_version: int = 2,
        recorder: ReplayRecorder | None = None,
        replay_dir: str | Path = "replays",
        on_save: Callable[[], None],
        on_exit: Callable[[], Scene],
        practice: bool = False,
    ) -> None:
        super().__init__()
        assert world.result is not None  # 只在结算出炉后进本画面
        self._world = world
        self._result = world.result
        self._store: ScoreStore = world.store
        self._recorder = recorder
        self._replay_dir = replay_dir
        self._on_save = on_save
        self._on_exit = on_exit
        self._frame_timer = 0
        self._frame = 0
        self._rank: int = self._result["rank"]
        has_lsnm = self._store.lsnm is not None
        self._has_lsnm = has_lsnm
        self._entry = NameEntry.create(self._result["name"], has_lsnm=has_lsnm)
        self._replay_name = self._result["name"]  # replayName (:1313)
        self._replay_date = ""
        self._slots: list[ReplayEntry] = []
        self._chosen = 0
        rng = Rng(0)  # view VM 专用, 与 sim 无关
        self._bank = _load_bank(world.archive, anm_version)
        scripts = self._bank.scripts if self._bank is not None else {}
        self._vms: list[MenuVm] = []
        for i in range(_VM_COUNT):
            m = AnmMachine(rng)
            m.start(scripts.get(i))  # ANM_SCRIPT_RESULT_ARRAY+i ↔ 链式键 i (:2562-2567)
            self._vms.append(MenuVm(m))
        if practice:
            # PRACTICE_END → REPLAY_SAVE_PROMPT (AddedCallback 转换,
            # ResultScreen.cpp:2603-2616): 练习局不入榜/不输名, 只出录像保存询问
            self._state = _ST_SAVE_PROMPT
            self._interrupt_all(2)
        elif self._rank >= 0:
            self._state = _ST_ENTER_NAME
            self._interrupt_all(self._result["difficulty"] + 3)  # :1153-1157
        else:
            # 未入榜直进总结算面板 (:1189-1191 → LAB_004470e9)
            self._state = _ST_STATS_SHOW
            self._interrupt_all(2)

    # ---- Scene 接口 ----
    def on_exit(self) -> None:
        """离场落盘 score(DeletedCallback WriteScore, :2653-2657)。"""
        self._on_save()

    def step(self, inp: InputFrame) -> None:
        self._update_input(inp)
        if self._state == _ST_ENTER_NAME:
            self._enter_name()
        elif self._state == _ST_STATS_SHOW:
            self._stats_show()
        elif self._state == _ST_STATS_WAIT:
            if self._frame_timer >= 30:
                self._frame_timer = 59  # :1718-1722
                self._state = _ST_SAVE_PROMPT
        elif self._state == _ST_SAVE_PROMPT:
            self._save_prompt()
        elif self._state == _ST_CANNOT_SAVE:
            self._cannot_save()
        elif self._state == _ST_SELECT_SLOT:
            self._select_slot()
        elif self._state == _ST_OVERWRITE:
            self._overwrite()
        elif self._state == _ST_SAVING:
            self._saving()
        elif self._state == _ST_EXITING:
            if self._frame_timer >= 60:
                self.done = True  # curState=MAINMENU + REMOVE_JOB (:918-924)
        for w in self._vms:
            w.vm.execute()  # ExecuteScript 全阵列 (:1122-1126)
        self._frame_timer += 1
        self._frame += 1

    def next_scene(self) -> Scene | None:
        return self._on_exit()

    # ---- ENTER_NAME (:1099-1101/:1133-1317) ----
    def _enter_name(self) -> None:
        if self._frame_timer < 30:
            return
        self._entry_step(self._entry, on_finish=self._finish_name_entry)

    def _finish_name_entry(self) -> None:
        """确认名字: 写回榜上记录 + LSNM, 进总结算面板 (:1301-1315)。"""
        name = self._entry.name
        self._store.set_entry_name(
            self._result["difficulty"], self._result["character"], self._rank, name
        )
        self._store.set_last_name(name)  # :1314
        self._replay_name = name  # replayName = curScore.name (:1313)
        self._interrupt_all(2)
        self._state = _ST_STATS_SHOW
        self._frame_timer = 0

    # ---- 总结算面板 (:1697-1726) ----
    def _stats_show(self) -> None:
        if self._frame_timer <= 30:
            self._vms[_VM_STATS].vm.pending_interrupt = 18  # 面板入场 (:1704-1708)
        if self._frame_timer >= 90 and self._confirm_pressed():
            self._vms[_VM_STATS].vm.pending_interrupt = 2
            self._frame_timer = 0
            self._state = _ST_STATS_WAIT

    # ---- 录像保存 (:1342-1694) ----
    def _save_prompt(self) -> None:
        if self._frame_timer == 60:
            # 续关过 → 不可存 (:1362-1365); slow mode 判定本无恒不触发
            interrupt = 14 if self._result["retries"] != 0 else 11
            self._interrupt_all(interrupt)
            if interrupt != 11:
                self._state = _ST_CANNOT_SAVE
            self.cursor = 0
        self._prompt_highlight()  # vms[19]/[20] 亮暗 (:1381-1395)
        if self._frame_timer < 80:
            return
        self._move_cursor_horizontal(2)  # MoveCursorHorizontally (:1400)
        if self._cancel_pressed():
            self._to_exiting()  # SOUND_BACK_AND_RETURN (:1421-1430)
        elif self._confirm_pressed():
            if self.cursor == 0:
                self._sounds.append(SE_SELECT)
                self._state = _ST_SELECT_SLOT
                self._interrupt_all(12)
                self._frame_timer = 0
                self._slot_scan()  # goto 当帧进选槽态, frame 0 扫槽 (:1418/:1451-1471)
            else:
                self._to_exiting()

    def _cannot_save(self) -> None:
        """续关录像不可存提示: 20 帧门后任确认/取消离场 (:1432-1448)。"""
        if self._frame_timer < 20:
            return
        if self._confirm_pressed() or self._cancel_pressed():
            self._to_exiting()

    def _select_slot(self) -> None:
        if self._frame_timer < 20:
            return
        self._move_cursor_vertical(len(self._slots) + 1)  # MoveCursor (:1477)
        if self._confirm_pressed():
            self._sounds.append(SE_SELECT)
            self._chosen = self.cursor
            self._frame_timer = 0
            self._replay_date = datetime.now().strftime("%m/%d")  # GetDate (:1484)
            row_vm = self._vms[_VM_SLOT_ROW + self._chosen].vm
            if self.cursor < len(self._slots):
                self._interrupt_all(13)  # 覆盖确认 (:1499-1509)
                self._state = _ST_OVERWRITE
            else:
                self._interrupt_all(17)  # 空槽直接改名存盘 (:1490-1497)
                self._state = _ST_SAVING
            row_vm.pending_interrupt = 16
            self.cursor = 0
            self._entry = NameEntry.create(self._replay_name, has_lsnm=self._has_lsnm)
        if self._cancel_pressed():
            self._sounds.append(SE_BACK)
            self._state = _ST_SAVE_PROMPT  # :1517-1527
            self._interrupt_all(2)
            self._frame_timer = 0

    def _overwrite(self) -> None:
        self._prompt_highlight()  # :1646-1660
        if self._frame_timer < 20:
            return
        self._move_cursor_horizontal(2)
        if self._cancel_pressed():
            self._back_to_slots()  # :1665-1669
        elif self._confirm_pressed():
            self._frame_timer = 0
            if self.cursor == 0:
                self._interrupt_all(17)
                self._vms[_VM_SLOT_ROW + self._chosen].vm.pending_interrupt = 16
                self._state = _ST_SAVING
            else:
                self._back_to_slots()

    def _saving(self) -> None:
        """录像名输入 (REPLAY_SAVING :1529-1644): 字表同 ENTER_NAME。"""
        if self._frame_timer < 30:
            return
        self._entry_step(self._entry, on_finish=self._save_replay, menu_back=True)

    def _save_replay(self) -> None:
        """END 格: 存盘 + LSNM 更新 + 离场 (:1605-1627)。"""
        name = self._entry.name
        self._store.set_last_name(name)  # :1617
        if self._recorder is not None:
            replay = self._recorder.finish(self._world)
            replay.name = name.strip()
            if self._chosen < len(self._slots):
                path: str | Path = self._slots[self._chosen].path
            else:
                path = new_replay_path(self._replay_dir)
            save_replay(replay, path)
        self._interrupt_all(2)
        self._state = _ST_EXITING
        self._frame_timer = 0

    def _back_to_slots(self) -> None:
        """回选槽态 (LAB_004473e3, :1409-1418)。"""
        self._sounds.append(SE_SELECT)
        self._state = _ST_SELECT_SLOT
        self._interrupt_all(12)
        self._frame_timer = 0
        self._slot_scan()

    def _to_exiting(self) -> None:
        self._sounds.append(SE_BACK)
        self._interrupt_all(2)
        self._state = _ST_EXITING
        self._frame_timer = 0

    def _slot_scan(self) -> None:
        """重扫录像目录(原版 ValidateReplayData 逐槽, :1453-1470); 末位留新槽。"""
        self._slots = list_replays(self._replay_dir)[: _MAX_SLOTS - 1]

    def _prompt_highlight(self) -> None:
        """Yes/No 两项红/灰(保 alpha, :1384-1395)。"""
        for i, vm_idx in enumerate((_VM_PROMPT_YES, _VM_PROMPT_YES + 1)):
            vm = self._vms[vm_idx].vm
            rgb = (
                (255, 96, 96) if i == self.cursor else (96, 96, 96)
            )  # 0xff6060/0x606060
            vm.color = [*rgb, vm.color[3]]

    def _entry_step(
        self,
        entry: NameEntry,
        *,
        on_finish: Callable[[], None],
        menu_back: bool = False,
    ) -> None:
        """字表输入一帧 (WAS_PRESSED_RAW_AND_IS_EIGHTH 全按键, :1204-1300)。

        menu_back=True (REPLAY_SAVING): MENU 键回选槽态 (:1640-1643);
        False (ENTER_NAME): MENU 键 = 完成输入 (:1301-1315)。
        """
        for b in (Button.UP, Button.DOWN, Button.LEFT, Button.RIGHT):
            if self._move_edge(b):
                entry.move(b)
                self._sounds.append(SE_MOVE)
        if self._move_edge(Button.SHOT):  # SELECTMENU
            finished = entry.confirm()
            # END 格: ENTER_NAME 放 SOUND_BACK (:1264-1277 goto), SAVING 放
            # SOUND_SELECT (:1627 不跳); 普通写字两态都 SOUND_SELECT (:1288)
            self._sounds.append(SE_BACK if finished and not menu_back else SE_SELECT)
            if finished:
                on_finish()
                return
        if self._move_edge(Button.BOMB) or self._move_edge(Button.PAUSE):
            # RETURNMENU = MENU|BOMB: Esc 也会先删一字 (:1290-1300)
            entry.delete()
            self._sounds.append(SE_BACK)
        if self._pressed(Button.PAUSE):  # TH_BUTTON_MENU = Esc
            if menu_back:
                self._back_to_slots()  # :1640-1643
            else:
                self._sounds.append(SE_BACK)  # :1304
                on_finish()

    def _interrupt_all(self, n: int) -> None:
        """全 41 台 pendingInterrupt=n(直接赋值, 同 Player Data)。"""
        for w in self._vms:
            w.vm.pending_interrupt = n

    # ---- 绘制(生产函数全在 result_draw.py) ----
    def snapshot(self) -> SceneSnapshot:
        sprites = [
            SpriteDraw(_BG, 320.0, 240.0, z=-1.0)
        ]  # CopySurfaceToBackBuffer (:2188)
        sprites.extend(vm_sprites(self._vms, self._bank))
        texts: list[TextDraw] = []
        panel = self._vms[_VM_PANEL].vm
        if panel.pos[0] < 640:  # 面板滑进屏内才画榜 (:2197)
            texts.extend(
                score_rows(
                    self._store,
                    self._result,
                    self._entry,
                    self._rank,
                    in_enter_name=self._state == _ST_ENTER_NAME,
                    pos=panel.pos,
                )
            )
        if self._state in (_ST_ENTER_NAME, _ST_SAVING):
            sprites.extend(name_grid_sprites(self._entry, self._frame_timer))
        if _ST_SAVE_PROMPT <= self._state <= _ST_OVERWRITE:
            texts.extend(
                slot_rows(  # :2430-2494
                    self._vms,
                    self._slots,
                    self._chosen,
                    self._result,
                    self._entry,
                    self._replay_name,
                    self._replay_date,
                    in_saving=self._state == _ST_SAVING,
                )
            )
        if self._state in (_ST_STATS_SHOW, _ST_STATS_WAIT):
            texts.extend(
                stats_lines(self._vms[_VM_STATS].vm, self._result)
            )  # DrawFinalStats (:2026-2158)
        return SceneSnapshot(self._frame, tuple(sprites), tuple(texts))
