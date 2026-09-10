"""ECL 弹幕/激光指令(发射参数/射击间隔/子弹变换/激光槽), 两作共享部分。"""

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
