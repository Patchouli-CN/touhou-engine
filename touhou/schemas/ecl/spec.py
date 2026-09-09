"""ECL 参数字段解码规格(_A/_Entry)与组表辅助工厂。"""

from __future__ import annotations

from typing import Any, NamedTuple

from .base import EclInstr
from .bullets import SpawnBulletPattern, SpawnLaserPattern, SpawnLaserPatternV800
from .control import (
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
)
from .mathops import (
    Add,
    AddAssign,
    AddAssignFloat,
    AddFloat,
    Div,
    DivAssign,
    DivAssignFloat,
    DivFloat,
    Mod,
    ModAssign,
    ModAssignFloat,
    ModFloat,
    Mul,
    MulAssign,
    MulAssignFloat,
    MulFloat,
    Sub,
    SubAssign,
    SubAssignFloat,
    SubFloat,
)


class _A(NamedTuple):
    """一个参数字段的解码规格: args 区第 word 个 u32 字按 view 视图解。

    view: "int"/"float" = 可变参操作数(paramMask 置位 → VarRef);
    "int_t"/"float_t" = 存储目标(置位 → VarRef, 否则 None);
    "ri"/"rf" = raw i32/f32; "h0"/"h1" = i16 低/高半字; "hu0"/"hu1" = u16;
    "h0m"/"h1m" = 可变参 i16 半字; "b0"/"b1" = u8 字节; "sb0"/"sb2" = i8;
    "fvid" = f32 值形式存的变量 id; "rest" = word 起剩余原始字。
    """

    name: str
    word: int
    view: str
    bit: int = -1  # paramMask 位(-1 = 与 word 同号)


class _Entry(NamedTuple):
    """一条 opcode 的解码表项: 指令类 + 字段规格 + 非字节来源的常量字段。"""

    cls: type[EclInstr]
    args: tuple[_A, ...] = ()
    consts: dict[str, Any] = {}


def _cond(cls: type[EclInstr], float_: bool) -> _Entry:
    """条件跳表项(int/float 视图按 float_ 切换)。"""
    v = "float" if float_ else "int"
    return _Entry(
        cls,
        (_A("a", 0, v), _A("b", 1, v), _A("dest", 2, "ri"), _A("set_time", 3, "ri")),
    )


def _bullet(aim_mode: int) -> _Entry:
    """弹幕生成表项(9 个 opcode 共享布局, aim_mode 按 opcode 填入)。"""
    return _Entry(
        SpawnBulletPattern,
        (
            _A("sprite", 0, "h0m", 0),
            _A("sprite_offset", 0, "h1m", 1),
            _A("count1", 1, "int", 2),
            _A("count2", 2, "int", 3),
            _A("speed1", 3, "float", 4),
            _A("speed2", 4, "float", 5),
            _A("angle1", 5, "float", 6),
            _A("angle2", 6, "float", 7),
            _A("flags", 7, "ri"),
        ),
        {"aim_mode": aim_mode},
    )


def _laser_v0(moving: bool) -> _Entry:
    """v0 激光表项(width/计时/flags 全 raw)。"""
    return _Entry(
        SpawnLaserPattern,
        (
            _A("sprite", 0, "h0"),
            _A("sprite_offset", 0, "h1m", 1),
            _A("angle", 1, "float", 2),
            _A("speed", 2, "float", 3),
            _A("start_offset", 3, "float", 4),
            _A("end_offset", 4, "float", 5),
            _A("start_length", 5, "float", 6),
            _A("width", 6, "rf"),
            _A("start_time", 7, "ri"),
            _A("duration", 8, "ri"),
            _A("end_time", 9, "ri"),
            _A("hitbox_start_time", 10, "ri"),
            _A("hitbox_end_time", 11, "ri"),
            _A("flags", 12, "ri"),
        ),
        {"moving": moving},
    )


def _laser_v800(aimed: bool) -> _Entry:
    """v800 激光表项(width/计时可变参)。"""
    return _Entry(
        SpawnLaserPatternV800,
        (
            _A("sprite", 0, "hu0"),
            _A("sprite_offset", 0, "h1m", 1),
            _A("angle", 1, "float", 2),
            _A("speed", 2, "float", 3),
            _A("start_offset", 3, "float", 4),
            _A("end_offset", 4, "float", 5),
            _A("start_length", 5, "float", 6),
            _A("width", 6, "float", 7),
            _A("start_time", 7, "int", 8),
            _A("duration", 8, "int", 9),
            _A("despawn_duration", 9, "int", 10),
            _A("hitbox_start_time", 10, "ri"),
            _A("hitbox_end_delay", 11, "ri"),
            _A("flags", 12, "ri"),
        ),
        {"aimed": aimed},
    )


def _spawn_enemy(cls: type[EclInstr]) -> _Entry:
    """敌生成表项(abs/rel 同布局)。"""
    return _Entry(
        cls,
        (
            _A("sub_id", 0, "ri"),
            _A("x", 1, "float"),
            _A("y", 2, "float"),
            _A("z", 3, "float"),
            _A("life", 4, "int"),
            _A("item_drop", 5, "int"),
            _A("score", 6, "int"),
        ),
    )


def _familiar(cls: type[EclInstr]) -> _Entry:
    """使魔生成表项(v800, 三个 opcode 同布局)。"""
    return _Entry(
        cls,
        (
            _A("sub_id", 0, "ri"),
            _A("x", 1, "float"),
            _A("y", 2, "float"),
            _A("life", 3, "int"),
            _A("item_drop", 4, "int"),
            _A("score", 5, "int"),
        ),
    )


_INT_ARITH: tuple[type[EclInstr], ...] = (Add, Sub, Mul, Div, Mod)
_FLOAT_ARITH: tuple[type[EclInstr], ...] = (
    AddFloat,
    SubFloat,
    MulFloat,
    DivFloat,
    ModFloat,
)
_INT_ASSIGN: tuple[type[EclInstr], ...] = (
    AddAssign,
    SubAssign,
    MulAssign,
    DivAssign,
    ModAssign,
)
_FLOAT_ASSIGN: tuple[type[EclInstr], ...] = (
    AddAssignFloat,
    SubAssignFloat,
    MulAssignFloat,
    DivAssignFloat,
    ModAssignFloat,
)
_CONDS: tuple[tuple[type[EclInstr], bool], ...] = (
    (JumpIfEq, False),
    (JumpIfEqFloat, True),
    (JumpIfNeq, False),
    (JumpIfNeqFloat, True),
    (JumpIfLt, False),
    (JumpIfLtFloat, True),
    (JumpIfLeq, False),
    (JumpIfLeqFloat, True),
    (JumpIfGt, False),
    (JumpIfGtFloat, True),
    (JumpIfGeq, False),
    (JumpIfGeqFloat, True),
)
