"""确定性伪随机源: 种子驱动, 可快照, 回放可复现。"""

from __future__ import annotations


class Rng:
    """16 位种子线性伪随机, 同种子同序列。"""

    __slots__ = ("gen", "seed")

    def __init__(self, seed: int = 0) -> None:
        self.seed = seed & 0xFFFF
        self.gen = 0  # 生成计数器

    def u16(self) -> int:
        """取下一个 u16。"""
        # 算法出处 old/touhou/engine/rng.py (Rng::GetRandomU16, TH07 0x00431870)
        u = ((self.seed ^ 0x9630) - 0x6553) & 0xFFFF
        self.seed = (((u & 0xC000) >> 14) + u * 4) & 0xFFFF
        self.gen += 1
        return self.seed

    def u32(self) -> int:
        """取下一个 u32, 由两个 u16 拼成。"""
        return (self.u16() << 16) | self.u16()

    def unit(self) -> float:
        """取 [0, 1) 浮点。"""
        return self.u32() / 4294967296.0

    def int_below(self, bound: int) -> int:
        """取 [0, bound) 整数。"""
        return self.u32() % bound if bound else 0

    def in_range(self, lo: float, hi: float) -> float:
        """取 [lo, hi) 浮点。"""
        return self.unit() * (hi - lo) + lo

    def in_int_range(self, lo: int, hi: int) -> int:
        """取 [lo, hi] 整数。"""
        return lo + self.u32() % (hi - lo + 1) if hi >= lo else lo

    def sign(self) -> int:
        """取 ±1。"""
        return 1 if self.u16() & 1 else -1

    def state(self) -> tuple[int, int]:
        """快照当前状态(种子 + 生成计数)。"""
        return (self.seed, self.gen)

    def restore(self, state: tuple[int, int]) -> None:
        """从 state() 的快照恢复。"""
        self.seed, self.gen = state
