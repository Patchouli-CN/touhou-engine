"""th08 ECL 指令集: v800 opcode 表 + 符卡定制编解码 + InstrSet 装配。

编号/布局出处 th08 EclRunLow.inl:223-929 / EclRunHigh.inl:163-972
(转引 scratch_dbg/investigation/th08-ref-facts.md:21 与旧实现
games/th08/ecl_vm.py 的逐条出处注释)。parse_ecl 薄包装把版本布局(0x800)/
指令集/时间轴解码器一并注入。
"""

from __future__ import annotations

from typing import Any

from ...schemas.ecl import (
    EclFile,
    EclInstr,
    InstrSet,
    build_instr_set,
)
from ...schemas.ecl import parse_ecl as _parse_ecl
from ...schemas.ecl.boss import (
    EndSpellcard,
    FreezeEclDuringBomb,
    RunExIns,
    SetBoss,
    SetBossHealth,
    SetExIns,
    SetNumBossLifeMarkers,
)
from ...schemas.ecl.bullets import (
    AddLaserAngle,
    AimLaserAtPlayer,
    ClearLasers,
    InitBulletCmd,
    RemoveAllBullets,
    RemoveBulletsRadius,
    SetBulletRankParams,
    SetBulletSound,
    SetLaserAngle,
    SetLaserHideWarning,
    SetLaserIdx,
    SetLaserOffsets,
    SetLaserPosRel,
    SetLaserStartLen,
    SetShootInterval,
    SetShootIntervalRand,
    SpawnPrevBulletPattern,
    StopLaser,
)
from ...schemas.ecl.control import (
    AddTime,
    DecJump,
    Jump,
    Nop,
    SetInterrupt,
    SetNoStackRet,
    SetWaitTimer,
    Stop,
    SubCall,
    SubRet,
)
from ...schemas.ecl.decode import (
    _decode_text,
    _encode_text,
    _i16,
    _i32,
    _u16,
)
from ...schemas.ecl.enemy import (
    BindTimerCallbackToDeath,
    PlaySound,
    RemoveAllEnemies,
    SetAnm,
    SetDeathAnm,
    SetDeathType,
    SetInvincibilityTimer,
    SetIsSurvivalSpellcard,
    SetLife,
    SetLifeCallback,
    SetPrimaryVmInterrupt,
    SetPrimaryVmRotZ,
    SetSubAnm,
    SetTimer,
    SetTrail,
    SetVmAutoRotate,
    SpawnEffect,
    SpawnEnemyAbs,
    SpawnEnemyRel,
    SpawnItem,
    SpawnItems,
    SpawnMovingParticles,
    SpawnParticles,
    SpawnPointItems,
)
from ...schemas.ecl.mathops import (
    Atan2,
    Cos,
    Dec,
    GetBossFloat,
    GetBossInt,
    Inc,
    InitInterp,
    Lerp,
    NormalizeAngle,
    RandExitAngle,
    RandSign,
    RandSignFloat,
    SetFloat,
    SetInt,
    Sin,
    VecFromAngleMagRaw,
)
from ...schemas.ecl.movement import (
    DisableMovementBounds,
    MoveAtPlayer,
    MoveDirTime,
    SetAngularVel,
    SetMoveAccel,
    SetMovementBounds,
)
from ...schemas.ecl.spec import (
    _A,
    _CONDS,
    _FLOAT_ARITH,
    _INT_ARITH,
    _bullet,
    _cond,
    _Entry,
    _spawn_enemy,
)
from ...schemas.exceptions import ParseError
from .ecl_instrs import (
    AddAssign,
    AddAssignFloat,
    AdvanceClock,
    BeginSpellcardV800,
    CallSubOnBoss,
    ClearBulletsForTransition,
    ClearEnemyFlags,
    DeferBulletPattern,
    DisableDeferBulletPattern,
    Dist,
    DivAssign,
    DivAssignFloat,
    EnableEnemyFlags,
    HideClock,
    ModAssign,
    ModAssignFloat,
    MoveAtPlayerTime,
    MoveBoundaryAware,
    MoveOrbitAroundSelf,
    MoveOrbitV800,
    MovePosTimeV800,
    MoveRandomBiased,
    MulAssign,
    MulAssignFloat,
    RunPendingSub,
    SetBonusUpdatesDisabled,
    SetBossPendingSub,
    SetChildContext,
    SetDeathCallbackSubV800,
    SetDrawGroup,
    SetEnemyFlags,
    SetEnemyManagerValue,
    SetExtraVmFixedOffset,
    SetFormEffect,
    SetGrazeSizeV800,
    SetHitboxSizeV800,
    SetItemDrop,
    SetItemDropCounts,
    SetLastSpellFlags,
    SetMinPlayerDistance,
    SetMoveAnmSeq,
    SetMoveAnmV800,
    SetMovePolar,
    SetNoDamageDuringStop,
    SetOrbitVels,
    SetPhaseStartLife,
    SetPosV800,
    SetShootOffsetV800,
    SetSpecialAnm,
    SetSpecialInteraction,
    SetSpellcardEffectTracking,
    SetStageScriptLabel,
    SetTimerCallback,
    SetVmInterruptV800,
    SpawnAlignmentEffect,
    SpawnFamiliar,
    SpawnFamiliarInherit,
    SpawnFamiliarRel,
    SpawnLaserPatternV800,
    StartStageBackgroundSequence,
    SubAssign,
    SubAssignFloat,
    SuppressTimelineSpawns,
    TestLaserInUse,
    VecFromAngleMag,
)
from .ecl_timeline import decode_timeline


