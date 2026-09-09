"""变量运算与条件跳转指令 handler。"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from ....schemas.anm_script import (
    Acos,
    Add,
    Add2,
    AddFloat,
    AddFloat2,
    AnmInstr,
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
from .base import Handler, Step, add_norm_angle, cond_jump

if TYPE_CHECKING:
    from ..vm import AnmMachine


def _mov(vm: AnmMachine, ins: Mov) -> None:
    vm.istore(ins.dst, ins.flags, 0, vm.ivar(ins.src, ins.flags, 1))


def _mov_float(vm: AnmMachine, ins: MovFloat) -> None:
    vm.fstore(ins.dst, ins.flags, 0, vm.fvar(ins.src, ins.flags, 1))


def _add(vm: AnmMachine, ins: Add) -> None:
    a, b = vm.iptr(ins.dst, ins.flags, 0), vm.ivar(ins.src, ins.flags, 1)
    vm.istore(ins.dst, ins.flags, 0, a + b)


def _add_float(vm: AnmMachine, ins: AddFloat) -> None:
    a, b = vm.fvar(ins.dst, ins.flags, 0), vm.fvar(ins.src, ins.flags, 1)
    vm.fstore(ins.dst, ins.flags, 0, a + b)


def _sub(vm: AnmMachine, ins: Sub) -> None:
    a, b = vm.iptr(ins.dst, ins.flags, 0), vm.ivar(ins.src, ins.flags, 1)
    vm.istore(ins.dst, ins.flags, 0, a - b)


def _sub_float(vm: AnmMachine, ins: SubFloat) -> None:
    a, b = vm.fvar(ins.dst, ins.flags, 0), vm.fvar(ins.src, ins.flags, 1)
    vm.fstore(ins.dst, ins.flags, 0, a - b)


def _mul(vm: AnmMachine, ins: Mul) -> None:
    a, b = vm.iptr(ins.dst, ins.flags, 0), vm.ivar(ins.src, ins.flags, 1)
    vm.istore(ins.dst, ins.flags, 0, a * b)


def _mul_float(vm: AnmMachine, ins: MulFloat) -> None:
    a, b = vm.fvar(ins.dst, ins.flags, 0), vm.fvar(ins.src, ins.flags, 1)
    vm.fstore(ins.dst, ins.flags, 0, a * b)


def _div(vm: AnmMachine, ins: Div) -> None:
    # 除零得 0(对齐旧 VM, 不抛异常)
    a, b = vm.iptr(ins.dst, ins.flags, 0), vm.ivar(ins.src, ins.flags, 1)
    vm.istore(ins.dst, ins.flags, 0, a // b if b else 0)


def _div_float(vm: AnmMachine, ins: DivFloat) -> None:
    a, b = vm.fvar(ins.dst, ins.flags, 0), vm.fvar(ins.src, ins.flags, 1)
    vm.fstore(ins.dst, ins.flags, 0, a / b if b else 0.0)


def _mod(vm: AnmMachine, ins: Mod) -> None:
    a, b = vm.iptr(ins.dst, ins.flags, 0), vm.ivar(ins.src, ins.flags, 1)
    vm.istore(ins.dst, ins.flags, 0, a % b if b else 0)


def _mod_float(vm: AnmMachine, ins: ModFloat) -> None:
    a, b = vm.fvar(ins.dst, ins.flags, 0), vm.fvar(ins.src, ins.flags, 1)
    vm.fstore(ins.dst, ins.flags, 0, math.fmod(a, b) if b else 0.0)


def _add2(vm: AnmMachine, ins: Add2) -> None:
    a, b = vm.ivar(ins.a, ins.flags, 1), vm.ivar(ins.b, ins.flags, 2)
    vm.istore(ins.dst, ins.flags, 0, a + b)


def _add_float2(vm: AnmMachine, ins: AddFloat2) -> None:
    a, b = vm.fvar(ins.a, ins.flags, 1), vm.fvar(ins.b, ins.flags, 2)
    vm.fstore(ins.dst, ins.flags, 0, a + b)


def _sub2(vm: AnmMachine, ins: Sub2) -> None:
    a, b = vm.ivar(ins.a, ins.flags, 1), vm.ivar(ins.b, ins.flags, 2)
    vm.istore(ins.dst, ins.flags, 0, a - b)


def _sub_float2(vm: AnmMachine, ins: SubFloat2) -> None:
    a, b = vm.fvar(ins.a, ins.flags, 1), vm.fvar(ins.b, ins.flags, 2)
    vm.fstore(ins.dst, ins.flags, 0, a - b)


def _mul2(vm: AnmMachine, ins: Mul2) -> None:
    a, b = vm.ivar(ins.a, ins.flags, 1), vm.ivar(ins.b, ins.flags, 2)
    vm.istore(ins.dst, ins.flags, 0, a * b)


def _mul_float2(vm: AnmMachine, ins: MulFloat2) -> None:
    a, b = vm.fvar(ins.a, ins.flags, 1), vm.fvar(ins.b, ins.flags, 2)
    vm.fstore(ins.dst, ins.flags, 0, a * b)


def _div2(vm: AnmMachine, ins: Div2) -> None:
    a, b = vm.ivar(ins.a, ins.flags, 1), vm.ivar(ins.b, ins.flags, 2)
    vm.istore(ins.dst, ins.flags, 0, a // b if b else 0)


def _div_float2(vm: AnmMachine, ins: DivFloat2) -> None:
    a, b = vm.fvar(ins.a, ins.flags, 1), vm.fvar(ins.b, ins.flags, 2)
    vm.fstore(ins.dst, ins.flags, 0, a / b if b else 0.0)


def _mod2(vm: AnmMachine, ins: Mod2) -> None:
    a, b = vm.ivar(ins.a, ins.flags, 1), vm.ivar(ins.b, ins.flags, 2)
    vm.istore(ins.dst, ins.flags, 0, a % b if b else 0)


def _mod_float2(vm: AnmMachine, ins: ModFloat2) -> None:
    a, b = vm.fvar(ins.a, ins.flags, 1), vm.fvar(ins.b, ins.flags, 2)
    vm.fstore(ins.dst, ins.flags, 0, math.fmod(a, b) if b else 0.0)


def _rand(vm: AnmMachine, ins: Rand) -> None:
    vm.istore(ins.dst, ins.flags, 0, vm.rng.int_below(vm.ivar(ins.bound, ins.flags, 1)))


def _rand_float(vm: AnmMachine, ins: RandFloat) -> None:
    bound = vm.fvar(ins.bound, ins.flags, 1)
    vm.fstore(ins.dst, ins.flags, 0, vm.rng.unit() * bound)


def _sin(vm: AnmMachine, ins: Sin) -> None:
    vm.fstore(ins.dst, ins.flags, 0, math.sin(vm.fvar(ins.src, ins.flags, 1)))


def _cos(vm: AnmMachine, ins: Cos) -> None:
    vm.fstore(ins.dst, ins.flags, 0, math.cos(vm.fvar(ins.src, ins.flags, 1)))


def _tan(vm: AnmMachine, ins: Tan) -> None:
    vm.fstore(ins.dst, ins.flags, 0, math.tan(vm.fvar(ins.src, ins.flags, 1)))


def _acos(vm: AnmMachine, ins: Acos) -> None:
    v = max(-1.0, min(1.0, vm.fvar(ins.src, ins.flags, 1)))
    vm.fstore(ins.dst, ins.flags, 0, math.acos(v))


def _atan(vm: AnmMachine, ins: Atan) -> None:
    vm.fstore(ins.dst, ins.flags, 0, math.atan(vm.fvar(ins.src, ins.flags, 1)))


def _normalize_angle(vm: AnmMachine, ins: NormalizeAngle) -> None:
    vm.fstore(
        ins.dst, ins.flags, 0, add_norm_angle(vm.fvar(ins.dst, ins.flags, 0), 0.0)
    )


def _jump_if_eq(vm: AnmMachine, ins: JumpIfEq) -> Step | None:
    ok = vm.ivar(ins.x, ins.flags, 0) == vm.ivar(ins.y, ins.flags, 1)
    return cond_jump(vm, ok, ins.dest, ins.set_time)


def _jump_if_eq_float(vm: AnmMachine, ins: JumpIfEqFloat) -> Step | None:
    ok = vm.fvar(ins.x, ins.flags, 0) == vm.fvar(ins.y, ins.flags, 1)
    return cond_jump(vm, ok, ins.dest, ins.set_time)


def _jump_if_neq(vm: AnmMachine, ins: JumpIfNeq) -> Step | None:
    ok = vm.ivar(ins.x, ins.flags, 0) != vm.ivar(ins.y, ins.flags, 1)
    return cond_jump(vm, ok, ins.dest, ins.set_time)


def _jump_if_neq_float(vm: AnmMachine, ins: JumpIfNeqFloat) -> Step | None:
    ok = vm.fvar(ins.x, ins.flags, 0) != vm.fvar(ins.y, ins.flags, 1)
    return cond_jump(vm, ok, ins.dest, ins.set_time)


def _jump_if_lt(vm: AnmMachine, ins: JumpIfLt) -> Step | None:
    ok = vm.ivar(ins.x, ins.flags, 0) < vm.ivar(ins.y, ins.flags, 1)
    return cond_jump(vm, ok, ins.dest, ins.set_time)


def _jump_if_lt_float(vm: AnmMachine, ins: JumpIfLtFloat) -> Step | None:
    ok = vm.fvar(ins.x, ins.flags, 0) < vm.fvar(ins.y, ins.flags, 1)
    return cond_jump(vm, ok, ins.dest, ins.set_time)


def _jump_if_leq(vm: AnmMachine, ins: JumpIfLeq) -> Step | None:
    ok = vm.ivar(ins.x, ins.flags, 0) <= vm.ivar(ins.y, ins.flags, 1)
    return cond_jump(vm, ok, ins.dest, ins.set_time)


def _jump_if_leq_float(vm: AnmMachine, ins: JumpIfLeqFloat) -> Step | None:
    ok = vm.fvar(ins.x, ins.flags, 0) <= vm.fvar(ins.y, ins.flags, 1)
    return cond_jump(vm, ok, ins.dest, ins.set_time)


def _jump_if_gt(vm: AnmMachine, ins: JumpIfGt) -> Step | None:
    ok = vm.ivar(ins.x, ins.flags, 0) > vm.ivar(ins.y, ins.flags, 1)
    return cond_jump(vm, ok, ins.dest, ins.set_time)


def _jump_if_gt_float(vm: AnmMachine, ins: JumpIfGtFloat) -> Step | None:
    ok = vm.fvar(ins.x, ins.flags, 0) > vm.fvar(ins.y, ins.flags, 1)
    return cond_jump(vm, ok, ins.dest, ins.set_time)


def _jump_if_geq(vm: AnmMachine, ins: JumpIfGeq) -> Step | None:
    ok = vm.ivar(ins.x, ins.flags, 0) >= vm.ivar(ins.y, ins.flags, 1)
    return cond_jump(vm, ok, ins.dest, ins.set_time)


def _jump_if_geq_float(vm: AnmMachine, ins: JumpIfGeqFloat) -> Step | None:
    ok = vm.fvar(ins.x, ins.flags, 0) >= vm.fvar(ins.y, ins.flags, 1)
    return cond_jump(vm, ok, ins.dest, ins.set_time)


MATH: dict[type[AnmInstr], Handler] = {
    Mov: _mov,
    MovFloat: _mov_float,
    Add: _add,
    AddFloat: _add_float,
    Sub: _sub,
    SubFloat: _sub_float,
    Mul: _mul,
    MulFloat: _mul_float,
    Div: _div,
    DivFloat: _div_float,
    Mod: _mod,
    ModFloat: _mod_float,
    Add2: _add2,
    AddFloat2: _add_float2,
    Sub2: _sub2,
    SubFloat2: _sub_float2,
    Mul2: _mul2,
    MulFloat2: _mul_float2,
    Div2: _div2,
    DivFloat2: _div_float2,
    Mod2: _mod2,
    ModFloat2: _mod_float2,
    Rand: _rand,
    RandFloat: _rand_float,
    Sin: _sin,
    Cos: _cos,
    Tan: _tan,
    Acos: _acos,
    Atan: _atan,
    NormalizeAngle: _normalize_angle,
    JumpIfEq: _jump_if_eq,
    JumpIfEqFloat: _jump_if_eq_float,
    JumpIfNeq: _jump_if_neq,
    JumpIfNeqFloat: _jump_if_neq_float,
    JumpIfLt: _jump_if_lt,
    JumpIfLtFloat: _jump_if_lt_float,
    JumpIfLeq: _jump_if_leq,
    JumpIfLeqFloat: _jump_if_leq_float,
    JumpIfGt: _jump_if_gt,
    JumpIfGtFloat: _jump_if_gt_float,
    JumpIfGeq: _jump_if_geq,
    JumpIfGeqFloat: _jump_if_geq_float,
}
