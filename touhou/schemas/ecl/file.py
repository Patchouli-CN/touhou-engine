"""ECL 文件解析: 头/sub 表/时间轴指令流 → EclFile。

时间轴两种布局: v0 = i16 time/arg0/opcode/size + 6 个 u32 参数字;
v800 = i32 time + i16 opcode + u8 size + u8 难度掩码 + 参数字
(出处见 timeline.py 头注)。
"""

from __future__ import annotations

import struct
from typing import TYPE_CHECKING

from ..exceptions import ParseError
from .base import EclFile, EclSub
from .control import SubEnd
from .decode import _f32, _i32, decode_instr
from .timeline import (
    TimelineInstr,
    TlEnd,
    TlEndV800,
    TlEventConsume,
    TlEventEmit,
    TlMsgRead,
    TlMsgReadV800,
    TlMsgWait,
    TlMsgWaitV800,
    TlSetBossInterrupt,
    TlSetBossPendingSub,
    TlSetPower,
    TlSetPowerV800,
    TlShowRetryMenu,
    TlSpawn,
    TlSpawnAt,
    TlSpawnDrops,
    TlSpawnRandomX,
    TlSpawnRangeX,
    TlWaitBossDead,
    TlWaitBossDeadV800,
)

if TYPE_CHECKING:
    from . import Instruction  # 仅类型检查期(__init__ 运行时依赖本模块)


_TL_HEADER_V0 = struct.Struct("<hhhh")  # time, arg0, opcode, size
_TL_HEADER_V800 = struct.Struct("<ihBB")  # time, opcode, size, difficultyMask


# ---- 时间轴 decode ----


def _decode_timeline_v0(data: bytes, off: int) -> tuple[TimelineInstr, ...]:
    """v0 时间轴: 8 字节头(i16×4) + 6 个 u32 参数字, time<0 结束。"""
    out: list[TimelineInstr] = []
    while off < len(data):
        if off + _TL_HEADER_V0.size > len(data):
            # 尾部可能有截短终止记录(如 ff ff 04 00, time=-1)
            tail = (
                struct.unpack_from("<h", data, off)[0] if off + 2 <= len(data) else -1
            )
            if tail < 0:
                out.append(TlEnd(time=tail))
                break
            raise ParseError(f"timeline 越界 (off={off:#x})")
        time, arg0, opcode, size = _TL_HEADER_V0.unpack_from(data, off)
        if size < 8 or (size - 8) % 4 != 0 or off + size > len(data):
            raise ParseError(f"timeline 非法 size={size} (off={off:#x})")
        nargs = (size - 8) // 4
        words = struct.unpack_from(f"<{nargs}I", data, off + 8)
        if time < 0:
            out.append(TlEnd(time=time, args=words))
            break
        if 0 <= opcode <= 7:
            if nargs != 6:
                raise ParseError(f"tl_spawn 参数数不符: {nargs} != 6 (off={off:#x})")
            out.append(
                TlSpawn(
                    time,
                    sub_id=arg0,
                    mode=opcode,
                    x=_f32(words[0]),
                    y=_f32(words[1]),
                    z=_f32(words[2]),
                    life=_i32(words[3]),
                    item_drop=_i32(words[4]),
                    score=_i32(words[5]),
                )
            )
        elif opcode == 8:
            out.append(TlMsgRead(time, msg_id=arg0))
        elif opcode == 9:
            out.append(TlMsgWait(time))
        elif opcode == 10:
            if nargs != 2:
                raise ParseError(
                    f"tl_set_boss_interrupt 参数数不符: {nargs} != 2 (off={off:#x})"
                )
            out.append(
                TlSetBossInterrupt(
                    time, boss_idx=_i32(words[0]), interrupt=_i32(words[1])
                )
            )
        elif opcode == 11:
            out.append(TlSetPower(time, value=arg0))
        elif opcode == 12:
            out.append(TlWaitBossDead(time, boss_idx=arg0))
        else:
            raise ParseError(f"未知 v0 时间轴 opcode: {opcode} (off={off:#x})")
        off += size
    return tuple(out)


