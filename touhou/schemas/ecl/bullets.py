"""ECL 弹幕/激光指令(发射参数/射击间隔/子弹变换/激光槽)。"""

from __future__ import annotations

from .base import EclInstr, FloatOperand, IntOperand

# 弹幕 ShotArgs 布局(v0/v800 同): word0 = sprite i16|color i16 两个半字,
# 之后 count1/count2/speed1/speed2/angle1/angle2/flags;
# 掩码位: sprite=bit0, color=bit1, count1=bit2, ..., angle2=bit7
# (v0: EclManager.cpp 弹幕系 case; v800: EclDependencies.cpp:687-780)


class SpawnBulletPattern(EclInstr, frozen=True, tag="spawn_bullet_pattern"):
    """按 aim_mode 展开一波弹幕(9 个 opcode 共享, aim_mode = 0..8)。"""

    # v0=64-72, v800=96-104; aim_mode 由解码表按 opcode 填入, 非字节来源
    aim_mode: int
    sprite: IntOperand
    sprite_offset: IntOperand
    count1: IntOperand
    count2: IntOperand
    speed1: FloatOperand
    speed2: FloatOperand
    angle1: FloatOperand
    angle2: FloatOperand
    flags: int


class SetShootInterval(EclInstr, frozen=True, tag="set_shoot_interval"):
    """设自动射击间隔(0 = 关)。"""

    interval: IntOperand


class SetShootIntervalRand(EclInstr, frozen=True, tag="set_shoot_interval_rand"):
    """设自动射击间隔, 计时器随机起步。"""

    interval: IntOperand


class DisableBullets(EclInstr, frozen=True, tag="disable_bullets"):
    """停弹幕发射(v0 专属)。"""


class EnableBullets(EclInstr, frozen=True, tag="enable_bullets"):
    """恢复弹幕发射(v0 专属)。"""


class DeferBulletPattern(EclInstr, frozen=True, tag="defer_bullet_pattern"):
    """弹幕指令延迟到自动射击时重新派发(v800 专属)。"""

    # ENEMY_FLAG_DEFER_BULLET_PATTERN(EclRunHigh.inl:174-181)


class DisableDeferBulletPattern(
    EclInstr, frozen=True, tag="disable_defer_bullet_pattern"
):
    """取消弹幕延迟派发(v800 专属)。"""


class SpawnPrevBulletPattern(EclInstr, frozen=True, tag="spawn_prev_bullet_pattern"):
    """按持久 descriptor 再发一次上一波弹幕。"""


class InitBulletCmd(EclInstr, frozen=True, tag="init_bullet_cmd"):
    """写子弹变换记录 slot(速度/角随时间变化)。"""

    slot: IntOperand
    type: IntOperand
    flag: IntOperand
    duration: IntOperand
    loop_count: IntOperand
    speed: FloatOperand
    angle: FloatOperand


class RemoveAllBullets(EclInstr, frozen=True, tag="remove_all_bullets"):
    """清全屏弹: mode 1 = 转道具, 0 = 直接消, 4 = despawn(v800)。"""

    # v0=80(mode 1)/146(mode 0); v800=162(mode 4, BulletManager.cpp:502-505)
    mode: int


class ClearBulletsForTransition(
    EclInstr, frozen=True, tag="clear_bullets_for_transition"
):
    """符卡转场清弹(v800 专属)。"""


class SetBulletSound(EclInstr, frozen=True, tag="set_bullet_sound"):
    """设发射音: sound_idx 负 = 清发射音标记。"""

    sound_idx: IntOperand
    sound_override: IntOperand


class SetBulletRankParams(EclInstr, frozen=True, tag="set_bullet_rank_params"):
    """设 rank 插值参数(弹速/弹数随 rank 缩放)。"""

    speed_low: FloatOperand
    speed_high: FloatOperand
    amount1_low: IntOperand
    amount1_high: IntOperand
    amount2_low: IntOperand
    amount2_high: IntOperand


class RemoveBulletsRadius(EclInstr, frozen=True, tag="remove_bullets_radius"):
    """清以敌为中心 radius 内的弹。"""

    radius: FloatOperand


class SetShootOffset(EclInstr, frozen=True, tag="set_shoot_offset"):
    """设发射点相对偏移(x/y/z, v0 专属)。"""

    x: FloatOperand
    y: FloatOperand
    z: FloatOperand


