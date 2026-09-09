"""对话脚本(msgN.dat)解析: 指令流 decode 成 tagged union。"""

from __future__ import annotations

import struct

import msgspec

from .exceptions import ParseError

# 文件头/指令布局 MsgRawHeader/MsgRawInstr: i32 指令数 + i32 偏移表,
# 指令 = u16 time + u8 opcode + u8 argsize + args
# (Reference/th07/src/th07/Gui.hpp:73-85); th08 逐字节同构
# (scratch_dbg/investigation/th08-ref-facts.md:46)
_MAX_MESSAGES = 4096


class MsgInstr(msgspec.Struct, frozen=True, tag_field="op"):
    """指令公共字段: time = 生效帧。"""

    time: int


# opcode 0-14 出处 Gui.hpp:36-63(MsgOpcode); 15-22 为 th08 扩展
# (th08-ref Gui.hpp:52-74, 参数布局 th08-ref Gui.cpp RunMsg,
# 转引 scratch_dbg/investigation/th08-ref-facts.md:46 与 old/touhou/games/th08/msg_vm.py)


class Delete(MsgInstr, frozen=True, tag=0):
    """消息结束(MSG_DELETE)。"""


class ShowPortrait(MsgInstr, frozen=True, tag=1):
    """显示立绘: portrait_idx 槽位, anm_script_idx 表情脚本号。"""

    portrait_idx: int
    anm_script_idx: int


class ChangeFace(MsgInstr, frozen=True, tag=2):
    """换表情(字段同 ShowPortrait)。"""

    portrait_idx: int
    anm_script_idx: int


class Dialogue(MsgInstr, frozen=True, tag=3):
    """一行对话文本: color 颜色序号, line 行号(0/1)。"""

    color: int
    line: int
    text: str


class Pause(MsgInstr, frozen=True, tag=4):
    """停顿 duration 帧(Z 可提前结束)。"""

    duration: int


class Switch(MsgInstr, frozen=True, tag=5):
    """立绘/文本行的 interrupt 切换: idx 槽位, interrupt 演出编号。"""

    idx: int
    interrupt: int


class AppearEnemy(MsgInstr, frozen=True, tag=6):
    """放行时间轴一次(boss 登场时对话不停)。"""


class Music(MsgInstr, frozen=True, tag=7):
    """切曲: music_idx 曲目号。"""

    music_idx: int


class TextIntroduce(MsgInstr, frozen=True, tag=8):
    """介绍文本(关卡标题等, 字段同 Dialogue)。"""

    color: int
    line: int
    text: str


class StageResults(MsgInstr, frozen=True, tag=9):
    """进关卡结算。"""


class Freeze(MsgInstr, frozen=True, tag=10):
    """永久停在该指令(消息保持活动)。"""


class NextLevel(MsgInstr, frozen=True, tag=11):
    """转场下一面。"""


class FadeoutMusic(MsgInstr, frozen=True, tag=12):
    """音乐淡出。"""


class AllowSkip(MsgInstr, frozen=True, tag=13):
    """设置对话是否可 Ctrl 跳过(读 args 首字节, Gui.cpp RunMsg)。"""

    skippable: int


class FadeInEffect(MsgInstr, frozen=True, tag=14):
    """淡入演出(纯视觉)。"""


class ConfigureAllPortraits(MsgInstr, frozen=True, tag=15):
    """全立绘配置: 说话方槽位 + 4 槽 sprite 号(负 = 不动)。"""

    portrait_idx: int
    sprites: tuple[int, int, int, int]


class ShowSpeakerText(MsgInstr, frozen=True, tag=16):
    """说话人文本(args 整体即文本, GuiMessagePlainTextArgs)。"""

    text: str


class ConfigurePortrait(MsgInstr, frozen=True, tag=17):
    """单立绘配置: 槽位 + sprite 号(负 = 不动)。"""

    portrait_idx: int
    sprite: int


class SetTextBoxVisible(MsgInstr, frozen=True, tag=18):
    """文本框显隐(读 args 首字节)。"""

    visible: bool


class ShowTopText(MsgInstr, frozen=True, tag=19):
    """顶部文本(落对话行 0)。"""

    text: str


class ShowBottomText(MsgInstr, frozen=True, tag=20):
    """底部文本(落对话行 1)。"""

    text: str


class ShowSelection(MsgInstr, frozen=True, tag=21):
    """二选一: 停 duration 帧(Z 提前确认)。"""

    duration: int


class ReadSelectedMessage(MsgInstr, frozen=True, tag=22):
    """按选项读消息分支。"""


Instruction = (
    Delete
    | ShowPortrait
    | ChangeFace
    | Dialogue
    | Pause
    | Switch
    | AppearEnemy
    | Music
    | TextIntroduce
    | StageResults
    | Freeze
    | NextLevel
    | FadeoutMusic
    | AllowSkip
    | FadeInEffect
    | ConfigureAllPortraits
    | ShowSpeakerText
    | ConfigurePortrait
    | SetTextBoxVisible
    | ShowTopText
    | ShowBottomText
    | ShowSelection
    | ReadSelectedMessage
)


