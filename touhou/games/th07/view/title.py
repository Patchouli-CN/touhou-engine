"""标题画面 + 主菜单 + 开局流(难度→机体→装备→开局/Quit)。

状态机/计时/键位照抄 MainMenu.cpp(OnUpdatePreInput/OnUpdateSelectDifficulty/
OnUpdateSelectCharacter/OnUpdateSelectShotType); 画面不手排布局, 直接跑
title01.anm 的 164 台 VM(C++ ExecuteVmsAnms 同构), 贴图动画即原版时序。
"""

from __future__ import annotations

import enum
from collections.abc import Callable

import msgspec

from ....engine import InputFrame, SceneSnapshot
from ....engine.score_store import ScoreStore
from ....schemas.archive import Archive
from .menu_vms import SE_BACK, SE_SELECT, MenuScene, MenuVmSet, description_texts
from .scene import Scene

_BG_TITLE = "title00.jpg"  # MainMenu.cpp:209
_BG_SELECT = "select00.jpg"  # MainMenu.cpp:1115

# 主菜单项(MainMenu.hpp:40-50 MenuCursorPreInput)
_MENU_START = 0
_MENU_EXTRA_START = 1
_MENU_EXIT = 7
_MENU_COUNT = 8

_DIFFICULTY_COUNT = 4  # 本篇难度页项数(MainMenu.cpp:1184)
_CHARACTER_COUNT = 3  # MainMenu.cpp:1454
_SHOT_COUNT = 2  # MainMenu.cpp:1706

# 说明文字(MainMenu.cpp:134-143 g_MainMenuStrings, 原文 i18n.csv TH_MAIN_MENU_*)
_DESCRIPTIONS = (
    "ゲームを開始します",
    "エキストラステージを開始します",
    "ステージを選択し、練習を開始します",
    "リプレイを鑑賞できます",
    "過去のスコアやスペルカードの取得歴を見られます",
    "音楽を聴けます",
    "各種設定できます",
    "いろいろと終了します",
)

# 机体选择页 15 台 VM 的分组: (机体名, 装备A, 装备B, 装备说明A, 装备说明B)
# (MainMenu.cpp:1346-1384 的 vms[71..85] 显隐表)
_CHAR_VMS = ((71, 72, 73, 80, 83), (74, 75, 76, 81, 84), (77, 78, 79, 82, 85))


class MenuState(enum.Enum):
    """菜单态(MainMenu.hpp:8-24; 只取本单用到的, 其余态后续单补)。"""

    PRE_INPUT = 0
    SELECT_DIFFICULTY = 4
    SELECT_CHARACTER = 5
    SELECT_SHOTTYPE = 6


class MenuMemory(msgspec.Struct):
    """跨画面记住的选择(C++ 的 GameManager.character/shotType + cfg.defaultDifficulty)。"""

    character: int = 0
    shot_type: int = 0
    default_difficulty: int = 1  # cfg 缺省 DIFF_NORMAL(Supervisor.cpp:1196)


class StartRequest(msgspec.Struct, frozen=True):
    """开局流走完交给装配处的开局参数。"""

    character: int  # shotType 0..5 = 机体*2 + 装备
    difficulty: int


