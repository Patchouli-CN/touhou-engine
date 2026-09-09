"""二维向量与角度工具: 屏幕系 y 向下, 角度弧度制。"""

from __future__ import annotations

import math

import msgspec


class Vec2(msgspec.Struct, frozen=True):
    """不可变二维向量/坐标点。"""

    # 移植自 old/touhou/utils/math.py Vec2
    x: float
    y: float

    @classmethod
    def from_angle(cls, angle: float, length: float = 1.0) -> Vec2:
        """按极坐标构造: (cos*l, sin*l)。"""
        return cls(math.cos(angle) * length, math.sin(angle) * length)

    @classmethod
    def zero(cls) -> Vec2:
        """零向量。"""
        return cls(0.0, 0.0)

    def __add__(self, o: Vec2) -> Vec2:
        return Vec2(self.x + o.x, self.y + o.y)

    def __sub__(self, o: Vec2) -> Vec2:
        return Vec2(self.x - o.x, self.y - o.y)

    def __neg__(self) -> Vec2:
        return Vec2(-self.x, -self.y)

    def __mul__(self, s: float) -> Vec2:
        return Vec2(self.x * s, self.y * s)

    __rmul__ = __mul__

    def __truediv__(self, s: float) -> Vec2:
        return Vec2(self.x / s, self.y / s)

    @property
    def length(self) -> float:
        """模长。"""
        return math.hypot(self.x, self.y)

    def distance(self, o: Vec2) -> float:
        """到另一点的距离。"""
        return (self - o).length

    def angle(self) -> float:
        """向量方位角(弧度)。"""
        return math.atan2(self.y, self.x)

    def rotated(self, angle: float) -> Vec2:
        """绕原点旋转 angle。"""
        return Vec2(
            self.x * math.cos(angle) - self.y * math.sin(angle),
            self.x * math.sin(angle) + self.y * math.cos(angle),
        )

    def normalized(self) -> Vec2:
        """单位化(零向量原样返回)。"""
        d = self.length or 1.0
        return Vec2(self.x / d, self.y / d)

    def lerp(self, other: Vec2, t: float) -> Vec2:
        """线性插值。"""
        return Vec2(self.x + (other.x - self.x) * t, self.y + (other.y - self.y) * t)


def angle_to(from_pos: Vec2, to_pos: Vec2) -> float:
    """从 from_pos 指向 to_pos 的方位角; 重合时返回 pi/2。"""
    # 移植自 old/touhou/utils/math.py angle_to
    if from_pos == to_pos:
        return math.pi / 2
    return math.atan2(to_pos.y - from_pos.y, to_pos.x - from_pos.x)


def normalize_angle_diff(angle: float) -> float:
    """把角度规范化到 (-pi, pi]。"""
    # 移植自 old/touhou/utils/math.py normalize_angle_diff (取模实现,
    # 与 ecl/num.py 的 ZUN_PI 循环版 add_norm_angle 不是一个函数, 别混用)
    return (angle + math.pi) % math.tau - math.pi
