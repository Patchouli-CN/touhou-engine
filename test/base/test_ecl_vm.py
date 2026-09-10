"""EclMachine 合成脚本测试: 变量/跳转/sub 调用/等待/插值移动/中断/周期回调。"""

from __future__ import annotations

from typing import get_args

import msgspec
import pytest

from touhou.engine.ecl import HANDLERS, EclHost, EclMachine
from touhou.engine.rng import Rng
from touhou.schemas.ecl import (
    Add,
    AddTime,
    DecJump,
    Div,
    EclFile,
    EclInstr,
    EclSub,
    ImmFloat,
    ImmInt,
    InitInterp,
    Jump,
    JumpIfEq,
    JumpIfLt,
    Mod,
    MulFloat,
    Nop,
    SetExIns,
    SetFloat,
    SetInt,
    SetInterrupt,
    SetLife,
    SetWaitTimer,
    SharedInstruction,
    Stop,
    SubCall,
    SubRet,
    VarRef,
)

INT_VARS = frozenset({10000, 10001, 10002, 10003})
FLOAT_VARS = frozenset({10004, 10005, 10006, 10007})

_STEP = 16  # 合成指令的伪字节偏移步长(跳转位移 = 下标差 × 16)


def build_file(*subs: list[EclInstr]) -> EclFile:
    """把指令列表拼成 EclFile, offset 按下标 × 16 重排。"""
    out = []
    for instrs in subs:
        out.append(
            EclSub(
                offset=0,
                instrs=tuple(
                    msgspec.structs.replace(ins, offset=i * _STEP)
                    for i, ins in enumerate(instrs)
                ),
            )
        )
    return EclFile(version=0, subs=tuple(out), timelines=())


def make(instrs: list[EclInstr], host: EclHost | None = None, **kw) -> EclMachine:
    """单 sub 机器, 直接 start(0) 就绪。"""
    m = EclMachine(
        build_file(instrs),
        host if host is not None else RecHost(),
        Rng(0),
        int_var_ids=INT_VARS,
        float_var_ids=FLOAT_VARS,
        **kw,
    )
    m.start(0)
    return m


def ins(cls, time: int, **kw) -> EclInstr:
    """合成一条指令(offset 由 build_file 重排, skip=0xFF 全难度执行)。"""
    return cls(offset=0, time=time, skip_difficulty=0xFF, **kw)


class RecHost(EclHost):
    """记录宿主: 特殊变量/回调全落 log。"""

    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def read_special_int(self, m: EclMachine, var_id: int) -> int:
        self.calls.append(("ri", var_id))
        return 42

    def write_special_int(self, m: EclMachine, var_id: int, value: int) -> None:
        self.calls.append(("wi", var_id, value))

    def read_special_float(self, m: EclMachine, var_id: int) -> float:
        self.calls.append(("rf", var_id))
        return 1.5

    def write_special_float(self, m: EclMachine, var_id: int, value: float) -> None:
        self.calls.append(("wf", var_id, value))

    def on_sub_call(self, m: EclMachine) -> None:
        self.calls.append(("sub_call", m.current.sub_id))

    def on_auto_shoot(self, m: EclMachine) -> None:
        self.calls.append(("shoot",))

    def run_ex_instr(self, m: EclMachine, idx: int, instr: EclInstr | None) -> bool:
        self.calls.append(("ex", idx))
        return True


def run_frames(m: EclMachine, n: int) -> None:
    for _ in range(n):
        m.step()


def test_handler_registry_covers_union() -> None:
    """共享指令 union 全覆盖: 每个类都有注册 handler, 没有漏网分派。"""
    assert set(get_args(SharedInstruction)) == set(HANDLERS)


# ---- 变量系统 ----


def test_set_and_read_local_vars() -> None:
    m = make(
        [
            ins(SetInt, 0, dest=VarRef(10000), value=ImmInt(7)),
            ins(Add, 0, dest=VarRef(10001), a=VarRef(10000), b=ImmInt(5)),
            ins(SetFloat, 0, dest=VarRef(10004), value=ImmFloat(2.5)),
            ins(MulFloat, 0, dest=VarRef(10005), a=VarRef(10004), b=ImmFloat(4.0)),
            ins(Stop, 1),
        ]
    )
    assert m.step() is True
    assert m.current.int_vars == {10000: 7, 10001: 12}
    assert m.current.float_vars == {10004: 2.5, 10005: 10.0}
    assert m.step() is False  # Stop → 结束


def test_cross_type_slot_read() -> None:
    """Int 读 float 槽 = 截断, float 读 int 槽 = 转换(C 变量表语义)。"""
    m = make(
        [
            ins(SetFloat, 0, dest=VarRef(10004), value=ImmFloat(2.9)),
            ins(SetInt, 0, dest=VarRef(10000), value=VarRef(10004)),
            ins(SetFloat, 0, dest=VarRef(10005), value=VarRef(10000)),
            ins(Stop, 1),
        ]
    )
    m.step()
    assert m.current.int_vars[10000] == 2
    assert m.current.float_vars[10005] == 2.0


