"""变量运算 handler: 赋值/随机/算术/三角/插值/boss 变量读。

语义移植 old/touhou/engine/ecl_std_ops.py + old/touhou/games/th07/ecl_vm.py
同名 handler(除零守卫/C 截断语义/f32 落盘都在); 出处 EclManager.cpp 各 case。
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from ....schemas.ecl import (
    Add,
    AddAssign,
    AddAssignFloat,
    AddFloat,
    Atan2,
    Cos,
    Dec,
    Dist,
    Div,
    DivAssign,
    DivAssignFloat,
    DivFloat,
    EclInstr,
    GetBossFloat,
    GetBossInt,
    GetExitAngle,
    Inc,
    InitInterp,
    Lerp,
    Mod,
    ModAssign,
    ModAssignFloat,
    ModFloat,
    Mul,
    MulAssign,
    MulAssignFloat,
    MulFloat,
    NormalizeAngle,
    Rand,
    RandAdd,
    RandExitAngle,
    RandFloat,
    RandFloatAdd,
    RandFloatRange,
    RandSign,
    RandSignFloat,
    SetFloat,
    SetInt,
    Sin,
    Sub,
    SubAssign,
    SubAssignFloat,
    SubFloat,
    VecFromAngleMag,
    VecFromAngleMagRaw,
)
from ..num import cdiv, cmod, norm_angle

if TYPE_CHECKING:
    from ..machine import EclMachine  # 仅类型检查期(机器运行时依赖本包)

from .base import Handler


def _set_int(m: EclMachine, ins: SetInt) -> None:
    m.store_int(ins.dest, m.ival(ins.value))


def _set_float(m: EclMachine, ins: SetFloat) -> None:
    m.store_float(ins.dest, m.fval(ins.value))


# ---- 随机(rng 注入, 同种子同序列) ----


def _rand(m: EclMachine, ins: Rand) -> None:
    m.store_int(ins.dest, m.rng.int_below(m.ival(ins.bound)))


def _rand_add(m: EclMachine, ins: RandAdd) -> None:
    m.store_int(ins.dest, m.rng.int_below(m.ival(ins.bound)) + m.ival(ins.addend))


def _rand_float(m: EclMachine, ins: RandFloat) -> None:
    m.store_float(ins.dest, m.rng.unit() * m.fval(ins.scale))


def _rand_float_add(m: EclMachine, ins: RandFloatAdd) -> None:
    m.store_float(ins.dest, m.rng.unit() * m.fval(ins.scale) + m.fval(ins.addend))


def _rand_float_range(m: EclMachine, ins: RandFloatRange) -> None:
    lo = m.fval(ins.lo)
    m.store_float(ins.dest, m.rng.unit() * (m.fval(ins.hi) - lo) + lo)


def _rand_sign(m: EclMachine, ins: RandSign) -> None:
    m.store_int(ins.dest, m.rng.sign() * m.ival(ins.magnitude))


def _rand_sign_float(m: EclMachine, ins: RandSignFloat) -> None:
    m.store_float(ins.dest, float(m.rng.sign()) * m.fval(ins.magnitude))


# ---- 算术: 3 操作数(+-*/%)与 v800 的 2 操作数自赋值 ----

_INT_BINOP = {
    Add: lambda a, b: a + b,
    Sub: lambda a, b: a - b,
    Mul: lambda a, b: a * b,
    Div: lambda a, b: cdiv(a, b) if b else 0,
    Mod: lambda a, b: cmod(a, b) if b else 0,
}
_FLOAT_BINOP = {
    AddFloat: lambda a, b: a + b,
    SubFloat: lambda a, b: a - b,
    MulFloat: lambda a, b: a * b,
    DivFloat: lambda a, b: a / b if b != 0.0 else 0.0,
    ModFloat: lambda a, b: math.fmod(a, b) if b != 0.0 else 0.0,
}
_INT_ASSIGN = {
    AddAssign: _INT_BINOP[Add],
    SubAssign: _INT_BINOP[Sub],
    MulAssign: _INT_BINOP[Mul],
    DivAssign: _INT_BINOP[Div],
    ModAssign: _INT_BINOP[Mod],
}
_FLOAT_ASSIGN = {
    AddAssignFloat: _FLOAT_BINOP[AddFloat],
    SubAssignFloat: _FLOAT_BINOP[SubFloat],
    MulAssignFloat: _FLOAT_BINOP[MulFloat],
    DivAssignFloat: _FLOAT_BINOP[DivFloat],
    ModAssignFloat: _FLOAT_BINOP[ModFloat],
}


def _int_arith(m: EclMachine, ins: EclInstr) -> None:
    m.store_int(ins.dest, _INT_BINOP[type(ins)](m.ival(ins.a), m.ival(ins.b)))  # type: ignore[attr-defined]


def _float_arith(m: EclMachine, ins: EclInstr) -> None:
    m.store_float(ins.dest, _FLOAT_BINOP[type(ins)](m.fval(ins.a), m.fval(ins.b)))  # type: ignore[attr-defined]


def _int_assign(m: EclMachine, ins: EclInstr) -> None:
    # 2 操作数自赋值: dest 非变量时整丢弃(v800, EclRunLow.inl:236-330)
    if ins.dest is not None:  # type: ignore[attr-defined]
        t = ins.dest.var_id  # type: ignore[attr-defined]
        m.write_int(t, _INT_ASSIGN[type(ins)](m.read_int(t), m.ival(ins.value)))  # type: ignore[attr-defined]


def _float_assign(m: EclMachine, ins: EclInstr) -> None:
    if ins.dest is not None:  # type: ignore[attr-defined]
        t = ins.dest.var_id  # type: ignore[attr-defined]
        m.write_float(t, _FLOAT_ASSIGN[type(ins)](m.read_float(t), m.fval(ins.value)))  # type: ignore[attr-defined]


def _inc(m: EclMachine, ins: Inc) -> None:
    if ins.dest is not None:
        m.write_int(ins.dest.var_id, m.read_int(ins.dest.var_id) + 1)


def _dec(m: EclMachine, ins: Dec) -> None:
    if ins.dest is not None:
        m.write_int(ins.dest.var_id, m.read_int(ins.dest.var_id) - 1)


# ---- 三角/插值 ----


def _sin(m: EclMachine, ins: Sin) -> None:
    m.store_float(ins.dest, math.sin(m.fval(ins.value)))


def _cos(m: EclMachine, ins: Cos) -> None:
    m.store_float(ins.dest, math.cos(m.fval(ins.value)))


def _atan2(m: EclMachine, ins: Atan2) -> None:
    m.store_float(
        ins.dest,
        math.atan2(m.fval(ins.y2) - m.fval(ins.y1), m.fval(ins.x2) - m.fval(ins.x1)),
    )


def _lerp(m: EclMachine, ins: Lerp) -> None:
    # 公式 (a-b)*t+b 两作逐字相同(EclDependencies.cpp:279-291)
    m.store_float(
        ins.dest, (m.fval(ins.a) - m.fval(ins.b)) * m.fval(ins.t) + m.fval(ins.b)
    )


def _init_interp(m: EclMachine, ins: InitInterp) -> None:
    """注册跨帧变量插值: 同目标占用原槽, 否则占第一个空槽(8 槽)。"""
    # EclDependencies.cpp:350-377 / EclManager.cpp:800-828
    ctx = m.current
    for it in ctx.interps:
        if it.active and it.target_var != ins.target_var:
            continue
        it.active = True
        it.timer = 0
        it.target_var = ins.target_var
        it.duration = m.ival(ins.duration)
        it.func_idx = m.ival(ins.func)
        it.easing = m.ival(ins.easing)
        it.params = [m.fval(ins.p0), m.fval(ins.p1), m.fval(ins.p2), m.fval(ins.p3)]
        break


def _normalize_angle(m: EclMachine, ins: NormalizeAngle) -> None:
    m.store_float(ins.dest, norm_angle(m.fval(ins.value)))


def _vec_from_angle_mag(m: EclMachine, ins: VecFromAngleMag) -> None:
    ang = norm_angle(m.fval(ins.angle))
    mag = m.fval(ins.magnitude)
    m.store_float(ins.dest_y, math.sin(ang) * mag)
    m.store_float(ins.dest_x, math.cos(ang) * mag)


def _vec_from_angle_mag_raw(m: EclMachine, ins: VecFromAngleMagRaw) -> None:
    ang = m.fval(ins.angle)
    mag = m.fval(ins.magnitude)
    m.store_float(ins.dest_y, math.sin(ang) * mag)
    m.store_float(ins.dest_x, math.cos(ang) * mag)


def _dist(m: EclMachine, ins: Dist) -> None:
    dx = m.fval(ins.x2) - m.fval(ins.x1)
    dy = m.fval(ins.y2) - m.fval(ins.y1)
    m.store_float(ins.dest, math.sqrt(dx * dx + dy * dy))


# ---- 逃角/ boss 变量 ----


def _get_exit_angle(m: EclMachine, ins: GetExitAngle) -> None:
    m.store_float(ins.dest, m.exit_angle())


def _rand_exit_angle(m: EclMachine, ins: RandExitAngle) -> None:
    m.store_float(ins.dest, m.exit_angle(simple=True))


def _get_boss_int(m: EclMachine, ins: GetBossInt) -> None:
    v = m.host.get_boss_int(m, ins)
    if v is not None:
        m.store_int(ins.dest, v)


def _get_boss_float(m: EclMachine, ins: GetBossFloat) -> None:
    v = m.host.get_boss_float(m, ins)
    if v is not None:
        m.store_float(ins.dest, v)


#: 变量运算指令类 → handler
MATH: dict[type[EclInstr], Handler] = {
    SetInt: _set_int,
    SetFloat: _set_float,
    Rand: _rand,
    RandAdd: _rand_add,
    RandFloat: _rand_float,
    RandFloatAdd: _rand_float_add,
    RandFloatRange: _rand_float_range,
    RandSign: _rand_sign,
    RandSignFloat: _rand_sign_float,
    Add: _int_arith,
    Sub: _int_arith,
    Mul: _int_arith,
    Div: _int_arith,
    Mod: _int_arith,
    AddFloat: _float_arith,
    SubFloat: _float_arith,
    MulFloat: _float_arith,
    DivFloat: _float_arith,
    ModFloat: _float_arith,
    AddAssign: _int_assign,
    SubAssign: _int_assign,
    MulAssign: _int_assign,
    DivAssign: _int_assign,
    ModAssign: _int_assign,
    AddAssignFloat: _float_assign,
    SubAssignFloat: _float_assign,
    MulAssignFloat: _float_assign,
    DivAssignFloat: _float_assign,
    ModAssignFloat: _float_assign,
    Inc: _inc,
    Dec: _dec,
    Sin: _sin,
    Cos: _cos,
    Atan2: _atan2,
    Lerp: _lerp,
    InitInterp: _init_interp,
    NormalizeAngle: _normalize_angle,
    VecFromAngleMag: _vec_from_angle_mag,
    VecFromAngleMagRaw: _vec_from_angle_mag_raw,
    Dist: _dist,
    GetExitAngle: _get_exit_angle,
    RandExitAngle: _rand_exit_angle,
    GetBossInt: _get_boss_int,
    GetBossFloat: _get_boss_float,
}
