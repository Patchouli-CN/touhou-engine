"""th07(v0 格式)专属 ECL 指令类 + 作品的 Instruction union。

两作共享的指令类住 schemas/ecl; 这里是 v0 opcode 表独有的部分(樱点等
th07 机制私货 + v800 已改布局/删号的旧版指令)。编号/布局出处
Reference/th07/src/th07/EclManager.hpp:115-271 + EclManager.cpp。
"""

from __future__ import annotations

from ...schemas.ecl import (
    EclInstr,
    FloatOperand,
    IntOperand,
    SharedInstruction,
    VarRef,
)


class SetRunInterrupt(EclInstr, frozen=True, tag="set_run_interrupt"):
    """登记并立即进 interrupt sub。"""

    slot: IntOperand


class Rand(EclInstr, frozen=True, tag="rand"):
    """dest = rng 取模 bound。"""

    dest: VarRef | None
    bound: IntOperand


class RandAdd(EclInstr, frozen=True, tag="rand_add"):
    """dest = rng 取模 bound + addend。"""

    dest: VarRef | None
    bound: IntOperand
    addend: IntOperand


class RandFloat(EclInstr, frozen=True, tag="rand_float"):
    """dest = rng 单位随机 × scale。"""

    dest: VarRef | None
    scale: FloatOperand


class RandFloatAdd(EclInstr, frozen=True, tag="rand_float_add"):
    """dest = rng 单位随机 × scale + addend。"""

    dest: VarRef | None
    scale: FloatOperand
    addend: FloatOperand


class RandFloatRange(EclInstr, frozen=True, tag="rand_float_range"):
    """dest = rng 单位随机 × (hi - lo) + lo。"""

    dest: VarRef | None
    lo: FloatOperand
    hi: FloatOperand


class GetExitAngle(EclInstr, frozen=True, tag="get_exit_angle"):
    """dest = 朝屏幕外逃的随机角(rest 是真实数据里的残余字)。"""

    # C 只写 dest(EclManager.cpp:1593-1632), 真实数据带 2 个未用字
    dest: VarRef | None
    rest: tuple[int, ...] = ()


class SetPos(EclInstr, frozen=True, tag="set_pos"):
    """直接设位置(x/y/z)。"""

    x: FloatOperand
    y: FloatOperand
    z: FloatOperand


class SetAxisSpeed(EclInstr, frozen=True, tag="set_axis_speed"):
    """设轴向速度并按 atan2 回算朝向。"""

    x: FloatOperand
    y: FloatOperand
    z: FloatOperand


class SetMoveSpeed(EclInstr, frozen=True, tag="set_move_speed"):
    """设移动速度(移动模式 1)。"""

    speed: FloatOperand


class MovePosTime(EclInstr, frozen=True, tag="move_pos_time"):
    """限时移动到目标点(x/y/z, 位移插值)。"""

    duration: IntOperand
    easing: IntOperand
    x: FloatOperand
    y: FloatOperand
    z: FloatOperand


class MoveOrbit(EclInstr, frozen=True, tag="move_orbit"):
    """绕指定原点轨道(原点 x/y/z, 移动模式 3)。"""

    duration: IntOperand
    origin_x: FloatOperand
    origin_y: FloatOperand
    origin_z: FloatOperand
    angle: FloatOperand
    angular_vel: FloatOperand
    radius: FloatOperand
    radial_vel: FloatOperand


class SetOrbitRadius(EclInstr, frozen=True, tag="set_orbit_radius"):
    """设轨道半径/径向速度。"""

    radius: FloatOperand
    radial_vel: FloatOperand


class SetOrbitAngle(EclInstr, frozen=True, tag="set_orbit_angle"):
    """设轨道角/角速度。"""

    angle: FloatOperand
    angular_vel: FloatOperand


class SetMoveInterpTimerPolar(EclInstr, frozen=True, tag="set_move_interp_timer_polar"):
    """设移动插值定时器(移动模式 1)。"""

    duration: IntOperand


