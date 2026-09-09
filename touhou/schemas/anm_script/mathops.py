"""ANM 变量运算与条件跳转指令。"""

from __future__ import annotations

from .base import AnmInstr

# opcode 出处 Reference/th07/src/th07/AnmManager.hpp:30-114(AnmOpcode 枚举);
# dst/src 为变量 id 时由 flags 位标记间接寻址(变量 id 表 AnmManager.hpp:16-28)


class Mov(AnmInstr, frozen=True, tag=37):
    """整数变量赋值。"""

    dst: int
    src: int


class MovFloat(AnmInstr, frozen=True, tag=38):
    """浮点变量赋值。"""

    dst: float
    src: float


class Add(AnmInstr, frozen=True, tag=39):
    """dst += src。"""

    dst: int
    src: int


class AddFloat(AnmInstr, frozen=True, tag=40):
    """dst += src(浮点)。"""

    dst: float
    src: float


class Sub(AnmInstr, frozen=True, tag=41):
    """dst -= src。"""

    dst: int
    src: int


class SubFloat(AnmInstr, frozen=True, tag=42):
    """dst -= src(浮点)。"""

    dst: float
    src: float


class Mul(AnmInstr, frozen=True, tag=43):
    """dst *= src。"""

    dst: int
    src: int


class MulFloat(AnmInstr, frozen=True, tag=44):
    """dst *= src(浮点)。"""

    dst: float
    src: float


class Div(AnmInstr, frozen=True, tag=45):
    """dst //= src。"""

    dst: int
    src: int


class DivFloat(AnmInstr, frozen=True, tag=46):
    """dst /= src(浮点)。"""

    dst: float
    src: float


class Mod(AnmInstr, frozen=True, tag=47):
    """dst %= src。"""

    dst: int
    src: int


class ModFloat(AnmInstr, frozen=True, tag=48):
    """dst fmod= src。"""

    dst: float
    src: float


class Add2(AnmInstr, frozen=True, tag=49):
    """dst = a + b。"""

    dst: int
    a: int
    b: int


class AddFloat2(AnmInstr, frozen=True, tag=50):
    """dst = a + b(浮点)。"""

    dst: float
    a: float
    b: float


class Sub2(AnmInstr, frozen=True, tag=51):
    """dst = a - b。"""

    dst: int
    a: int
    b: int


class SubFloat2(AnmInstr, frozen=True, tag=52):
    """dst = a - b(浮点)。"""

    dst: float
    a: float
    b: float


class Mul2(AnmInstr, frozen=True, tag=53):
    """dst = a * b。"""

    dst: int
    a: int
    b: int


class MulFloat2(AnmInstr, frozen=True, tag=54):
    """dst = a * b(浮点)。"""

    dst: float
    a: float
    b: float


class Div2(AnmInstr, frozen=True, tag=55):
    """dst = a // b。"""

    dst: int
    a: int
    b: int


class DivFloat2(AnmInstr, frozen=True, tag=56):
    """dst = a / b(浮点)。"""

    dst: float
    a: float
    b: float


class Mod2(AnmInstr, frozen=True, tag=57):
    """dst = a % b。"""

    dst: int
    a: int
    b: int


class ModFloat2(AnmInstr, frozen=True, tag=58):
    """dst = fmod(a, b)。"""

    dst: float
    a: float
    b: float


class Rand(AnmInstr, frozen=True, tag=59):
    """dst = [0, bound) 随机整数。"""

    dst: int
    bound: int


class RandFloat(AnmInstr, frozen=True, tag=60):
    """dst = [0, bound) 随机浮点。"""

    dst: float
    bound: float


class Sin(AnmInstr, frozen=True, tag=61):
    """dst = sin(src)。"""

    dst: float
    src: float


class Cos(AnmInstr, frozen=True, tag=62):
    """dst = cos(src)。"""

    dst: float
    src: float


class Tan(AnmInstr, frozen=True, tag=63):
    """dst = tan(src)。"""

    dst: float
    src: float


class Acos(AnmInstr, frozen=True, tag=64):
    """dst = acos(src)。"""

    dst: float
    src: float


class Atan(AnmInstr, frozen=True, tag=65):
    """dst = atan(src)。"""

    dst: float
    src: float


class NormalizeAngle(AnmInstr, frozen=True, tag=66):
    """dst 归一化到 [-pi, pi]。"""

    dst: float


class JumpIfEq(AnmInstr, frozen=True, tag=67):
    """x == y 则跳转。"""

    x: int
    y: int
    dest: int
    set_time: int


class JumpIfEqFloat(AnmInstr, frozen=True, tag=68):
    """x == y 则跳转(浮点)。"""

    x: float
    y: float
    dest: int
    set_time: int


class JumpIfNeq(AnmInstr, frozen=True, tag=69):
    """x != y 则跳转。"""

    x: int
    y: int
    dest: int
    set_time: int


class JumpIfNeqFloat(AnmInstr, frozen=True, tag=70):
    """x != y 则跳转(浮点)。"""

    x: float
    y: float
    dest: int
    set_time: int


class JumpIfLt(AnmInstr, frozen=True, tag=71):
    """x < y 则跳转。"""

    x: int
    y: int
    dest: int
    set_time: int


class JumpIfLtFloat(AnmInstr, frozen=True, tag=72):
    """x < y 则跳转(浮点)。"""

    x: float
    y: float
    dest: int
    set_time: int


class JumpIfLeq(AnmInstr, frozen=True, tag=73):
    """x <= y 则跳转。"""

    x: int
    y: int
    dest: int
    set_time: int


class JumpIfLeqFloat(AnmInstr, frozen=True, tag=74):
    """x <= y 则跳转(浮点)。"""

    x: float
    y: float
    dest: int
    set_time: int


class JumpIfGt(AnmInstr, frozen=True, tag=75):
    """x > y 则跳转。"""

    x: int
    y: int
    dest: int
    set_time: int


class JumpIfGtFloat(AnmInstr, frozen=True, tag=76):
    """x > y 则跳转(浮点)。"""

    x: float
    y: float
    dest: int
    set_time: int


class JumpIfGeq(AnmInstr, frozen=True, tag=77):
    """x >= y 则跳转。"""

    x: int
    y: int
    dest: int
    set_time: int


class JumpIfGeqFloat(AnmInstr, frozen=True, tag=78):
    """x >= y 则跳转(浮点)。"""

    x: float
    y: float
    dest: int
    set_time: int
