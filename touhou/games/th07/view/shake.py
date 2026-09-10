"""画面震动(震屏): BombEffects type=1 的 view 侧衰减 (ScreenEffect.cpp:249-293)。

引擎侧在注册点透出 (duration, amp_start, amp_end) 事件(world.frame_shakes),
ScreenShake 在 view 层维护衰减并给出整帧位移。C++ 每帧: timer++ 到期移除,
振幅线性插值, x/y 各三选一 {0,+amp,-amp}, 多个并存后注册者覆写生效。
RNG 用本地独立源, 不消耗游戏 rng(回放确定性)。
"""

from __future__ import annotations

import random


class ScreenShake:
    """震屏状态: register() 登记事件, tick() 推进一帧并返回 (dx, dy) 偏移。"""

    def __init__(self, seed: int = 0x5EED) -> None:
        self._rng = random.Random(seed)
        # 元素 [duration, amp_start, amp_end, timer]
        self._active: list[list[float]] = []

    def register(self, duration: int, amp_start: int, amp_end: int) -> None:
        """登记一次震动 (BombEffects::RegisterChain type=1 的参数原样)。"""
        if duration <= 0:
            return
        self._active.append([duration, amp_start, amp_end, 0])

    @property
    def active(self) -> bool:
        """还有未衰减完的震动。"""
        return bool(self._active)

    def _pick(self, amp: float) -> float:
        """g_Rng.GetRandomU32InRange(3): 0→0 / 1→+amp / 2→-amp。"""
        r = self._rng.randrange(3)
        return 0.0 if r == 0 else (amp if r == 1 else -amp)

    def tick(self) -> tuple[int, int]:
        """推进一帧, 返回本帧整帧位移 (dx, dy)。"""
        dx = dy = 0.0
        alive: list[list[float]] = []
        for s in self._active:
            s[3] += 1
            if s[3] >= s[0]:
                continue  # timer >= duration → 移除 (ScreenEffect.cpp:262-265)
            alive.append(s)
            amp = (s[2] - s[1]) * s[3] / s[0] + s[1]  # :267-269
            dx, dy = self._pick(amp), self._pick(amp)  # 后注册者覆写, 同 C++
        self._active = alive
        return int(dx), int(dy)
