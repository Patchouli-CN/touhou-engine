"""th07 ECL 指令集: v0 opcode 表 + 符卡定制编解码 + InstrSet 装配。

编号/布局出处 Reference/th07/src/th07/EclManager.hpp:115-271 + EclManager.cpp。
parse_ecl 薄包装把版本布局(0)/指令集/时间轴解码器一并注入(架构稿 §2.6:
格式变体走变体专用的薄函数)。
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
    AddCherryPlus,
    BeginSpellcard,
    DisableBullets,
    EnableBullets,
    GetExitAngle,
    Idfk,
    MoveOrbit,
    MovePosTime,
    Rand,
    RandAdd,
    RandFloat,
    RandFloatAdd,
    RandFloatRange,
    SetAxisSpeed,
    SetBossRunInterrupt,
    SetCanBeDamaged,
    SetDeathCallbackSub,
    SetDespawnOnOob,
    SetEnemyCanDie,
    SetGlobalEffectColorMul,
    SetGrazeSize,
    SetHasContactHitbox,
    SetHasNoCollision,
    SetHitboxSize,
    SetIsHittable,
    SetIsProjectile,
    SetLifeCallbackSub,
    SetLifeCallbackThreshold,
    SetMoveAnm,
    SetMoveInterpTimerInterp,
    SetMoveInterpTimerPolar,
    SetMoveInterpTimerRadial,
    SetMoveSpeed,
    SetOrbitAngle,
    SetOrbitRadius,
    SetPeriodicCallback,
    SetPos,
    SetRunInterrupt,
    SetScriptWaitTime,
    SetShootOffset,
    SetSpecialEffectPos,
    SetTimerCallbackSub,
    SetTimerCallbackThreshold,
    SetVmInterrupt,
    SpawnLaserPattern,
    TestLaserNotInUse,
)
from .ecl_timeline import decode_timeline


def _laser_v0(moving: bool) -> _Entry:
    """激光表项(width/计时/flags 全 raw)。"""
    return _Entry(
        SpawnLaserPattern,
        (
            _A("sprite", 0, "h0"),
            _A("sprite_offset", 0, "h1m", 1),
            _A("angle", 1, "float", 2),
            _A("speed", 2, "float", 3),
            _A("start_offset", 3, "float", 4),
            _A("end_offset", 4, "float", 5),
            _A("start_length", 5, "float", 6),
            _A("width", 6, "rf"),
            _A("start_time", 7, "ri"),
            _A("duration", 8, "ri"),
            _A("end_time", 9, "ri"),
            _A("hitbox_start_time", 10, "ri"),
            _A("hitbox_end_time", 11, "ri"),
            _A("flags", 12, "ri"),
        ),
        {"moving": moving},
    )


_V0: dict[int, _Entry] = {
    0: _Entry(Nop, (_A("rest", 0, "rest"),)),
    141: _Entry(Nop, (_A("rest", 0, "rest"),)),
    1: _Entry(Stop),
    2: _Entry(Jump, (_A("dest", 0, "ri"), _A("set_time", 1, "ri"))),
    3: _Entry(
        DecJump, (_A("dest", 0, "ri"), _A("set_time", 1, "ri"), _A("count", 2, "int"))
    ),
    4: _Entry(SetInt, (_A("dest", 0, "int_t"), _A("value", 1, "int"))),
    5: _Entry(SetFloat, (_A("dest", 0, "float_t"), _A("value", 1, "float"))),
    6: _Entry(Rand, (_A("dest", 0, "int_t"), _A("bound", 1, "int"))),
    7: _Entry(
        RandAdd, (_A("dest", 0, "int_t"), _A("bound", 1, "int"), _A("addend", 2, "int"))
    ),
    8: _Entry(RandFloat, (_A("dest", 0, "float_t"), _A("scale", 1, "float"))),
    9: _Entry(
        RandFloatAdd,
        (_A("dest", 0, "float_t"), _A("scale", 1, "float"), _A("addend", 2, "float")),
    ),
    10: _Entry(RandSign, (_A("dest", 0, "int_t"), _A("magnitude", 1, "int"))),
    11: _Entry(RandSignFloat, (_A("dest", 0, "float_t"), _A("magnitude", 1, "float"))),
    17: _Entry(Inc, (_A("dest", 0, "int_t"),)),
    18: _Entry(Dec, (_A("dest", 0, "int_t"),)),
    24: _Entry(Sin, (_A("dest", 0, "float_t"), _A("value", 1, "float"))),
    25: _Entry(Cos, (_A("dest", 0, "float_t"), _A("value", 1, "float"))),
    26: _Entry(
        Atan2,
        (
            _A("dest", 0, "float_t"),
            _A("x1", 1, "float"),
            _A("y1", 2, "float"),
            _A("x2", 3, "float"),
            _A("y2", 4, "float"),
        ),
    ),
    27: _Entry(
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
    40: _Entry(NormalizeAngle, (_A("dest", 0, "float_t"), _A("value", 0, "float"))),
    41: _Entry(SubCall, (_A("sub_id", 0, "ri"),)),
    42: _Entry(SubRet),
    43: _Entry(
        GetBossInt,
        (_A("dest", 0, "int_t"), _A("var", 1, "int"), _A("boss_idx", 2, "int")),
    ),
    44: _Entry(
        GetBossFloat,
        (_A("dest", 0, "float_t"), _A("var", 1, "float"), _A("boss_idx", 2, "int")),
    ),
    45: _Entry(SetWaitTimer, (_A("frames", 0, "int"),)),
    46: _Entry(SetPos, (_A("x", 0, "float"), _A("y", 1, "float"), _A("z", 2, "float"))),
    47: _Entry(
        SetAxisSpeed, (_A("x", 0, "float"), _A("y", 1, "float"), _A("z", 2, "float"))
    ),
    48: _Entry(SetAngularVel, (_A("velocity", 0, "float"),)),
    49: _Entry(SetMoveSpeed, (_A("speed", 0, "float"),)),
    50: _Entry(SetMoveAccel, (_A("accel", 0, "float"),)),
    51: _Entry(
        RandFloatRange,
        (_A("dest", 0, "float_t"), _A("lo", 1, "float"), _A("hi", 2, "float")),
    ),
    52: _Entry(GetExitAngle, (_A("dest", 0, "float_t"), _A("rest", 1, "rest"))),
    53: _Entry(MoveAtPlayer, (_A("angle_offset", 0, "float"), _A("speed", 1, "float"))),
    54: _Entry(
        MoveDirTime,
        (
            _A("duration", 0, "int"),
            _A("easing", 1, "int"),
            _A("angle", 2, "float"),
            _A("speed", 3, "float"),
        ),
    ),
    55: _Entry(
        MovePosTime,
        (
            _A("duration", 0, "int"),
            _A("easing", 1, "int"),
            _A("x", 2, "float"),
            _A("y", 3, "float"),
            _A("z", 4, "float"),
        ),
    ),
    56: _Entry(
        MoveOrbit,
        (
            _A("duration", 0, "int"),
            _A("origin_x", 1, "float"),
            _A("origin_y", 2, "float"),
            _A("origin_z", 3, "float"),
            _A("angle", 4, "float"),
            _A("angular_vel", 5, "float"),
            _A("radius", 6, "float"),
            _A("radial_vel", 7, "float"),
        ),
    ),
    57: _Entry(
        SetOrbitRadius, (_A("radius", 0, "float"), _A("radial_vel", 1, "float"))
    ),
    58: _Entry(SetOrbitAngle, (_A("angle", 0, "float"), _A("angular_vel", 1, "float"))),
    59: _Entry(SetMoveInterpTimerPolar, (_A("duration", 0, "int"),)),
    60: _Entry(SetMoveInterpTimerRadial, (_A("duration", 0, "int"),)),
    61: _Entry(SetMoveInterpTimerInterp, (_A("duration", 0, "int"),)),
    62: _Entry(
        SetMovementBounds,
        (
            _A("x_min", 0, "float"),
            _A("y_min", 1, "float"),
            _A("x_max", 2, "float"),
            _A("y_max", 3, "float"),
        ),
    ),
    63: _Entry(DisableMovementBounds),
    73: _Entry(SetShootInterval, (_A("interval", 0, "int"),)),
    74: _Entry(SetShootIntervalRand, (_A("interval", 0, "int"),)),
    75: _Entry(DisableBullets),
    76: _Entry(EnableBullets),
    77: _Entry(SpawnPrevBulletPattern),
    78: _Entry(
        SetShootOffset, (_A("x", 0, "float"), _A("y", 1, "float"), _A("z", 2, "float"))
    ),
    79: _Entry(
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
    80: _Entry(RemoveAllBullets, consts={"mode": 1}),
    81: _Entry(
        SetBulletSound, (_A("sound_idx", 0, "int"), _A("sound_override", 1, "int"))
    ),
    82: _laser_v0(False),
    83: _laser_v0(True),
    84: _Entry(SetLaserIdx, (_A("idx", 0, "int"),)),
    85: _Entry(AddLaserAngle, (_A("idx", 0, "int"), _A("delta", 1, "float"))),
    86: _Entry(AimLaserAtPlayer, (_A("idx", 0, "int"), _A("aim_offset", 1, "float"))),
    87: _Entry(
        SetLaserPosRel,
        (
            _A("idx", 0, "int"),
            _A("x", 1, "float"),
            _A("y", 2, "float"),
            _A("z", 3, "float"),
        ),
    ),
    88: _Entry(TestLaserNotInUse, (_A("idx", 0, "int"),)),
    89: _Entry(StopLaser, (_A("idx", 0, "int"),)),
    90: _Entry(BeginSpellcard),
    91: _Entry(EndSpellcard),
    92: _spawn_enemy(SpawnEnemyAbs),
    93: _spawn_enemy(SpawnEnemyRel),
    94: _Entry(RemoveAllEnemies),
    95: _Entry(SetAnm, (_A("anm_idx", 0, "int"),), {"alt_bank": False}),
    96: _Entry(
        SetMoveAnm,
        (
            _A("scripts", 0, "h0"),
            _A("scripts", 0, "h1"),
            _A("scripts", 1, "h0"),
            _A("scripts", 1, "h1"),
            _A("scripts", 2, "h0"),
        ),
    ),
    97: _Entry(
        SetSubAnm, (_A("idx", 0, "int"), _A("anm_idx", 1, "int")), {"alt_bank": False}
    ),
    98: _Entry(SetDeathAnm, (_A("a", 0, "sb0"), _A("b", 0, "b1"), _A("c", 0, "sb2"))),
    99: _Entry(SetBoss, (_A("idx", 0, "int"),)),
    100: _Entry(
        SpawnEffect,
        (
            _A("color", 0, "ri"),
            _A("dx", 1, "rf"),
            _A("dy", 2, "rf"),
            _A("dz", 3, "rf"),
            _A("distance", 4, "rf"),
        ),
    ),
    101: _Entry(
        SetHitboxSize, (_A("x", 0, "float"), _A("y", 1, "float"), _A("z", 2, "float"))
    ),
    102: _Entry(SetHasContactHitbox, (_A("value", 0, "b0"),)),
    103: _Entry(SetCanBeDamaged, (_A("value", 0, "b0"),)),
    104: _Entry(SetIsHittable, (_A("value", 0, "b0"),)),
    105: _Entry(PlaySound, (_A("sound_idx", 0, "int"),)),
    106: _Entry(SetDeathType, (_A("value", 0, "b0"),)),
    107: _Entry(SetDeathCallbackSub, (_A("sub_id", 0, "b0"),)),
    108: _Entry(SetInterrupt, (_A("sub_id", 0, "int"), _A("slot", 1, "int"))),
    109: _Entry(SetRunInterrupt, (_A("slot", 0, "int"),)),
    110: _Entry(SetLife, (_A("life", 0, "int"),)),
    111: _Entry(SetTimer, (_A("value", 0, "int"),)),
    112: _Entry(SetLifeCallbackThreshold, (_A("value", 0, "int"),)),
    113: _Entry(SetLifeCallbackSub, (_A("sub_id", 0, "int"),)),
    114: _Entry(SetTimerCallbackThreshold, (_A("value", 0, "int"),)),
    115: _Entry(SetTimerCallbackSub, (_A("sub_id", 0, "int"),)),
    116: _Entry(SetEnemyCanDie, (_A("value", 0, "b0"),)),
    117: _Entry(
        SpawnParticles,
        (_A("effect_idx", 0, "int"), _A("count", 1, "int"), _A("color", 2, "int")),
    ),
    118: _Entry(
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
    119: _Entry(SpawnItems, (_A("count", 0, "int"),)),
    120: _Entry(SetVmAutoRotate, (_A("value", 0, "b0"),)),
    121: _Entry(RunExIns, (_A("idx", 0, "int"), _A("args", 1, "rest"))),
    122: _Entry(SetExIns, (_A("idx", 0, "int"), _A("args", 1, "rest"))),
    123: _Entry(AddTime, (_A("delta", 0, "int"),)),
    124: _Entry(SpawnItem, (_A("item_type", 0, "int"),)),
    125: _Entry(SetScriptWaitTime, (_A("frames", 0, "int"),)),
    126: _Entry(SetNumBossLifeMarkers, (_A("count", 0, "int"),)),
    128: _Entry(SetPrimaryVmInterrupt, (_A("value", 0, "int"),)),
    129: _Entry(SetVmInterrupt, (_A("idx", 0, "ri"), _A("value", 1, "h0"))),
    130: _Entry(SetNoStackRet, (_A("value", 0, "b0"),)),
    131: _Entry(
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
    132: _Entry(SetHasNoCollision, (_A("value", 0, "b0"),)),
    133: _Entry(BindTimerCallbackToDeath),
    134: _Entry(ClearLasers),
    135: _Entry(SetIsSurvivalSpellcard, (_A("value", 0, "b0"),)),
    136: _Entry(SetIsProjectile, (_A("value", 0, "b0"),)),
    137: _Entry(SetDespawnOnOob, (_A("value", 0, "b0"),)),
    138: _Entry(
        SetTrail,
        (
            _A("flags", 0, "b0"),
            _A("count", 1, "int"),
            _A("interval", 2, "int"),
            _A("node_step", 3, "int"),
        ),
    ),
    139: _Entry(
        SetBossHealth,
        (
            _A("idx", 0, "int"),
            _A("current", 1, "int"),
            _A("max", 2, "int"),
            _A("color", 3, "int"),
        ),
    ),
    140: _Entry(
        SetGlobalEffectColorMul,
        (
            _A("r", 0, "float"),
            _A("g", 1, "float"),
            _A("b", 2, "float"),
            _A("a", 3, "float"),
        ),
    ),
    142: _Entry(SetInvincibilityTimer, (_A("frames", 0, "int"),)),
    143: _Entry(RemoveBulletsRadius, (_A("radius", 0, "float"),)),
    144: _Entry(SetPeriodicCallback, (_A("timer", 0, "int"), _A("sub_id", 1, "int"))),
    145: _Entry(SetBossRunInterrupt, (_A("idx", 0, "int"), _A("interrupt", 1, "int"))),
    146: _Entry(RemoveAllBullets, consts={"mode": 0}),
    147: _Entry(Idfk, (_A("value", 0, "int"),)),
    148: _Entry(
        SetLifeCallback,
        (_A("idx", 0, "int"), _A("threshold", 1, "int"), _A("sub_id", 2, "int")),
    ),
    149: _Entry(
        SetSpecialEffectPos,
        (
            _A("enabled", 0, "int"),
            _A("x", 1, "float"),
            _A("y", 2, "float"),
            _A("z", 3, "float"),
        ),
    ),
    150: _Entry(SetPrimaryVmRotZ, (_A("value", 0, "float"),)),
    151: _Entry(
        VecFromAngleMagRaw,
        (
            _A("dest_x", 0, "float_t"),
            _A("dest_y", 1, "float_t"),
            _A("angle", 2, "float"),
            _A("magnitude", 3, "float"),
        ),
    ),
    152: _Entry(SetLaserAngle, (_A("idx", 0, "int"), _A("angle", 1, "float"))),
    153: _Entry(
        SetGrazeSize, (_A("x", 0, "float"), _A("y", 1, "float"), _A("z", 2, "float"))
    ),
    154: _Entry(SpawnPointItems, (_A("count", 0, "int"),)),
    155: _Entry(RandExitAngle, (_A("dest", 0, "float_t"),)),
    156: _Entry(SetLaserHideWarning, (_A("idx", 0, "int"), _A("value", 1, "int"))),
    157: _Entry(SetLaserStartLen, (_A("idx", 0, "int"), _A("value", 1, "float"))),
    158: _Entry(
        SetLaserOffsets,
        (_A("idx", 0, "int"), _A("start", 1, "float"), _A("end", 2, "float")),
    ),
    159: _Entry(
        Lerp,
        (
            _A("dest", 0, "float_t"),
            _A("a", 1, "float"),
            _A("b", 2, "float"),
            _A("t", 3, "float"),
        ),
    ),
    160: _Entry(AddCherryPlus, (_A("value", 0, "int"),)),
    161: _Entry(FreezeEclDuringBomb, (_A("value", 0, "int"),)),
}
for _i, _cls in enumerate(_INT_ARITH):  # 12-16: int 三操作数算术(同序 +,-,*,/,%)
    _V0[12 + _i] = _Entry(
        _cls, (_A("dest", 0, "int_t"), _A("a", 1, "int"), _A("b", 2, "int"))
    )
for _i, _cls in enumerate(_FLOAT_ARITH):  # 19-23: float 版
    _V0[19 + _i] = _Entry(
        _cls, (_A("dest", 0, "float_t"), _A("a", 1, "float"), _A("b", 2, "float"))
    )
for _i, (_cls, _f) in enumerate(_CONDS):  # 28-39: 条件跳(int/float 交错)
    _V0[28 + _i] = _cond(_cls, _f)
for _op in range(64, 73):  # 弹幕生成 9 合一(aim_mode = opcode - 64)
    _V0[_op] = _bullet(_op - 64)


# ---- 符卡定制编解码(内嵌 XOR 0xAA 字符串, 字段规格表达不了) ----


def _decode_spellcard(
    base: dict[str, Any], words: tuple[int, ...], mask: int
) -> EclInstr:
    # 布局: word0 = gui_id i16|spellcard_idx u16, word1-12 = 符卡名 48B
    # (EclManager.cpp BeginSpellcard: 名字取 instr->args[1] 起 0x30 字节)
    if len(words) != 13:
        raise ParseError(f"begin_spellcard 参数数不符: {len(words)} != 13")
    return BeginSpellcard(
        **base,
        gui_id=_i16(words[0], 0),
        spellcard_idx=_u16(words[0], 1),
        name=_decode_text(words[1:13]),
    )


def _encode_spellcard(instr: Any) -> list[int]:
    words = [(instr.gui_id & 0xFFFF) | ((instr.spellcard_idx & 0xFFFF) << 16)]
    return words + _encode_text(instr.name, 48)


#: th07 的 ECL 指令集(v0 表 + 符卡定制钩子 + encode 反查表)
ECL_INSTR_SET: InstrSet = build_instr_set(
    _V0,
    custom_decode={BeginSpellcard: _decode_spellcard},
    custom_encode={BeginSpellcard: _encode_spellcard},
)


def parse_ecl(data: bytes) -> EclFile:
    """解析 th07 的 .ecl(v0 布局 + v0 指令集 + v0 时间轴)。"""
    return _parse_ecl(data, version=0, instrs=ECL_INSTR_SET, decode_tl=decode_timeline)
