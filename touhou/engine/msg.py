"""MSG 对话执行器: 消费 schemas.msg 指令 union, handler 查表分派(同 ANM/ECL)。

每帧语义 = GuiImpl::MsgRead/RunMsg (Reference/th07/src/th07/Gui.cpp:735-1060),
移植 old/touhou/schema/msg.py MsgVm。引擎只放流派通用对话机制: 指令推进/
PAUSE 等待/Z 提前/Ctrl 快进/立绘与文本行状态(数据透出给 view, 不做渲染)/
APPEAR_ENEMY 放行窗/STAGERESULTS·NEXT_LEVEL·切曲事件; 过关结算与换关规则
是作品语义(games 侧订事件实现)。作品扩展指令(opcode 15-22)经 extra_handlers
注入(同 EclMachine 的 extra_handlers)。
"""

from __future__ import annotations

import enum
from collections.abc import Callable
from typing import Any

import msgspec

from ..schemas.msg import (
    AllowSkip,
    AppearEnemy,
    ChangeFace,
    Delete,
    Dialogue,
    FadeInEffect,
    FadeoutMusic,
    Freeze,
    MsgFile,
    MsgInstr,
    Music,
    NextLevel,
    Pause,
    ShowPortrait,
    StageResults,
    Switch,
    TextIntroduce,
)
from .events import Event

FONT_SIZE = 15  # MsgRead: fontSize=15
PAUSE_MIN_FRAMES = 12  # Z 提前结束 PAUSE 的最短停留(RunMsg: <12 不响应)
TYPEWRITER_FRAMES_PER_CHAR = 2  # 打字机速度(视觉近似, 原版由 anm 脚本控制)


# ---- 控制事件(作品侧订阅: 切曲/结算/换关) ----


class MsgMusicChange(Event, frozen=True, tag="msg_music_change"):
    """MSG_MUSIC: 切曲, music_idx 曲目号(索引关卡 BGM 表是作品语义)。"""

    music_idx: int


class MsgMusicFadeout(Event, frozen=True, tag="msg_music_fadeout"):
    """MSG_FADEOUT_MUSIC: 音乐淡出。"""


class MsgStageResults(Event, frozen=True, tag="msg_stage_results"):
    """MSG_STAGERESULTS: 进关卡结算(奖励公式/面板数据是作品语义)。"""


class MsgNextLevel(Event, frozen=True, tag="msg_next_level"):
    """MSG_NEXT_LEVEL: 转场下一面(分流/换关规则是作品语义)。"""


class MsgInput(msgspec.Struct, frozen=True):
    """一帧的对话输入: advance_pressed = Z 新按下, skip_held = Ctrl 按住。"""

    advance_pressed: bool = False
    skip_held: bool = False


# ---- 透出给 view 的渲染状态(数据, 引擎不画) ----

# SWITCH 的 interrupt 约定(由 msg 脚本实际用法归纳):
# 立绘 1=入场, 3=亮(说话方), 4=暗(非说话方), 5=退场; 文本行同组值控制显隐。


class MsgPortraitState(msgspec.Struct):
    """一侧立绘的渲染状态(C 里是 AnmVm, 这里只留渲染需要的最小字段)。"""

    visible: bool = False
    face: int = 0  # CHANGE_FACE/SHOW_PORTRAIT 的 anmScriptIdx
    pending_interrupt: int = 0

    @property
    def speaking(self) -> bool:
        """亮暗: SWITCH interrupt 3=说话方(亮), 4=非说话方(暗)。"""
        return self.pending_interrupt != 4

    @property
    def exited(self) -> bool:
        """Interrupt 5 = 退场(滑出), 不再绘制。"""
        return self.pending_interrupt == 5


class MsgLineState(msgspec.Struct):
    """一行对话/介绍文本的渲染状态。"""

    visible: bool = False
    text: str = ""
    color: int = 0
    reveal: int = 0  # 打字机已显示字符数
    pending_interrupt: int = 0

    def set_text(self, text: str, color: int) -> None:
        self.visible = True
        self.text = text
        self.color = color
        self.reveal = 0

    def clear(self) -> None:
        self.visible = False
        self.text = ""
        self.reveal = 0

    @property
    def shown_text(self) -> str:
        return self.text[: self.reveal]


class MsgStep(enum.Enum):
    """handler 返回: 前进下一条 / 停在本指令(消息仍活动) / 消息结束。"""

    ADVANCE = "advance"
    STAY = "stay"
    END = "end"


#: 指令类 → handler(参数按 Any 收, 同指令 VM 表); 作品扩展指令经构造注入
MsgHandler = Callable[["MsgExecutor", Any, MsgInput], MsgStep]


# ---- 指令 handler(Gui.cpp RunMsg 各 case; 语义逐条对齐旧 MsgVm.step) ----


def _op_delete(vm: MsgExecutor, ins: Delete, inp: MsgInput) -> MsgStep:
    vm.current_msg_idx = -1
    return MsgStep.END


