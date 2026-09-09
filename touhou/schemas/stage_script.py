"""STD 场景脚本指令(相机/雾/背景 VM)与 decode。"""

from __future__ import annotations

import struct
from typing import Any, cast

import msgspec

from .exceptions import ParseError

# opcode 0-30 出处 Reference/th07/src/th07/Stage.hpp:28-59(枚举序),
# 语义 Stage.cpp:188-373(Stage::OnUpdate);
# 31 = 等待标记(OnUpdate 脚本扫描 while 条件, Stage.cpp:172-174);
# 32-34 为 th08 扩展(32=相机 positionOffset, 33=cameraMotionMode,
# 34=背景 VM2 脚本, 转引 scratch_dbg/investigation/th08-ref-facts.md:40)


class StdInstr(msgspec.Struct, frozen=True, tag_field="op"):
    """指令公共字段: frame = 生效帧。"""

    # StdRawInstr: i32 frame + i16 opcode + i16 size + 12 字节参数(3 个
    # i32/f32 双视图字), 定长 20 字节 (Stage.hpp:108-124)
    frame: int


class PosKey(StdInstr, frozen=True, tag=0):
    """世界原点位置关键帧(两条一组构成插值起止)。"""

    x: float
    y: float
    z: float


class SetFog(StdInstr, frozen=True, tag=1):
    """雾设置: color + 近/远平面。"""

    color: int
    near: float
    far: float


class FogInterp(StdInstr, frozen=True, tag=2):
    """雾插值时长(帧)。"""

    duration: int


class Halt(StdInstr, frozen=True, tag=3):
    """停脚本(scriptWaitTime 非 0 时只清等待)。"""


class Jump(StdInstr, frozen=True, tag=4):
    """跳转: instr_idx 指令下标, time 跳转后时刻。"""

    instr_idx: int
    time: int


class CamPos(StdInstr, frozen=True, tag=5):
    """相机位置目标。"""

    x: float
    y: float
    z: float


class CamPosInterp(StdInstr, frozen=True, tag=6):
    """相机位置插值: duration 帧 + ease_mode。"""

    duration: int
    ease_mode: int


class CamLookAt(StdInstr, frozen=True, tag=7):
    """相机注视点目标。"""

    x: float
    y: float
    z: float


class CamLookAtInterp(StdInstr, frozen=True, tag=8):
    """注视点插值: duration 帧 + ease_mode。"""

    duration: int
    ease_mode: int


class CamUp(StdInstr, frozen=True, tag=9):
    """相机 up 向量目标。"""

    x: float
    y: float
    z: float


class CamUpInterp(StdInstr, frozen=True, tag=10):
    """up 向量插值: duration 帧 + ease_mode。"""

    duration: int
    ease_mode: int


class CamFov(StdInstr, frozen=True, tag=11):
    """相机 fov 目标。"""

    fov: float


class CamFovInterp(StdInstr, frozen=True, tag=12):
    """fov 插值: duration 帧 + ease_mode。"""

    duration: int
    ease_mode: int


class ClearColor(StdInstr, frozen=True, tag=13):
    """清屏色。"""

    color: int


class CamPosBezierStart(StdInstr, frozen=True, tag=14):
    """相机位置贝塞尔起点。"""

    x: float
    y: float
    z: float


class CamPosBezierEnd(StdInstr, frozen=True, tag=15):
    """相机位置贝塞尔终点。"""

    x: float
    y: float
    z: float


class CamPosBezierTanStart(StdInstr, frozen=True, tag=16):
    """相机位置贝塞尔起点切线。"""

    x: float
    y: float
    z: float


class CamPosBezierTanEnd(StdInstr, frozen=True, tag=17):
    """相机位置贝塞尔终点切线。"""

    x: float
    y: float
    z: float


class CamPosBezier(StdInstr, frozen=True, tag=18):
    """相机位置贝塞尔插值时长(ease 恒 cubic, Stage.cpp:317)。"""

    duration: int


class CamLookAtBezierStart(StdInstr, frozen=True, tag=19):
    """注视点贝塞尔起点。"""

    x: float
    y: float
    z: float


class CamLookAtBezierEnd(StdInstr, frozen=True, tag=20):
    """注视点贝塞尔终点。"""

    x: float
    y: float
    z: float


class CamLookAtBezierTanStart(StdInstr, frozen=True, tag=21):
    """注视点贝塞尔起点切线。"""

    x: float
    y: float
    z: float


class CamLookAtBezierTanEnd(StdInstr, frozen=True, tag=22):
    """注视点贝塞尔终点切线。"""

    x: float
    y: float
    z: float


class CamLookAtBezier(StdInstr, frozen=True, tag=23):
    """注视点贝塞尔插值时长。"""

    duration: int


class CamUpBezierStart(StdInstr, frozen=True, tag=24):
    """up 向量贝塞尔起点。"""

    x: float
    y: float
    z: float


