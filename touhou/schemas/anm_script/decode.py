"""ANM 指令流 decode(字节 → 指令对象)。"""

from __future__ import annotations

import struct
from typing import Any, cast

import msgspec

from ..exceptions import ParseError
from .base import AnmInstr
from .control import (
    DecJump,
    Exit,
    ExitHide,
    ExitHide2,
    InterruptLabel,
    Jump,
    Nop,
    Stop,
    StopHide,
    Wait,
)
from .mathops import (
    Acos,
    Add,
    Add2,
    AddFloat,
    AddFloat2,
    Atan,
    Cos,
    Div,
    Div2,
    DivFloat,
    DivFloat2,
    JumpIfEq,
    JumpIfEqFloat,
    JumpIfGeq,
    JumpIfGeqFloat,
    JumpIfGt,
    JumpIfGtFloat,
    JumpIfLeq,
    JumpIfLeqFloat,
    JumpIfLt,
    JumpIfLtFloat,
    JumpIfNeq,
    JumpIfNeqFloat,
    Mod,
    Mod2,
    ModFloat,
    ModFloat2,
    Mov,
    MovFloat,
    Mul,
    Mul2,
    MulFloat,
    MulFloat2,
    NormalizeAngle,
    Rand,
    RandFloat,
    Sin,
    Sub,
    Sub2,
    SubFloat,
    SubFloat2,
    Tan,
)
from .visual import (
    Anchor3,
    Fade,
    FlipX,
    FlipY,
    InterpAlpha,
    InterpColor,
    InterpPos,
    InterpRotate,
    InterpScale,
    InterpScale2,
    PosTimeAccel,
    PosTimeDecel,
    PosTimeLinear,
    SetActiveSprite,
    SetAlpha,
    SetAngleVel,
    SetAutoRotate,
    SetBlend,
    SetCameraMode,
    SetColor,
    SetRotation,
    SetScale,
    SetScaleSpeed,
    SetScrollPosX,
    SetScrollPosY,
    SetScrollVelX,
    SetScrollVelY,
    SetTranslation,
    SetUseOffset,
    SetVisibility,
    SetZwriteDisable,
)

Instruction = (
    ExitHide
    | Nop
    | ExitHide2
    | Exit
    | SetActiveSprite
    | Jump
    | DecJump
    | SetTranslation
    | SetScale
    | SetAlpha
    | SetColor
    | FlipX
    | FlipY
    | SetRotation
    | SetAngleVel
    | SetScaleSpeed
    | Fade
    | SetBlend
    | PosTimeLinear
    | PosTimeDecel
    | PosTimeAccel
    | Stop
    | InterruptLabel
    | Anchor3
    | StopHide
    | SetUseOffset
    | SetAutoRotate
    | SetScrollPosX
    | SetScrollPosY
    | SetVisibility
    | InterpScale
    | SetZwriteDisable
    | SetCameraMode
    | InterpPos
    | InterpColor
    | InterpAlpha
    | InterpRotate
    | InterpScale2
    | Mov
    | MovFloat
    | Add
    | AddFloat
    | Sub
    | SubFloat
    | Mul
    | MulFloat
    | Div
    | DivFloat
    | Mod
    | ModFloat
    | Add2
    | AddFloat2
    | Sub2
    | SubFloat2
    | Mul2
    | MulFloat2
    | Div2
    | DivFloat2
    | Mod2
    | ModFloat2
    | Rand
    | RandFloat
    | Sin
    | Cos
    | Tan
    | Acos
    | Atan
    | NormalizeAngle
    | JumpIfEq
    | JumpIfEqFloat
    | JumpIfNeq
    | JumpIfNeqFloat
    | JumpIfLt
    | JumpIfLtFloat
    | JumpIfLeq
    | JumpIfLeqFloat
    | JumpIfGt
    | JumpIfGtFloat
    | JumpIfGeq
    | JumpIfGeqFloat
    | Wait
    | SetScrollVelX
    | SetScrollVelY
)

