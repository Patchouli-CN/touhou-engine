"""ECL 控制流指令(结束/等待/跳转/调用/中断), 两作共享部分。"""

from __future__ import annotations

from .base import EclInstr, FloatOperand, IntOperand

# v0 opcode 出处 Reference/th07/src/th07/EclManager.hpp:115-271(EclOpcode 枚举);
# v800 编号(0x800 版本头格式)出处 th08 EclRunLow.inl:223-929 / EclRunHigh.inl:163-972
# (转引 scratch_dbg/investigation/th08-ref-facts.md:21-22, 两作编号系统性错位)


class Nop(EclInstr, frozen=True, tag="nop"):
    """空转(编译器时间同步点/填充号; rest 收真实数据里携带的多余字)。"""

    # v0=0/141, v800=0/3/84/85; v800 op3 实测带 1 个参数字(编译器残留)
    rest: tuple[int, ...] = ()


class Stop(EclInstr, frozen=True, tag="stop"):
    """脚本结束(RunEcl 返回错误 → despawn)。"""


class SubEnd(EclInstr, frozen=True, tag="sub_end"):
    """sub 指令流终止记录(time=0xFFFFFFFF, id=-1)。"""

    rest: tuple[int, ...] = ()


class SetWaitTimer(EclInstr, frozen=True, tag="set_wait_timer"):
    """等待 frames 帧(v800 走 secondaryTime)。"""

    frames: IntOperand


class Jump(EclInstr, frozen=True, tag="jump"):
    """无条件跳转: dest = 相对当前指令的字节偏移, set_time = 跳转后时刻。"""

    # 跳转位移/时间用 raw 操作数(v800 同, EclRunLow.inl:16-20)
    dest: int
    set_time: int


class DecJump(EclInstr, frozen=True, tag="dec_jump"):
    """count 自减, 仍为正则跳转(count 是 VarRef 时自减写回该变量)。"""

    dest: int
    set_time: int
    count: IntOperand


class JumpIfEq(EclInstr, frozen=True, tag="jump_if_eq"):
    """a == b 则跳转(int)。"""

    a: IntOperand
    b: IntOperand
    dest: int
    set_time: int


class JumpIfEqFloat(EclInstr, frozen=True, tag="jump_if_eq_float"):
    """a == b 则跳转(float)。"""

    a: FloatOperand
    b: FloatOperand
    dest: int
    set_time: int


class JumpIfNeq(EclInstr, frozen=True, tag="jump_if_neq"):
    """a != b 则跳转(int)。"""

    a: IntOperand
    b: IntOperand
    dest: int
    set_time: int


class JumpIfNeqFloat(EclInstr, frozen=True, tag="jump_if_neq_float"):
    """a != b 则跳转(float)。"""

    a: FloatOperand
    b: FloatOperand
    dest: int
    set_time: int


class JumpIfLt(EclInstr, frozen=True, tag="jump_if_lt"):
    """a < b 则跳转(int)。"""

    a: IntOperand
    b: IntOperand
    dest: int
    set_time: int


class JumpIfLtFloat(EclInstr, frozen=True, tag="jump_if_lt_float"):
    """a < b 则跳转(float)。"""

    a: FloatOperand
    b: FloatOperand
    dest: int
    set_time: int


class JumpIfLeq(EclInstr, frozen=True, tag="jump_if_leq"):
    """a <= b 则跳转(int)。"""

    a: IntOperand
    b: IntOperand
    dest: int
    set_time: int


class JumpIfLeqFloat(EclInstr, frozen=True, tag="jump_if_leq_float"):
    """a <= b 则跳转(float)。"""

    a: FloatOperand
    b: FloatOperand
    dest: int
    set_time: int


class JumpIfGt(EclInstr, frozen=True, tag="jump_if_gt"):
    """a > b 则跳转(int)。"""

    a: IntOperand
    b: IntOperand
    dest: int
    set_time: int


class JumpIfGtFloat(EclInstr, frozen=True, tag="jump_if_gt_float"):
    """a > b 则跳转(float)。"""

    a: FloatOperand
    b: FloatOperand
    dest: int
    set_time: int


class JumpIfGeq(EclInstr, frozen=True, tag="jump_if_geq"):
    """a >= b 则跳转(int)。"""

    a: IntOperand
    b: IntOperand
    dest: int
    set_time: int


class JumpIfGeqFloat(EclInstr, frozen=True, tag="jump_if_geq_float"):
    """a >= b 则跳转(float)。"""

    a: FloatOperand
    b: FloatOperand
    dest: int
    set_time: int


class SubCall(EclInstr, frozen=True, tag="sub_call"):
    """压栈调用 sub(raw sub id)。"""

    sub_id: int


class SubRet(EclInstr, frozen=True, tag="sub_ret"):
    """弹栈返回调用点。"""


class AddTime(EclInstr, frozen=True, tag="add_time"):
    """上下文时刻 += delta。"""

    delta: IntOperand


class SetNoStackRet(EclInstr, frozen=True, tag="set_no_stack_ret"):
    """设置调用不压栈(args[0] 低字节)。"""

    value: int


class SetInterrupt(EclInstr, frozen=True, tag="set_interrupt"):
    """interrupt 槽位登记: interrupts[slot] = sub_id。"""

    sub_id: IntOperand
    slot: IntOperand
