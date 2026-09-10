"""th07 专属指令经 extra_handlers 注入后的 EclMachine 行为测试(合成脚本)。"""

from __future__ import annotations

from typing import get_args

import msgspec
import pytest

from touhou.engine.ecl import HANDLERS, EclHost, EclMachine
from touhou.engine.rng import Rng
from touhou.games.th07.ecl_handlers import ECL_EXTRA_HANDLERS
from touhou.games.th07.ecl_instrs import (
    Instruction,
    MovePosTime,
    SetAxisSpeed,
    SetPeriodicCallback,
    SetPos,
)
from touhou.schemas.ecl import (
    Add,
    EclFile,
    EclInstr,
    EclSub,
    ImmFloat,
    ImmInt,
    Nop,
    SetMovementBounds,
    SubRet,
    VarRef,
)

INT_VARS = frozenset({10000, 10001, 10002, 10003})
FLOAT_VARS = frozenset({10004, 10005, 10006, 10007})

_STEP = 16  # 合成指令的伪字节偏移步长(跳转位移 = 下标差 × 16)


def build_file(*subs: list[EclInstr]) -> EclFile:
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


def make(instrs: list[EclInstr], host: EclHost | None = None) -> EclMachine:
    """单 sub 机器(v0 专属 handler 全量注入), 直接 start(0) 就绪。"""
    m = EclMachine(
        build_file(instrs),
        host if host is not None else EclHost(),
        Rng(0),
        int_var_ids=INT_VARS,
        float_var_ids=FLOAT_VARS,
        extra_handlers=ECL_EXTRA_HANDLERS,
    )
    m.start(0)
    return m


def ins(cls, time: int, **kw) -> EclInstr:
    return cls(offset=0, time=time, skip_difficulty=0xFF, **kw)


def run_frames(m: EclMachine, n: int) -> None:
    for _ in range(n):
        m.step()


def test_handler_injection_covers_union() -> None:
    """注入后分派表覆盖 th07 全 union。"""
    m = make([ins(Nop, 99)])
    assert set(get_args(Instruction)) == set(m.handlers)
    assert set(HANDLERS) <= set(m.handlers)


def test_periodic_callback() -> None:
    """周期回调: 计数到点进 sub, 变量区经 saved 快照往返。"""
    sub0 = [
        ins(SetPeriodicCallback, 0, timer=ImmInt(2), sub_id=ImmInt(1)),
        ins(Nop, 99),
    ]
    sub1 = [
        ins(Add, 0, dest=VarRef(10003), a=VarRef(10003), b=ImmInt(1)),
        ins(SubRet, 0),
    ]
    m = EclMachine(
        build_file(sub0, sub1),
        EclHost(),
        Rng(0),
        int_var_ids=INT_VARS,
        float_var_ids=FLOAT_VARS,
        extra_handlers=ECL_EXTRA_HANDLERS,
    )
    m.start(0)
    run_frames(m, 3)
    assert m.enemy.saved_int_vars.get(10003) == 1  # 首次触发: 空快照 0+1
    run_frames(m, 1)
    assert m.enemy.saved_int_vars.get(10003) == 2  # 第二次: 快照载入 1+1


def test_move_pos_time_linear() -> None:
    """限时移动到目标点: 4 帧线性走完 (0,0,0)→(8,0,0), 每帧 2。"""
    m = make(
        [
            ins(SetPos, 0, x=ImmFloat(0.0), y=ImmFloat(0.0), z=ImmFloat(0.0)),
            ins(
                MovePosTime,
                0,
                duration=ImmInt(4),
                easing=ImmInt(0),
                x=ImmFloat(8.0),
                y=ImmFloat(0.0),
                z=ImmFloat(0.0),
            ),
            ins(Nop, 99),
        ]
    )
    for expect in (2.0, 4.0, 6.0, 8.0):
        m.step()
        assert m.enemy.pos.x == pytest.approx(expect)
    assert m.enemy.move_mode == 0  # 走完归零
    assert m.enemy.axis_speed.x == 0.0


def test_movement_bounds_clamp() -> None:
    """移动范围: SetPos/帧积分都被 ClampPos 夹住。"""
    m = make(
        [
            ins(
                SetMovementBounds,
                0,
                x_min=ImmFloat(-10.0),
                y_min=ImmFloat(-10.0),
                x_max=ImmFloat(10.0),
                y_max=ImmFloat(10.0),
            ),
            ins(SetPos, 0, x=ImmFloat(100.0), y=ImmFloat(0.0), z=ImmFloat(0.0)),
            ins(SetAxisSpeed, 0, x=ImmFloat(50.0), y=ImmFloat(0.0), z=ImmFloat(0.0)),
            ins(Nop, 99),
        ]
    )
    m.step()
    assert m.enemy.pos.x == 10.0  # SetPos 当场夹
    m.step()
    assert m.enemy.pos.x == 10.0  # 积分后仍夹在界内
