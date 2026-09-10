"""标题画面 + 主菜单 + 开局流(本篇/Practice/Extra: 难度→机体→装备→(选面)→开局/Quit)。

状态机/计时/键位照抄 MainMenu.cpp(OnUpdatePreInput/OnUpdateSelectDifficulty/
OnUpdateSelectCharacter/OnUpdateSelectShotType/OnUpdateSelectPracticeStage);
画面不手排布局, 直接跑 title01.anm 的 164 台 VM(C++ ExecuteVmsAnms 同构),
贴图动画即原版时序。
"""

from __future__ import annotations

import enum
from collections.abc import Callable

import msgspec

from ....engine import InputFrame, SceneSnapshot, TextDraw
from ....engine.score_store import ScoreStore
from ....schemas.archive import Archive
from ..results import practice_pscr_key
from .menu_vms import SE_BACK, SE_SELECT, MenuScene, MenuVmSet, description_texts
from .scene import Scene

_BG_TITLE = "title00.jpg"  # MainMenu.cpp:209
_BG_SELECT = "select00.jpg"  # MainMenu.cpp:1115

# 主菜单项(MainMenu.hpp:40-50 MenuCursorPreInput)
_MENU_START = 0
_MENU_EXTRA_START = 1
_MENU_PRACTICE_START = 2
_MENU_EXIT = 7
_MENU_COUNT = 8

_DIFFICULTY_COUNT = 4  # 本篇难度页项数(MainMenu.cpp:1184)
_EXTRA_DIFFICULTY_VMS = 162  # Extra 难度页项 = vms[162..163](:1157-1165)
_PHANTASM_INDICATOR_VM = 161  # Phantasm 未解锁时 Extra 系页的难度指示(:1309-1312)
_CHARACTER_COUNT = 3  # MainMenu.cpp:1454
_SHOT_COUNT = 2  # MainMenu.cpp:1706

# 练习选面页文字(MainMenu.cpp:34-40 g_StagePracticeStrings / :2348-2404 DrawPracticeMenu)
_PRACTICE_STAGE_NAMES = tuple(f"Stage{i}" for i in range(1, 7))
_PRACTICE_HEADER_VM = 131  # 表头/行位置锚(:2357-2362)
_PRACTICE_COLORS = ((255, 255, 255, 255), (160, 160, 160, 255), (64, 64, 64, 255))
_PRACTICE_TEXT_SIZE = 15


def _ascii_text(text: str, x: float, y: float, rgba: tuple[int, int, int, int]):
    """Ascii 文字 + 黑影(原版字库烘焙描边近似, 同 Player Data 页)。"""
    return (
        TextDraw(text, x + 1, y + 1, _PRACTICE_TEXT_SIZE, (0, 0, 0, rgba[3])),
        TextDraw(text, x, y, _PRACTICE_TEXT_SIZE, rgba),
    )


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
    """菜单态(MainMenu.hpp:8-24; Replay/Option/KeyConfig 态在各自 scene)。"""

    PRE_INPUT = 0
    SELECT_DIFFICULTY = 4
    SELECT_CHARACTER = 5
    SELECT_SHOTTYPE = 6
    PRACTICE_SELECT_DIFFICULTY = 8
    PRACTICE_SELECT_CHARACTER = 9
    PRACTICE_SELECT_SHOTTYPE = 10
    SELECT_PRACTICE_STAGE = 11
    EXTRA_SELECT_DIFFICULTY = 12
    EXTRA_SELECT_CHARACTER = 13
    EXTRA_SELECT_SHOTTYPE = 14


# 三族选择态(MainMenu.cpp:150-181 的 case 分组)
_DIFFICULTY_STATES = frozenset(
    {
        MenuState.SELECT_DIFFICULTY,
        MenuState.PRACTICE_SELECT_DIFFICULTY,
        MenuState.EXTRA_SELECT_DIFFICULTY,
    }
)
_CHARACTER_STATES = frozenset(
    {
        MenuState.SELECT_CHARACTER,
        MenuState.PRACTICE_SELECT_CHARACTER,
        MenuState.EXTRA_SELECT_CHARACTER,
    }
)
_EXTRA_STATES = frozenset(
    {
        MenuState.EXTRA_SELECT_DIFFICULTY,
        MenuState.EXTRA_SELECT_CHARACTER,
        MenuState.EXTRA_SELECT_SHOTTYPE,
    }
)


