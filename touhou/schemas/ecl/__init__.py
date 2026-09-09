"""ECL(敌机脚本)格式解析: 文件头/sub 表/时间轴 → 强类型 tagged union 指令。

两作差集: v0(无版本头)/v800(0x800 版本头)两套 opcode 表显式参数化,
编号系统性错位, 同布局共享指令类, 布局分叉另立 V800 变体类。
"""

from __future__ import annotations

from .base import (
    EclFile,
    EclInstr,
    EclSub,
    FloatOperand,
    ImmFloat,
    ImmInt,
    IntOperand,
    Operand,
    TlInstr,
    VarRef,
)
from .boss import (
    AddCherryPlus,
    AdvanceClock,
    BeginSpellcard,
    BeginSpellcardV800,
    EndSpellcard,
    FreezeEclDuringBomb,
    HideClock,
    RunExIns,
    SetBonusUpdatesDisabled,
    SetBoss,
    SetBossHealth,
    SetBossRunInterrupt,
    SetExIns,
    SetLastSpellFlags,
    SetNumBossLifeMarkers,
    SetScriptWaitTime,
    SetSpellcardEffectTracking,
    SetStageScriptLabel,
    StartStageBackgroundSequence,
    SuppressTimelineSpawns,
)
from .bullets import (
    AddLaserAngle,
    AimLaserAtPlayer,
    ClearBulletsForTransition,
    ClearLasers,
    DeferBulletPattern,
    DisableBullets,
    DisableDeferBulletPattern,
    EnableBullets,
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
    SetShootOffset,
    SetShootOffsetV800,
    SpawnBulletPattern,
    SpawnLaserPattern,
    SpawnLaserPatternV800,
    SpawnPrevBulletPattern,
    StopLaser,
    TestLaserInUse,
    TestLaserNotInUse,
)
from .control import (
    AddTime,
    CallSubOnBoss,
    DecJump,
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
    RunPendingSub,
    SetBossPendingSub,
    SetChildContext,
    SetInterrupt,
    SetNoStackRet,
    SetRunInterrupt,
    SetWaitTimer,
    Stop,
    SubCall,
    SubEnd,
    SubRet,
)
from .decode import decode_instr, encode_instr
from .enemy import (
    BindTimerCallbackToDeath,
    ClearEnemyFlags,
    EnableEnemyFlags,
    Idfk,
    PlaySound,
    RemoveAllEnemies,
    SetAnm,
    SetCanBeDamaged,
    SetDeathAnm,
    SetDeathCallbackSub,
    SetDeathCallbackSubV800,
    SetDeathType,
    SetDespawnOnOob,
    SetDrawGroup,
    SetEnemyCanDie,
    SetEnemyFlags,
    SetEnemyManagerValue,
    SetExtraVmFixedOffset,
    SetFormEffect,
    SetGlobalEffectColorMul,
    SetGrazeSize,
    SetGrazeSizeV800,
    SetHasContactHitbox,
    SetHasNoCollision,
    SetHitboxSize,
    SetHitboxSizeV800,
    SetInvincibilityTimer,
    SetIsHittable,
    SetIsProjectile,
    SetIsSurvivalSpellcard,
    SetItemDrop,
    SetItemDropCounts,
    SetLife,
    SetLifeCallback,
    SetLifeCallbackSub,
    SetLifeCallbackThreshold,
    SetMoveAnm,
    SetMoveAnmSeq,
    SetMoveAnmV800,
    SetNoDamageDuringStop,
    SetPeriodicCallback,
    SetPhaseStartLife,
    SetPrimaryVmInterrupt,
    SetPrimaryVmRotZ,
    SetSpecialAnm,
    SetSpecialEffectPos,
    SetSpecialInteraction,
    SetSubAnm,
    SetTimer,
    SetTimerCallback,
    SetTimerCallbackSub,
    SetTimerCallbackThreshold,
    SetTrail,
    SetVmAutoRotate,
    SetVmInterrupt,
    SetVmInterruptV800,
    SpawnAlignmentEffect,
    SpawnEffect,
    SpawnEnemyAbs,
    SpawnEnemyRel,
    SpawnFamiliar,
    SpawnFamiliarInherit,
    SpawnFamiliarRel,
    SpawnItem,
    SpawnItems,
    SpawnMovingParticles,
    SpawnParticles,
    SpawnPointItems,
)
from .file import parse_ecl
from .mathops import (
    Add,
    AddAssign,
    AddAssignFloat,
    AddFloat,
    Atan2,
    Cos,
    Dec,
    Dist,
    Div,
    DivAssign,
    DivAssignFloat,
    DivFloat,
    GetBossFloat,
    GetBossInt,
    GetExitAngle,
    Inc,
    InitInterp,
    Lerp,
    Mod,
    ModAssign,
    ModAssignFloat,
    ModFloat,
    Mul,
    MulAssign,
    MulAssignFloat,
    MulFloat,
    NormalizeAngle,
    Rand,
    RandAdd,
    RandExitAngle,
    RandFloat,
    RandFloatAdd,
    RandFloatRange,
    RandSign,
    RandSignFloat,
    SetFloat,
    SetInt,
    Sin,
    Sub,
    SubAssign,
    SubAssignFloat,
    SubFloat,
    VecFromAngleMag,
    VecFromAngleMagRaw,
)
from .movement import (
    DisableMovementBounds,
    MoveAtPlayer,
    MoveAtPlayerTime,
    MoveBoundaryAware,
    MoveDirTime,
    MoveOrbit,
    MoveOrbitAroundSelf,
    MoveOrbitV800,
    MovePosTime,
    MovePosTimeV800,
    MoveRandomBiased,
    SetAngularVel,
    SetAxisSpeed,
    SetMinPlayerDistance,
    SetMoveAccel,
    SetMoveInterpTimerInterp,
    SetMoveInterpTimerPolar,
    SetMoveInterpTimerRadial,
    SetMovementBounds,
    SetMovePolar,
    SetMoveSpeed,
    SetOrbitAngle,
    SetOrbitRadius,
    SetOrbitVels,
    SetPos,
    SetPosV800,
)
from .timeline import (
    TimelineInstr,
    TlEnd,
    TlEndV800,
    TlEventConsume,
    TlEventEmit,
    TlMsgRead,
    TlMsgReadV800,
    TlMsgWait,
    TlMsgWaitV800,
    TlSetBossInterrupt,
    TlSetBossPendingSub,
    TlSetPower,
    TlSetPowerV800,
    TlShowRetryMenu,
    TlSpawn,
    TlSpawnAt,
    TlSpawnDrops,
    TlSpawnRandomX,
    TlSpawnRangeX,
    TlWaitBossDead,
    TlWaitBossDeadV800,
)

