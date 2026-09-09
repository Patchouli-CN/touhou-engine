"""TH08(东方永夜抄)的对话 VM 扩展 —— MsgVmTh08(MsgVm)。

th08 的 msg opcode 扩到 0-22(Gui.hpp:67-74); 扩展字段与 op15-22 分支
自 schema/msg.py 下沉(纯搬运, C 行号注释随行), 经基类的
``_handle_extra_op`` 扩展点接入:
- op15/17 立绘配置(Gui.cpp:286-328/:330-383): 说话方切换(旧方跨对→6
  原地压暗/同对→4, 其余→4, 新方→3) + 各槽 SetSprite(≥0 才设),
  落 ``portrait_sprites``/``current_portrait_index``;
- op18 SET_TEXT_BOX_VISIBLE: 落 ``text_box_visible``;
- op16 SHOW_SPEAKER_TEXT(Gui.cpp:486-512)/op19/op20: 纯文本落对话行
  (GuiMessagePlainTextArgs, Gui.hpp:121-124);
- op21 SHOW_SELECTION(Gui.cpp:540-573): 二选一, wait 式停留;
- op22 READ_SELECTED_MESSAGE(Gui.cpp:574-578): finalStageRoute =
  selectedOption 并 MsgRead(selectedOption+1);
- PAUSE 的 Z 提前结束最短停留 waitThreshold=6(Gui.cpp:241) 经构造参数
  ``pause_min_frames=6`` 传入。

op1 SET_PORTRAIT_ANM_SCRIPT 的 anmScriptIdx 是槽位 anm 的扁平脚本号
(Gui.cpp:385-417 SetAndExecuteScriptIdx), 由基类落 ``portraits[i].face``;
view 侧(games/th08/view/dialog_view.py)按脚本号起 VM。op2 全数据仅
msg1b 一次且与同帧 op1 冗余, 未单独区分(按脚本号解读, 见 gaps 文档 #5)。
"""

from __future__ import annotations

import struct
from typing import Optional

from ...schema.msg import MsgFile, MsgInstr, MsgOpcode, MsgVm