class MenuMemory(msgspec.Struct):
    """跨画面记住的选择(C++ 的 GameManager.character/shotType/currentStage + cfg.defaultDifficulty)。"""

    character: int = 0
    shot_type: int = 0
    default_difficulty: int = 1  # cfg 缺省 DIFF_NORMAL(Supervisor.cpp:1196)
    practice_stage: int = (
        1  # 最近练习的面(1-based; C++ currentStage, 回标题直跳选面页用)
    )


class StartRequest(msgspec.Struct, frozen=True):
    """开局流走完交给装配处的开局参数。"""

    character: int  # shotType 0..5 = 机体*2 + 装备
    difficulty: int
    stage_no: int = 1  # 1-based; Extra=7 Phantasm=8(:1774 difficulty+2 是 0-based)
    practice: bool = False


class TitleScene(MenuScene):
    """标题/主菜单/选择画面: PRE_INPUT → 难度 → 机体 → 装备 → (练习选面) → 开局或 Quit。

    submenus: 主菜单项 → scene 工厂(吃当前 TitleScene, 取共享 VM 阵列用);
    已接 Replay/PlayerData/MusicRoom/Option(空项按下无反应)。
    practice_mode: 练习对局结束回标题时置真 = C++ isPracticeMode
    (MainMenu.cpp:2637-2643), 主菜单 INIT 直跳练习选择链, 落到选面页。
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
        practice_mode: bool = False,
        spellcard_count: int = 0,
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
        self._practice = False  # g_GameManager.practice  analog(GameManager.hpp:263)
        self._is_practice_mode = practice_mode
        # Phantasm 解锁判定的符卡张数口径(C++ SPELLCARD_COUNT; 0 = 按库存)
        self._spellcard_count = spellcard_count

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
        # 分派(MainMenu.cpp:150-181): 本篇/Practice/Extra 三族共用三个选择函数
        if self._state is MenuState.PRE_INPUT:
            self._update_pre_input()
        elif self._state is MenuState.SELECT_PRACTICE_STAGE:
            self._update_select_practice_stage()
        elif self._state in _DIFFICULTY_STATES:
            self._update_select_difficulty()
        elif self._state in _CHARACTER_STATES:
            self._update_select_character()
        else:
            self._update_select_shot_type()
        self.menu_vms.execute()
        self._frame += 1

    def snapshot(self) -> SceneSnapshot:
        sprites = self.menu_vms.sprites(self._background)
        texts = description_texts(self.menu_vms.cur_desc, _DESCRIPTIONS[self.cursor])
        if self._state is MenuState.SELECT_PRACTICE_STAGE:
            texts += self._practice_menu_texts()  # OnDraw 只有该态加画(:2489-2491)
        return SceneSnapshot(self._frame, tuple(sprites), texts)

    def next_scene(self) -> Scene | None:
        if self.start_request is not None and self._on_start is not None:
            return self._on_start(self.start_request)
        return self._next

    # ---- 主菜单 (MainMenu.cpp:192-472 OnUpdatePreInput) ----
    def _update_pre_input(self) -> None:
        mv = self.menu_vms
        if self._substate == 0:  # MENU_SUBSTATE_PREINPUT_INIT
            # 从选择页回来才换标题背景(:204-212; REPLAY 来源态留待 Replay 单)
            if self._prev_state in (
                MenuState.PRE_INPUT,
                MenuState.SELECT_DIFFICULTY,
                MenuState.PRACTICE_SELECT_DIFFICULTY,
                MenuState.EXTRA_SELECT_DIFFICULTY,
            ):
                self._background = _BG_TITLE
            mv.interrupt_all(2)  # :219
            mv.highlight(1, _MENU_COUNT, self.cursor)  # 菜单 8 项 = vms[1..8]
            self._selected = -1
            self._substate = 1
            self._demo_frames = 0
            # replay 直跳分支(:233-245 对局/回放回来 g_GameManager.replay=1 时
            # 主菜单 INIT 直跳 SELECT_REPLAY): 本作由回放 scene 出口直接回列表
            if self._is_practice_mode:
                # 练习对局回来: 直跳练习难度页, 沿选择链落到选面页(:246-257)
                self._set_menu_state(MenuState.PRACTICE_SELECT_DIFFICULTY)
                mv.interrupt_all(5)
                if mv.cur_desc is not None:
                    mv.cur_desc.pending_interrupt = 2
                return
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
                # demo 播放(MainMenu.cpp:286-322): 原版播 data/demo/demorpyN.rpy
                # (原版二进制格式, 与本引擎 sim 不兼容), 不接, 只重置计数
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
            self._practice = False  # :341
            self._set_menu_state(MenuState.SELECT_DIFFICULTY)
            mv.interrupt_all(5)  # :353
            if mv.cur_desc is not None:
                mv.cur_desc.pending_interrupt = 2
            return True
        if cursor == _MENU_EXTRA_START:
            if not self._extra_unlocked:
                # 未解锁 confirm 落空跌进 REPLAY case(:386-387 无 break);
                # 光标停不上来实际不可达, 按无反应处理
                return False
            self._practice = False  # :375
            self.cursor = int(self.memory.default_difficulty == 5)  # :376
            self._set_menu_state(MenuState.EXTRA_SELECT_DIFFICULTY)
            mv.interrupt_all(5)
            if mv.cur_desc is not None:
                mv.cur_desc.pending_interrupt = 2
            return True
        if cursor == _MENU_PRACTICE_START:
            self._practice = True  # :357
            self.cursor = self.memory.default_difficulty  # :358-362
            if self.cursor >= 4:
                self.cursor = 2
            self._set_menu_state(MenuState.PRACTICE_SELECT_DIFFICULTY)
            mv.interrupt_all(5)
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
            return False  # 未接项按下无反应
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

    def _has_max_clears(self, shot: int) -> bool:
        """该机体任一主难度无续关通关(HasReachedMaxClears, GameManager.cpp:970-978)。"""
        return any(v >= 6 for v in self._store.clrd[shot]["with_retries"][:4])

    def _has_unlocked_phantom(self, shot: int) -> bool:
        """该机体 Phantasm 解锁(HasUnlockedPhantom, GameManager.cpp:981-997)。

        C++ 就地把 clrd[shot][5] 写成 99, 这里纯查询: >=60 张捕获(合计槽)
        + 该机体 Extra 无续关通关(with_retries[4]>=7), 或已有 Phantasm 记录。
        """
        c = self._store.clrd[shot]["with_retries"]
        if c[5] >= 8:
            return True
        return self._captured_total() >= 60 and c[4] >= 7

    def _captured_total(self) -> int:
        """捕获张数(合计槽 successes 非零计数; 口径 SPELLCARD_COUNT=作品表)。"""
        total = self._store.catk_slot_count - 1
        n = self._spellcard_count or len(self._store.catk)
        return sum(1 for e in self._store.catk[:n] if e["successes"][total] > 0)

    @property
    def _phantasm_unlocked(self) -> bool:
        """任一机体 Phantasm 解锁(HasUnlockedPhantomAndMaxClears, GameManager.cpp:1014-1049)。"""
        return any(self._has_unlocked_phantom(shot) for shot in range(6))

    # ---- 难度选择 (MainMenu.cpp:1101-1291) ----
    def _update_select_difficulty(self) -> None:
        mv = self.menu_vms
        extra = self._state is MenuState.EXTRA_SELECT_DIFFICULTY
        if self._substate == 0:  # MENU_SUBSTATE_SELECT_INIT
            if self._state_timer == 0:
                if self._prev_state not in _CHARACTER_STATES:
                    self._background = _BG_SELECT  # :1112-1119 从机体页回来不换
                self.cursor = self.memory.default_difficulty  # :1120
                if not extra:
                    mv.interrupt_all(7)  # :1123
                    if self.cursor >= 4:
                        self.cursor = (
                            1  # cfg 停在 Extra/Phantasm 时回 Normal(:1136-1139)
                        )
                    mv.highlight(67, _DIFFICULTY_COUNT, self.cursor)  # vms[67..70]
                else:
                    if not self._phantasm_unlocked:
                        mv.interrupt_all(12)  # :1127 只亮 Extra 一项
                        self.cursor = 4  # MENU_CURSOR_SELECTDIFFICULTY_EXTRA
                    else:
                        mv.interrupt_all(22)  # :1132 Extra + Phantasm 两项
                    self.cursor = max(0, self.cursor - 4)  # :1152-1156
                    mv.highlight(_EXTRA_DIFFICULTY_VMS, 2, self.cursor)  # vms[162..163]
                self._input_delay = 0
                mv.cur_desc = None  # :1169 选择页没有说明文字
            if self._is_practice_mode:
                # 练习直跳链: 难度页不停, 落机体页(:1171-1176)
                self._set_menu_state(MenuState.PRACTICE_SELECT_CHARACTER)
                self.cursor = 0
                return
            if self._state_timer == 30:  # 滑入 30 帧后才吃输入(:1177-1180)
                self._substate = 1
        elif self._substate == 1:  # MENU_SUBSTATE_SELECT_INPUT
            num = (
                (2 if self._phantasm_unlocked else 1) if extra else _DIFFICULTY_COUNT
            )  # :1183-1187
            if self._move_cursor_vertical(num):
                if not extra:
                    mv.highlight(67, _DIFFICULTY_COUNT, self.cursor)
                elif num == 2:
                    mv.highlight(_EXTRA_DIFFICULTY_VMS, 2, self.cursor)
            if self._confirm_pressed():
                # cfg.defaultDifficulty(:1219/1223); Extra 页存 cursor+4
                self.memory.default_difficulty = (
                    self.cursor + 4 if extra else self.cursor
                )
                self._sounds.append(SE_SELECT)
                if extra:
                    self._set_menu_state(MenuState.EXTRA_SELECT_CHARACTER)
                elif self._practice:
                    self._set_menu_state(MenuState.PRACTICE_SELECT_CHARACTER)
                else:
                    self._set_menu_state(MenuState.SELECT_CHARACTER)
                self.cursor = 0
                return
            if self._cancel_pressed():
                self.memory.default_difficulty = (  # :1250/1254 取消也记难度
                    self.cursor + 4 if extra else self.cursor
                )
                self._sounds.append(SE_BACK)
                self._substate = 3
                self._input_delay = 0
                mv.interrupt_all(6)  # :1260
        elif self._substate == 3:  # 离场 30 帧回主菜单(:1263-1285)
            if self._input_delay >= 30:
                from_extra = self._state is MenuState.EXTRA_SELECT_DIFFICULTY
                self._set_menu_state(MenuState.PRE_INPUT)
                if from_extra:
                    self.cursor = _MENU_EXTRA_START
                elif self._practice:
                    self.cursor = _MENU_PRACTICE_START
                else:
                    self.cursor = _MENU_START
                self._practice = False  # :1283
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
                self._flash_difficulty_indicator()
                self.cursor = self.memory.character  # :1319 记得上次机体
                self._filter_character_cursor()  # Extra/Phantasm 未解锁机体滑过(:1320-1345)
                self._char_select_enter()
                self._input_delay = 0
            if self._is_practice_mode:
                # 练习直跳链: 机体页不停, 落装备页(:1442-1447)
                self._set_menu_state(MenuState.PRACTICE_SELECT_SHOTTYPE)
                self.cursor = 0
                return
            if self._state_timer == 30:
                self._substate = 1
        elif self._substate == 1:
            if self._move_cursor_horizontal(_CHARACTER_COUNT):
                self._filter_character_cursor()  # :1456-1481
                self._char_select_move()
            if self._confirm_pressed():
                self.memory.character = self.cursor  # g_GameManager.character (:1536)
                self._sounds.append(SE_SELECT)
                self._set_menu_state(
                    self._mode_state(
                        MenuState.SELECT_SHOTTYPE,
                        MenuState.PRACTICE_SELECT_SHOTTYPE,
                        MenuState.EXTRA_SELECT_SHOTTYPE,
                    )
                )
                self.cursor = 0
                return
            if self._cancel_pressed():
                self._sounds.append(SE_BACK)
                self.memory.character = self.cursor  # :1561 取消也记机体
                self._set_menu_state(
                    self._mode_state(
                        MenuState.SELECT_DIFFICULTY,
                        MenuState.PRACTICE_SELECT_DIFFICULTY,
                        MenuState.EXTRA_SELECT_DIFFICULTY,
                    )
                )
                self.cursor = 0  # :1577(INIT 会按 defaultDifficulty 重设)
                return
        self._idle_frames += 1
        self._input_delay += 1
        self._state_timer += 1

    def _mode_state(
        self, normal: MenuState, practice: MenuState, extra: MenuState
    ) -> MenuState:
        """本篇/Practice/Extra 三向分派(:1539-1553/:1791-1805: extra 看态, practice 看标记)。"""
        if self._state in _EXTRA_STATES:
            return extra
        if self._practice:
            return practice
        return normal

    def _flash_difficulty_indicator(self) -> None:
        """机体/装备页顶部的难度回闪(:1302-1317/:1597-1612)。"""
        mv = self.menu_vms
        d = self.memory.default_difficulty
        if d < 4:
            mv.vms[d + 67].vm.pending_interrupt = 9
        elif not self._phantasm_unlocked:
            mv.vms[_PHANTASM_INDICATOR_VM].vm.pending_interrupt = 9
        else:
            mv.vms[d + 158].vm.pending_interrupt = 9  # d=4→162, d=5→163

    def _filter_character_cursor(self) -> None:
        """Extra/Phantasm 未解锁机体直接滑过(:1320-1345/:1456-1481)。"""
        d = self.memory.default_difficulty
        if d == 4:
            while not (
                self._has_max_clears(self.cursor * 2)
                or self._has_max_clears(self.cursor * 2 + 1)
            ):
                self.cursor = (self.cursor + 1) % _CHARACTER_COUNT
        elif d == 5:
            while not (
                self._has_unlocked_phantom(self.cursor * 2)
                or self._has_unlocked_phantom(self.cursor * 2 + 1)
            ):
                self.cursor = (self.cursor + 1) % _CHARACTER_COUNT

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
                self._flash_difficulty_indicator()
                for idx in range(71, 86):
                    mv.vms[idx].active = False  # :1614-1628
                self.cursor = self.memory.shot_type  # g_GameManager.shotType (:1629)
                self._filter_shot_cursor()  # Extra/Phantasm 未解锁装备滑过(:1630-1653)
                name, shot_a, shot_b = _CHAR_VMS[self.memory.character][:3]
                mv.vms[name].active = True  # 只显当前机体名 + A/B (:1654-1689)
                mv.vms[shot_a].active = True
                mv.vms[shot_b].active = True
                self._highlight_shot()
                self._input_delay = 0
            if self._is_practice_mode:
                # 练习直跳链终点: 落选面页, 光标停在最近练习的面(:1693-1699)
                self._set_menu_state(MenuState.SELECT_PRACTICE_STAGE)
                self._is_practice_mode = False
                self.cursor = self.memory.practice_stage - 1
                return
            if self._state_timer == 30:
                self._substate = 1
        elif self._substate == 1:
            if self._move_cursor_vertical(_SHOT_COUNT):
                self._filter_shot_cursor()  # :1708-1731
                self._highlight_shot()
            if self._confirm_pressed():
                self.memory.shot_type = self.cursor  # :1762
                self._sounds.append(SE_SELECT)
                if self._practice:
                    # 练习: 落选面页(:1783-1785; C++ EXECUTE_AGAIN 当帧跑,
                    # 这里与既有取消路径一致次帧跑)
                    self.cursor = 0
                    self._set_menu_state(MenuState.SELECT_PRACTICE_STAGE)
                    return
                # 开局(:1765-1781): difficulty=cfg; 本篇 currentStage=DUMMYSTAGE(=一面),
                # Extra/Phantasm currentStage=difficulty+2(0-based)=7/8 面
                # 标题 BGM 停止点(:1778 StopAudio, BGM 链留待)
                d = self.memory.default_difficulty
                self.start_request = StartRequest(
                    character=self.memory.character * 2 + self.memory.shot_type,
                    difficulty=d,
                    stage_no=d + 3 if d >= 4 else 1,
                )
                self.done = True
                return
            if self._cancel_pressed():
                self._sounds.append(SE_BACK)
                self.memory.shot_type = self.cursor  # :1790 取消也记装备
                self._set_menu_state(
                    self._mode_state(
                        MenuState.SELECT_CHARACTER,
                        MenuState.PRACTICE_SELECT_CHARACTER,
                        MenuState.EXTRA_SELECT_CHARACTER,
                    )
                )
                for idx in range(71, 86):
                    mv.vms[idx].active = True  # :1806-1820
                return
        self._idle_frames += 1
        self._input_delay += 1
        self._state_timer += 1

    def _filter_shot_cursor(self) -> None:
        """Extra/Phantasm 未解锁装备直接滑过(:1630-1653/:1708-1731)。"""
        d = self.memory.default_difficulty
        shot = self.memory.character * 2
        if d == 4:
            while not self._has_max_clears(shot + self.cursor):
                self.cursor = (self.cursor + 1) % _SHOT_COUNT
        elif d == 5:
            while not self._has_unlocked_phantom(shot + self.cursor):
                self.cursor = (self.cursor + 1) % _SHOT_COUNT

    # ---- 练习选面 (MainMenu.cpp:1832-1943 OnUpdateSelectPracticeStage) ----
    def _update_select_practice_stage(self) -> None:
        mv = self.menu_vms
        if self._substate == 0:
            if self._state_timer == 0:
                mv.interrupt_all(18)  # :1841
                for idx in range(71, 86):
                    mv.vms[idx].active = False  # :1842-1856
                name, shot_a, shot_b = _CHAR_VMS[self.memory.character][:3]
                mv.vms[name].active = True  # 只显当前机体名 + A/B (:1857-1874)
                mv.vms[shot_a].active = True
                mv.vms[shot_b].active = True
                self._input_delay = 0
                self._practice = True  # :1877
            if self._state_timer == 30:
                self._substate = 1
        elif self._substate == 1:
            allowed = self._practice_stages_unlocked()  # :1885-1895
            if self.cursor >= allowed:
                self.cursor = 0  # :1896-1899
            self._move_cursor_vertical(allowed)
            if self._confirm_pressed():
                # 开局(:1901-1913): difficulty=cfg, currentStage=cursor(0-based)
                self._sounds.append(SE_SELECT)
                self.memory.practice_stage = self.cursor + 1
                self.start_request = StartRequest(
                    character=self.memory.character * 2 + self.memory.shot_type,
                    difficulty=self.memory.default_difficulty,
                    stage_no=self.cursor + 1,
                    practice=True,
                )
                self.done = True
                return
            if self._cancel_pressed():
                self._sounds.append(SE_BACK)
                self.cursor = self.memory.shot_type  # :1918
                # :1919 指 NORMAL_SELECT_SHOTTYPE; practice 标记还在, 行为等价
                self._set_menu_state(MenuState.PRACTICE_SELECT_SHOTTYPE)
                for idx in range(71, 86):
                    mv.vms[idx].active = True  # :1920-1934
                return
        self._idle_frames += 1
        self._input_delay += 1
        self._state_timer += 1

    def _practice_stages_unlocked(self) -> int:
        """可选面数(:1885-1895): clrd[机体].without_retries[难度](=到达面数)。

        C++ 通关标记 99 ↔ 本库 >=6; 下限 1(v=0 时 C++ MoveCursorVertical(0)
        光标卡 0, 实际只能选 Stage1)。
        """
        v = self._store.clrd[self.memory.character * 2 + self.memory.shot_type][
            "without_retries"
        ][self.memory.default_difficulty]
        if v >= 6:
            return 6
        return max(1, v)

    def _practice_menu_texts(self) -> tuple[TextDraw, ...]:
        """选面页 Stage/HI-Score 文字列(DrawPracticeMenu, MainMenu.cpp:2348-2404)。"""
        mv = self.menu_vms
        pos = mv.vms[_PRACTICE_HEADER_VM].vm.pos
        x, y = pos[0], pos[1]
        allowed = self._practice_stages_unlocked()
        d = self.memory.default_difficulty
        shot = self.memory.character * 2 + self.memory.shot_type
        out = [_ascii_text("Stage    HI-Score", x, y, _PRACTICE_COLORS[0])]
        for i, name in enumerate(_PRACTICE_STAGE_NAMES):
            y += 16.0
            p = self._store.pscr.get(practice_pscr_key(d, shot, i + 1), {})
            line = f"{name} {p.get('highscore', 0):9d}0 ({p.get('play_count', 0):3d})"
            if i == self.cursor:
                color = _PRACTICE_COLORS[0]  # 光标行白
            elif i < allowed:
                color = _PRACTICE_COLORS[1]  # 已解锁灰(:2381)
            else:
                color = _PRACTICE_COLORS[2]  # 未解锁暗灰(:2385)
            out.append(_ascii_text(line, x, y, color))
        return tuple(t for pair in out for t in pair)

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