def test_special_var_passthrough_to_host() -> None:
    """局部 id 集合外的变量走宿主透出; dest=None 的写入丢弃。"""
    host = RecHost()
    m = make(
        [
            ins(SetInt, 0, dest=VarRef(10050), value=ImmInt(3)),
            ins(SetInt, 0, dest=VarRef(10000), value=VarRef(10060)),
            ins(SetInt, 0, dest=None, value=ImmInt(9)),
            ins(Stop, 1),
        ],
        host,
    )
    m.step()
    assert ("wi", 10050, 3) in host.calls
    assert ("ri", 10060) in host.calls
    assert m.current.int_vars[10000] == 42  # 宿主读值落进局部槽
    assert len(m.current.int_vars) == 1  # dest=None 的没落盘


def test_c_div_mod_semantics() -> None:
    """C 语义: 向零截断除, 余数符号随被除数; 除零得 0。"""
    m = make(
        [
            ins(Div, 0, dest=VarRef(10000), a=ImmInt(-7), b=ImmInt(2)),
            ins(Mod, 0, dest=VarRef(10001), a=ImmInt(-7), b=ImmInt(2)),
            ins(Div, 0, dest=VarRef(10002), a=ImmInt(7), b=ImmInt(0)),
            ins(Stop, 1),
        ]
    )
    m.step()
    assert m.current.int_vars == {10000: -3, 10001: -1, 10002: 0}


# ---- 跳转/等待 ----


def test_dec_jump_loop() -> None:
    """Count 自减循环: 同帧跑到 count 归零, 然后顺序前进。"""
    c, r = VarRef(10000), VarRef(10001)
    m = make(
        [
            ins(SetInt, 0, dest=c, value=ImmInt(3)),
            ins(Nop, 1),
            ins(DecJump, 1, dest=-_STEP, set_time=1, count=c),
            ins(SetInt, 2, dest=r, value=ImmInt(99)),
            ins(Stop, 2),
        ]
    )
    m.step()  # SetInt, 然后 Nop.time=1 不到帧
    assert m.current.int_vars == {10000: 3}
    m.step()  # Nop/DecJump 循环 3 圈同帧跑完
    assert m.current.int_vars[10000] == 0
    assert 10001 not in m.current.int_vars
    m.step()
    assert m.current.int_vars[10001] == 99
    assert m.step() is False


def test_cond_jump_taken_and_not() -> None:
    m = make(
        [
            ins(JumpIfEq, 0, a=ImmInt(1), b=ImmInt(1), dest=2 * _STEP, set_time=5),
            ins(SetInt, 0, dest=VarRef(10000), value=ImmInt(1)),  # 被跳过
            ins(JumpIfLt, 5, a=ImmInt(3), b=ImmInt(2), dest=_STEP, set_time=0),
            ins(SetInt, 5, dest=VarRef(10001), value=ImmInt(2)),
            ins(Stop, 6),
        ]
    )
    m.step()  # JumpIfEq 跳 idx2(set_time=5), JumpIfLt 不成立, SetInt 执行
    assert 10000 not in m.current.int_vars
    assert m.current.int_vars[10001] == 2
    assert m.current.time == 6  # 帧尾 time++


def test_wait_timer_freezes_time() -> None:
    """SetWaitTimer(3): 当帧立即冻结(后续指令不跑), 3 帧后恢复。"""
    m = make(
        [
            ins(SetWaitTimer, 0, frames=ImmInt(3)),
            ins(SetInt, 0, dest=VarRef(10000), value=ImmInt(1)),
            ins(SetInt, 1, dest=VarRef(10001), value=ImmInt(2)),
            ins(Stop, 2),
        ]
    )
    m.step()
    assert m.current.int_vars == {}  # 设置当帧即进入等待(old 同语义)
    for _ in range(2):
        m.step()
        assert m.current.int_vars == {}
        assert m.current.time == 0  # 等待期间时刻冻结
    m.step()  # 第 4 帧: 等待耗尽, time=0 指令执行
    assert m.current.int_vars == {10000: 1}
    m.step()
    assert m.current.int_vars[10001] == 2


def test_difficulty_skip() -> None:
    """指令掩码不含当前难度位则跳过。"""

    class Hard(RecHost):
        difficulty = 2

    # 第二条掩码 0b0011 不含 H(位值 4) → 跳过
    skipped = msgspec.structs.replace(
        ins(SetInt, 0, dest=VarRef(10001), value=ImmInt(2)), skip_difficulty=0b0011
    )
    m = make(
        [ins(SetInt, 0, dest=VarRef(10000), value=ImmInt(1)), skipped, ins(Stop, 1)],
        Hard(),
    )
    m.step()
    assert m.current.int_vars == {10000: 1}


def test_add_time() -> None:
    m = make(
        [
            ins(AddTime, 0, delta=ImmInt(10)),
            ins(SetInt, 10, dest=VarRef(10000), value=ImmInt(1)),
            ins(Stop, 11),
        ]
    )
    assert m.step() is True  # AddTime 后 time=10, 同帧继续执行 time=10 指令
    assert m.current.int_vars[10000] == 1


# ---- sub 调用 ----