def _decode_timeline_v800(data: bytes, off: int) -> tuple[TimelineInstr, ...]:
    """v800 时间轴: 8 字节头(i32 time + i16 opcode + u8 size + u8 难度掩码) + 参数字。"""
    out: list[TimelineInstr] = []
    while off < len(data):
        if off + _TL_HEADER_V800.size > len(data):
            tail = (
                struct.unpack_from("<h", data, off)[0] if off + 2 <= len(data) else -1
            )
            if tail < 0:
                out.append(TlEndV800(time=tail, difficulty_mask=0))
                break
            raise ParseError(f"timeline 越界 (off={off:#x})")
        time, opcode, size, dm = _TL_HEADER_V800.unpack_from(data, off)
        if size == 0 and time < 0:
            # 截短终止记录: 只有 8 字节头, size 字段为 0(真实数据 ecldata8 tl1)
            out.append(TlEndV800(time=time, difficulty_mask=dm))
            break
        if size < 8 or (size - 8) % 4 != 0 or off + size > len(data):
            raise ParseError(f"timeline 非法 size={size} (off={off:#x})")
        nargs = (size - 8) // 4
        words = struct.unpack_from(f"<{nargs}I", data, off + 8)
        if time < 0:
            out.append(TlEndV800(time=time, difficulty_mask=dm, args=words))
            break

        def need(n: int) -> None:
            if nargs != n:
                raise ParseError(
                    f"timeline op{opcode} 参数数不符: {nargs} != {n} (off={off:#x})"
                )

        if opcode in (0, 1, 15):  # 定点生敌(1=镜像, 15=无门控)
            need(6)
            out.append(
                TlSpawnAt(
                    time,
                    difficulty_mask=dm,
                    sub_id=_i32(words[0]),
                    mirror=opcode == 1,
                    forced=opcode == 15,
                    x=_f32(words[1]),
                    y=_f32(words[2]),
                    life=_i32(words[3]),
                    item_drop=_i32(words[4]),
                    score=_i32(words[5]),
                )
            )
        elif opcode in (2, 4):  # x 区间随机(4=镜像)
            need(7)
            out.append(
                TlSpawnRangeX(
                    time,
                    difficulty_mask=dm,
                    sub_id=_i32(words[0]),
                    mirror=opcode == 4,
                    x_lo=_f32(words[1]),
                    x_hi=_f32(words[2]),
                    y=_f32(words[3]),
                    life=_i32(words[4]),
                    item_drop=_i32(words[5]),
                    score=_i32(words[6]),
                )
            )
        elif opcode in (3, 5):  # 全屏随机 x
            need(5)
            out.append(
                TlSpawnRandomX(
                    time,
                    difficulty_mask=dm,
                    sub_id=_i32(words[0]),
                    y=_f32(words[1]),
                    life=_i32(words[2]),
                    item_drop=_i32(words[3]),
                    score=_i32(words[4]),
                )
            )
        elif opcode in (11, 12):  # 带掉落数(12=镜像)
            need(7)
            out.append(
                TlSpawnDrops(
                    time,
                    difficulty_mask=dm,
                    sub_id=_i32(words[0]),
                    mirror=opcode == 12,
                    x=_f32(words[1]),
                    y=_f32(words[2]),
                    life=_i32(words[3]),
                    point_drops=_i32(words[4]),
                    power_or_point_drops=_i32(words[5]),
                    score=_i32(words[6]),
                )
            )
        elif opcode == 6:
            need(1)
            out.append(TlMsgReadV800(time, difficulty_mask=dm, msg_id=_i32(words[0])))
        elif opcode == 7:
            need(0)
            out.append(TlMsgWaitV800(time, difficulty_mask=dm))
        elif opcode == 8:
            need(2)
            out.append(
                TlSetBossPendingSub(
                    time,
                    difficulty_mask=dm,
                    boss_idx=_i32(words[0]),
                    sub_id=_i32(words[1]),
                )
            )
        elif opcode == 9:
            need(1)
            out.append(TlSetPowerV800(time, difficulty_mask=dm, value=_i32(words[0])))
        elif opcode == 10:
            need(1)
            out.append(
                TlWaitBossDeadV800(time, difficulty_mask=dm, boss_idx=_i32(words[0]))
            )
        elif opcode == 13:
            need(1)
            out.append(TlEventConsume(time, difficulty_mask=dm, value=_i32(words[0])))
        elif opcode == 14:
            need(1)
            out.append(TlEventEmit(time, difficulty_mask=dm, value=_i32(words[0])))
        elif opcode == 16:
            need(0)
            out.append(TlShowRetryMenu(time, difficulty_mask=dm))
        else:
            raise ParseError(f"未知 v800 时间轴 opcode: {opcode} (off={off:#x})")
        off += size
    return tuple(out)