Instruction = (
    Nop
    | Stop
    | SubEnd
    | SetWaitTimer
    | Jump
    | DecJump
    | JumpIfEq
    | JumpIfEqFloat
    | JumpIfNeq
    | JumpIfNeqFloat
    | JumpIfLt
    | JumpIfLtFloat
    | JumpIfLeq
    | JumpIfLeqFloat
    | JumpIfGt
    | JumpIfGtFloat
    | JumpIfGeq
    | JumpIfGeqFloat
    | SubCall
    | SubRet
    | AddTime
    | SetNoStackRet
    | SetInterrupt
    | SetRunInterrupt
    | RunPendingSub
    | SetChildContext
    | CallSubOnBoss
    | SetBossPendingSub
    | SetInt
    | SetFloat
    | Rand
    | RandAdd
    | RandFloat
    | RandFloatAdd
    | RandSign
    | RandSignFloat
    | Add
    | Sub
    | Mul
    | Div
    | Mod
    | AddFloat
    | SubFloat
    | MulFloat
    | DivFloat
    | ModFloat
    | AddAssign
    | SubAssign
    | MulAssign
    | DivAssign
    | ModAssign
    | AddAssignFloat
    | SubAssignFloat
    | MulAssignFloat
    | DivAssignFloat
    | ModAssignFloat
    | Inc
    | Dec
    | Sin
    | Cos
    | Atan2
    | Lerp
    | InitInterp
    | NormalizeAngle
    | VecFromAngleMag
    | VecFromAngleMagRaw
    | Dist
    | RandFloatRange
    | GetExitAngle
    | RandExitAngle
    | GetBossInt
    | GetBossFloat
    | SetPos
    | SetPosV800
    | SetAxisSpeed
    | SetAngularVel
    | SetMoveSpeed
    | SetMoveAccel
    | MoveAtPlayer
    | MoveAtPlayerTime
    | MoveDirTime
    | MoveBoundaryAware
    | MoveRandomBiased
    | MovePosTime
    | MovePosTimeV800
    | SetMovePolar
    | MoveOrbit
    | MoveOrbitV800
    | MoveOrbitAroundSelf
    | SetOrbitVels
    | SetOrbitRadius
    | SetOrbitAngle
    | SetMoveInterpTimerPolar
    | SetMoveInterpTimerRadial
    | SetMoveInterpTimerInterp
    | SetMovementBounds
    | DisableMovementBounds
    | SetMinPlayerDistance
    | SpawnBulletPattern
    | SetShootInterval
    | SetShootIntervalRand
    | DisableBullets
    | EnableBullets
    | DeferBulletPattern
    | DisableDeferBulletPattern
    | SpawnPrevBulletPattern
    | InitBulletCmd
    | RemoveAllBullets
    | ClearBulletsForTransition
    | SetBulletSound
    | SetBulletRankParams
    | RemoveBulletsRadius
    | SetShootOffset
    | SetShootOffsetV800
    | SpawnLaserPattern
    | SpawnLaserPatternV800
    | SetLaserIdx
    | AddLaserAngle
    | SetLaserAngle
    | AimLaserAtPlayer
    | SetLaserPosRel
    | TestLaserNotInUse
    | TestLaserInUse
    | StopLaser
    | ClearLasers
    | SetLaserHideWarning
    | SetLaserStartLen
    | SetLaserOffsets
    | SpawnEnemyAbs
    | SpawnEnemyRel
    | SpawnFamiliar
    | SpawnFamiliarRel
    | SpawnFamiliarInherit
    | RemoveAllEnemies
    | SetAnm
    | SetMoveAnm
    | SetMoveAnmSeq
    | SetMoveAnmV800
    | SetSubAnm
    | SetSpecialAnm
    | SetDeathAnm
    | SetHitboxSize
    | SetHitboxSizeV800
    | SetGrazeSize
    | SetGrazeSizeV800
    | SetHasContactHitbox
    | SetCanBeDamaged
    | SetIsHittable
    | SetEnemyCanDie
    | SetVmAutoRotate
    | SetHasNoCollision
    | SetIsSurvivalSpellcard
    | SetIsProjectile
    | SetSpecialInteraction
    | SetDespawnOnOob
    | SetEnemyFlags
    | ClearEnemyFlags
    | EnableEnemyFlags
    | SetFormEffect
    | SetTrail
    | SetLife
    | SetTimer
    | SetLifeCallbackThreshold
    | SetLifeCallbackSub
    | SetTimerCallbackThreshold
    | SetTimerCallbackSub
    | SetLifeCallback
    | SetTimerCallback
    | SetPeriodicCallback
    | BindTimerCallbackToDeath
    | SetDeathType
    | SetDeathCallbackSub
    | SetDeathCallbackSubV800
    | SetInvincibilityTimer
    | SetPrimaryVmInterrupt
    | SetVmInterrupt
    | SetVmInterruptV800
    | SetPrimaryVmRotZ
    | SetItemDrop
    | SetItemDropCounts
    | SetDrawGroup
    | SetNoDamageDuringStop
    | SetExtraVmFixedOffset
    | SetPhaseStartLife
    | PlaySound
    | SpawnItem
    | SpawnItems
    | SpawnPointItems
    | SpawnEffect
    | SpawnParticles
    | SpawnMovingParticles
    | SpawnAlignmentEffect
    | Idfk
    | SetEnemyManagerValue
    | SetSpecialEffectPos
    | SetGlobalEffectColorMul
    | SetBoss
    | BeginSpellcard
    | BeginSpellcardV800
    | EndSpellcard
    | SetBossHealth
    | SetNumBossLifeMarkers
    | SetBossRunInterrupt
    | RunExIns
    | SetExIns
    | SetScriptWaitTime
    | SetStageScriptLabel
    | SuppressTimelineSpawns
    | SetLastSpellFlags
    | SetSpellcardEffectTracking
    | FreezeEclDuringBomb
    | AddCherryPlus
    | StartStageBackgroundSequence
    | HideClock
    | AdvanceClock
    | SetBonusUpdatesDisabled
)