class SetMoveInterpTimerRadial(
    EclInstr, frozen=True, tag="set_move_interp_timer_radial"
):
    """设移动插值定时器(移动模式 3)。"""

    duration: IntOperand


class SetMoveInterpTimerInterp(
    EclInstr, frozen=True, tag="set_move_interp_timer_interp"
):
    """设移动插值定时器(移动模式 2)。"""

    duration: IntOperand


class DisableBullets(EclInstr, frozen=True, tag="disable_bullets"):
    """停弹幕发射。"""


class EnableBullets(EclInstr, frozen=True, tag="enable_bullets"):
    """恢复弹幕发射。"""


class SetShootOffset(EclInstr, frozen=True, tag="set_shoot_offset"):
    """设发射点相对偏移(x/y/z)。"""

    x: FloatOperand
    y: FloatOperand
    z: FloatOperand


class SpawnLaserPattern(EclInstr, frozen=True, tag="spawn_laser_pattern"):
    """生成激光(width/计时/flags 全 raw; moving = 跟随敌人)。"""

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


class TestLaserNotInUse(EclInstr, frozen=True, tag="test_laser_not_in_use"):
    """测激光槽是否空闲, 结果写上下文标记。"""

    idx: IntOperand


class SetMoveAnm(EclInstr, frozen=True, tag="set_move_anm"):
    """设移动 anm 组(5 个 i16 脚本号, 打包在 3 字里)。"""

    scripts: tuple[int, int, int, int, int]


class SetHitboxSize(EclInstr, frozen=True, tag="set_hitbox_size"):
    """设判定盒尺寸(x/y/z)。"""

    x: FloatOperand
    y: FloatOperand
    z: FloatOperand


class SetGrazeSize(EclInstr, frozen=True, tag="set_graze_size"):
    """设擦弹判定尺寸(x/y/z)。"""

    x: FloatOperand
    y: FloatOperand
    z: FloatOperand


class SetHasContactHitbox(EclInstr, frozen=True, tag="set_has_contact_hitbox"):
    """设体术判定(args[0] 低字节)。"""

    value: int


class SetCanBeDamaged(EclInstr, frozen=True, tag="set_can_be_damaged"):
    """设可否受击(args[0] 低字节)。"""

    value: int


class SetIsHittable(EclInstr, frozen=True, tag="set_is_hittable"):
    """设可否被命中(args[0] 低字节)。"""

    value: int


class SetEnemyCanDie(EclInstr, frozen=True, tag="set_enemy_can_die"):
    """设可否被击坠(args[0] 低字节)。"""

    value: int


class SetHasNoCollision(EclInstr, frozen=True, tag="set_has_no_collision"):
    """设无碰撞(args[0] 低字节)。"""

    value: int


class SetIsProjectile(EclInstr, frozen=True, tag="set_is_projectile"):
    """设投射物标记(args[0] 低字节)。"""

    value: int


class SetDespawnOnOob(EclInstr, frozen=True, tag="set_despawn_on_oob"):
    """设出屏不消(args[0] 低字节)。"""

    value: int


class SetLifeCallbackThreshold(
    EclInstr, frozen=True, tag="set_life_callback_threshold"
):
    """设血量回调阈值 0 号。"""

    value: IntOperand


class SetLifeCallbackSub(EclInstr, frozen=True, tag="set_life_callback_sub"):
    """设血量回调 sub 0 号。"""

    sub_id: IntOperand


class SetTimerCallbackThreshold(
    EclInstr, frozen=True, tag="set_timer_callback_threshold"
):
    """设计时器回调阈值并清零计时。"""

    value: IntOperand


class SetTimerCallbackSub(EclInstr, frozen=True, tag="set_timer_callback_sub"):
    """设计时器回调 sub。"""

    sub_id: IntOperand


