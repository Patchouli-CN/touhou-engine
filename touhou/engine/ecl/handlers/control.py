"""控制流 handler: 结束/等待/跳转/调用/中断/计时, 外加 VM 机制系(ex 分发/周期回调)。

语义逐句移植 old/touhou/engine/ecl_std_ops.py 与 old/touhou/games/th07/ecl_vm.py
的同名 handler; 操作数已是 schemas 层解好的数据(ImmInt/ImmFloat/VarRef)。
CONTROL 只注册两作共享的指令类; 作品专属指令的 handler 是公开函数
(set_run_interrupt 等), 由 games 侧绑定自己的指令类后注入 VM。
"""

from __future__ import annotations

import operator
from collections.abc import Callable
from typing import TYPE_CHECKING

from ....schemas.ecl import (
    AddTime,
    DecJump,
    EclInstr,
    Jump,
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
    Nop,
    RunExIns,
    SetExIns,
    SetInterrupt,
    SetInvincibilityTimer,
    SetLife,
    SetNoStackRet,
    SetTimer,
    SetWaitTimer,
    Stop,
    SubCall,
    SubEnd,
    SubRet,
    VarRef,
)
from ....utils.logger import LoggerManager
from ..num import i32

if TYPE_CHECKING:
    from ..machine import EclMachine  # 仅类型检查期(机器运行时依赖本包)

from .base import Handler, Step

log = LoggerManager.get_logger("ENGINE")


def _nop(m: EclMachine, ins: Nop) -> None:
    """空转(编译器时间同步点)。"""


def _stop(m: EclMachine, ins: Stop) -> Step:
    """脚本结束(RunEcl 返回错误 → despawn)。"""
    return Step.HALT


def _sub_end(m: EclMachine, ins: SubEnd) -> Step:
    """终止记录被执行到 = 指令流跑飞, 安全收尾。"""
    log.error("ECL 执行到 sub 终止符: offset={:#x}", ins.offset)
    return Step.HALT


def _set_wait_timer(m: EclMachine, ins: SetWaitTimer) -> None:
    m.current.wait_timer = m.ival(ins.frames)


def _jump(m: EclMachine, ins: Jump) -> Step:
    return m.jump(ins, ins.dest, ins.set_time)


def _dec_jump(m: EclMachine, ins: DecJump) -> Step | None:
    # count 是 VarRef 时先自减写回, 再按新值判断(EclManager.cpp:410-419)
    if isinstance(ins.count, VarRef):
        m.write_int(ins.count.var_id, m.read_int(ins.count.var_id) - 1)
    if m.ival(ins.count) <= 0:
        return None
    return m.jump(ins, ins.dest, ins.set_time)


_INT_CMP: dict[type[EclInstr], Callable[[int, int], bool]] = {
    JumpIfEq: operator.eq,
    JumpIfNeq: operator.ne,
    JumpIfLt: operator.lt,
    JumpIfLeq: operator.le,
    JumpIfGt: operator.gt,
    JumpIfGeq: operator.ge,
}
_FLOAT_CMP: dict[type[EclInstr], Callable[[float, float], bool]] = {
    JumpIfEqFloat: operator.eq,
    JumpIfNeqFloat: operator.ne,
    JumpIfLtFloat: operator.lt,
    JumpIfLeqFloat: operator.le,
    JumpIfGtFloat: operator.gt,
    JumpIfGeqFloat: operator.ge,
}


def _jump_if_int(m: EclMachine, ins: EclInstr) -> Step | None:
    if _INT_CMP[type(ins)](m.ival(ins.a), m.ival(ins.b)):  # type: ignore[attr-defined]
        return m.jump(ins, ins.dest, ins.set_time)  # type: ignore[attr-defined]
    return None


def _jump_if_float(m: EclMachine, ins: EclInstr) -> Step | None:
    if _FLOAT_CMP[type(ins)](m.fval(ins.a), m.fval(ins.b)):  # type: ignore[attr-defined]
        return m.jump(ins, ins.dest, ins.set_time)  # type: ignore[attr-defined]
    return None


def _sub_call(m: EclMachine, ins: SubCall) -> Step | None:
    ctx = m.current
    ctx.pc += 1  # 返回点 = 下一条
    if not m.enemy.no_stack_ret:
        m.push_context()
    if not m.call_sub(ins.sub_id):
        return Step.HALT
    # 新 sub 的全局变量快照等交接(旧实现内联拷 global_ints/floats, 现归宿主)
    m.host.on_sub_call(m)
    return Step.RESTART


def _sub_ret(m: EclMachine, ins: SubRet) -> Step:
    e, ctx = m.enemy, m.current
    if e.no_stack_ret:
        log.warning("ECL_SUB_RET with noStackRet")
    if not m.stack:
        log.error("ECL 调用栈下溢")
        return Step.HALT
    if ctx.is_periodic_sub:
        # 周期 sub 的变量区回存(C: savedContextArgs, EclManager.cpp:560-570)
        e.saved_int_vars = dict(ctx.int_vars)
        e.saved_float_vars = dict(ctx.float_vars)
        ctx.is_periodic_sub = 0
    m.current = m.stack.pop()
    return Step.RESTART


