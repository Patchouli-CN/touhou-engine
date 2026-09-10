"""MainMenu VM 阵列 + 菜单输入账本: 标题/Option 等菜单 scene 的公共件。

C++ 的 MainMenu 是一个对象持有 vms[164] + descriptionVms[14] 贯穿所有菜单态
(主菜单/选择/Option 都在同一 VM 体系里切 interrupt); 这里 VM 阵列提成
MenuVmSet 由 scene 间共享, eighth 重复输入/光标移动提成 MenuScene 基类。
"""

from __future__ import annotations

from ....engine import InputFrame, SpriteDraw, TextDraw
from ....engine.anm import AnmBank, AnmMachine, build_bank
from ....engine.input import Button
from ....engine.rng import Rng
from ....schemas.anm import parse_anm
from ....schemas.archive import Archive, load_entry
from .scene import Scene

# SE idx(SoundPlayer.hpp:27-29)
SE_SELECT = 10
SE_BACK = 11
SE_MOVE = 12

_TITLE_ANM = "title01.anm"
_TEXT_ANM = "text.anm"

_VM_COUNT = 164  # ExecuteVmsAnms(vms, ANM_OFFSET_TITLE, 164) (MainMenu.cpp:215)
_DESC_VM_COUNT = 14  # MainMenu.hpp:198 descriptionVms[14]
_DESC_SCRIPT = 6  # ANM_SCRIPT_TEXT_MAINMENU_OPTION_DESC (AnmIdx.hpp:276)

_DESC_RGB = (255, 240, 224)  # 0xfff0e0 (MainMenu.cpp:260)
_DESC_SHADOW_RGB = (48, 0, 0)  # 0x300000
_DESC_SIZE = 15  # C++ fontWidth 缺省 15(AnmManager.cpp:2288-2294)


class MenuVm:
    """一台标题 VM: AnmMachine + C++ AnmVm 的 active/baseSpriteIdx 两位。"""

    __slots__ = ("vm", "active", "base_sprite_idx")

    def __init__(self, vm: AnmMachine) -> None:
        self.vm = vm
        self.active = True
        # ExecuteVmsAnms: 挂脚本跑完首帧后记录 baseSpriteIdx (AnmManager.cpp:2708)
        self.base_sprite_idx = vm.active_sprite_idx


class MenuVmSet:
    """title01.anm 的 164 台 VM + 14 台说明文字 VM(MainMenu 的 vms/descriptionVms)。

    资源缺失时全阵列无脚本, 菜单状态机照跑(文本兜底不可见)。
    """

    def __init__(self, archive: Archive | None, anm_version: int = 2) -> None:
        self._archive = archive
        rng = Rng(0)  # view VM 专用, 与 sim 无关
        bank: AnmBank | None = None
        text_bank: AnmBank | None = None
        if archive is not None:
            try:
                bank = build_bank(
                    parse_anm(
                        load_entry(archive, _TITLE_ANM),
                        version=anm_version,
                        flat_layout=False,
                    ),
                    flat_layout=False,
                )
                text_bank = build_bank(
                    parse_anm(
                        load_entry(archive, _TEXT_ANM),
                        version=anm_version,
                        flat_layout=False,
                    ),
                    flat_layout=False,
                )
            except (KeyError, ValueError):
                bank = None
                text_bank = None
        self.bank = bank
        # C++ 全局脚本 0x900+i ↔ 链式键 i(实测: TITLE_1..9 偏移与链基一一对应)
        scripts = bank.scripts if bank is not None else {}
        self.vms: list[MenuVm] = []
        for i in range(_VM_COUNT):
            m = AnmMachine(rng)
            m.start(scripts.get(i))
            self.vms.append(MenuVm(m))
        desc_scripts = text_bank.scripts if text_bank is not None else {}
        self.desc_vms: list[AnmMachine] = []
        for i in range(_DESC_VM_COUNT):
            m = AnmMachine(rng)
            m.start(desc_scripts.get(_DESC_SCRIPT))
            if m.active_sprite_idx >= 0:
                m.active_sprite_idx += i  # MainMenu.cpp:2676-2677 每台一个文字槽
            self.desc_vms.append(m)
        self.cur_desc: AnmMachine | None = self.desc_vms[0]

    def interrupt_all(self, n: int) -> None:
        """SetInterruptActiveVms (AnmManager.cpp:2661-2686)。"""
        for w in self.vms:
            if w.vm.alive:
                w.vm.pending_interrupt = n

    def set_sprite(self, idx: int, dim: bool) -> None:
        """选中亮(base)/未选暗(base+1); 无效 sprite 不动(AnmManager.cpp:656-659)。"""
        w = self.vms[idx]
        if w.base_sprite_idx < 0:
            return
        gid = w.base_sprite_idx + (1 if dim else 0)
        if self.bank is not None and gid not in self.bank.sprites:
            return
        w.vm.active_sprite_idx = gid

    def highlight(self, first: int, count: int, selected: int) -> None:
        """一组菜单项刷高亮(MainMenu.cpp:220-227 模式)。"""
        for i in range(count):
            self.set_sprite(first + i, dim=i != selected)

    def execute(self) -> None:
        """ExecuteScripts(vms) + curDescriptionVm (MainMenu.cpp:182-186)。"""
        for w in self.vms:
            w.vm.execute()
        if self.cur_desc is not None:
            self.cur_desc.execute()

    def sprites(self, background: str | None) -> list[SpriteDraw]:
        """本帧 VM 阵列的绘制清单(背景在最底, C++ 按 VM 数组序绘制)。"""
        sprites: list[SpriteDraw] = []
        if self._archive is not None and background is not None:
            sprites.append(SpriteDraw(background, 320.0, 240.0, z=-1.0))
        for i, w in enumerate(self.vms):
            vm = w.vm
            if (
                not w.active
                or not vm.visible
                or vm.active_sprite_idx < 0
                or vm.color[3] <= 0
            ):
                continue  # ShouldDraw/DrawNoRotation 的可见判定 (AnmManager.cpp:993-1006)
            x = vm.pos[0] + vm.offset[0]  # OnDraw: pos += offset (MainMenu.cpp:2499)
            y = vm.pos[1] + vm.offset[1]
            if vm.anchor & 3:  # bit0=左缘 bit1=顶缘 (AnmManager.cpp:1011-1041)
                slot = (
                    self.bank.sprites.get(vm.active_sprite_idx)
                    if self.bank is not None
                    else None
                )
                if slot is not None:
                    if vm.anchor & 1:
                        x += slot.sprite.w * vm.scale[0] / 2
                    if vm.anchor & 2:
                        y += slot.sprite.h * vm.scale[1] / 2
            sprites.append(
                SpriteDraw(
                    f"{_TITLE_ANM}:{vm.active_sprite_idx}",
                    x,
                    y,
                    z=float(i),
                    rotation=vm.rotation[2],
                    alpha=vm.color[3],
                    scale_x=vm.scale[0],
                    scale_y=vm.scale[1],
                    color=(vm.color[0], vm.color[1], vm.color[2]),
                    blend_mode=vm.blend_mode,
                )
            )
        return sprites