__all__ = [
    "Add",
    "AddAssign",
    "AddAssignFloat",
    "AddCherryPlus",
    "AddFloat",
    "AddLaserAngle",
    "AddTime",
    "AdvanceClock",
    "AimLaserAtPlayer",
    "Atan2",
    "BeginSpellcard",
    "BeginSpellcardV800",
    "BindTimerCallbackToDeath",
    "CallSubOnBoss",
    "ClearBulletsForTransition",
    "ClearEnemyFlags",
    "ClearLasers",
    "Cos",
    "Dec",
    "DecJump",
    "DeferBulletPattern",
    "DisableBullets",
    "DisableDeferBulletPattern",
    "DisableMovementBounds",
    "Dist",
    "Div",
    "DivAssign",
    "DivAssignFloat",
    "DivFloat",
    "EclFile",
    "EclInstr",
    "EclSub",
    "EnableBullets",
    "EnableEnemyFlags",
    "EndSpellcard",
    "FloatOperand",
    "FreezeEclDuringBomb",
    "GetBossFloat",
    "GetBossInt",
    "GetExitAngle",
    "HideClock",
    "Idfk",
    "ImmFloat",
    "ImmInt",
    "Inc",
    "InitBulletCmd",
    "InitInterp",
    "IntOperand",
    "Jump",
    "JumpIfEq",
    "JumpIfEqFloat",
    "JumpIfGeq",
    "JumpIfGeqFloat",
    "JumpIfGt",
    "JumpIfGtFloat",
    "JumpIfLeq",
    "JumpIfLeqFloat",
    "JumpIfLt",
    "JumpIfLtFloat",
    "JumpIfNeq",
    "JumpIfNeqFloat",
    "Lerp",
    "Mod",
    "ModAssign",
    "ModAssignFloat",
    "ModFloat",
    "MoveAtPlayer",
    "MoveAtPlayerTime",
    "MoveBoundaryAware",
    "MoveDirTime",
    "MoveOrbit",
    "MoveOrbitAroundSelf",
    "MoveOrbitV800",
    "MovePosTime",
    "MovePosTimeV800",
    "MoveRandomBiased",
    "Mul",
    "MulAssign",
    "MulAssignFloat",
    "MulFloat",
    "Nop",
    "NormalizeAngle",
    "Operand",
    "PlaySound",
    "Rand",
    "RandAdd",
    "RandExitAngle",
    "RandFloat",
    "RandFloatAdd",
    "RandFloatRange",
    "RandSign",
    "RandSignFloat",
    "RemoveAllBullets",
    "RemoveAllEnemies",
    "RemoveBulletsRadius",
    "RunExIns",
    "RunPendingSub",
    "SetAngularVel",
    "SetAnm",
    "SetAxisSpeed",
    "SetBonusUpdatesDisabled",
    "SetBoss",
    "SetBossHealth",
    "SetBossPendingSub",
    "SetBossRunInterrupt",
    "SetBulletRankParams",
    "SetBulletSound",
    "SetCanBeDamaged",
    "SetChildContext",
    "SetDeathAnm",
    "SetDeathCallbackSub",
    "SetDeathCallbackSubV800",
    "SetDeathType",
    "SetDespawnOnOob",
    "SetDrawGroup",
    "SetEnemyCanDie",
    "SetEnemyFlags",
    "SetEnemyManagerValue",
    "SetExIns",
    "SetExtraVmFixedOffset",
    "SetFloat",
    "SetFormEffect",
    "SetGlobalEffectColorMul",
    "SetGrazeSize",
    "SetGrazeSizeV800",
    "SetHasContactHitbox",
    "SetHasNoCollision",
    "SetHitboxSize",
    "SetHitboxSizeV800",
    "SetInt",
    "SetInterrupt",
    "SetInvincibilityTimer",
    "SetIsHittable",
    "SetIsProjectile",
    "SetIsSurvivalSpellcard",
    "SetItemDrop",
    "SetItemDropCounts",
    "SetLaserAngle",
    "SetLaserHideWarning",
    "SetLaserIdx",
    "SetLaserOffsets",
    "SetLaserPosRel",
    "SetLaserStartLen",
    "SetLastSpellFlags",
    "SetLife",
    "SetLifeCallback",
    "SetLifeCallbackSub",
    "SetLifeCallbackThreshold",
    "SetMinPlayerDistance",
    "SetMoveAccel",
    "SetMoveAnm",
    "SetMoveAnmSeq",
    "SetMoveAnmV800",
    "SetMoveInterpTimerInterp",
    "SetMoveInterpTimerPolar",
    "SetMoveInterpTimerRadial",
    "SetMovePolar",
    "SetMoveSpeed",
    "SetMovementBounds",
    "SetNoDamageDuringStop",
    "SetNoStackRet",
    "SetNumBossLifeMarkers",
    "SetOrbitAngle",
    "SetOrbitRadius",
    "SetOrbitVels",
    "SetPeriodicCallback",
    "SetPhaseStartLife",
    "SetPos",
    "SetPosV800",
    "SetPrimaryVmInterrupt",
    "SetPrimaryVmRotZ",
    "SetRunInterrupt",
    "SetScriptWaitTime",
    "SetShootInterval",
    "SetShootIntervalRand",
    "SetShootOffset",
    "SetShootOffsetV800",
    "SetSpecialAnm",
    "SetSpecialEffectPos",
    "SetSpecialInteraction",
    "SetSpellcardEffectTracking",
    "SetStageScriptLabel",
    "SetSubAnm",
    "SetTimer",
    "SetTimerCallback",
    "SetTimerCallbackSub",
    "SetTimerCallbackThreshold",
    "SetTrail",
    "SetVmAutoRotate",
    "SetVmInterrupt",
    "SetVmInterruptV800",
    "SetWaitTimer",
    "Sin",
    "SpawnAlignmentEffect",
    "SpawnBulletPattern",
    "SpawnEffect",
    "SpawnEnemyAbs",
    "SpawnEnemyRel",
    "SpawnFamiliar",
    "SpawnFamiliarInherit",
    "SpawnFamiliarRel",
    "SpawnItem",
    "SpawnItems",
    "SpawnLaserPattern",
    "SpawnLaserPatternV800",
    "SpawnMovingParticles",
    "SpawnParticles",
    "SpawnPointItems",
    "SpawnPrevBulletPattern",
    "StartStageBackgroundSequence",
    "Stop",
    "StopLaser",
    "Sub",
    "SubAssign",
    "SubAssignFloat",
    "SubCall",
    "SubEnd",
    "SubFloat",
    "SubRet",
    "SuppressTimelineSpawns",
    "TestLaserInUse",
    "TestLaserNotInUse",
    "TimelineInstr",
    "TlEnd",
    "TlEndV800",
    "TlEventConsume",
    "TlEventEmit",
    "TlInstr",
    "TlMsgRead",
    "TlMsgReadV800",
    "TlMsgWait",
    "TlMsgWaitV800",
    "TlSetBossInterrupt",
    "TlSetBossPendingSub",
    "TlSetPower",
    "TlSetPowerV800",
    "TlShowRetryMenu",
    "TlSpawn",
    "TlSpawnAt",
    "TlSpawnDrops",
    "TlSpawnRandomX",
    "TlSpawnRangeX",
    "TlWaitBossDead",
    "TlWaitBossDeadV800",
    "VarRef",
    "VecFromAngleMag",
    "VecFromAngleMagRaw",
    "Instruction",
    "decode_instr",
    "encode_instr",
    "parse_ecl",
]