def _op_show_portrait(vm: MsgExecutor, ins: ShowPortrait, inp: MsgInput) -> MsgStep:
    p = vm.portraits[ins.portrait_idx]
    p.visible = True
    p.face = ins.anm_script_idx
    return MsgStep.ADVANCE


def _op_change_face(vm: MsgExecutor, ins: ChangeFace, inp: MsgInput) -> MsgStep:
    vm.portraits[ins.portrait_idx].face = ins.anm_script_idx
    return MsgStep.ADVANCE


def _op_dialogue(vm: MsgExecutor, ins: Dialogue, inp: MsgInput) -> MsgStep:
    if ins.line == 0 and vm.dialogue_lines[1].visible:
        # RunMsg: 新顶行时把第 2 行清成 " "
        vm.dialogue_lines[1].clear()
    vm.dialogue_lines[ins.line].set_text(ins.text, ins.color)
    vm.frames_elapsed_during_pause = 0
    return MsgStep.ADVANCE


def _op_pause(vm: MsgExecutor, ins: Pause, inp: MsgInput) -> MsgStep:
    if vm.dialogue_skippable == 0 or not inp.skip_held:
        if (
            not inp.advance_pressed
            or vm.frames_elapsed_during_pause < vm.pause_min_frames
        ):
            if vm.frames_elapsed_during_pause < ins.duration:
                vm.frames_elapsed_during_pause += 1
                vm._post_step()
                return MsgStep.STAY  # SKIP_TIME_INCREMENT: 停在该指令
    # Z 提前结束(停满 pause_min_frames)/时长到/Ctrl 快进: 落普通前进
    return MsgStep.ADVANCE


def _op_switch(vm: MsgExecutor, ins: Switch, inp: MsgInput) -> MsgStep:
    if ins.idx < vm.num_portraits:
        vm.portraits[ins.idx].pending_interrupt = ins.interrupt
    else:
        vm.dialogue_lines[ins.idx - vm.num_portraits].pending_interrupt = ins.interrupt
    return MsgStep.ADVANCE


def _op_appear_enemy(vm: MsgExecutor, ins: AppearEnemy, inp: MsgInput) -> MsgStep:
    vm.ignore_wait_counter += 1  # MsgWait 当帧放行(对话不停, 时间轴过去刷 boss)
    return MsgStep.ADVANCE


def _op_music(vm: MsgExecutor, ins: Music, inp: MsgInput) -> MsgStep:
    vm.events.append(MsgMusicChange(ins.music_idx))
    return MsgStep.ADVANCE


def _op_text_introduce(vm: MsgExecutor, ins: TextIntroduce, inp: MsgInput) -> MsgStep:
    vm.intro_lines[ins.line].set_text(ins.text, ins.color)
    vm.frames_elapsed_during_pause = 0
    return MsgStep.ADVANCE


def _op_stage_results(vm: MsgExecutor, ins: StageResults, inp: MsgInput) -> MsgStep:
    vm.finished_stage = 1
    vm.events.append(MsgStageResults())
    return MsgStep.ADVANCE


def _op_freeze(vm: MsgExecutor, ins: Freeze, inp: MsgInput) -> MsgStep:
    vm._post_step()
    return MsgStep.STAY  # 永久停在该指令(msg 保持活动)


def _op_next_level(vm: MsgExecutor, ins: NextLevel, inp: MsgInput) -> MsgStep:
    # 转场结算, msg 置 -2(HasCurrentMsgIdx 对 -2 仍 True, 世界保持门控)
    vm.current_msg_idx = -2
    vm.events.append(MsgNextLevel())
    vm._post_step()
    return MsgStep.END


def _op_fadeout_music(vm: MsgExecutor, ins: FadeoutMusic, inp: MsgInput) -> MsgStep:
    vm.events.append(MsgMusicFadeout())
    return MsgStep.ADVANCE


def _op_allow_skip(vm: MsgExecutor, ins: AllowSkip, inp: MsgInput) -> MsgStep:
    vm.dialogue_skippable = ins.skippable
    return MsgStep.ADVANCE


def _op_fade_in_effect(vm: MsgExecutor, ins: FadeInEffect, inp: MsgInput) -> MsgStep:
    return MsgStep.ADVANCE  # 演出, 逻辑侧忽略


#: 通用指令(opcode 0-14)的 handler 表; 作品扩展指令(15-22)由 games 侧注入
HANDLERS: dict[type[MsgInstr], MsgHandler] = {
    Delete: _op_delete,
    ShowPortrait: _op_show_portrait,
    ChangeFace: _op_change_face,
    Dialogue: _op_dialogue,
    Pause: _op_pause,
    Switch: _op_switch,
    AppearEnemy: _op_appear_enemy,
    Music: _op_music,
    TextIntroduce: _op_text_introduce,
    StageResults: _op_stage_results,
    Freeze: _op_freeze,
    NextLevel: _op_next_level,
    FadeoutMusic: _op_fadeout_music,
    AllowSkip: _op_allow_skip,
    FadeInEffect: _op_fade_in_effect,
}


