"""ECL boss/符卡/系统指令(boss 槽/符卡/ex 指令), 两作共享部分。"""

from __future__ import annotations

from .base import EclInstr, IntOperand


class SetBoss(EclInstr, frozen=True, tag="set_boss"):
    """登记/注销 boss 槽(idx 负 = 注销)。"""

    idx: IntOperand


class EndSpellcard(EclInstr, frozen=True, tag="end_spellcard"):
    """结束符卡。"""


class SetBossHealth(EclInstr, frozen=True, tag="set_boss_health"):
    """设 boss 血条(idx, current, max, color; v800 叫 SetBossGaugeSlot)。"""

    # v800=158(EclRunHigh.inl:530-540)
    idx: IntOperand
    current: IntOperand
    max: IntOperand
    color: IntOperand


class SetNumBossLifeMarkers(EclInstr, frozen=True, tag="set_num_boss_life_markers"):
    """设 boss 命数标记个数。"""

    count: IntOperand


class RunExIns(EclInstr, frozen=True, tag="run_ex_ins"):
    """立即跑一次 ex 指令(args = 原始载荷字, 布局按 idx 由执行侧解释)。"""

    # v0=121/v800=136; ex 指令语义在宿主层(v0 24 条, v800 32 条,
    # EclGlobals.cpp:65-98)
    idx: IntOperand
    args: tuple[int, ...] = ()


class SetExIns(EclInstr, frozen=True, tag="set_ex_ins"):
    """注册每帧 ex 回调(idx 负 = 注销; args 同 RunExIns)。"""

    idx: IntOperand
    args: tuple[int, ...] = ()


class FreezeEclDuringBomb(EclInstr, frozen=True, tag="freeze_ecl_during_bomb"):
    """设炸弹中冻结本 VM 的 ECL 推进(v800 叫 pauseTimer)。"""

    # v0=161; v800=173
    value: IntOperand