class SetShootOffsetV800(EclInstr, frozen=True, tag="set_shoot_offset_v800"):
    """设发射点相对偏移(v800 版: 只有 x/y)。"""

    x: FloatOperand
    y: FloatOperand


class SpawnLaserPattern(EclInstr, frozen=True, tag="spawn_laser_pattern"):
    """生成激光(v0 版: width/计时/flags 全 raw; moving = 跟随敌人)。"""

    # v0=82/83; LaserSpawnArgs: sprite i16|color i16 @word0, 之后 angle/speed/
    # start_offset/end_offset/start_length(f32, bit2-6), width f32 raw,
    # start_time/duration/end_time/hitbox_start/hitbox_end i32 raw, flags raw
    moving: bool
    sprite: int
    sprite_offset: IntOperand
    angle: FloatOperand
    speed: FloatOperand
    start_offset: FloatOperand
    end_offset: FloatOperand
    start_length: FloatOperand
    width: float
    start_time: int
    duration: int
    end_time: int
    hitbox_start_time: int
    hitbox_end_time: int
    flags: int


class SpawnLaserPatternV800(EclInstr, frozen=True, tag="spawn_laser_pattern_v800"):
    """生成激光(v800 版: width/计时也可变参; aimed = 出生即瞄自机)。"""

    # v800=114/115(EclRunHigh.inl:260-334); 掩码位: color=bit1, angle=bit2,
    # speed=bit3, start/end_offset=bit4/5, start_length=bit6, width=bit7,
    # start_time=bit8, duration=bit9, despawn_duration=bit10
    aimed: bool
    sprite: int
    sprite_offset: IntOperand
    angle: FloatOperand
    speed: FloatOperand
    start_offset: FloatOperand
    end_offset: FloatOperand
    start_length: FloatOperand
    width: FloatOperand
    start_time: IntOperand
    duration: IntOperand
    despawn_duration: IntOperand
    hitbox_start_time: int
    hitbox_end_delay: int
    flags: int


class SetLaserIdx(EclInstr, frozen=True, tag="set_laser_idx"):
    """设当前激光槽位。"""

    idx: IntOperand


class AddLaserAngle(EclInstr, frozen=True, tag="add_laser_angle"):
    """激光角度 += delta。"""

    idx: IntOperand
    delta: FloatOperand


class SetLaserAngle(EclInstr, frozen=True, tag="set_laser_angle"):
    """设激光角度。"""

    idx: IntOperand
    angle: FloatOperand


class AimLaserAtPlayer(EclInstr, frozen=True, tag="aim_laser_at_player"):
    """激光瞄自机 + aim_offset。"""

    idx: IntOperand
    aim_offset: FloatOperand


class SetLaserPosRel(EclInstr, frozen=True, tag="set_laser_pos_rel"):
    """设激光位置(相对敌机 + x/y/z)。"""

    idx: IntOperand
    x: FloatOperand
    y: FloatOperand
    z: FloatOperand


class TestLaserNotInUse(EclInstr, frozen=True, tag="test_laser_not_in_use"):
    """测激光槽是否空闲, 结果写上下文标记(v0 专属)。"""

    idx: IntOperand


class TestLaserInUse(EclInstr, frozen=True, tag="test_laser_in_use"):
    """测激光是否在用, 结果写 extraIntVariables[2](v800 专属)。"""

    # EclRunHigh.inl:385-393
    idx: IntOperand


class StopLaser(EclInstr, frozen=True, tag="stop_laser"):
    """停指定槽激光。"""

    idx: IntOperand


class ClearLasers(EclInstr, frozen=True, tag="clear_lasers"):
    """清空全部激光槽。"""


class SetLaserHideWarning(EclInstr, frozen=True, tag="set_laser_hide_warning"):
    """设激光预警期隐头。"""

    idx: IntOperand
    value: IntOperand


class SetLaserStartLen(EclInstr, frozen=True, tag="set_laser_start_len"):
    """设激光起始长度。"""

    idx: IntOperand
    value: FloatOperand


class SetLaserOffsets(EclInstr, frozen=True, tag="set_laser_offsets"):
    """设激光起点/终点偏移。"""

    idx: IntOperand
    start: FloatOperand
    end: FloatOperand