class SetPeriodicCallback(EclInstr, frozen=True, tag="set_periodic_callback"):
    """设周期回调(timer 帧一次进 sub_id)。"""

    timer: IntOperand
    sub_id: IntOperand


class SetDeathCallbackSub(EclInstr, frozen=True, tag="set_death_callback_sub"):
    """设死亡回调 sub(args[0] 低字节)。"""

    sub_id: int


class SetVmInterrupt(EclInstr, frozen=True, tag="set_vm_interrupt"):
    """设次级 anm VM 的 interrupt(idx raw, value = word1 低 i16)。"""

    idx: int
    value: int


class SetSpecialEffectPos(EclInstr, frozen=True, tag="set_special_effect_pos"):
    """设自定义特效位置(enabled = 0 时取用 x/y/z)。"""

    # EclManager.cpp:1947-1954
    enabled: IntOperand
    x: FloatOperand
    y: FloatOperand
    z: FloatOperand


class SetGlobalEffectColorMul(EclInstr, frozen=True, tag="set_global_effect_color_mul"):
    """设全局特效颜色乘数。"""

    # EclManager.cpp:1921-1930
    r: FloatOperand
    g: FloatOperand
    b: FloatOperand
    a: FloatOperand


class Idfk(EclInstr, frozen=True, tag="idfk"):
    """写 world 的 unused_9545f0(用途不明)。"""

    value: IntOperand


class BeginSpellcard(EclInstr, frozen=True, tag="begin_spellcard"):
    """开符卡(word0 = gui_id i16|spellcard_idx u16, 之后 12 字符卡名)。"""

    # 符卡名 48 字节 XOR 0xAA, NUL 截断, Shift-JIS
    # (EclManager.cpp BeginSpellcard; 解码在 ecl_table 定制钩子)
    gui_id: int
    spellcard_idx: int
    name: str


class SetBossRunInterrupt(EclInstr, frozen=True, tag="set_boss_run_interrupt"):
    """设指定 boss 的 run_interrupt。"""

    idx: IntOperand
    interrupt: IntOperand


class SetScriptWaitTime(EclInstr, frozen=True, tag="set_script_wait_time"):
    """设全局脚本等待时间。"""

    frames: IntOperand


class AddCherryPlus(EclInstr, frozen=True, tag="add_cherry_plus"):
    """樱点入账(th07 专属机制)。"""

    value: IntOperand


#: th07 的 ECL 指令 union(两作共享 + v0 专属)
Instruction = (
    SharedInstruction
    | SetRunInterrupt
    | Rand
    | RandAdd
    | RandFloat
    | RandFloatAdd
    | RandFloatRange
    | GetExitAngle
    | SetPos
    | SetAxisSpeed
    | SetMoveSpeed
    | MovePosTime
    | MoveOrbit
    | SetOrbitRadius
    | SetOrbitAngle
    | SetMoveInterpTimerPolar
    | SetMoveInterpTimerRadial
    | SetMoveInterpTimerInterp
    | DisableBullets
    | EnableBullets
    | SetShootOffset
    | SpawnLaserPattern
    | TestLaserNotInUse
    | SetMoveAnm
    | SetHitboxSize
    | SetGrazeSize
    | SetHasContactHitbox
    | SetCanBeDamaged
    | SetIsHittable
    | SetEnemyCanDie
    | SetHasNoCollision
    | SetIsProjectile
    | SetDespawnOnOob
    | SetLifeCallbackThreshold
    | SetLifeCallbackSub
    | SetTimerCallbackThreshold
    | SetTimerCallbackSub
    | SetPeriodicCallback
    | SetDeathCallbackSub
    | SetVmInterrupt
    | SetSpecialEffectPos
    | SetGlobalEffectColorMul
    | Idfk
    | BeginSpellcard
    | SetBossRunInterrupt
    | SetScriptWaitTime
    | AddCherryPlus
)
