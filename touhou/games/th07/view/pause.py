"""Esc 暂停菜单: AsciiManager.cpp PauseMenu 的移植(GameScene 的冻结子态, 两项精简)。

只接 Resume/Return to Title 两行(= C++ replay 模式的两行 toggle 语义; restart 行
不实现, sprite 3 恒隐, AsciiManager.cpp:531-534), Return 带 はい/いいえ 确认
(默认 No)。快捷键: Q 无确认直退回标题 (:462-475), R 无确认重开 (:476-489,
RESTART_FROM_BEGINNING: 通常难度回一面全量重开, practice/Ex/Ph 重开本面,
Supervisor.cpp:281-297)。菜单叠在冻结帧上(C++ menuBackground 是游戏截屏,
:525-545, 本作由 GameScene 冻结快照承担)。quit = SUPERVISOR_STATE_MAINMENU
直回标题不进结算 (:755-759), 出口由 GameScene.on_quit/on_restart 接缝落地。
"""

from __future__ import annotations

from ....engine import InputFrame, SpriteDraw
from ....engine.anm import AnmMachine
from ....engine.input import Button
from ....engine.rng import Rng
from ..world import Th07World
from .menu_vms import SE_SELECT
from .music import BgmPlayer
from .retry import _load_bank

_SE_TOGGLE = 0  # SOUND_SHOOTING (AsciiManager.cpp:565/577 等, 原作就是射击音)
SE_PAUSED = 37  # SOUND_PAUSED (GameManager.cpp:144, 开菜单时由 GameScene 播)

_SCR_MENU = 254  # ANM_SCRIPT_ASCII_PAUSE_MENU (AnmIdx.hpp:154) ↔ 链式键 254..263
_SPR_DIFFICULTY = 269  # ANM_SPRITE_ASCII_PAUSE_MENU_DIFFICULTY (AnmIdx.hpp:163)
_SKIP_ROWS = (3, 9)  # 3=restart 行(不实现), 9=slowMode 指示(引擎无 slow mode)

# 状态 (AsciiManager.hpp PauseMenuState; confirm 两态合并写)
_ST_INIT = 0
_ST_SELECT_RESUME = 1
_ST_SELECT_RETURN = 2
_ST_CONFIRM_YES = 3
_ST_CONFIRM_NO = 4
_ST_UNPAUSING = 5
_ST_QUITTING = 6
_ST_RESTARTING = 7  # PAUSE_MENU_STATE_RESTART_STAGE (R 键, :476-489/:766-776)

_GATE = 4  # 选择态输入门 (AsciiManager.cpp:547 等)
_FRAMES_EXIT = 20  # 离场等 20 帧 (:652/:747/:760)

_LIT = (255, 255, 255, 255)  # 0xffffffff 选中行 (:552)
_DIM = (48, 48, 48, 128)  # 0x80303030 未选中行 (:553)
_LIT_CF = (255, 128, 128, 255)  # 0xffff8080 确认选中 (:676)
_DIM_CF = (128, 128, 128, 128)  # 0x80808080 确认未选 (:677)

_Z = 200.0  # 叠在 HUD(Gui 层 ~103)之上(与续关菜单同段)