def description_texts(vm: AnmMachine | None, text: str) -> tuple[TextDraw, ...]:
    """底部说明行(C++ 把字贴进 text.anm 空纹理槽, 这里直出 TextDraw)。"""
    if vm is None or not vm.visible or vm.color[3] <= 0:
        return ()
    alpha = vm.color[3]
    x = vm.pos[0] - len(text) * _DESC_SIZE / 2  # DrawStringFormat2 水平居中
    y = vm.pos[1] - 8  # 文字槽高 17 取顶缘
    return (
        TextDraw(text, x + 1, y + 1, _DESC_SIZE, (*_DESC_SHADOW_RGB, alpha)),
        TextDraw(text, x, y, _DESC_SIZE, (*_DESC_RGB, alpha)),
    )


class MenuScene(Scene):
    """C++ MainMenu 各态的公共件: eighth 重复输入/光标移动/确认取消/菜单 SE。"""

    def __init__(self) -> None:
        super().__init__()
        self.cursor = 0
        self._sounds: list[int] = []
        # eighth 重复输入账本(Supervisor.cpp:177-191)
        self._last_held: frozenset[Button] = frozenset()
        self._held_frames = 0
        self._eighth = False
        self._inp = InputFrame()

    def drain_sounds(self) -> list[int]:
        out, self._sounds = self._sounds, []
        return out

    def _update_input(self, inp: InputFrame) -> None:
        """Eighth 重复: 整包 held 不变 30 帧起每 8 帧再触发(Supervisor.cpp:177-196)。"""
        self._inp = inp
        self._eighth = False
        if inp.held == self._last_held:
            if self._held_frames >= 30:
                if self._held_frames % 8 == 0:
                    self._eighth = True
                if self._held_frames >= 38:
                    self._held_frames = 30
            self._held_frames += 1
        else:
            self._held_frames = 0
        self._last_held = inp.held

    def _pressed(self, b: Button) -> bool:
        return b in self._inp.pressed

    def _move_edge(self, b: Button) -> bool:
        """WAS_PRESSED_RAW_AND_IS_EIGHTH (Controller.hpp:42-43)。"""
        return b in self._inp.pressed or (self._eighth and b in self._inp.held)

    def _move_cursor_vertical(self, count: int) -> int:
        """MainMenu.cpp:2407-2442(环绕 + 移动音)。"""
        if count == 0:
            return 0
        if self._move_edge(Button.UP):
            self.cursor = (self.cursor - 1) % count
            self._sounds.append(SE_MOVE)
            return -1
        if self._move_edge(Button.DOWN):
            self.cursor = (self.cursor + 1) % count
            self._sounds.append(SE_MOVE)
            return 1
        return 0

    def _move_cursor_horizontal(self, count: int) -> int:
        """MainMenu.cpp:2445-2472。"""
        if count == 0:
            return 0
        if self._move_edge(Button.LEFT):
            self.cursor = (self.cursor - 1) % count
            self._sounds.append(SE_MOVE)
            return -1
        if self._move_edge(Button.RIGHT):
            self.cursor = (self.cursor + 1) % count
            self._sounds.append(SE_MOVE)
            return 1
        return 0

    def _confirm_pressed(self) -> bool:
        """TH_BUTTON_SELECTMENU = Enter|射击 (Controller.hpp:30); Enter 无 Button 对应。"""
        return self._pressed(Button.SHOT)

    def _cancel_pressed(self) -> bool:
        """TH_BUTTON_RETURNMENU = 菜单键(Esc)|炸弹 (Controller.hpp:31)。"""
        return self._pressed(Button.BOMB) or self._pressed(Button.PAUSE)
