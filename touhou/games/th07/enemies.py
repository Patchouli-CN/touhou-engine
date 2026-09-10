"""th07 的敌人场: EnemyField 子类(ReimuA 伤害修正/伤害时刻记账/回调作品侧复位)。

伤害得分与樱点公式需要"受伤当帧的敌 timer"(奇偶判定), engine 事件不带,
借 adjust_damage 的帧内调用点按 enemy_id 记账, world 每帧清。
"""

from __future__ import annotations

import msgspec

from ...engine.enemies import Enemy, EnemyField
from .ecl_host import Th07EclHost
from .ecl_state import BulletShooter


class Th07EnemyField(EnemyField):
    """th07 的敌人场: stage/is_reimu_a 由组合根注入, host 由 world 接线。"""

    stage: int = 1
    is_reimu_a: bool = False
    host: Th07EclHost | None = None
    damage_timers: dict[int, int] = msgspec.field(default_factory=dict)

    def adjust_damage(self, e: Enemy, damage: int, *, bomb_damage: bool) -> int:
        """记伤害时刻 + ReimuA 高面伤害减免 (EnemyManager.cpp:815-835)。"""
        # 出处 old/touhou/engine/enemies.py:85-91
        self.damage_timers[e.enemy_id] = e.machine.enemy.timer
        if self.is_reimu_a and not e.is_boss:
            if 5 <= self.stage <= 6:
                damage = damage // 2
            elif self.stage == 4:
                damage -= damage // 4 + damage // 16
        return damage

    def enemy_callback_reset(self, e: Enemy) -> None:
        """回调切换的作品侧复位: rank 参数回默认 + 持久弹幕参数重开。"""
        # 出处 old/touhou/engine/enemies.py:671-680
        if self.host is None:
            return
        ex = self.host.extras.get(id(e.machine))
        if ex is None:
            return
        ex.bullet_rank_speed_low = -0.5
        ex.bullet_rank_speed_high = 0.5
        ex.bullet_rank_amount1_low = ex.bullet_rank_amount1_high = 0
        ex.bullet_rank_amount2_low = ex.bullet_rank_amount2_high = 0
        ex.shooter = BulletShooter()
