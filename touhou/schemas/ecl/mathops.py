"""ECL 变量运算指令(赋值/随机/算术/三角/插值/boss 变量), 两作共享部分。"""

from __future__ import annotations

from .base import EclInstr, FloatOperand, IntOperand, VarRef

# 编号出处同 control.py 头注; 操作数解析语义 EclManager.hpp:362-397
# (GetVar/GetVarValue/GetFloatVar/GetFloatVarValue):
# 存储目标 = paramMask 置位的变量 id(未置位 = 写入被丢弃, 解出 None);
# float 目标的变量 id 按 f32 值形式存(如 10004.0f), 解码还原成 int


class SetInt(EclInstr, frozen=True, tag="set_int"):
    """dest = value(int)。"""

    dest: VarRef | None
    value: IntOperand


class SetFloat(EclInstr, frozen=True, tag="set_float"):
    """dest = value(float)。"""

    dest: VarRef | None
    value: FloatOperand


class RandSign(EclInstr, frozen=True, tag="rand_sign"):
    """dest = 随机符号 × magnitude(int)。"""

    dest: VarRef | None
    magnitude: IntOperand


class RandSignFloat(EclInstr, frozen=True, tag="rand_sign_float"):
    """dest = 随机符号 × magnitude(float)。"""

    dest: VarRef | None
    magnitude: FloatOperand


class Add(EclInstr, frozen=True, tag="add"):
    """dest = a + b(int)。"""

    dest: VarRef | None
    a: IntOperand
    b: IntOperand


class Sub(EclInstr, frozen=True, tag="sub"):
    """dest = a - b(int)。"""

    dest: VarRef | None
    a: IntOperand
    b: IntOperand


class Mul(EclInstr, frozen=True, tag="mul"):
    """dest = a * b(int)。"""

    dest: VarRef | None
    a: IntOperand
    b: IntOperand


class Div(EclInstr, frozen=True, tag="div"):
    """dest = a / b(int, C 语义截断除法)。"""

    dest: VarRef | None
    a: IntOperand
    b: IntOperand


class Mod(EclInstr, frozen=True, tag="mod"):
    """dest = a % b(int, C 语义)。"""

    dest: VarRef | None
    a: IntOperand
    b: IntOperand


class AddFloat(EclInstr, frozen=True, tag="add_float"):
    """dest = a + b(float)。"""

    dest: VarRef | None
    a: FloatOperand
    b: FloatOperand


class SubFloat(EclInstr, frozen=True, tag="sub_float"):
    """dest = a - b(float)。"""

    dest: VarRef | None
    a: FloatOperand
    b: FloatOperand


class MulFloat(EclInstr, frozen=True, tag="mul_float"):
    """dest = a * b(float)。"""

    dest: VarRef | None
    a: FloatOperand
    b: FloatOperand


class DivFloat(EclInstr, frozen=True, tag="div_float"):
    """dest = a / b(float)。"""

    dest: VarRef | None
    a: FloatOperand
    b: FloatOperand


class ModFloat(EclInstr, frozen=True, tag="mod_float"):
    """dest = fmod(a, b)。"""

    dest: VarRef | None
    a: FloatOperand
    b: FloatOperand


class Inc(EclInstr, frozen=True, tag="inc"):
    """dest += 1(dest 非 VarRef 时无效果)。"""

    dest: VarRef | None


class Dec(EclInstr, frozen=True, tag="dec"):
    """dest -= 1(dest 非 VarRef 时无效果)。"""

    dest: VarRef | None


class Sin(EclInstr, frozen=True, tag="sin"):
    """dest = sin(value)。"""

    dest: VarRef | None
    value: FloatOperand


class Cos(EclInstr, frozen=True, tag="cos"):
    """dest = cos(value)。"""

    dest: VarRef | None
    value: FloatOperand


class Atan2(EclInstr, frozen=True, tag="atan2"):
    """dest = atan2(y2 - y1, x2 - x1)。"""

    dest: VarRef | None
    x1: FloatOperand
    y1: FloatOperand
    x2: FloatOperand
    y2: FloatOperand


class Lerp(EclInstr, frozen=True, tag="lerp"):
    """dest = (a - b) * t + b。"""

    # 公式 v0/v800 逐字相同(v800: EclDependencies.cpp:279-291)
    dest: VarRef | None
    a: FloatOperand
    b: FloatOperand
    t: FloatOperand


class InitInterp(EclInstr, frozen=True, tag="init_interp"):
    """注册跨帧变量插值: target_var 按 f32 值形式存的变量 id。"""

    # 8 参布局两作相同(v800: EclDependencies.cpp:350-377)
    target_var: int
    duration: IntOperand
    func: IntOperand
    easing: IntOperand
    p0: FloatOperand
    p1: FloatOperand
    p2: FloatOperand
    p3: FloatOperand


class NormalizeAngle(EclInstr, frozen=True, tag="normalize_angle"):
    """dest = 规范化到 [-π, π) 的 value(dest 与 value 同字)。"""

    dest: VarRef | None
    value: FloatOperand


class VecFromAngleMagRaw(EclInstr, frozen=True, tag="vec_from_angle_mag_raw"):
    """角度不规范化直接分解: dest_x = cos(angle)*mag, dest_y = sin(angle)*mag。"""

    # v0=151; v800=166(EclRunHigh.inl:868-881)
    dest_x: VarRef | None
    dest_y: VarRef | None
    angle: FloatOperand
    magnitude: FloatOperand


class RandExitAngle(EclInstr, frozen=True, tag="rand_exit_angle"):
    """dest = 简化版出场随机角(只看自机侧/右边缘)。"""

    # v0=155; v800=169(EclRunHigh.inl:882-893)
    dest: VarRef | None


class GetBossInt(EclInstr, frozen=True, tag="get_boss_int"):
    """dest = 以 boss_idx 号 boss 为上下文读 var(int)。"""

    # v0=43(EclManager.cpp:998-1002); v800=86(EclRunLow.inl:694-701)
    dest: VarRef | None
    var: IntOperand
    boss_idx: IntOperand


class GetBossFloat(EclInstr, frozen=True, tag="get_boss_float"):
    """dest = 以 boss_idx 号 boss 为上下文读 var(float)。"""

    dest: VarRef | None
    var: FloatOperand
    boss_idx: IntOperand