def test_sub_call_and_ret() -> None:
    host = RecHost()
    sub0 = [
        ins(SetInt, 0, dest=VarRef(10000), value=ImmInt(1)),
        ins(SubCall, 0, sub_id=1),
        ins(SetInt, 0, dest=VarRef(10002), value=ImmInt(3)),
        ins(Stop, 1),
    ]
    sub1 = [
        ins(SetInt, 0, dest=VarRef(10001), value=ImmInt(2)),
        ins(SubRet, 0),
    ]
    m = EclMachine(
        build_file(sub0, sub1),
        host,
        Rng(0),
        int_var_ids=INT_VARS,
        float_var_ids=FLOAT_VARS,
    )
    m.start(0)
    m.step()
    # 同帧: sub0 头 → call → sub1 → ret → sub0 尾; 变量区随上下文各有一份
    assert ("sub_call", 1) in host.calls
    assert m.current.int_vars == {10000: 1, 10002: 3}  # sub1 写的 10001 在 sub1 上下文
    assert not m.stack
    assert m.step() is False


def test_sub_ret_underflow_halts() -> None:
    m = make([ins(SubRet, 0)])
    assert m.step() is False
    assert m.finished


def test_stack_depth_capped() -> None:
    """调用栈封顶 15, 超深丢最老一层(C savedContextStack[16])。"""
    m = make([ins(Stop, 99)])
    for _ in range(20):
        m.push_context()
    assert len(m.stack) == 15


def test_interrupt_call() -> None:
    """SET_INTERRUPT 登记槽位; run_interrupt 置位后下一帧压栈进中断 sub。"""
    sub0 = [
        ins(SetInterrupt, 0, sub_id=ImmInt(1), slot=ImmInt(2)),
        ins(Nop, 5),
        ins(Stop, 6),
    ]
    sub1 = [ins(SetInt, 0, dest=VarRef(10001), value=ImmInt(9)), ins(SubRet, 0)]
    m = EclMachine(
        build_file(sub0, sub1),
        RecHost(),
        Rng(0),
        int_var_ids=INT_VARS,
        float_var_ids=FLOAT_VARS,
    )
    m.start(0)
    m.step()
    assert m.enemy.interrupts[2] == 1
    m.enemy.run_interrupt = 2
    m.step()  # 进 sub1 跑完 ret 回来, 继续等 Nop(time=5)
    assert m.current.sub_id == 0
    assert m.enemy.run_interrupt == -1
    assert not m.stack
    for _ in range(4):
        m.step()
    assert m.step() is False  # Stop(time=6)


def test_ex_instr_dispatch() -> None:
    """SetExIns 注册每帧 ex 回调; noop idx 不分发; 负 idx 注销。"""
    host = RecHost()
    m = make(
        [
            ins(SetLife, 0, life=ImmInt(10)),
            ins(SetExIns, 0, idx=ImmInt(5)),
            ins(Nop, 10),
        ],
        host,
    )
    run_frames(m, 2)
    assert [c for c in host.calls if c[0] == "ex"] == [("ex", 5)] * 2
    # noop idx(默认 3)不发宿主
    m2 = make(
        [
            ins(SetLife, 0, life=ImmInt(10)),
            ins(SetExIns, 0, idx=ImmInt(3)),
            ins(Nop, 10),
        ],
        host,
    )
    n0 = len(host.calls)
    run_frames(m2, 2)
    assert all(c != ("ex", 3) for c in host.calls[n0:])


def test_auto_shoot_timer() -> None:
    """shoot_interval 走满一周期 → 宿主 on_auto_shoot; life<=0 不走。"""
    host = RecHost()
    m = make([ins(SetLife, 0, life=ImmInt(10)), ins(Nop, 99)], host)
    m.enemy.shoot_interval = 2
    run_frames(m, 5)
    assert [c for c in host.calls if c[0] == "shoot"] == [("shoot",), ("shoot",)]
    m.enemy.life = 0
    n0 = len(host.calls)
    run_frames(m, 4)
    assert all(c[0] != "shoot" for c in host.calls[n0:])


# ---- 移动/插值 ----


def test_init_interp_lerp() -> None:
    """变量插值: duration=2 线性从 p0 到 p1, 到顶清除。"""
    m = make(
        [
            ins(SetLife, 0, life=ImmInt(10)),
            ins(
                InitInterp,
                0,
                target_var=10004,
                duration=ImmInt(2),
                func=ImmInt(0),
                easing=ImmInt(0),
                p0=ImmFloat(0.0),
                p1=ImmFloat(10.0),
                p2=ImmFloat(0.0),
                p3=ImmFloat(0.0),
            ),
            ins(Nop, 99),
        ]
    )
    m.step()
    assert m.current.float_vars[10004] == pytest.approx(5.0)
    m.step()
    assert m.current.float_vars[10004] == pytest.approx(10.0)
    assert not any(it.active for it in m.current.interps)
    m.step()
    assert m.current.float_vars[10004] == pytest.approx(10.0)  # 不再动


def test_jump_invalid_target_halts() -> None:
    m = make([ins(Jump, 0, dest=9999, set_time=0)])
    assert m.step() is False
    assert m.finished