class CamUpBezierEnd(StdInstr, frozen=True, tag=25):
    """up 向量贝塞尔终点。"""

    x: float
    y: float
    z: float


class CamUpBezierTanStart(StdInstr, frozen=True, tag=26):
    """up 向量贝塞尔起点切线。"""

    x: float
    y: float
    z: float


class CamUpBezierTanEnd(StdInstr, frozen=True, tag=27):
    """up 向量贝塞尔终点切线。"""

    x: float
    y: float
    z: float


class CamUpBezier(StdInstr, frozen=True, tag=28):
    """up 向量贝塞尔插值时长。"""

    duration: int


class BgScript1(StdInstr, frozen=True, tag=29):
    """全屏背景 VM1 的 anm script 号(负 = 隐藏)。"""

    script: int


class BgScript2(StdInstr, frozen=True, tag=30):
    """全屏背景 VM2 的 anm script 号(负 = 隐藏)。"""

    script: int


class WaitLabel(StdInstr, frozen=True, tag=31):
    """等待标记: 脚本扫描停在 label 匹配的指令(Stage.cpp:172-174)。"""

    label: int


class CameraOffset(StdInstr, frozen=True, tag=32):
    """相机 positionOffset(th08 扩展)。"""

    x: float
    y: float
    z: float


class CameraMotionMode(StdInstr, frozen=True, tag=33):
    """相机运动模式(th08 扩展)。"""

    mode: int


class BgScript3(StdInstr, frozen=True, tag=34):
    """背景 VM2 的 anm script 号(th08 扩展, 负 = 隐藏)。"""

    script: int


Instruction = (
    PosKey
    | SetFog
    | FogInterp
    | Halt
    | Jump
    | CamPos
    | CamPosInterp
    | CamLookAt
    | CamLookAtInterp
    | CamUp
    | CamUpInterp
    | CamFov
    | CamFovInterp
    | ClearColor
    | CamPosBezierStart
    | CamPosBezierEnd
    | CamPosBezierTanStart
    | CamPosBezierTanEnd
    | CamPosBezier
    | CamLookAtBezierStart
    | CamLookAtBezierEnd
    | CamLookAtBezierTanStart
    | CamLookAtBezierTanEnd
    | CamLookAtBezier
    | CamUpBezierStart
    | CamUpBezierEnd
    | CamUpBezierTanStart
    | CamUpBezierTanEnd
    | CamUpBezier
    | BgScript1
    | BgScript2
    | WaitLabel
    | CameraOffset
    | CameraMotionMode
    | BgScript3
)

_DECODERS: dict[int, type[StdInstr]] = {
    0: PosKey,
    1: SetFog,
    2: FogInterp,
    3: Halt,
    4: Jump,
    5: CamPos,
    6: CamPosInterp,
    7: CamLookAt,
    8: CamLookAtInterp,
    9: CamUp,
    10: CamUpInterp,
    11: CamFov,
    12: CamFovInterp,
    13: ClearColor,
    14: CamPosBezierStart,
    15: CamPosBezierEnd,
    16: CamPosBezierTanStart,
    17: CamPosBezierTanEnd,
    18: CamPosBezier,
    19: CamLookAtBezierStart,
    20: CamLookAtBezierEnd,
    21: CamLookAtBezierTanStart,
    22: CamLookAtBezierTanEnd,
    23: CamLookAtBezier,
    24: CamUpBezierStart,
    25: CamUpBezierEnd,
    26: CamUpBezierTanStart,
    27: CamUpBezierTanEnd,
    28: CamUpBezier,
    29: BgScript1,
    30: BgScript2,
    31: WaitLabel,
    32: CameraOffset,
    33: CameraMotionMode,
    34: BgScript3,
}


def decode_instr(data: bytes, p: int) -> Instruction:
    """把 p 处一条 20 字节定长指令 decode 成指令对象。

    参数区 12 字节是 3 个 i32/f32 双视图字, 各指令类按字段注解取视图,
    未用的尾字忽略。
    """
    frame, opcode, _size = struct.unpack_from("<ihh", data, p)
    cls = _DECODERS.get(opcode)
    if cls is None:
        raise ParseError(f"未知 std 指令 opcode: {opcode}")
    arg_fields: tuple[msgspec.structs.FieldInfo, ...] = msgspec.structs.fields(cls)[1:]
    if len(arg_fields) > 3:
        raise ParseError(f"std 指令 {cls.__name__} 声明参数超 3 字")
    args_i = struct.unpack_from("<3i", data, p + 8)
    args_f = struct.unpack_from("<3f", data, p + 8)
    kwargs: dict[str, Any] = {}
    for i, fld in enumerate(arg_fields):
        kwargs[fld.name] = args_f[i] if fld.type is float else args_i[i]
    return cast("Instruction", cls(frame=frame, **kwargs))
