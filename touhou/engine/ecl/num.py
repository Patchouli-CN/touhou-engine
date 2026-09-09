"""ECL 执行器的数值小件: C 语义截断取整/f32 精度还原/角度归一化/插值缓动。"""

from __future__ import annotations

import math
import struct


def f32(x: float) -> float:
    """按 C float 截断精度。"""
    v: float = struct.unpack("<f", struct.pack("<f", x))[0]
    return v


def i32(x: int) -> int:
    """按 C int32 回绕。"""
    x &= 0xFFFFFFFF
    return x - 0x100000000 if x >= 0x80000000 else x


def cdiv(a: int, b: int) -> int:
    """C 语义整除(向零截断)。"""
    q = abs(a) // abs(b)
    return -q if (a < 0) != (b < 0) else q


def cmod(a: int, b: int) -> int:
    """C 语义取余(符号随被除数)。"""
    return a - cdiv(a, b) * b


def add_norm_angle(a: float, b: float) -> float:
    """a+b 包到 [-pi, pi]。"""
    # utils::AddNormalizeAngle, 移植自 old/touhou/utils
    a += b
    while a > math.pi:
        a -= 2 * math.pi
    while a < -math.pi:
        a += 2 * math.pi
    return a


def norm_angle(a: float) -> float:
    """单角度包到 [-pi, pi]。"""
    return add_norm_angle(a, 0.0)


def ease(t: float, mode: int) -> float:
    """插值缓动: 0 线性, 1..3 ease-in, 4..6 ease-out。"""
    # AnmManager.cpp:2155-2183(ANM_EASE_*, ECL 插值/移动共用同一组曲线)
    if mode == 1:
        return t * t
    if mode == 2:
        return t * t * t
    if mode == 3:
        t = t * t
        return t * t
    if mode == 4:
        t = 1.0 - t
        return 1.0 - t * t
    if mode == 5:
        t = 1.0 - t
        return 1.0 - t * t * t
    if mode == 6:
        t = 1.0 - t
        t = t * t
        return 1.0 - t * t
    return t