class TitleScene(MenuScene):
    """标题/主菜单/选择画面: PRE_INPUT → 难度 → 机体 → 装备 → 开局或 Quit。

    submenus: 主菜单项 → scene 工厂(吃当前 TitleScene, 取共享 VM 阵列用);
    已接 Option/MusicRoom; Extra/Practice/Replay/Result 后续单
    往这个表里挂(空项按下无反应)。
    """

    def __init__(
        self,
        archive: Archive | None,
        store: ScoreStore,
        memory: MenuMemory,
        *,
        anm_version: int = 2,
        on_start: Callable[[StartRequest], Scene] | None = None,
        submenus: dict[int, Callable[[TitleScene], Scene]] | None = None,
        vm_set: MenuVmSet | None = None,
        cursor: int = 0,
    ) -> None:
        super().__init__()
        self._archive = archive
        self._store = store
        self.memory = memory
        self._anm_version = anm_version
        self._on_start = on_start
        self._submenus = submenus if submenus is not None else {}
        self.start_request: StartRequest | None = None
        self._next: Scene | None = None
        # 状态机账本(MainMenu.hpp:152-160 SetMenuState)
        self._state = MenuState.PRE_INPUT
        self._prev_state = MenuState.PRE_INPUT
        self._substate = 0  # 0=INIT 1=INPUT 2=EXIT 3=离场延迟(MainMenu.cpp:1263)
        self.cursor = cursor
        self._selected = -1
        self._input_delay = 0
        self._state_timer = 0
        self._idle_frames = 0
        self._demo_frames = 0
        self._frame = 0
        self._vm_set = vm_set
        self._background = _BG_TITLE

    @property
    def menu_vms(self) -> MenuVmSet:
        """共享 VM 阵列(未注入时懒建; Option 等子画面经此与主菜单共用)。"""
        if self._vm_set is None:
            self._vm_set = MenuVmSet(self._archive, self._anm_version)
        return self._vm_set

    # ---- Scene 接口 ----
    def on_enter(self) -> None:
        """建 VM 阵列(标题 BGM 起播点: LoadAudio(8, th07_01.mid), BGM 链留待)。"""
        self.menu_vms  # 触发懒建(进画面前把 VM 阵列备好)

    def step(self, inp: InputFrame) -> None:
        self._update_input(inp)
        if self._state is MenuState.PRE_INPUT:
            self._update_pre_input()
        elif self._state is MenuState.SELECT_DIFFICULTY:
            self._update_select_difficulty()
        elif self._state is MenuState.SELECT_CHARACTER:
            self._update_select_character()
        else:
            self._update_select_shot_type()
        self.menu_vms.execute()
        self._frame += 1

    def snapshot(self) -> SceneSnapshot:
        sprites = self.menu_vms.sprites(self._background)
        texts = description_texts(self.menu_vms.cur_desc, _DESCRIPTIONS[self.cursor])
        return SceneSnapshot(self._frame, tuple(sprites), texts)

    def next_scene(self) -> Scene | None:
        if self.start_request is not None and self._on_start is not None:
            return self._on_start(self.start_request)
        return self._next

    # ---- 主菜单 (MainMenu.cpp:192-472 OnUpdatePreInput) ----
    def _update_pre_input(self) -> None:
        mv = self.menu_vms
        if self._substate == 0:  # MENU_SUBSTATE_PREINPUT_INIT
            # 从选择页回来才换标题背景(:204-212; REPLAY/PRACTICE/EXTRA 来源后续单补)
            if self._prev_state in (MenuState.PRE_INPUT, MenuState.SELECT_DIFFICULTY):
                self._background = _BG_TITLE
            mv.interrupt_all(2)  # :219
            mv.highlight(1, _MENU_COUNT, self.cursor)  # 菜单 8 项 = vms[1..8]
            self._selected = -1
            self._substate = 1
            self._demo_frames = 0
            # isPracticeMode/replay 直跳分支(:233-257)属 Practice/Replay 单
            # C++ INIT 落空直接落进 INPUT 同帧执行
        if self._substate == 1:  # MENU_SUBSTATE_PREINPUT_INPUT
            moved = self._move_cursor_vertical(_MENU_COUNT)
            if moved:
                while not self._extra_unlocked and self.cursor == _MENU_EXTRA_START:
                    self.cursor += moved  # Extra Start 未解锁直接滑过(:266-271)
                mv.highlight(1, _MENU_COUNT, self.cursor)
            self._demo_frames += 1
            if self._inp.held:
                self._demo_frames = 0
            if self._demo_frames > 900:
                # demo 播放(data/demo/demorpyN.rpy)留待 Replay 单(MainMenu.cpp:286-322)
                self._demo_frames = 0
            if self._selected != self.cursor:
                mv.cur_desc = mv.desc_vms[self.cursor]
                mv.cur_desc.pending_interrupt = 1
            self._selected = self.cursor
            if self._state_timer >= 10:  # :330-333 进场 10 帧不吃确认/取消
                if self._confirm_pressed():
                    self._sounds.append(SE_SELECT)
                    if self._confirm_main_menu():
                        return  # C++ confirm 转移早退, 本帧不计时(:355 等)
                if self._cancel_pressed():
                    self.cursor = _MENU_EXIT  # RETURNMENU 光标跳 Exit(:427-438)
                    mv.highlight(1, _MENU_COUNT, self.cursor)
                    self._sounds.append(SE_BACK)
        elif self._substate == 2:  # MENU_SUBSTATE_PREINPUT_EXIT
            if self._input_delay >= 60:  # :441-451 离场动画 60 帧后退出
                self.done = True
                return
        self._idle_frames += 1
        self._input_delay += 1
        self._state_timer += 1

    def _confirm_main_menu(self) -> bool:
        """主菜单 confirm 分派(:338-425); 返回 True = C++ 当帧早退(不递增计时)。"""
        mv = self.menu_vms
        cursor = self.cursor
        if cursor == _MENU_START:
            self._set_menu_state(MenuState.SELECT_DIFFICULTY)
            mv.interrupt_all(5)  # :353
            if mv.cur_desc is not None:
                mv.cur_desc.pending_interrupt = 2
            return True
        if cursor == _MENU_EXIT:
            self._substate = 2  # :416-419 离场动画后退出
            self._input_delay = 0
            mv.interrupt_all(1)
            return False
        factory = self._submenus.get(cursor)
        if factory is None:
            return False  # Extra/Practice/Replay/Result 留待后续单
        if mv.cur_desc is not None:
            mv.cur_desc.pending_interrupt = 2
        self._next = factory(self)
        self.done = True
        return True

    @property
    def _extra_unlocked(self) -> bool:
        """全 6 机体各有任一主难度通关(GameManager.cpp:1000-1010)。

        C++ 读 difficultyClearedWithRetries(ZUN 字段名写反, 无续关通关才记),
        通关标记==99 ↔ 本库该难度通过面数>=6。
        """
        for c in self._store.clrd:
            if not any(v >= 6 for v in c["with_retries"][:4]):
                return False
        return True

    # ---- 难度选择 (MainMenu.cpp:1101-1291) ----
    def _update_select_difficulty(self) -> None:
        mv = self.menu_vms
        if self._substate == 0:  # MENU_SUBSTATE_SELECT_INIT
            if self._state_timer == 0:
                if self._prev_state is not MenuState.SELECT_CHARACTER:
                    self._background = _BG_SELECT  # :1112-1119 从机体页回来不换
                self.cursor = self.memory.default_difficulty
                mv.interrupt_all(7)  # :1123
                if self.cursor >= 4:
                    self.cursor = 1  # cfg 停在 Extra/Phantasm 时回 Normal(:1136-1139)
                mv.highlight(67, _DIFFICULTY_COUNT, self.cursor)  # vms[67..70]
                self._input_delay = 0
                mv.cur_desc = None  # :1169 选择页没有说明文字
            if self._state_timer == 30:  # 滑入 30 帧后才吃输入(:1177-1180)
                self._substate = 1
        elif self._substate == 1:  # MENU_SUBSTATE_SELECT_INPUT
            if self._move_cursor_vertical(_DIFFICULTY_COUNT):
                mv.highlight(67, _DIFFICULTY_COUNT, self.cursor)
            if self._confirm_pressed():
                self.memory.default_difficulty = self.cursor  # cfg.defaultDifficulty
                self._sounds.append(SE_SELECT)
                self._set_menu_state(MenuState.SELECT_CHARACTER)
                self.cursor = 0
                return
            if self._cancel_pressed():
                self.memory.default_difficulty = self.cursor  # :1250 取消也记难度
                self._sounds.append(SE_BACK)
                self._substate = 3
                self._input_delay = 0
                mv.interrupt_all(6)  # :1260
        elif self._substate == 3:  # 离场 30 帧回主菜单(:1263-1285)
            if self._input_delay >= 30:
                self._set_menu_state(MenuState.PRE_INPUT)
                self.cursor = _MENU_START
                return
        self._input_delay += 1
        self._idle_frames += 1
        self._state_timer += 1

    # ---- 机体选择 (MainMenu.cpp:1294-1586) ----
    def _update_select_character(self) -> None:
        mv = self.menu_vms
        if self._substate == 0:
            if self._state_timer == 0:
                mv.interrupt_all(8)  # :1301
                d = self.memory.default_difficulty
                if d < 4:
                    mv.vms[d + 67].vm.pending_interrupt = 9  # 难度回闪(:1302-1306)
                self.cursor = self.memory.character  # :1319 记得上次机体
                self._char_select_enter()
                self._input_delay = 0
            if self._state_timer == 30:
                self._substate = 1
        elif self._substate == 1:
            if self._move_cursor_horizontal(_CHARACTER_COUNT):
                self._char_select_move()
            if self._confirm_pressed():
                self.memory.character = self.cursor  # g_GameManager.character (:1536)
                self._sounds.append(SE_SELECT)
                self._set_menu_state(MenuState.SELECT_SHOTTYPE)
                self.cursor = 0
                return
            if self._cancel_pressed():
                self._sounds.append(SE_BACK)
                self.memory.character = self.cursor  # :1561 取消也记机体
                self._set_menu_state(MenuState.SELECT_DIFFICULTY)
                self.cursor = 0  # :1577(INIT 会按 defaultDifficulty 重设)
                return
        self._idle_frames += 1
        self._input_delay += 1
        self._state_timer += 1

    def _char_select_enter(self) -> None:
        """进机体页: 只显当前机体五件套, 其余暗名 alpha=0(:1346-1438)。"""
        vms = self.menu_vms.vms
        for idx in range(71, 86):
            vms[idx].active = False
        for idx in _CHAR_VMS[self.cursor]:
            vms[idx].active = True
        for g in range(3):
            sel = g == self.cursor
            for idx in (_CHAR_VMS[g][0], _CHAR_VMS[g][3], _CHAR_VMS[g][4]):
                vms[idx].vm.pending_interrupt = 9 if sel else 8
                if not sel:
                    vms[idx].vm.color[3] = 0

    def _char_select_move(self) -> None:
        """移动: 15 台全亮, 名/说明按选中发 9/8 号 interrupt(:1482-1531)。"""
        vms = self.menu_vms.vms
        for idx in range(71, 86):
            vms[idx].active = True
        for g in range(3):
            sel = g == self.cursor
            for idx in (_CHAR_VMS[g][0], _CHAR_VMS[g][3], _CHAR_VMS[g][4]):
                vms[idx].vm.pending_interrupt = 9 if sel else 8

    # ---- 装备选择 (MainMenu.cpp:1589-1829) ----
    def _update_select_shot_type(self) -> None:
        mv = self.menu_vms
        if self._substate == 0:
            if self._state_timer == 0:
                mv.interrupt_all(10)  # :1596
                d = self.memory.default_difficulty
                if d < 4:
                    mv.vms[d + 67].vm.pending_interrupt = 9  # :1597-1601
                for idx in range(71, 86):
                    mv.vms[idx].active = False  # :1614-1628
                self.cursor = self.memory.shot_type  # g_GameManager.shotType (:1629)
                name, shot_a, shot_b = _CHAR_VMS[self.memory.character][:3]
                mv.vms[name].active = True  # 只显当前机体名 + A/B (:1654-1689)
                mv.vms[shot_a].active = True
                mv.vms[shot_b].active = True
                self._highlight_shot()
                self._input_delay = 0
            if self._state_timer == 30:
                self._substate = 1
        elif self._substate == 1:
            if self._move_cursor_vertical(_SHOT_COUNT):
                self._highlight_shot()
            if self._confirm_pressed():
                self.memory.shot_type = self.cursor  # :1762
                self._sounds.append(SE_SELECT)
                # 开局(:1765-1781): difficulty=cfg, currentStage=DUMMYSTAGE(=一面)
                # 标题 BGM 停止点(:1778 StopAudio, BGM 链留待)
                self.start_request = StartRequest(
                    character=self.memory.character * 2 + self.memory.shot_type,
                    difficulty=self.memory.default_difficulty,
                )
                self.done = True
                return
            if self._cancel_pressed():
                self._sounds.append(SE_BACK)
                self.memory.shot_type = self.cursor  # :1790 取消也记装备
                self._set_menu_state(MenuState.SELECT_CHARACTER)
                for idx in range(71, 86):
                    mv.vms[idx].active = True  # :1806-1820
                return
        self._idle_frames += 1
        self._input_delay += 1
        self._state_timer += 1

    def _highlight_shot(self) -> None:
        """A/B 高亮: 选中 base(亮), 未选 base+1(暗)(:1660-1665 模式)。"""
        _, shot_a, shot_b = _CHAR_VMS[self.memory.character][:3]
        shots = (shot_a, shot_b)
        mv = self.menu_vms
        mv.set_sprite(shots[1 - self.cursor], dim=True)
        mv.set_sprite(shots[self.cursor], dim=False)

    def _set_menu_state(self, state: MenuState) -> None:
        """SetMenuState (MainMenu.hpp:152-160)。"""
        self._prev_state = self._state
        self._state = state
        self._input_delay = 0
        self._state_timer = 0
        self._substate = 0
        self._idle_frames = 0
