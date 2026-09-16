"""GameOver 续关菜单: AsciiManager.cpp RetryMenu 的移植(GameScene 的冻结子态)。

菜单开在原游戏画面上(世界冻结, 快照停在死亡帧); 默认选中"いいえ"
(INIT 的 `curState += 2` 怪癖, AsciiManager.cpp:891)。Yes → 原世界
continue_play 接着打; No → finalize_game_over 进结算。
"""

from __future__ import annotations

from ....engine import InputFrame, SpriteDraw
from ....engine.anm import AnmBank, AnmMachine, build_bank
from ....engine.input import Button
from ....engine.rng import Rng
from ....schemas.anm import parse_anm
from ....schemas.archive import Archive, load_entry
from ..world import Th07World
from .menu_vms import SE_SELECT
from .music import BgmPlayer

_SE_TOGGLE = 0  # SOUND_SHOOTING (AsciiManager.cpp:903/927, 原作就是射击音)

_ASCII = "ascii.anm"
_SCR_MENU = 264  # ANM_SCRIPT_ASCII_RETRY_MENU (AnmIdx.hpp:155) ↔ 链式键 264..267
_SCR_LIVES = 268  # ANM_SCRIPT_ASCII_RETRY_MENU_LIVES (AnmIdx.hpp:156)
# 剩余次数数字 sprite 基址: ANM_SPRITE_ASCII_RETRY_MENU_LIVES (AnmIdx.hpp:161),
# C++ SetActiveSprite(maxRetries + 262 - numRetries) (AsciiManager.cpp:864-868)
_SPR_LIVES = 262

# 状态 (AsciiManager.hpp:27-31 RetryMenuState)
_ST_INIT = 0
_ST_SELECT_CONTINUE = 1  # はい
_ST_SELECT_RETURN = 2  # いいえ
_ST_CONTINUE_GAME = 3
_ST_RETURN_TO_MENU = 4

_GATE_CONTINUE = 4  # SELECTING_CONTINUE 输入门 (:898)
_GATE_RETURN = 30  # SELECTING_RETURN 输入门 (:923)
_FRAMES_CONTINUE = 30  # 选 Yes 后等 30 帧复活 (:959)
_FRAMES_RETURN = 20  # 选 No 后等 20 帧进结算 (:943)

_LIT = (255, 128, 128, 255)  # 0xffff8080 选中 (:894)
_DIM = (128, 128, 128, 128)  # 0x80808080 未选中 (:895)

_Z = 200.0  # 叠在 HUD(Gui 层 ~103)之上


def _load_bank(archive: Archive | None, anm_version: int) -> AnmBank | None:
    if archive is None:
        return None
    try:
        return build_bank(
            parse_anm(
                load_entry(archive, _ASCII), version=anm_version, flat_layout=False
            ),
            flat_layout=False,
        )
    except (KeyError, ValueError):
        return None


class RetryMenu:
    """续关菜单状态机: step 吃输入推进, sprites 出覆层绘制项, choice 为出口。"""

    def __init__(
        self,
        world: Th07World,
        *,
        anm_version: int = 2,
        music: BgmPlayer | None = None,
    ) -> None:
        if music is not None:
            music.pause()  # AUDIO_PAUSE (AsciiManager.cpp:853, 仅 WAV 音源)
        self._music = music
        self._state = _ST_INIT
        self._frames = 0
        self.choice: str | None = None  # "continue" / "quit"
        self._sounds: list[int] = []
        rng = Rng(0)  # view VM 专用, 与 sim 无关
        self._bank = _load_bank(world.archive, anm_version)
        scripts = self._bank.scripts if self._bank is not None else {}
        self._vms: list[AnmMachine] = []
        for i in range(4):
            m = AnmMachine(rng)
            m.start(scripts.get(_SCR_MENU + i))  # SetAnmIdxAndExecuteScript (:856-860)
            self._vms.append(m)
        lives = AnmMachine(rng)
        lives.start(scripts.get(_SCR_LIVES))  # :861-863
        if lives.active_sprite_idx >= 0:
            lives.active_sprite_idx = _SPR_LIVES + (
                world.max_retries - world.th07.num_retries
            )
        self._vms.append(lives)
        for m in self._vms:
            m.pending_interrupt = 1  # 入场 (:859/:869)

    def step(self, inp: InputFrame) -> None:
        """推进一帧: 状态机(AsciiManager.cpp:848-1022) + VM 全阵列 execute。"""
        if self._state == _ST_INIT:
            # INIT 怪癖: `curState += SELECTING_RETURN` (:891) → 默认选中 No,
            # 当帧接着跑 SELECT_CONTINUE 的亮暗段(fallthrough)
            self._state = _ST_SELECT_RETURN
            self._frames = 0
            self._highlight(_ST_SELECT_CONTINUE)
        elif self._state in (_ST_SELECT_CONTINUE, _ST_SELECT_RETURN):
            self._highlight(self._state)
            gate = (
                _GATE_CONTINUE if self._state == _ST_SELECT_CONTINUE else _GATE_RETURN
            )
            if self._frames >= gate:
                if Button.UP in inp.pressed or Button.DOWN in inp.pressed:
                    # 切项 (:900-904/:925-929; numFrames 不重置)
                    self._state = (
                        _ST_SELECT_RETURN
                        if self._state == _ST_SELECT_CONTINUE
                        else _ST_SELECT_CONTINUE
                    )
                    self._sounds.append(_SE_TOGGLE)
                if Button.SHOT in inp.pressed:  # TH_BUTTON_SELECTMENU (:905/:930)
                    self._sounds.append(SE_SELECT)
                    for m in self._vms:
                        m.pending_interrupt = 2  # 退场 (:908-911/:933-936)
                    self._state = (
                        _ST_CONTINUE_GAME
                        if self._state == _ST_SELECT_CONTINUE
                        else _ST_RETURN_TO_MENU
                    )
                    self._frames = 0
        elif self._state == _ST_CONTINUE_GAME:
            if self._frames >= _FRAMES_CONTINUE:
                if self._music is not None:
                    self._music.unpause()  # AUDIO_UNPAUSE (:1007)
                self.choice = "continue"
        else:  # _ST_RETURN_TO_MENU
            if self._frames >= _FRAMES_RETURN:
                self.choice = "quit"  # curState=RESULTSCREEN_FROM_GAME (:948)
        for m in self._vms:
            m.execute()  # :1013-1016
        self._frames += 1

    def sprites(self) -> list[SpriteDraw]:
        """本帧覆层 sprite(游戏区坐标 + 窗口偏移, 中心锚, 无裁剪)。"""
        out: list[SpriteDraw] = []
        for i, vm in enumerate(self._vms):
            if not vm.visible or vm.active_sprite_idx < 0 or vm.color[3] <= 0:
                continue
            out.append(
                SpriteDraw(
                    f"{_ASCII}:{vm.active_sprite_idx}",
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

    def _highlight(self, selected: int) -> None:
        """はい/いいえ 两行亮暗 + 选中偏移 (-4,-4) (:893-897/:919-922)。"""
        for row, vm_idx in ((0, 2), (1, 3)):  # row 0=はい(vm 2), 1=いいえ(vm 3)
            lit = (row == 0) == (selected == _ST_SELECT_CONTINUE)
            vm = self._vms[vm_idx]
            vm.color = list(_LIT if lit else _DIM)
            vm.offset = [-4.0, -4.0, 0.0] if lit else [0.0, 0.0, 0.0]