def _laser_v800(aimed: bool) -> _Entry:
    """激光表项(width/计时可变参)。"""
    return _Entry(
        SpawnLaserPatternV800,
        (
            _A("sprite", 0, "hu0"),
            _A("sprite_offset", 0, "h1m", 1),
            _A("angle", 1, "float", 2),
            _A("speed", 2, "float", 3),
            _A("start_offset", 3, "float", 4),
            _A("end_offset", 4, "float", 5),
            _A("start_length", 5, "float", 6),
            _A("width", 6, "float", 7),
            _A("start_time", 7, "int", 8),
            _A("duration", 8, "int", 9),
            _A("despawn_duration", 9, "int", 10),
            _A("hitbox_start_time", 10, "ri"),
            _A("hitbox_end_delay", 11, "ri"),
            _A("flags", 12, "ri"),
        ),
        {"aimed": aimed},
    )


def _familiar(cls: type[EclInstr]) -> _Entry:
    """使魔生成表项(三个 opcode 同布局)。"""
    return _Entry(
        cls,
        (
            _A("sub_id", 0, "ri"),
            _A("x", 1, "float"),
            _A("y", 2, "float"),
            _A("life", 3, "int"),
            _A("item_drop", 4, "int"),
            _A("score", 5, "int"),
        ),
    )


_INT_ASSIGN: tuple[type[EclInstr], ...] = (
    AddAssign,
    SubAssign,
    MulAssign,
    DivAssign,
    ModAssign,
)
_FLOAT_ASSIGN: tuple[type[EclInstr], ...] = (
    AddAssignFloat,
    SubAssignFloat,
    MulAssignFloat,
    DivAssignFloat,
    ModAssignFloat,
)

