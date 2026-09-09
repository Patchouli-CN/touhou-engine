"""ANM 指令公共基类。"""

from __future__ import annotations

import msgspec


class AnmInstr(msgspec.Struct, frozen=True, tag_field="op"):
    """指令公共字段: time = 生效帧, flags = 参数间接变量位标记。"""

    # 指令头布局 AnmRawInstr: i16 opcode + u16 size + i16 time + u16 flags
    # (Reference/th07/src/th07/AnmManager.hpp:192-199)
    time: int
    flags: int