# ---- 文件解析 ----

_MAX_SUBS = 4096  # 同旧实现的防御上限(old/touhou/engine/ecl.py EclFile.parse)
_HEADER_V0 = 68  # counts(4) + timelineOffsets[16](64)
_HEADER_V800 = 0x48  # version(4) + counts(4) + timelineOffsets[16](64)


def _decode_sub(data: bytes, off: int, version: int) -> EclSub:
    start = off
    instrs: list[Instruction] = []
    while True:
        instr = decode_instr(data, off, version=version)
        instrs.append(instr)
        (size,) = struct.unpack_from("<h", data, off + 6)  # 头的 size 字段步进
        off += size
        if isinstance(instr, SubEnd):
            break
    return EclSub(offset=start, instrs=tuple(instrs))


def parse_ecl(data: bytes, *, version: int = 0) -> EclFile:
    """解析 .ecl 文件头/sub 表/时间轴指令流。

    Args:
        data: .ecl 字节
        version: 格式版本; 0 = 无版本头布局, 0x800 = 带 u32 版本头布局
            (头部结构 EclManager.hpp:277-288 / th08 EclManager.hpp:181-190,
            后者的 version 字段硬性校验 == 0x800)
    """
    if version == 0:
        if len(data) < _HEADER_V0:
            raise ParseError("文件太小, 没有完整 ECL 头")
        sub_count, tl_count = struct.unpack_from("<hh", data, 0)
        header = _HEADER_V0
    elif version == 0x800:
        if len(data) < _HEADER_V800:
            raise ParseError("文件太小, 没有完整 ECL 头")
        magic, sub_count, tl_count = struct.unpack_from("<Ihh", data, 0)
        if magic != 0x800:
            raise ParseError(f"非法 ECL version: {magic:#x} (期望 0x800)")
        header = _HEADER_V800
    else:
        raise ParseError(f"未知 ecl 格式版本: {version:#x} (已知: 0, 0x800)")
    if not (0 <= sub_count <= _MAX_SUBS and 0 <= tl_count <= 16):
        raise ParseError(f"非法 ECL 头: subCount={sub_count} timelineCount={tl_count}")
    if header + 4 * sub_count > len(data):
        raise ParseError(f"ECL sub 表截断: subCount={sub_count} (size={len(data)})")
    word = "i" if version == 0 else "I"
    tl_offsets = struct.unpack_from(f"<16{word}", data, header - 64)
    sub_offsets = struct.unpack_from(f"<{sub_count}{word}", data, header)

    subs = tuple(_decode_sub(data, off, version) for off in sub_offsets)
    decode_tl = _decode_timeline_v0 if version == 0 else _decode_timeline_v800
    timelines = tuple(decode_tl(data, tl_offsets[i]) for i in range(tl_count))
    return EclFile(version=version, subs=subs, timelines=timelines)