_V800: dict[int, _Entry] = {
    0: _Entry(Nop, (_A("rest", 0, "rest"),)),
    3: _Entry(Nop, (_A("rest", 0, "rest"),)),
    84: _Entry(Nop, (_A("rest", 0, "rest"),)),
    85: _Entry(Nop, (_A("rest", 0, "rest"),)),
    1: _Entry(Stop),
    2: _Entry(SetWaitTimer, (_A("frames", 0, "int"),)),
    4: _Entry(Jump, (_A("dest", 0, "ri"), _A("set_time", 1, "ri"))),
    5: _Entry(
        DecJump, (_A("dest", 0, "ri"), _A("set_time", 1, "ri"), _A("count", 2, "int"))
    ),
    6: _Entry(SetInt, (_A("dest", 0, "int_t"), _A("value", 1, "int"))),
    7: _Entry(SetFloat, (_A("dest", 0, "float_t"), _A("value", 1, "float"))),
    8: _Entry(RandSign, (_A("dest", 0, "int_t"), _A("magnitude", 1, "int"))),
    9: _Entry(RandSignFloat, (_A("dest", 0, "float_t"), _A("magnitude", 1, "float"))),
    30: _Entry(Inc, (_A("dest", 0, "int_t"),)),
    31: _Entry(Dec, (_A("dest", 0, "int_t"),)),
    32: _Entry(Sin, (_A("dest", 0, "float_t"), _A("value", 1, "float"))),
    33: _Entry(Cos, (_A("dest", 0, "float_t"), _A("value", 1, "float"))),
    34: _Entry(
        Atan2,
        (
            _A("dest", 0, "float_t"),
            _A("x1", 1, "float"),
            _A("y1", 2, "float"),
            _A("x2", 3, "float"),
            _A("y2", 4, "float"),
        ),
    ),
    35: _Entry(
        Lerp,
        (
            _A("dest", 0, "float_t"),
            _A("a", 1, "float"),
            _A("b", 2, "float"),
            _A("t", 3, "float"),
        ),
    ),
    36: _Entry(
        InitInterp,
        (
            _A("target_var", 0, "fvid"),
            _A("duration", 1, "int"),
            _A("func", 2, "int"),
            _A("easing", 3, "int"),
            _A("p0", 4, "float"),
            _A("p1", 5, "float"),
            _A("p2", 6, "float"),
            _A("p3", 7, "float"),
        ),
    ),
    37: _Entry(NormalizeAngle, (_A("dest", 0, "float_t"), _A("value", 0, "float"))),
    38: _Entry(
        VecFromAngleMag,
        (
            _A("dest_x", 0, "float_t"),
            _A("dest_y", 1, "float_t"),
            _A("angle", 2, "float"),
            _A("magnitude", 3, "float"),
        ),
    ),
    39: _Entry(
        Dist,
        (
            _A("dest", 0, "float_t"),
            _A("x1", 1, "float"),
            _A("y1", 2, "float"),
            _A("x2", 3, "float"),
            _A("y2", 4, "float"),
        ),
    ),
    52: _Entry(SubCall, (_A("sub_id", 0, "ri"),)),
    53: _Entry(SubRet),
    54: _Entry(SetAnm, (_A("anm_idx", 0, "int"),), {"alt_bank": False}),
    55: _Entry(SetMoveAnmSeq, (_A("base", 0, "int"),), {"alt_bank": False}),
    56: _Entry(
        SetMoveAnmV800,
        tuple(_A("scripts", w, "int") for w in range(6)),
        {"alt_bank": False},
    ),
    57: _Entry(
        SetSubAnm, (_A("idx", 0, "int"), _A("anm_idx", 1, "int")), {"alt_bank": False}
    ),
    58: _Entry(SetAnm, (_A("anm_idx", 0, "int"),), {"alt_bank": True}),
    59: _Entry(SetMoveAnmSeq, (_A("base", 0, "int"),), {"alt_bank": True}),
    60: _Entry(
        SetMoveAnmV800,
        tuple(_A("scripts", w, "int") for w in range(6)),
        {"alt_bank": True},
    ),
    61: _Entry(
        SetSubAnm, (_A("idx", 0, "int"), _A("anm_idx", 1, "int")), {"alt_bank": True}
    ),
    62: _Entry(SetSpecialAnm),
    63: _Entry(SetPosV800, (_A("x", 0, "float"), _A("y", 1, "float"))),
    64: _Entry(
        MovePosTimeV800,
        (
            _A("duration", 0, "int"),
            _A("easing", 1, "int"),
            _A("x", 2, "float"),
            _A("y", 3, "float"),
        ),
    ),
    65: _Entry(SetMovePolar, (_A("angle", 0, "float"), _A("speed", 1, "float"))),
    66: _Entry(
        MoveDirTime,
        (
            _A("duration", 0, "int"),
            _A("easing", 1, "int"),
            _A("angle", 2, "float"),
            _A("speed", 3, "float"),
        ),
    ),
    67: _Entry(
        MoveBoundaryAware,
        (_A("duration", 0, "int"), _A("easing", 1, "int"), _A("speed", 2, "float")),
    ),
    68: _Entry(MoveAtPlayer, (_A("angle_offset", 0, "float"), _A("speed", 1, "float"))),
    69: _Entry(
        MoveAtPlayerTime,
        (
            _A("duration", 0, "int"),
            _A("easing", 1, "int"),
            _A("angle", 2, "float"),
            _A("speed", 3, "float"),
        ),
    ),
    70: _Entry(SetAngularVel, (_A("velocity", 0, "float"),)),
    71: _Entry(SetMoveAccel, (_A("accel", 0, "float"),)),
    72: _Entry(
        MoveOrbitV800,
        (
            _A("duration", 0, "int"),
            _A("origin_x", 1, "float"),
            _A("origin_y", 2, "float"),
            _A("angle", 3, "float"),
            _A("angular_vel", 4, "float"),
            _A("radius", 5, "float"),
            _A("radial_vel", 6, "float"),
        ),
    ),
    73: _Entry(
        MoveOrbitAroundSelf,
        (
            _A("duration", 0, "int"),
            _A("angle", 1, "float"),
            _A("angular_vel", 2, "float"),
            _A("radial_vel", 3, "float"),
        ),
    ),
    74: _Entry(
        SetOrbitVels,
        (
            _A("duration", 0, "int"),
            _A("angular_vel", 1, "float"),
            _A("radial_vel", 2, "float"),
        ),
    ),
    75: _Entry(
        SetMovementBounds,
        (
            _A("x_min", 0, "float"),
            _A("y_min", 1, "float"),
            _A("x_max", 2, "float"),
            _A("y_max", 3, "float"),
        ),
    ),
    76: _Entry(DisableMovementBounds),
    77: _Entry(SetHitboxSizeV800, (_A("x", 0, "float"), _A("y", 1, "float"))),
    78: _Entry(SetGrazeSizeV800, (_A("x", 0, "float"), _A("y", 1, "float"))),
    79: _Entry(SetEnemyFlags, (_A("mask", 0, "int"),)),
    80: _Entry(ClearEnemyFlags, (_A("mask", 0, "int"),)),
    81: _Entry(EnableEnemyFlags, (_A("mask", 0, "int"),)),
    82: _Entry(SetMinPlayerDistance, (_A("distance", 0, "float"),)),
    83: _Entry(SetFormEffect, (_A("value", 0, "int"),)),
    86: _Entry(
        GetBossInt,
        (_A("dest", 0, "int_t"), _A("var", 1, "int"), _A("boss_idx", 2, "int")),
    ),
    87: _Entry(
        GetBossFloat,
        (_A("dest", 0, "float_t"), _A("var", 1, "float"), _A("boss_idx", 2, "int")),
    ),
    88: _Entry(CallSubOnBoss, (_A("boss_idx", 0, "int"), _A("sub_id", 1, "ri"))),
    89: _Entry(SetBossPendingSub, (_A("boss_idx", 0, "int"), _A("sub_id", 1, "int"))),
    90: _familiar(SpawnFamiliar),
    91: _familiar(SpawnFamiliarRel),
    92: _familiar(SpawnFamiliarInherit),
    93: _spawn_enemy(SpawnEnemyAbs),
    94: _spawn_enemy(SpawnEnemyRel),
    95: _Entry(RemoveAllEnemies),
    105: _Entry(SetShootInterval, (_A("interval", 0, "int"),)),
    106: _Entry(SetShootIntervalRand, (_A("interval", 0, "int"),)),
    107: _Entry(DeferBulletPattern),
    108: _Entry(DisableDeferBulletPattern),
    109: _Entry(SpawnPrevBulletPattern),
    110: _Entry(SetShootOffsetV800, (_A("x", 0, "float"), _A("y", 1, "float"))),
    111: _Entry(
        InitBulletCmd,
        (
            _A("slot", 0, "int"),
            _A("type", 1, "int"),
            _A("flag", 2, "int"),
            _A("duration", 3, "int"),
            _A("loop_count", 4, "int"),
            _A("speed", 5, "float"),
            _A("angle", 6, "float"),
        ),
    ),
    112: _Entry(ClearBulletsForTransition),
    113: _Entry(
        SetBulletSound, (_A("sound_idx", 0, "int"), _A("sound_override", 1, "int"))
    ),
    114: _laser_v800(False),
    115: _laser_v800(True),
    116: _Entry(SetLaserIdx, (_A("idx", 0, "int"),)),
    117: _Entry(AddLaserAngle, (_A("idx", 0, "int"), _A("delta", 1, "float"))),
    118: _Entry(AimLaserAtPlayer, (_A("idx", 0, "int"), _A("aim_offset", 1, "float"))),
    119: _Entry(
        SetLaserPosRel,
        (
            _A("idx", 0, "int"),
            _A("x", 1, "float"),
            _A("y", 2, "float"),
            _A("z", 3, "float"),
        ),
    ),
    120: _Entry(TestLaserInUse, (_A("idx", 0, "int"),)),
    121: _Entry(StopLaser, (_A("idx", 0, "int"),)),
    122: _Entry(BeginSpellcardV800),
    123: _Entry(EndSpellcard),
    124: _Entry(PlaySound, (_A("sound_idx", 0, "int"),)),
    125: _Entry(RunPendingSub, (_A("slot", 0, "int"),)),
    126: _Entry(SetInterrupt, (_A("sub_id", 0, "int"), _A("slot", 1, "int"))),
    127: _Entry(SetBoss, (_A("idx", 0, "int"),)),
    128: _Entry(
        SpawnEffect,
        (
            _A("color", 0, "ri"),
            _A("dx", 1, "rf"),
            _A("dy", 2, "rf"),
            _A("dz", 3, "rf"),
            _A("distance", 4, "rf"),
        ),
    ),
    129: _Entry(SetDeathType, (_A("value", 0, "b0"),)),
    130: _Entry(SetDeathCallbackSubV800, (_A("sub_id", 0, "h0"),)),
    131: _Entry(SetLife, (_A("life", 0, "int"),)),
    132: _Entry(SetTimer, (_A("value", 0, "int"),)),
    133: _Entry(
        SetLifeCallback,
        (_A("idx", 0, "int"), _A("threshold", 1, "int"), _A("sub_id", 2, "int")),
    ),
    134: _Entry(SetTimerCallback, (_A("threshold", 0, "int"), _A("sub_id", 1, "int"))),
    135: _Entry(SetChildContext, (_A("slot", 0, "int"), _A("sub_id", 1, "int"))),
    136: _Entry(RunExIns, (_A("idx", 0, "int"), _A("args", 1, "rest"))),
    137: _Entry(SetExIns, (_A("idx", 0, "int"), _A("args", 1, "rest"))),
    138: _Entry(SetDeathAnm, (_A("a", 0, "sb0"), _A("b", 0, "b1"), _A("c", 0, "sb2"))),
    139: _Entry(
        SpawnParticles,
        (_A("effect_idx", 0, "int"), _A("count", 1, "int"), _A("color", 2, "int")),
    ),
    140: _Entry(
        SpawnMovingParticles,
        (
            _A("effect_idx", 0, "int"),
            _A("count", 1, "int"),
            _A("color", 2, "int"),
            _A("vx", 3, "float"),
            _A("vy", 4, "float"),
            _A("vz", 5, "float"),
        ),
    ),
    141: _Entry(SpawnItem, (_A("item_type", 0, "int"),)),
    142: _Entry(SpawnItems, (_A("count", 0, "int"),)),
    143: _Entry(SetItemDrop, (_A("value", 0, "int"),)),
    144: _Entry(
        SetItemDropCounts,
        (_A("point_count", 0, "int"), _A("power_or_point_count", 1, "int")),
    ),
    145: _Entry(SetVmAutoRotate, (_A("value", 0, "b0"),)),
    146: _Entry(AddTime, (_A("delta", 0, "int"),)),
    147: _Entry(SetStageScriptLabel, (_A("label", 0, "int"),)),
    148: _Entry(SetNumBossLifeMarkers, (_A("count", 0, "int"),)),
    149: _Entry(SetPrimaryVmInterrupt, (_A("value", 0, "int"),)),
    150: _Entry(SetVmInterruptV800, (_A("idx", 0, "ri"), _A("value", 1, "hu0"))),
    151: _Entry(SetNoStackRet, (_A("value", 0, "b0"),)),
    152: _Entry(
        SetBulletRankParams,
        (
            _A("speed_low", 0, "float"),
            _A("speed_high", 1, "float"),
            _A("amount1_low", 2, "int"),
            _A("amount1_high", 3, "int"),
            _A("amount2_low", 4, "int"),
            _A("amount2_high", 5, "int"),
        ),
    ),
    153: _Entry(BindTimerCallbackToDeath),
    154: _Entry(ClearLasers),
    155: _Entry(SetIsSurvivalSpellcard, (_A("value", 0, "b0"),)),
    156: _Entry(SetSpecialInteraction, (_A("value", 0, "b0"),)),
    157: _Entry(
        SetTrail,
        (
            _A("flags", 0, "b0"),
            _A("count", 1, "int"),
            _A("interval", 2, "int"),
            _A("node_step", 3, "int"),
        ),
    ),
    158: _Entry(
        SetBossHealth,
        (
            _A("idx", 0, "int"),
            _A("current", 1, "int"),
            _A("max", 2, "int"),
            _A("color", 3, "int"),
        ),
    ),
    159: _Entry(SetDrawGroup, (_A("value", 0, "int"),)),
    160: _Entry(SetInvincibilityTimer, (_A("frames", 0, "int"),)),
    161: _Entry(RemoveBulletsRadius, (_A("radius", 0, "float"),)),
    162: _Entry(RemoveAllBullets, consts={"mode": 4}),
    163: _Entry(SetEnemyManagerValue, (_A("value", 0, "int"),)),
    164: _Entry(
        SetSpellcardEffectTracking,
        (
            _A("value", 0, "int"),
            _A("x", 1, "float"),
            _A("y", 2, "float"),
            _A("z", 3, "float"),
        ),
    ),
    165: _Entry(SetPrimaryVmRotZ, (_A("value", 0, "float"),)),
    166: _Entry(
        VecFromAngleMagRaw,
        (
            _A("dest_x", 0, "float_t"),
            _A("dest_y", 1, "float_t"),
            _A("angle", 2, "float"),
            _A("magnitude", 3, "float"),
        ),
    ),
    167: _Entry(SetLaserAngle, (_A("idx", 0, "int"), _A("angle", 1, "float"))),
    168: _Entry(SpawnPointItems, (_A("count", 0, "int"),)),
    169: _Entry(RandExitAngle, (_A("dest", 0, "float_t"),)),
    170: _Entry(SetLaserHideWarning, (_A("idx", 0, "int"), _A("value", 1, "int"))),
    171: _Entry(SetLaserStartLen, (_A("idx", 0, "int"), _A("value", 1, "float"))),
    172: _Entry(
        SetLaserOffsets,
        (_A("idx", 0, "int"), _A("start", 1, "float"), _A("end", 2, "float")),
    ),
    173: _Entry(FreezeEclDuringBomb, (_A("value", 0, "int"),)),
    174: _Entry(SpawnAlignmentEffect, (_A("value", 0, "int"),)),
    175: _Entry(SuppressTimelineSpawns, (_A("value", 0, "int"),)),
    176: _Entry(SetLastSpellFlags, (_A("rest", 0, "rest"),)),
    177: _Entry(SetPhaseStartLife, (_A("value", 0, "int"),)),
    178: _Entry(
        MoveRandomBiased,
        (_A("duration", 0, "int"), _A("easing", 1, "int"), _A("speed", 2, "float")),
    ),
    179: _Entry(StartStageBackgroundSequence),
    180: _Entry(HideClock),
    181: _Entry(AdvanceClock),
    182: _Entry(SetExtraVmFixedOffset, (_A("value", 0, "int"),)),
    183: _Entry(SetNoDamageDuringStop, (_A("value", 0, "int"),)),
    184: _Entry(SetBonusUpdatesDisabled, (_A("value", 0, "int"),)),
}
for _i, _cls in enumerate(_INT_ASSIGN):  # 10-14: 2 操作数算术 int(v800 独有)
    _V800[10 + _i] = _Entry(_cls, (_A("dest", 0, "int_t"), _A("value", 1, "int")))
