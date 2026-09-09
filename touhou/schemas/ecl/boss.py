"""ECL boss/符卡/系统指令(boss 槽/符卡/ex 指令/脚本等待/时刻)。"""

from __future__ import annotations

from .base import EclInstr, FloatOperand, IntOperand


class SetBoss(EclInstr, frozen=True, tag="set_boss"):
    """登记/注销 boss 槽(idx 负 = 注销)。"""

    idx: IntOperand


class BeginSpellcard(EclInstr, frozen=True, tag="begin_spellcard"):
    """开符卡(v0 版: word0 = gui_id i16|spellcard_idx u16, 之后 12 字符卡名)。"""

    # 符卡名 48 字节 XOR 0xAA, NUL 截断, Shift-JIS
    # (EclManager.cpp BeginSpellcard; 解码在 decode.py 定制)
    gui_id: int
    spellcard_idx: int
    name: str


class BeginSpellcardV800(EclInstr, frozen=True, tag="begin_spellcard_v800"):
    """开符卡(v800 版: 多 bonus/机主名/两行注释)。"""

    # EclSpellCardInstructionArgs(EclDependencies.cpp:18-36):
    # word0 = enemyFace i16|spellCardNumber u16, bonus i32 @word1,
    # name[48] @word2, owner[48] @word14, comment[64]×2 @word26/42;
    # name 是 XOR 0xAA 文本(实测解码正确), owner/comment 编码未核实
    # (旧实现也不消费), 保留原始字
    gui_id: int
    spellcard_idx: int
    bonus: int
    name: str
    owner: tuple[int, ...]
    comment1: tuple[int, ...]
    comment2: tuple[int, ...]


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


class SetBossRunInterrupt(EclInstr, frozen=True, tag="set_boss_run_interrupt"):
    """设指定 boss 的 run_interrupt(v0 专属)。"""

    idx: IntOperand
    interrupt: IntOperand


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


class SetScriptWaitTime(EclInstr, frozen=True, tag="set_script_wait_time"):
    """设全局脚本等待时间(v0 专属)。"""

    frames: IntOperand


class SetStageScriptLabel(EclInstr, frozen=True, tag="set_stage_script_label"):
    """设场景脚本待跳转 label(v800 专属)。"""

    label: IntOperand


class SuppressTimelineSpawns(EclInstr, frozen=True, tag="suppress_timeline_spawns"):
    """全局抑制时间轴生敌(v800 专属)。"""

    value: IntOperand


class SetLastSpellFlags(EclInstr, frozen=True, tag="set_last_spell_flags"):
    """置 Last Spell 标志位 + pause timer(v800 专属; rest 收携带的未用字)。"""

    # EclRunHigh.inl:902-919; 真实数据带 1 个参数字, C 不读
    rest: tuple[int, ...] = ()


class SetSpellcardEffectTracking(
    EclInstr, frozen=True, tag="set_spellcard_effect_tracking"
):
    """设符卡特效跟踪(v800 专属)。"""

    value: IntOperand
    x: FloatOperand
    y: FloatOperand
    z: FloatOperand


class FreezeEclDuringBomb(EclInstr, frozen=True, tag="freeze_ecl_during_bomb"):
    """设炸弹中冻结本 VM 的 ECL 推进(v800 叫 pauseTimer)。"""

    # v0=161; v800=173
    value: IntOperand


class AddCherryPlus(EclInstr, frozen=True, tag="add_cherry_plus"):
    """樱点入账(v0 专属机制)。"""

    value: IntOperand


class StartStageBackgroundSequence(
    EclInstr, frozen=True, tag="start_stage_background_sequence"
):
    """启动关卡背景序列(v800 专属, 无参数)。"""


class HideClock(EclInstr, frozen=True, tag="hide_clock"):
    """隐藏时刻表盘(v800 专属, 无参数)。"""


class AdvanceClock(EclInstr, frozen=True, tag="advance_clock"):
    """时刻 +1 封顶 12(v800 专属, 无参数)。"""

    # EclRunHigh.inl:957-967


class SetBonusUpdatesDisabled(EclInstr, frozen=True, tag="set_bonus_updates_disabled"):
    """设符卡分更新禁止(v800 专属)。"""

    value: IntOperand
