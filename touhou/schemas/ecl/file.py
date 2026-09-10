"""ECL 文件解析: 头/sub 表/时间轴指令流 → EclFile。

文件头/sub 偏移表两种布局(version 0 = 无版本头, 0x800 = 带 u32 版本头)
是格式事实, 由 version 参数校验; 指令集与时间轴解码器是作品数据, 由
games/thNN 侧组好注入(薄包装见各作品 ecl_table 模块)。
"""

from __future__ import annotations

import struct
from collections.abc import Callable

from ..exceptions import ParseError
from .base import EclFile, EclInstr, EclSub, TlInstr
from .control import SubEnd
from .decode import InstrSet, decode_instr

#: 时间轴解码器: (文件字节, 起始偏移) → 一条时间轴的指令序列(作品注入)
TlDecoder = Callable[[bytes, int], tuple[TlInstr, ...]]


# ---- 文件解析 ----

_MAX_SUBS = 4096  # 同旧实现的防御上限(old/touhou/engine/ecl.py EclFile.parse)
_HEADER_V0 = 68  # counts(4) + timelineOffsets[16](64)
_HEADER_V800 = 0x48  # version(4) + counts(4) + timelineOffsets[16](64)


def _decode_sub(data: bytes, off: int, instrs: InstrSet) -> EclSub:
    start = off
    out: list[EclInstr] = []
    while True:
        instr = decode_instr(data, off, instrs=instrs)
        out.append(instr)
        (size,) = struct.unpack_from("<h", data, off + 6)  # 头的 size 字段步进
        off += size
        if isinstance(instr, SubEnd):
            break
    return EclSub(offset=start, instrs=tuple(out))


def parse_ecl(
    data: bytes, *, version: int, instrs: InstrSet, decode_tl: TlDecoder
) -> EclFile:
    """解析 .ecl 文件头/sub 表/时间轴指令流。

    Args:
        data: .ecl 字节
        version: 格式版本; 0 = 无版本头布局, 0x800 = 带 u32 版本头布局
            (头部结构 EclManager.hpp:277-288 / th08 EclManager.hpp:181-190,
            后者的 version 字段硬性校验 == 0x800)
        instrs: 作品指令集(作品的 ecl_table 模块提供)
        decode_tl: 时间轴解码器(作品的 ecl_timeline 模块提供)
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

    subs = tuple(_decode_sub(data, off, instrs) for off in sub_offsets)
    timelines = tuple(decode_tl(data, tl_offsets[i]) for i in range(tl_count))
    return EclFile(version=version, subs=subs, timelines=timelines)
