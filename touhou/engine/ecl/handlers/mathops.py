"""变量运算 handler: 赋值/随机/算术/三角/插值/boss 变量读。

语义移植 old/touhou/engine/ecl_std_ops.py + old/touhou/games/th07/ecl_vm.py
同名 handler(除零守卫/C 截断语义/f32 落盘都在); 出处 EclManager.cpp 各 case。
MATH 只注册两作共享的指令类; 作品专属指令的 handler 是公开函数/工厂
(rand/int_assign 等), 由 games 侧绑定自己的指令类后注入 VM。
"""

from __future__ import annotations

import math
from collections.abc import Callable
from typing import TYPE_CHECKING

from ....schemas.ecl import (
    Add,
    AddFloat,
    Atan2,
    Cos,
    Dec,
    Div,
    DivFloat,
    EclInstr,
    GetBossFloat,
    GetBossInt,
    Inc,
    InitInterp,
    Lerp,
    Mod,
    ModFloat,
    Mul,
    MulFloat,
    NormalizeAngle,
    RandExitAngle,
    RandSign,
    RandSignFloat,
    SetFloat,
    SetInt,
    Sin,
    Sub,
    SubFloat,
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


def rand(m: EclMachine, ins: EclInstr) -> None:
    """Dest = rng 取模 bound。"""
    m.store_int(ins.dest, m.rng.int_below(m.ival(ins.bound)))  # type: ignore[attr-defined]


def rand_add(m: EclMachine, ins: EclInstr) -> None:
    """Dest = rng 取模 bound + addend。"""
    m.store_int(ins.dest, m.rng.int_below(m.ival(ins.bound)) + m.ival(ins.addend))  # type: ignore[attr-defined]


def rand_float(m: EclMachine, ins: EclInstr) -> None:
    """Dest = rng 单位随机 × scale。"""
    m.store_float(ins.dest, m.rng.unit() * m.fval(ins.scale))  # type: ignore[attr-defined]


def rand_float_add(m: EclMachine, ins: EclInstr) -> None:
    """Dest = rng 单位随机 × scale + addend。"""
    m.store_float(ins.dest, m.rng.unit() * m.fval(ins.scale) + m.fval(ins.addend))  # type: ignore[attr-defined]


def rand_float_range(m: EclMachine, ins: EclInstr) -> None:
    """Dest = rng 单位随机 × (hi - lo) + lo。"""
    lo = m.fval(ins.lo)  # type: ignore[attr-defined]
    m.store_float(ins.dest, m.rng.unit() * (m.fval(ins.hi) - lo) + lo)  # type: ignore[attr-defined]


def _rand_sign(m: EclMachine, ins: RandSign) -> None:
    m.store_int(ins.dest, m.rng.sign() * m.ival(ins.magnitude))


def _rand_sign_float(m: EclMachine, ins: RandSignFloat) -> None:
    m.store_float(ins.dest, float(m.rng.sign()) * m.fval(ins.magnitude))


# ---- 算术: 3 操作数(+-*/%)与 2 操作数自赋值 ----

INT_BINOP: dict[type[EclInstr], Callable[[int, int], int]] = {
    Add: lambda a, b: a + b,
    Sub: lambda a, b: a - b,
    Mul: lambda a, b: a * b,
    Div: lambda a, b: cdiv(a, b) if b else 0,
    Mod: lambda a, b: cmod(a, b) if b else 0,
}
FLOAT_BINOP: dict[type[EclInstr], Callable[[float, float], float]] = {
    AddFloat: lambda a, b: a + b,
    SubFloat: lambda a, b: a - b,
    MulFloat: lambda a, b: a * b,
    DivFloat: lambda a, b: a / b if b != 0.0 else 0.0,
    ModFloat: lambda a, b: math.fmod(a, b) if b != 0.0 else 0.0,
}


def _int_arith(m: EclMachine, ins: EclInstr) -> None:
    m.store_int(ins.dest, INT_BINOP[type(ins)](m.ival(ins.a), m.ival(ins.b)))  # type: ignore[attr-defined]


def _float_arith(m: EclMachine, ins: EclInstr) -> None:
    m.store_float(ins.dest, FLOAT_BINOP[type(ins)](m.fval(ins.a), m.fval(ins.b)))  # type: ignore[attr-defined]


def int_assign(op: Callable[[int, int], int]) -> Handler:
    """2 操作数 int 自赋值 handler 工厂: dest 非变量时整丢弃(EclRunLow.inl:236-330)。"""

    def handler(m: EclMachine, ins: EclInstr) -> None:
        if ins.dest is not None:  # type: ignore[attr-defined]
            t = ins.dest.var_id  # type: ignore[attr-defined]
            m.write_int(t, op(m.read_int(t), m.ival(ins.value)))  # type: ignore[attr-defined]

    return handler


def float_assign(op: Callable[[float, float], float]) -> Handler:
    """2 操作数 float 自赋值 handler 工厂。"""

    def handler(m: EclMachine, ins: EclInstr) -> None:
        if ins.dest is not None:  # type: ignore[attr-defined]
            t = ins.dest.var_id  # type: ignore[attr-defined]
            m.write_float(t, op(m.read_float(t), m.fval(ins.value)))  # type: ignore[attr-defined]

    return handler


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


def vec_from_angle_mag(m: EclMachine, ins: EclInstr) -> None:
    """角度先规范化再分解: dest_x = cos(angle)*mag, dest_y = sin(angle)*mag。"""
    ang = norm_angle(m.fval(ins.angle))  # type: ignore[attr-defined]
    mag = m.fval(ins.magnitude)  # type: ignore[attr-defined]
    m.store_float(ins.dest_y, math.sin(ang) * mag)  # type: ignore[attr-defined]
    m.store_float(ins.dest_x, math.cos(ang) * mag)  # type: ignore[attr-defined]


def _vec_from_angle_mag_raw(m: EclMachine, ins: VecFromAngleMagRaw) -> None:
    ang = m.fval(ins.angle)
    mag = m.fval(ins.magnitude)
    m.store_float(ins.dest_y, math.sin(ang) * mag)
    m.store_float(ins.dest_x, math.cos(ang) * mag)


def dist(m: EclMachine, ins: EclInstr) -> None:
    """Dest = (x1, y1) 到 (x2, y2) 的距离。"""
    dx = m.fval(ins.x2) - m.fval(ins.x1)  # type: ignore[attr-defined]
    dy = m.fval(ins.y2) - m.fval(ins.y1)  # type: ignore[attr-defined]
    m.store_float(ins.dest, math.sqrt(dx * dx + dy * dy))  # type: ignore[attr-defined]


# ---- 逃角/ boss 变量 ----


def get_exit_angle(m: EclMachine, ins: EclInstr) -> None:
    """Dest = 朝屏幕外逃的随机角(带移动边界反弹修正)。"""
    m.store_float(ins.dest, m.exit_angle())  # type: ignore[attr-defined]


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


#: 变量运算指令类 → handler(两作共享部分)
MATH: dict[type[EclInstr], Handler] = {
    SetInt: _set_int,
    SetFloat: _set_float,
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
    Inc: _inc,
    Dec: _dec,
    Sin: _sin,
    Cos: _cos,
    Atan2: _atan2,
    Lerp: _lerp,
    InitInterp: _init_interp,
    NormalizeAngle: _normalize_angle,
    VecFromAngleMagRaw: _vec_from_angle_mag_raw,
    RandExitAngle: _rand_exit_angle,
    GetBossInt: _get_boss_int,
    GetBossFloat: _get_boss_float,
}