class MsgExecutor:
    """对话 VM(C GuiMsgVm + RunMsg 每帧语义); 一关一份, read() 清零重来。

    num_portraits: 立绘槽数(作品差异显式传入); SWITCH 的 idx<num_portraits →
    立绘, 否则文本行 idx-num_portraits。pause_min_frames: PAUSE 的 Z 提前
    结束最短停留(作品差异显式传入)。
    """

    def __init__(
        self,
        msg_file: MsgFile | None = None,
        *,
        num_portraits: int = 2,
        pause_min_frames: int = PAUSE_MIN_FRAMES,
        extra_handlers: dict[type[MsgInstr], MsgHandler] | None = None,
    ) -> None:
        self.msg_file = msg_file
        self.num_portraits = num_portraits
        self.pause_min_frames = pause_min_frames
        self.handlers: dict[type[MsgInstr], MsgHandler] = (
            HANDLERS if extra_handlers is None else {**HANDLERS, **extra_handlers}
        )
        self.current_msg_idx = -1
        self.instr_idx = 0  # 当前指令下标(模拟 curInstr 指针)
        self.timer = 0
        self.frames_elapsed_during_pause = 0
        self.ignore_wait_counter = 0
        self.dialogue_skippable = 1
        self.font_size = FONT_SIZE
        self.portraits = [MsgPortraitState() for _ in range(num_portraits)]
        self.dialogue_lines = [MsgLineState(), MsgLineState()]
        self.intro_lines = [MsgLineState(), MsgLineState()]
        self.finished_stage = 0  # STAGERESULTS 置 1
        self.events: list[Event] = []  # 待透出事件(作品侧 take_events 取走)
        self._type_timer = 0

    # ---- C 访问器 ----
    def msg_wait(self) -> bool:
        """Gui::MsgWait: True = 消息仍在显示(时间轴应停; APPEAR_ENEMY 窗口放行)。"""
        if self.ignore_wait_counter > 0:
            return False
        return self.current_msg_idx >= 0

    def has_current_msg_idx(self) -> bool:
        """Gui::HasCurrentMsgIdx: 对话门控(NEXT_LEVEL 后的 -2 也算)。"""
        return self.current_msg_idx >= 0 or self.current_msg_idx == -2

    @property
    def active(self) -> bool:
        return self.current_msg_idx >= 0

    def _cur(self) -> MsgInstr:
        # 仅在 read() 成功后有意义(active 为真时 msg_file 必已加载)
        assert self.msg_file is not None
        return self.msg_file.messages[self.current_msg_idx][self.instr_idx]

    # ---- MsgRead ----
    def read(self, msg_idx: int) -> None:
        """GuiImpl::MsgRead: 越界无操作; 否则整个 VM 清零重来。"""
        if self.msg_file is None or len(self.msg_file.messages) <= msg_idx:
            return
        self.current_msg_idx = msg_idx
        self.instr_idx = 0
        self.timer = 0
        self.frames_elapsed_during_pause = 0
        self.ignore_wait_counter = 0
        self.dialogue_skippable = 1
        self.font_size = FONT_SIZE
        self.portraits = [MsgPortraitState() for _ in range(self.num_portraits)]
        self.dialogue_lines = [MsgLineState(), MsgLineState()]
        self.intro_lines = [MsgLineState(), MsgLineState()]
        self.finished_stage = 0
        self.events = []
        self._type_timer = 0

    # ---- RunMsg ----
    def step(self, input: MsgInput | None = None) -> bool:
        """每帧一次; 返回 True = 消息仍活动。"""
        if input is None:
            input = MsgInput()
        if self.current_msg_idx < 0:
            return False
        if self.ignore_wait_counter > 0:
            self.ignore_wait_counter -= 1
        cur = self._cur()
        if self.dialogue_skippable and input.skip_held:
            self.timer = cur.time
        while self.timer >= cur.time:
            r = self.handlers[type(cur)](self, cur, input)
            if r is MsgStep.END:
                return False
            if r is MsgStep.STAY:
                return True
            self.instr_idx += 1
            cur = self._cur()
        self.timer += 1
        self._post_step()
        # RunMsg 尾部: 按住 SKIP 时跳过对话框淡入(前 60 帧)
        if self.timer < 60 and self.dialogue_skippable and input.skip_held:
            self.timer = 60
        return True

    def _post_step(self) -> None:
        """SKIP_TIME_INCREMENT 之后: 打字机推进(C 里是 ExecuteScript 驱动 VMs)。"""
        self._type_timer += 1
        if self._type_timer % TYPEWRITER_FRAMES_PER_CHAR == 0:
            for line in (*self.dialogue_lines, *self.intro_lines):
                if line.visible and line.reveal < len(line.text):
                    line.reveal += 1

    def take_events(self) -> list[Event]:
        """取走待透出事件(切曲/结算/换关), 取后清空。"""
        ev, self.events = self.events, []
        return ev