def _add_time(m: EclMachine, ins: AddTime) -> None:
    ctx = m.current
    ctx.time = i32(ctx.time + m.ival(ins.delta))


def _set_no_stack_ret(m: EclMachine, ins: SetNoStackRet) -> None:
    m.enemy.no_stack_ret = ins.value


def _set_interrupt(m: EclMachine, ins: SetInterrupt) -> None:
    m.enemy.interrupts[m.ival(ins.slot) & 31] = m.ival(ins.sub_id)


# ---- 作品专属指令的机制 handler(games 侧绑定自己的指令类后注入) ----


def set_run_interrupt(m: EclMachine, ins: EclInstr) -> Step | None:
    """登记并立即进 interrupt sub。"""
    e = m.enemy
    e.run_interrupt = m.ival(ins.slot)  # type: ignore[attr-defined]
    if not m.interrupt_call(e.interrupts[e.run_interrupt]):
        return Step.HALT
    return Step.RESTART


def run_pending_sub(m: EclMachine, ins: EclInstr) -> Step | None:
    """Pending 槽位 → 压栈调 sub(pending 表在宿主侧)。"""
    if m.host.run_pending_sub(m, m.ival(ins.slot)):  # type: ignore[attr-defined]
        return Step.RESTART
    return None


def set_child_context(m: EclMachine, ins: EclInstr) -> None:
    """安装/释放 child 上下文块(宿主侧)。"""
    m.host.set_child_context(m, m.ival(ins.slot), m.ival(ins.sub_id))  # type: ignore[attr-defined]


def call_sub_on_boss(m: EclMachine, ins: EclInstr) -> None:
    """让指定 boss 压栈调 sub(宿主侧)。"""
    m.host.call_sub_on_boss(m, m.ival(ins.boss_idx), ins.sub_id)  # type: ignore[attr-defined]


def set_boss_pending_sub(m: EclMachine, ins: EclInstr) -> None:
    """设置 boss 的 pendingEclSubroutineIndex(宿主侧)。"""
    m.host.set_boss_pending_sub(m.ival(ins.boss_idx), m.ival(ins.sub_id))  # type: ignore[attr-defined]


def set_periodic_callback(m: EclMachine, ins: EclInstr) -> None:
    """设周期回调(timer 帧一次进 sub_id, 变量区快照)。"""
    e, ctx = m.enemy, m.current
    e.periodic_timer = m.ival(ins.timer)  # type: ignore[attr-defined]
    e.periodic_callback_sub = m.ival(ins.sub_id)  # type: ignore[attr-defined]
    e.periodic_counter = 0
    e.saved_int_vars = dict(ctx.int_vars)
    e.saved_float_vars = dict(ctx.float_vars)


# ---- VM 机制系(状态在 engine, 语义触发在宿主) ----


def _set_ex_ins(m: EclMachine, ins: SetExIns) -> None:
    ctx = m.current
    idx = m.ival(ins.idx)
    if idx >= 0:
        ctx.ex_instr_idx = idx
        ctx.ex_instr = ins
    else:
        ctx.ex_instr_idx = -1
        ctx.ex_instr = None


def _run_ex_ins(m: EclMachine, ins: RunExIns) -> None:
    m.run_ex(m.ival(ins.idx), ins)


def _set_life(m: EclMachine, ins: SetLife) -> None:
    e = m.enemy
    e.life = e.max_life = m.ival(ins.life)
    if m.file.version != 0:
        # v800 顺带记 phaseStartingLife(宿主状态), 透出一份
        m.host.enemy_config(m, ins)


def _set_timer(m: EclMachine, ins: SetTimer) -> None:
    m.enemy.timer = m.ival(ins.value)


def _set_invincibility_timer(m: EclMachine, ins: SetInvincibilityTimer) -> None:
    m.enemy.invincibility_timer = m.ival(ins.frames)


#: 控制流指令类 → handler(两作共享部分)
CONTROL: dict[type[EclInstr], Handler] = {
    Nop: _nop,
    Stop: _stop,
    SubEnd: _sub_end,
    SetWaitTimer: _set_wait_timer,
    Jump: _jump,
    DecJump: _dec_jump,
    JumpIfEq: _jump_if_int,
    JumpIfNeq: _jump_if_int,
    JumpIfLt: _jump_if_int,
    JumpIfLeq: _jump_if_int,
    JumpIfGt: _jump_if_int,
    JumpIfGeq: _jump_if_int,
    JumpIfEqFloat: _jump_if_float,
    JumpIfNeqFloat: _jump_if_float,
    JumpIfLtFloat: _jump_if_float,
    JumpIfLeqFloat: _jump_if_float,
    JumpIfGtFloat: _jump_if_float,
    JumpIfGeqFloat: _jump_if_float,
    SubCall: _sub_call,
    SubRet: _sub_ret,
    AddTime: _add_time,
    SetNoStackRet: _set_no_stack_ret,
    SetInterrupt: _set_interrupt,
    SetExIns: _set_ex_ins,
    RunExIns: _run_ex_ins,
    SetLife: _set_life,
    SetTimer: _set_timer,
    SetInvincibilityTimer: _set_invincibility_timer,
}
