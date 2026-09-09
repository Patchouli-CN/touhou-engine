"""ANM 视觉状态指令(sprite/位置/旋转/缩放/颜色/插值/滚动)。"""

from __future__ import annotations

from .base import AnmInstr

# opcode 出处 Reference/th07/src/th07/AnmManager.hpp:30-114(AnmOpcode 枚举)


class SetActiveSprite(AnmInstr, frozen=True, tag=3):
    """切换当前 sprite 并显示。"""

    sprite: int


class SetTranslation(AnmInstr, frozen=True, tag=6):
    """设置位置(或偏移, 取决于 use_offset)。"""

    x: float
    y: float
    z: float


class SetScale(AnmInstr, frozen=True, tag=7):
    """设置缩放。"""

    x: float
    y: float


class SetAlpha(AnmInstr, frozen=True, tag=8):
    """设置 alpha。"""

    alpha: int


class SetColor(AnmInstr, frozen=True, tag=9):
    """设置颜色(0xRRGGBB)。"""

    rgb: int


class FlipX(AnmInstr, frozen=True, tag=10):
    """水平翻转。"""


class FlipY(AnmInstr, frozen=True, tag=11):
    """垂直翻转。"""


class SetRotation(AnmInstr, frozen=True, tag=12):
    """设置旋转角。"""

    x: float
    y: float
    z: float


class SetAngleVel(AnmInstr, frozen=True, tag=13):
    """设置角速度。"""

    x: float
    y: float
    z: float


class SetScaleSpeed(AnmInstr, frozen=True, tag=14):
    """设置缩放增速。"""

    x: float
    y: float


class Fade(AnmInstr, frozen=True, tag=15):
    """alpha 线性淡入/出。"""

    alpha: int
    duration: int


class SetBlend(AnmInstr, frozen=True, tag=16):
    """设置混合模式。"""

    mode: int


class PosTimeLinear(AnmInstr, frozen=True, tag=17):
    """位置限时插值(匀速)。"""

    x: float
    y: float
    z: float
    duration: int


class PosTimeDecel(AnmInstr, frozen=True, tag=18):
    """位置限时插值(减速)。"""

    x: float
    y: float
    z: float
    duration: int


class PosTimeAccel(AnmInstr, frozen=True, tag=19):
    """位置限时插值(加速)。"""

    x: float
    y: float
    z: float
    duration: int


class Anchor3(AnmInstr, frozen=True, tag=22):
    """anchor = 3。"""  # AnmManager.cpp:1846-1848


class SetUseOffset(AnmInstr, frozen=True, tag=24):
    """位置写入切到 offset。"""

    value: int


class SetAutoRotate(AnmInstr, frozen=True, tag=25):
    """设置自动旋转。"""

    value: int


class SetScrollPosX(AnmInstr, frozen=True, tag=26):
    """uv 滚动位置 x 累加。"""

    delta: float


class SetScrollPosY(AnmInstr, frozen=True, tag=27):
    """uv 滚动位置 y 累加。"""

    delta: float


class SetVisibility(AnmInstr, frozen=True, tag=28):
    """设置可见性。"""

    visible: int


class InterpScale(AnmInstr, frozen=True, tag=29):
    """缩放插值。"""

    x: float
    y: float
    duration: int


class SetZwriteDisable(AnmInstr, frozen=True, tag=30):
    """设置深度写禁用。"""

    value: int


class SetCameraMode(AnmInstr, frozen=True, tag=31):
    """设置相机模式。"""

    mode: int


class InterpPos(AnmInstr, frozen=True, tag=32):
    """位置插值(带 ease 模式)。"""

    duration: int
    ease: int
    x: float
    y: float
    z: float


class InterpColor(AnmInstr, frozen=True, tag=33):
    """颜色插值(rgb 为 0xBBGGRR 小端三字节)。"""

    duration: int
    ease: int
    rgb: int


class InterpAlpha(AnmInstr, frozen=True, tag=34):
    """alpha 插值。"""

    duration: int
    ease: int
    alpha: int


class InterpRotate(AnmInstr, frozen=True, tag=35):
    """旋转插值。"""

    duration: int
    ease: int
    x: float
    y: float
    z: float


class InterpScale2(AnmInstr, frozen=True, tag=36):
    """缩放插值(带 ease 模式)。"""

    duration: int
    ease: int
    x: float
    y: float


class SetScrollVelX(AnmInstr, frozen=True, tag=80):
    """设置 uv 滚动速度 x。"""

    v: float


class SetScrollVelY(AnmInstr, frozen=True, tag=81):
    """设置 uv 滚动速度 y。"""

    v: float
