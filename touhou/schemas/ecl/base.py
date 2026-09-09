"""ECL 操作数/指令/文件的公共数据结构。"""

from __future__ import annotations

import msgspec


class Operand(msgspec.Struct, frozen=True, tag_field="kind"):
    """ECL 操作数基类: 立即数或变量引用。"""


class ImmInt(Operand, frozen=True, tag=0):
    """i32 立即数。"""

    value: int


class ImmFloat(Operand, frozen=True, tag=1):
    """f32 立即数。"""

    value: float


class VarRef(Operand, frozen=True, tag=2):
    """变量引用(paramMask 置位): var_id 命中作品变量表(10000+)由执行器解析。"""

    # paramMask: bit i = 1 → args[i] 是变量 id 而非立即数
    # (Reference/th07/src/th07/EclManager.hpp:362-366, 375-397)
    var_id: int


IntOperand = ImmInt | VarRef
FloatOperand = ImmFloat | VarRef


class EclInstr(msgspec.Struct, frozen=True, tag_field="op"):
    """指令公共字段: offset = 文件偏移, time = 生效帧, skip_difficulty = 难度位掩码。"""

    # 指令头 EclRawInstr: u32 time + i16 id + i16 size + u8 unused +
    # u8 skipOnDifficulty + u16 paramMask (EclManager.hpp:291-299);
    # unused 字节与 paramMask 在解码时消费, 不进结构
    offset: int
    time: int
    skip_difficulty: int


class TlInstr(msgspec.Struct, frozen=True, tag_field="op"):
    """时间轴指令公共字段: time = 生效帧(负 = 时间轴结束)。"""

    time: int


class EclSub(msgspec.Struct, frozen=True):
    """一个 sub 的指令流(含结尾 SubEnd)。"""

    offset: int  # 文件内起始偏移
    instrs: tuple[EclInstr, ...]


class EclFile(msgspec.Struct, frozen=True):
    """解析后的 .ecl: sub 表 + 时间轴(布局差异由 parse 的 version 参数消化)。"""

    version: int
    subs: tuple[EclSub, ...]
    timelines: tuple[tuple[TlInstr, ...], ...]