class PauseMenu:
    """暂停菜单状态机: step 吃输入推进, sprites 出覆层绘制项, choice 为出口。"""

    def __init__(
        self,
        world: Th07World,
        *,
        anm_version: int = 2,
        music: BgmPlayer | None = None,
    ) -> None:
        if music is not None:
            music.pause()  # AUDIO_PAUSE (GameManager.cpp:140-143, 仅 WAV 音源)
        self._music = music
        self._state = _ST_INIT
        self._frames = 0
        self.choice: str | None = None  # "resume" / "quit" / "restart"
        self._sounds: list[int] = []
        rng = Rng(0)  # view VM 专用, 与 sim 无关
        self._bank = _load_bank(world.archive, anm_version)
        scripts = self._bank.scripts if self._bank is not None else {}
        self._vms: list[AnmMachine] = []
        for i in range(10):
            m = AnmMachine(rng)
            # SetAnmIdxAndExecuteScript (:499-502); 隐藏行不起脚本
            if i in _SKIP_ROWS or (i == 8 and not world.practice):
                m.start(None)
            else:
                m.start(scripts.get(_SCR_MENU + i))
            self._vms.append(m)
        diff = self._vms[7]
        if diff.active_sprite_idx >= 0:
            # 难度图标 (:510-511)
            diff.active_sprite_idx = _SPR_DIFFICULTY + world.difficulty
        for m in self._vms[:4]:
            m.pending_interrupt = 1  # 入场 (:504-507)

    def step(self, inp: InputFrame) -> None:
        """推进一帧: 状态机(AsciiManager.cpp:444-792) + VM 全阵列 execute。"""
        if Button.PAUSE in inp.pressed and self._state not in (
            _ST_UNPAUSING,
            _ST_QUITTING,
        ):
            # 菜单中再按 Esc = 直退 (:448-460)
            self._sounds.append(SE_SELECT)
            self._exit_vms(range(10))
            self._state = _ST_UNPAUSING
            self._frames = 0
        elif Button.Q in inp.pressed and self._state != _ST_QUITTING:
            # Q = 直退回标题, 无确认 (:462-475)
            self._sounds.append(SE_SELECT)
            self._exit_vms(range(10))
            self._state = _ST_QUITTING
            self._frames = 0
        elif Button.RESET in inp.pressed and self._state != _ST_QUITTING:
            # R = 重开, 无确认 (:476-489; C++ 回放模式禁用, 本菜单不回放用)
            self._sounds.append(SE_SELECT)
            self._exit_vms(range(10))
            self._state = _ST_RESTARTING
            self._frames = 0
        elif self._state == _ST_INIT:
            self._state = _ST_SELECT_RESUME  # INIT fallthrough (:521)
            self._frames = 0
        elif self._state in (_ST_SELECT_RESUME, _ST_SELECT_RETURN):
            self._highlight()
            if self._frames >= _GATE:
                if Button.UP in inp.pressed or Button.DOWN in inp.pressed:
                    # 两行 toggle (= C++ replay 模式, :558-577/:590-609)
                    self._state = (
                        _ST_SELECT_RETURN
                        if self._state == _ST_SELECT_RESUME
                        else _ST_SELECT_RESUME
                    )
                    self._sounds.append(_SE_TOGGLE)
                if Button.SHOT in inp.pressed:  # TH_BUTTON_SELECTMENU
                    self._sounds.append(SE_SELECT)
                    if self._state == _ST_SELECT_RESUME:
                        self._exit_vms(range(4))  # :563-567
                        self._state = _ST_UNPAUSING
                    else:
                        # Return → 确认: 0-3 退场 + 4-6 入场 (:617-625)
                        self._exit_vms(range(4))
                        self._enter_vms(range(4, 7))
                        self._state = _ST_CONFIRM_NO  # 默认 No (:625)
                    self._frames = 0
        elif self._state in (_ST_CONFIRM_YES, _ST_CONFIRM_NO):
            self._highlight()
            if self._frames >= _GATE:
                if Button.UP in inp.pressed or Button.DOWN in inp.pressed:
                    self._state = (
                        _ST_CONFIRM_NO
                        if self._state == _ST_CONFIRM_YES
                        else _ST_CONFIRM_YES
                    )
                    self._sounds.append(_SE_TOGGLE)  # :689-695
                if Button.SHOT in inp.pressed:
                    self._sounds.append(SE_SELECT)
                    if self._state == _ST_CONFIRM_YES:
                        self._exit_vms(range(4, 7))  # :702-705
                        self._state = _ST_QUITTING
                    else:
                        # No → 回选择: 0-3 再入场 + 4-6 退场 (:726-734)
                        self._enter_vms(range(4))
                        self._exit_vms(range(4, 7))
                        self._state = _ST_SELECT_RETURN
                    self._frames = 0
        elif self._state == _ST_UNPAUSING:
            if self._frames >= _FRAMES_EXIT:
                if self._music is not None:
                    self._music.unpause()  # AUDIO_UNPAUSE (:663-666)
                self.choice = "resume"
        elif self._state == _ST_RESTARTING:
            if self._frames >= _FRAMES_EXIT:
                self.choice = "restart"  # RESTART_FROM_BEGINNING (:766-776)
        else:  # _ST_QUITTING
            if self._frames >= _FRAMES_EXIT:
                self.choice = "quit"  # curState=MAINMENU (:755-759)
        for m in self._vms:
            m.execute()  # :784-787
        self._frames += 1

    def sprites(self) -> list[SpriteDraw]:
        """本帧覆层 sprite(游戏区坐标 + 窗口偏移, 中心锚, 无裁剪; 同续关菜单)。"""
        out: list[SpriteDraw] = []
        for i, vm in enumerate(self._vms):
            if not vm.visible or vm.active_sprite_idx < 0 or vm.color[3] <= 0:
                continue
            out.append(
                SpriteDraw(
                    f"ascii.anm:{vm.active_sprite_idx}",
                    32.0 + vm.pos[0] + vm.offset[0],  # GAME_X/GAME_Y (snapshot.py:34)
                    16.0 + vm.pos[1] + vm.offset[1],
                    z=_Z + i,
                    alpha=vm.color[3],
                    scale_x=vm.scale[0],
                    scale_y=vm.scale[1],
                    color=(vm.color[0], vm.color[1], vm.color[2]),
                )
            )
        return out

    def drain_sounds(self) -> list[int]:
        out, self._sounds = self._sounds, []
        return out

    def _enter_vms(self, idxs) -> None:
        for i in idxs:
            self._vms[i].pending_interrupt = 1

    def _exit_vms(self, idxs) -> None:
        for i in idxs:
            if self._vms[i].visible:
                self._vms[i].pending_interrupt = 2

    def _highlight(self) -> None:
        """选中行亮 + 偏移 (-4,-4), 未选暗 (:552-556/:676-680)。"""
        if self._state in (_ST_SELECT_RESUME, _ST_SELECT_RETURN):
            rows = (
                (1, self._state == _ST_SELECT_RESUME),
                (2, self._state == _ST_SELECT_RETURN),
            )
            colors = (_LIT, _DIM)
        else:
            rows = (
                (5, self._state == _ST_CONFIRM_YES),
                (6, self._state == _ST_CONFIRM_NO),
            )
            colors = (_LIT_CF, _DIM_CF)
        for vm_idx, lit in rows:
            vm = self._vms[vm_idx]
            vm.color = list(colors[0] if lit else colors[1])
            vm.offset = [-4.0, -4.0, 0.0] if lit else [0.0, 0.0, 0.0]
