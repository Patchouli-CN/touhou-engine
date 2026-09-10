"""th07 ECL 宿主侧状态: 每台 EclMachine 一份的作品语义字段(弹幕射手/激光槽等)。

engine 的 EclEnemyState 只持移动/生命周期; 弹幕持久参数(EnemyBulletShooter)/
激光句柄槽/rank 插值参数/anm 附属字段这些 th07 语义状态全住这里, 由宿主按
machine 建账。出处 old/touhou/engine/ecl.py EclEnemyState 的作品字段段与
EnemyBulletShooter/EnemyLaserShooter。
"""

from __future__ import annotations

import msgspec

from ...engine.bullets import BulletCommand, CmdFlag
from ...engine.ecl.state import Vec3
from ...engine.lasers import Laser

#: 持久弹幕命令槽数(C EnemyBulletShooter.commands[8])
SHOOTER_COMMAND_SLOTS = 8
#: 每敌激光句柄槽数(C enemy->lasers[32], 下标按 &31 取)
LASER_SLOTS = 32


class BulletCommandData(msgspec.Struct):
    """持久射手的一条命令槽(InitBulletCmd 写入; type=0 截断评估)。"""

    # 出处 old/touhou/engine/ecl.py BulletCommandData
    type: int = 0
    flag: int = 0
    duration: int = 0
    loop_count: int = 0
    speed: float = 0.0
    angle: float = 0.0


class BulletShooter(msgspec.Struct):
    """持久弹幕参数(C EnemyBulletShooter): 发射指令烹好后存这, 周期射击复用。"""

    sprite: int = 0
    sprite_offset: int = 0
    aim_mode: int = 0
    count1: int = 0
    count2: int = 0
    speed1: float = 0.0
    speed2: float = 0.0
    angle1: float = 0.0
    angle2: float = 0.0
    flags: int = 0
    sound_idx: int = 0
    sound_override: int = 0
    commands: list[BulletCommandData] = msgspec.field(
        default_factory=lambda: [
            BulletCommandData() for _ in range(SHOOTER_COMMAND_SLOTS)
        ]
    )

    def cooked_commands(self) -> tuple[BulletCommand, ...]:
        """展开成引擎命令队列: 首个 type==0 槽截断(BulletManager.cpp:318-320)。"""
        out: list[BulletCommand] = []
        for c in self.commands:
            if not c.type:
                break
            try:
                t = CmdFlag(c.type)
            except ValueError:
                continue
            out.append(
                BulletCommand(
                    t,
                    speed=c.speed,
                    angle=c.angle,
                    duration=c.duration,
                    loop=c.loop_count,
                    flag=c.flag,
                )
            )
        return tuple(out)


class EnemyExtras(msgspec.Struct):
    """一台 EclMachine 的宿主侧账本(作品语义状态, 按 machine 建/销)。"""

    shooter: BulletShooter = msgspec.field(default_factory=BulletShooter)
    shoot_offset: Vec3 = msgspec.field(default_factory=Vec3)
    disable_bullets: int = 0
    # rank 插值参数(EclManager.hpp bulletRank*; BeginSpellcard 重置)
    bullet_rank_speed_low: float = 0.0
    bullet_rank_speed_high: float = 0.0
    bullet_rank_amount1_low: int = 0
    bullet_rank_amount1_high: int = 0
    bullet_rank_amount2_low: int = 0
    bullet_rank_amount2_high: int = 0
    lasers: list[Laser | None] = msgspec.field(
        default_factory=lambda: [None] * LASER_SLOTS
    )
    laser_idx: int = 0
    is_survival_spellcard: int = 0
    disable_oob_despawn: int = 0
    last_damage: int = 0
    boss_id: int = -1
    laser_not_in_use: int = 0  # TestLaserNotInUse 结果(旧 ctx 字段, 无消费方)
    # anm 附属(逻辑侧只读; 渲染后续单消费)
    sub_anm_idx: list[int] = msgspec.field(default_factory=lambda: [-1, -1])
    move_anm: tuple[int, ...] = ()
    death_anm: tuple[int, int, int] = (0, 0, 0)
    primary_vm_interrupt: int = 0
    primary_vm_auto_rotate: int = 0

    def bullet_rank_amount1(self, rank: int) -> int:
        """count1 的 rank 插值(向零截断, EnemyManager.hpp BulletRankAmountInner)。"""
        d = rank * (self.bullet_rank_amount1_high - self.bullet_rank_amount1_low)
        return (d // 32 if d >= 0 else -((-d) // 32)) + self.bullet_rank_amount1_low

    def bullet_rank_amount2(self, rank: int) -> int:
        """count2 的 rank 插值。"""
        d = rank * (self.bullet_rank_amount2_high - self.bullet_rank_amount2_low)
        return (d // 32 if d >= 0 else -((-d) // 32)) + self.bullet_rank_amount2_low

    def bullet_rank_speed(self, rank: float) -> float:
        """弹速的 rank 插值。"""
        return (
            rank * (self.bullet_rank_speed_high - self.bullet_rank_speed_low) / 32
            + self.bullet_rank_speed_low
        )