# opcode → 指令类(AnmOpcode 枚举全集 AnmManager.hpp:30-114, 另加实测存在的 0=Nop)
_DECODERS: dict[int, type[AnmInstr]] = {
    -1: ExitHide,
    0: Nop,
    1: ExitHide2,
    2: Exit,
    3: SetActiveSprite,
    4: Jump,
    5: DecJump,
    6: SetTranslation,
    7: SetScale,
    8: SetAlpha,
    9: SetColor,
    10: FlipX,
    11: FlipY,
    12: SetRotation,
    13: SetAngleVel,
    14: SetScaleSpeed,
    15: Fade,
    16: SetBlend,
    17: PosTimeLinear,
    18: PosTimeDecel,
    19: PosTimeAccel,
    20: Stop,
    21: InterruptLabel,
    22: Anchor3,
    23: StopHide,
    24: SetUseOffset,
    25: SetAutoRotate,
    26: SetScrollPosX,
    27: SetScrollPosY,
    28: SetVisibility,
    29: InterpScale,
    30: SetZwriteDisable,
    31: SetCameraMode,
    32: InterpPos,
    33: InterpColor,
    34: InterpAlpha,
    35: InterpRotate,
    36: InterpScale2,
    37: Mov,
    38: MovFloat,
    39: Add,
    40: AddFloat,
    41: Sub,
    42: SubFloat,
    43: Mul,
    44: MulFloat,
    45: Div,
    46: DivFloat,
    47: Mod,
    48: ModFloat,
    49: Add2,
    50: AddFloat2,
    51: Sub2,
    52: SubFloat2,
    53: Mul2,
    54: MulFloat2,
    55: Div2,
    56: DivFloat2,
    57: Mod2,
    58: ModFloat2,
    59: Rand,
    60: RandFloat,
    61: Sin,
    62: Cos,
    63: Tan,
    64: Acos,
    65: Atan,
    66: NormalizeAngle,
    67: JumpIfEq,
    68: JumpIfEqFloat,
    69: JumpIfNeq,
    70: JumpIfNeqFloat,
    71: JumpIfLt,
    72: JumpIfLtFloat,
    73: JumpIfLeq,
    74: JumpIfLeqFloat,
    75: JumpIfGt,
    76: JumpIfGtFloat,
    77: JumpIfGeq,
    78: JumpIfGeqFloat,
    79: Wait,
    80: SetScrollVelX,
    81: SetScrollVelY,
}


def decode_instr(data: bytes, p: int, size: int) -> Instruction:
    """按参数布局把一条指令的 args 区 decode 成对应指令对象。

    参数区是 i32/f32 的双视图(AnyArg 数组), 每个参数按指令类的字段注解
    取 int 或 float 视图; 参数个数与指令布局不符抛 ParseError。
    """
    opcode, _size, time, flags = struct.unpack_from("<hHhH", data, p)
    cls = _DECODERS.get(opcode)
    if cls is None:
        raise ParseError(f"未知 anm 指令 opcode: {opcode}")
    nargs = (size - 8) // 4
    # 前两个字段是公共的 time/flags; stub 把 fields() 切片推成 Any,
    # 显式注解(msgspec/structs.pyi:37)
    arg_fields: tuple[msgspec.structs.FieldInfo, ...] = msgspec.structs.fields(cls)[2:]
    if len(arg_fields) != nargs:
        raise ParseError(
            f"anm 指令 {cls.__name__} 参数数不符: 声明 {len(arg_fields)}, 实际 {nargs}"
        )
    args_i = struct.unpack_from(f"<{nargs}i", data, p + 8)
    args_f = struct.unpack_from(f"<{nargs}f", data, p + 8)
    kwargs: dict[str, Any] = {}
    for i, fld in enumerate(arg_fields):
        kwargs[fld.name] = args_f[i] if fld.type is float else args_i[i]
    return cast("Instruction", cls(time=time, flags=flags, **kwargs))


def decode_script(data: bytes, offset: int) -> list[Instruction]:
    """从 offset 起 decode 一段脚本, 到 ExitHide(opcode -1) 或数据尽头为止。"""
    # 脚本段以 -1 结尾, 出处 old/touhou/schema/anm.py parse_scripts
    out: list[Instruction] = []
    p = offset
    while p + 8 <= len(data):
        opcode, size, _time, _flags = struct.unpack_from("<hHhH", data, p)
        if size < 8 or p + size > len(data):
            break
        out.append(decode_instr(data, p, size))
        if opcode == -1:
            break
        p += size
    return out