class MsgVmTh08(MsgVm):
    """th08 对话 VM: 基类 + 扩展字段(Gui.hpp GuiMsgVm 尾部) + op15-22。"""

    def __init__(
        self,
        msg_file: Optional[MsgFile] = None,
        *,
        num_portraits: int = 4,
        pause_min_frames: int = 6,  # th08 MsgRead: waitThreshold=6 (Gui.cpp:241)
    ) -> None:
        super().__init__(
            msg_file, num_portraits=num_portraits, pause_min_frames=pause_min_frames
        )
        # ---- th08 扩展(Gui.hpp GuiMsgVm 尾部字段) ----
        self.dialogue_line_index = 0  # op16 说话人文本的落行游标
        self.selected_option = 0  # op21 二选一的当前选项(0/1)
        self.final_stage_route: int | None = None  # op22 写出(Gui.cpp:574-578)
        self.portrait_sprites = [-1] * num_portraits  # op15/17 各槽 SetSprite 值
        self.current_portrait_index = -1  # 说话方槽位(C 初值 0xff, Gui.cpp:240)
        self.text_box_visible = True  # op18(Gui.cpp:225 MsgRead 置 1)

    def read(self, msg_idx: int) -> None:
        """MsgRead: 基类清零后补清 th08 扩展字段(越界无操作同基类)。"""
        if self.msg_file is None or self.msg_file.num_messages <= msg_idx:
            return
        super().read(msg_idx)
        self.dialogue_line_index = 0
        self.portrait_sprites = [-1] * self.num_portraits
        self.current_portrait_index = -1
        self.text_box_visible = True

    def _switch_speaker(self, new_idx: int) -> None:
        """op15/17 的说话方切换(Gui.cpp:288-308/:332-352): 旧说话方跨对
        (0-1 自机/2-3 敌方)→ 6(原地压暗), 同对 → 4, 其余槽 → 4;
        新说话方恒 → 3(亮)。"""
        cur = self.current_portrait_index
        if cur != new_idx:
            for j, p in enumerate(self.portraits):
                if j == cur:
                    p.pending_interrupt = 6 if (cur // 2) != (new_idx // 2) else 4
                else:
                    p.pending_interrupt = 4
        self.portraits[new_idx].pending_interrupt = 3
        self.current_portrait_index = new_idx

    def _handle_extra_op(self, cur: MsgInstr, advance_pressed: bool) -> Optional[bool]:
        """op15-22(Gui.cpp RunMsg)。"""
        op = cur.opcode
        if op == MsgOpcode.CONFIGURE_ALL_PORTRAITS:
            # Gui.cpp:286-328: i32 portraitIndex + i32 spriteIndices[4]
            vals = struct.unpack_from("<5i", cur.args, 0)
            self._switch_speaker(vals[0])
            for i, s in enumerate(vals[1:]):
                if s >= 0:
                    self.portrait_sprites[i] = s
        elif op == MsgOpcode.CONFIGURE_PORTRAIT:
            # Gui.cpp:330-383: i32 portraitIndex + i32 spriteIndex
            new_idx, sprite = struct.unpack_from("<2i", cur.args, 0)
            self._switch_speaker(new_idx)
            if sprite >= 0:
                self.portrait_sprites[new_idx] = sprite
        elif op == MsgOpcode.SET_TEXT_BOX_VISIBLE:
            # GuiMessageByteToggleArgs: 直接读 args 首字节
            self.text_box_visible = bool(cur.args and cur.args[0])
        elif op == MsgOpcode.SHOW_SPEAKER_TEXT:
            # Gui.cpp:486-512: 落 dialogueLines[dialogueLineIndex] 并自增
            line_state = self.dialogue_lines[
                min(self.dialogue_line_index, len(self.dialogue_lines) - 1)
            ]
            line_state.set_text(cur.plain_text, 0)
            self.frames_elapsed_during_pause = 0
            self.dialogue_line_index += 1
        elif op == MsgOpcode.SHOW_TOP_TEXT:
            # Gui.cpp:514-525: 落对话行 0
            self.dialogue_lines[0].set_text(cur.plain_text, 0)
            self.frames_elapsed_during_pause = 0
        elif op == MsgOpcode.SHOW_BOTTOM_TEXT:
            # Gui.cpp:527-538: 落对话行 1
            self.dialogue_lines[1].set_text(cur.plain_text, 0)
            self.frames_elapsed_during_pause = 0
        elif op == MsgOpcode.SHOW_SELECTION:
            # 二选一 (Gui.cpp:540-573): wait 式停留; Z 新按下(停满 60 帧)
            # 提前确认, 否则停满 args.wait.frames 自然前进; 上下键改
            # selected_option 是输入侧职责(headless 由上层直写字段)。
            if (
                not advance_pressed
                or self.frames_elapsed_during_pause < 60
            ):
                if self.frames_elapsed_during_pause < cur.pause_duration:
                    self.frames_elapsed_during_pause += 1
                    self._post_step()
                    return True  # 停在该指令
        elif op == MsgOpcode.READ_SELECTED_MESSAGE:
            # Gui.cpp:574-578: finalStageRoute=selectedOption,
            # MsgRead(selectedOption+1) 后 continue(新消息当帧继续跑);
            # 越界时 MsgRead 无操作, 原地 continue 会死循环, 按普通前进兜底
            self.final_stage_route = self.selected_option
            prev_idx = self.current_msg_idx
            self.read(self.selected_option + 1)
            if self.current_msg_idx != prev_idx:
                # read 已把 instr_idx 清 0; 置 -1 抵消基类链尾的普通前进,
                # 等效 C 的 continue(新消息当帧继续跑)
                self.instr_idx = -1
        return None
