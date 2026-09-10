"""ECL(敌机脚本)格式解析: 文件头/sub 表 → 强类型 tagged union 指令。

schemas 只持格式事实与机制: 操作数/指令基类、两作 genuinely 共享的指令类
(v0/v800 两张 opcode 表的实际交集)、字段规格/取字段/文件布局解析。
作品专属指令类与 opcode 表住 games/thNN(ecl_instrs/ecl_table), 指令集经
InstrSet 注入 decode_instr/encode_instr/parse_ecl; 作品的 Instruction
union 也在 games 侧装配(SharedInstruction | 作品专属类)。
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
    EndSpellcard,
    FreezeEclDuringBomb,
    RunExIns,
    SetBoss,
    SetBossHealth,
    SetExIns,
    SetNumBossLifeMarkers,
)
from .bullets import (
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
    SpawnBulletPattern,
    SpawnPrevBulletPattern,
    StopLaser,
)
from .control import (
    AddTime,
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
    SetInterrupt,
    SetNoStackRet,
    SetWaitTimer,
    Stop,
    SubCall,
    SubEnd,
    SubRet,
)
from .decode import (
    CustomDecode,
    CustomEncode,
    InstrSet,
    build_instr_set,
    decode_instr,
    encode_instr,
)
from .enemy import (
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
from .file import TlDecoder, parse_ecl
from .mathops import (
    Add,
    AddFloat,
    Atan2,
    Cos,
    Dec,
    Div,
    DivFloat,
    GetBossFloat,
    GetBossInt,
    Inc,
    InitInterp,
    Lerp,
    Mod,
    ModFloat,
    Mul,
    MulFloat,
    NormalizeAngle,
    RandExitAngle,
    RandSign,
    RandSignFloat,
    SetFloat,
    SetInt,
    Sin,
    Sub,
    SubFloat,
    VecFromAngleMagRaw,
)
from .movement import (
    DisableMovementBounds,
    MoveAtPlayer,
    MoveDirTime,
    SetAngularVel,
    SetMoveAccel,
    SetMovementBounds,
)

#: 两作 genuinely 共享的指令 union(v0/v800 opcode 表交集); 作品侧在此基础上
#: 并上自己的专属类装配作品的 Instruction union
SharedInstruction = (
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
    | SetInt
    | SetFloat
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
    | Inc
    | Dec
    | Sin
    | Cos
    | Atan2
    | Lerp
    | InitInterp
    | NormalizeAngle
    | VecFromAngleMagRaw
    | RandExitAngle
    | GetBossInt
    | GetBossFloat
    | SetAngularVel
    | SetMoveAccel
    | MoveAtPlayer
    | MoveDirTime
    | SetMovementBounds
    | DisableMovementBounds
    | SpawnBulletPattern
    | SetShootInterval
    | SetShootIntervalRand
    | SpawnPrevBulletPattern
    | InitBulletCmd
    | RemoveAllBullets
    | SetBulletSound
    | SetBulletRankParams
    | RemoveBulletsRadius
    | SetLaserIdx
    | AddLaserAngle
    | SetLaserAngle
    | AimLaserAtPlayer
    | SetLaserPosRel
    | StopLaser
    | ClearLasers
    | SetLaserHideWarning
    | SetLaserStartLen
    | SetLaserOffsets
    | SpawnEnemyAbs
    | SpawnEnemyRel
    | RemoveAllEnemies
    | SetAnm
    | SetSubAnm
    | SetDeathAnm
    | SetVmAutoRotate
    | SetIsSurvivalSpellcard
    | SetTrail
    | SetLife
    | SetTimer
    | SetLifeCallback
    | BindTimerCallbackToDeath
    | SetDeathType
    | SetInvincibilityTimer
    | SetPrimaryVmInterrupt
    | SetPrimaryVmRotZ
    | PlaySound
    | SpawnItem
    | SpawnItems
    | SpawnPointItems
    | SpawnEffect
    | SpawnParticles
    | SpawnMovingParticles
    | SetBoss
    | EndSpellcard
    | SetBossHealth
    | SetNumBossLifeMarkers
    | RunExIns
    | SetExIns
    | FreezeEclDuringBomb
)

__all__ = [
    "Add",
    "AddFloat",
    "AddLaserAngle",
    "AddTime",
    "AimLaserAtPlayer",
    "Atan2",
    "BindTimerCallbackToDeath",
    "ClearLasers",
    "Cos",
    "CustomDecode",
    "CustomEncode",
    "Dec",
    "DecJump",
    "DisableMovementBounds",
    "Div",
    "DivFloat",
    "EclFile",
    "EclInstr",
    "EclSub",
    "EndSpellcard",
    "FloatOperand",
    "FreezeEclDuringBomb",
    "GetBossFloat",
    "GetBossInt",
    "ImmFloat",
    "ImmInt",
    "Inc",
    "InitBulletCmd",
    "InitInterp",
    "InstrSet",
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
    "ModFloat",
    "MoveAtPlayer",
    "MoveDirTime",
    "Mul",
    "MulFloat",
    "Nop",
    "NormalizeAngle",
    "Operand",
    "PlaySound",
    "RandExitAngle",
    "RandSign",
    "RandSignFloat",
    "RemoveAllBullets",
    "RemoveAllEnemies",
    "RemoveBulletsRadius",
    "RunExIns",
    "SetAnm",
    "SetAngularVel",
    "SetBoss",
    "SetBossHealth",
    "SetBulletRankParams",
    "SetBulletSound",
    "SetDeathAnm",
    "SetDeathType",
    "SetExIns",
    "SetFloat",
    "SetInt",
    "SetInterrupt",
    "SetInvincibilityTimer",
    "SetIsSurvivalSpellcard",
    "SetLaserAngle",
    "SetLaserHideWarning",
    "SetLaserIdx",
    "SetLaserOffsets",
    "SetLaserPosRel",
    "SetLaserStartLen",
    "SetLife",
    "SetLifeCallback",
    "SetMoveAccel",
    "SetMovementBounds",
    "SetNoStackRet",
    "SetNumBossLifeMarkers",
    "SetPrimaryVmInterrupt",
    "SetPrimaryVmRotZ",
    "SetShootInterval",
    "SetShootIntervalRand",
    "SetSubAnm",
    "SetTimer",
    "SetTrail",
    "SetVmAutoRotate",
    "SetWaitTimer",
    "SharedInstruction",
    "Sin",
    "SpawnBulletPattern",
    "SpawnEffect",
    "SpawnEnemyAbs",
    "SpawnEnemyRel",
    "SpawnItem",
    "SpawnItems",
    "SpawnMovingParticles",
    "SpawnParticles",
    "SpawnPointItems",
    "SpawnPrevBulletPattern",
    "Stop",
    "StopLaser",
    "Sub",
    "SubCall",
    "SubEnd",
    "SubFloat",
    "SubRet",
    "TlDecoder",
    "TlInstr",
    "VarRef",
    "VecFromAngleMagRaw",
    "build_instr_set",
    "decode_instr",
    "encode_instr",
    "parse_ecl",
]