class MsgFile(msgspec.Struct):
    """解析后的 msg 文件: messages[i] = 第 i 条消息的指令序列(含结尾 Delete)。"""

    messages: list[tuple[Instruction, ...]]


def _decode_text(raw: bytes, text_xor: int) -> str:
    # 文本: XOR(th08=0x77, th08-ref Gui.cpp:773) → NUL 截断 → Shift-JIS 容错
    if text_xor:
        raw = bytes(b ^ text_xor for b in raw)
    return raw.split(b"\x00")[0].decode("shift_jis", errors="replace")


def _decode_instr(time: int, opcode: int, args: bytes, text_xor: int) -> Instruction:
    def need(n: int) -> None:
        if len(args) < n:
            raise ParseError(f"msg 指令 op{opcode} 参数截断: {len(args)} < {n}")

    if opcode == 0:
        return Delete(time)
    if opcode == 1:
        need(4)
        return ShowPortrait(time, *struct.unpack_from("<hh", args))
    if opcode == 2:
        need(4)
        return ChangeFace(time, *struct.unpack_from("<hh", args))
    if opcode == 3:
        need(4)
        color, line = struct.unpack_from("<hh", args)
        return Dialogue(time, color, line, _decode_text(args[4:], text_xor))
    if opcode == 4:
        need(4)
        return Pause(time, struct.unpack_from("<i", args)[0])
    if opcode == 5:
        need(3)
        idx, interrupt = struct.unpack_from("<hB", args)
        return Switch(time, idx, interrupt)
    if opcode == 6:
        return AppearEnemy(time)
    if opcode == 7:
        need(4)
        return Music(time, struct.unpack_from("<i", args)[0])
    if opcode == 8:
        need(4)
        color, line = struct.unpack_from("<hh", args)
        return TextIntroduce(time, color, line, _decode_text(args[4:], text_xor))
    if opcode == 9:
        return StageResults(time)
    if opcode == 10:
        return Freeze(time)
    if opcode == 11:
        return NextLevel(time)
    if opcode == 12:
        return FadeoutMusic(time)
    if opcode == 13:
        need(1)
        return AllowSkip(time, args[0])
    if opcode == 14:
        return FadeInEffect(time)
    if opcode == 15:
        need(20)
        vals = struct.unpack_from("<5i", args)
        return ConfigureAllPortraits(
            time, vals[0], (vals[1], vals[2], vals[3], vals[4])
        )
    if opcode == 16:
        return ShowSpeakerText(time, _decode_text(args, text_xor))
    if opcode == 17:
        need(8)
        portrait_idx, sprite = struct.unpack_from("<2i", args)
        return ConfigurePortrait(time, portrait_idx, sprite)
    if opcode == 18:
        need(1)
        return SetTextBoxVisible(time, bool(args[0]))
    if opcode == 19:
        return ShowTopText(time, _decode_text(args, text_xor))
    if opcode == 20:
        return ShowBottomText(time, _decode_text(args, text_xor))
    if opcode == 21:
        need(4)
        return ShowSelection(time, struct.unpack_from("<i", args)[0])
    if opcode == 22:
        return ReadSelectedMessage(time)
    raise ParseError(f"未知 msg 指令 opcode: {opcode}")


def parse_msg(data: bytes, *, text_xor: int = 0) -> MsgFile:
    """解析 msg 文件。

    Args:
        data: msgN.dat 字节
        text_xor: 文本解码 XOR 值(作品差异显式传入; 无加密 = 0, th08 = 0x77)
    """
    # 解析语义出处 old/touhou/schema/msg.py MsgFile.parse
    if len(data) < 4:
        raise ParseError("msg 文件太小, 没有指令数")
    (num,) = struct.unpack_from("<i", data, 0)
    if not (0 <= num <= _MAX_MESSAGES) or 4 + 4 * num > len(data):
        raise ParseError(f"非法 msg 指令流数: {num} (size={len(data)})")
    offsets = struct.unpack_from(f"<{num}i", data, 4)
    messages: list[tuple[Instruction, ...]] = []
    for idx, off in enumerate(offsets):
        if not (0 <= off < len(data)):
            raise ParseError(f"msg {idx}: 偏移越界 (off={off})")
        instrs: list[Instruction] = []
        pos = off
        while pos + 4 <= len(data):
            time, opcode, argsize = struct.unpack_from("<HBB", data, pos)
            if pos + 4 + argsize > len(data):
                raise ParseError(f"msg {idx}: 指令截断 (pos={pos})")
            instrs.append(
                _decode_instr(time, opcode, data[pos + 4 : pos + 4 + argsize], text_xor)
            )
            pos += 4 + argsize
            if opcode == 0:
                break
        else:
            raise ParseError(f"msg {idx}: 缺 Delete 终止 (off={off})")
        messages.append(tuple(instrs))
    return MsgFile(messages)