for _i, _cls in enumerate(_FLOAT_ASSIGN):  # 15-19: float 版
    _V800[15 + _i] = _Entry(_cls, (_A("dest", 0, "float_t"), _A("value", 1, "float")))
for _i, _cls in enumerate(_INT_ARITH):  # 20-24
    _V800[20 + _i] = _Entry(
        _cls, (_A("dest", 0, "int_t"), _A("a", 1, "int"), _A("b", 2, "int"))
    )
for _i, _cls in enumerate(_FLOAT_ARITH):  # 25-29
    _V800[25 + _i] = _Entry(
        _cls, (_A("dest", 0, "float_t"), _A("a", 1, "float"), _A("b", 2, "float"))
    )
for _i, (_cls, _f) in enumerate(_CONDS):  # 40-51
    _V800[40 + _i] = _cond(_cls, _f)
for _op in range(96, 105):  # 弹幕生成 9 合一(aim_mode = opcode - 96)
    _V800[_op] = _bullet(_op - 96)


# ---- 符卡定制编解码(内嵌 XOR 0xAA 字符串, 字段规格表达不了) ----


def _decode_spellcard(
    base: dict[str, Any], words: tuple[int, ...], mask: int
) -> EclInstr:
    # 布局(EclDependencies.cpp:18-36): word0 = face i16|number u16,
    # bonus i32 @word1, name[48] @word2, owner[48] @word14, comment[64]×2 @word26/42
    if len(words) != 58:
        raise ParseError(f"begin_spellcard_v800 参数数不符: {len(words)} != 58")
    return BeginSpellcardV800(
        **base,
        gui_id=_i16(words[0], 0),
        spellcard_idx=_u16(words[0], 1),
        bonus=_i32(words[1]),
        name=_decode_text(words[2:14]),
        owner=words[14:26],
        comment1=words[26:42],
        comment2=words[42:58],
    )


def _encode_spellcard(instr: Any) -> list[int]:
    words = [(instr.gui_id & 0xFFFF) | ((instr.spellcard_idx & 0xFFFF) << 16)]
    words.append(instr.bonus & 0xFFFFFFFF)
    words += _encode_text(instr.name, 48)
    for raw in (instr.owner, instr.comment1, instr.comment2):
        words.extend(raw)
    return words


#: th08 的 ECL 指令集(v800 表 + 符卡定制钩子 + encode 反查表)
ECL_INSTR_SET: InstrSet = build_instr_set(
    _V800,
    custom_decode={BeginSpellcardV800: _decode_spellcard},
    custom_encode={BeginSpellcardV800: _encode_spellcard},
)


def parse_ecl(data: bytes) -> EclFile:
    """解析 th08 的 .ecl(v800 布局 + v800 指令集 + v800 时间轴)。"""
    return _parse_ecl(
        data, version=0x800, instrs=ECL_INSTR_SET, decode_tl=decode_timeline
    )
