"""th08(v800 格式)专属 ECL 指令类 + 作品的 Instruction union。

两作共享的指令类住 schemas/ecl; 这里是 v800 opcode 表独有的部分(时刻/
结界/使魔等 th08 机制 + 布局分叉的 V800 变体)。编号/布局出处 th08
EclRunLow.inl:223-929 / EclRunHigh.inl:163-972(转引
scratch_dbg/investigation/th08-ref-facts.md:21)。
"""

from __future__ import annotations

from ...schemas.ecl import (
    EclInstr,
    FloatOperand,
    IntOperand,
    SharedInstruction,
    VarRef,
)


class RunPendingSub(EclInstr, frozen=True, tag="run_pending_sub"):
    """pending 槽位 → eclSubroutineIds[slot] 压栈调用。"""

    # EclRunHigh.inl:492-519
    slot: IntOperand


class SetChildContext(EclInstr, frozen=True, tag="set_child_context"):
    """安装/释放 child 上下文块(sub_id < 0 = 释放)。"""

    # EclRunHigh.inl:580-613
    slot: IntOperand
    sub_id: IntOperand


class CallSubOnBoss(EclInstr, frozen=True, tag="call_sub_on_boss"):
    """让指定 boss 压栈调 sub(sub_id 为 raw)。"""

    # EclRunLow.inl:712-735
    boss_idx: IntOperand
    sub_id: int


class SetBossPendingSub(EclInstr, frozen=True, tag="set_boss_pending_sub"):
    """设置 boss 的 pendingEclSubroutineIndex。"""

    boss_idx: IntOperand
    sub_id: IntOperand


class AddAssign(EclInstr, frozen=True, tag="add_assign"):
    """dest += value(int)。"""

    dest: VarRef | None
    value: IntOperand


class SubAssign(EclInstr, frozen=True, tag="sub_assign"):
    """dest -= value(int)。"""

    dest: VarRef | None
    value: IntOperand


class MulAssign(EclInstr, frozen=True, tag="mul_assign"):
    """dest *= value(int)。"""

    dest: VarRef | None
    value: IntOperand


class DivAssign(EclInstr, frozen=True, tag="div_assign"):
    """dest /= value(int)。"""

    dest: VarRef | None
    value: IntOperand


class ModAssign(EclInstr, frozen=True, tag="mod_assign"):
    """dest %%= value(int)。"""

    dest: VarRef | None
    value: IntOperand


class AddAssignFloat(EclInstr, frozen=True, tag="add_assign_float"):
    """dest += value(float)。"""

    dest: VarRef | None
    value: FloatOperand


class SubAssignFloat(EclInstr, frozen=True, tag="sub_assign_float"):
    """dest -= value(float)。"""

    dest: VarRef | None
    value: FloatOperand


class MulAssignFloat(EclInstr, frozen=True, tag="mul_assign_float"):
    """dest *= value(float)。"""

    dest: VarRef | None
    value: FloatOperand


class DivAssignFloat(EclInstr, frozen=True, tag="div_assign_float"):
    """dest /= value(float)。"""

    dest: VarRef | None
    value: FloatOperand


class ModAssignFloat(EclInstr, frozen=True, tag="mod_assign_float"):
    """dest = fmod(dest, value)。"""

    dest: VarRef | None
    value: FloatOperand


class VecFromAngleMag(EclInstr, frozen=True, tag="vec_from_angle_mag"):
    """角度先规范化再分解: dest_x = cos(angle)*mag, dest_y = sin(angle)*mag。"""

    # EclRunLow.inl:368-373
    dest_x: VarRef | None
    dest_y: VarRef | None
    angle: FloatOperand
    magnitude: FloatOperand


class Dist(EclInstr, frozen=True, tag="dist"):
    """dest = (x1, y1) 到 (x2, y2) 的距离。"""

    # EclRunLow.inl:375-388
    dest: VarRef | None
    x1: FloatOperand
    y1: FloatOperand
    x2: FloatOperand
    y2: FloatOperand


class SetPosV800(EclInstr, frozen=True, tag="set_pos_v800"):
    """直接设位置(只有 x/y, z 恒 0)。"""

    x: FloatOperand
    y: FloatOperand


class MovePosTimeV800(EclInstr, frozen=True, tag="move_pos_time_v800"):
    """限时移动到目标点(只有 x/y)。"""

    # ConfigureRelativeMotion(EclHelpers.cpp:59-87)
    duration: IntOperand
    easing: IntOperand
    x: FloatOperand
    y: FloatOperand


class MoveAtPlayerTime(EclInstr, frozen=True, tag="move_at_player_time"):
    """限时朝自机位移(duration <= 0 = 直飞)。"""

    # EclRunLow.inl:543-560
    duration: IntOperand
    easing: IntOperand
    angle: FloatOperand
    speed: FloatOperand


class MoveBoundaryAware(EclInstr, frozen=True, tag="move_boundary_aware"):
    """朝屏外逃的限时位移(duration <= 0 = 直飞)。"""

    # BeginBoundaryAwareMove(EclDependencies.cpp:122-185)
    duration: IntOperand
    easing: IntOperand
    speed: FloatOperand


class MoveRandomBiased(EclInstr, frozen=True, tag="move_random_biased"):
    """3/4 概率偏向自机的随机限时位移(duration <= 0 = 直飞)。"""

    # ApplyRandomBiasedMove(EclDependencies.cpp:188-274)
    duration: IntOperand
    easing: IntOperand
    speed: FloatOperand


class SetMovePolar(EclInstr, frozen=True, tag="set_move_polar"):
    """angle + speed 直飞(移动模式 1)。"""

    angle: FloatOperand
    speed: FloatOperand


class MoveOrbitV800(EclInstr, frozen=True, tag="move_orbit_v800"):
    """绕指定原点轨道(原点只有 x/y, 移动模式 3)。"""

    duration: IntOperand
    origin_x: FloatOperand
    origin_y: FloatOperand
    angle: FloatOperand
    angular_vel: FloatOperand
    radius: FloatOperand
    radial_vel: FloatOperand


class MoveOrbitAroundSelf(EclInstr, frozen=True, tag="move_orbit_around_self"):
    """绕当前位置轨道(半径 0 起, 移动模式 3)。"""

    duration: IntOperand
    angle: FloatOperand
    angular_vel: FloatOperand
    radial_vel: FloatOperand


class SetOrbitVels(EclInstr, frozen=True, tag="set_orbit_vels"):
    """设轨道角速度/径向速度(移动模式 3)。"""

    duration: IntOperand
    angular_vel: FloatOperand
    radial_vel: FloatOperand


class SetMinPlayerDistance(EclInstr, frozen=True, tag="set_min_player_distance"):
    """距自机过近压住弹幕的距离阈值(存平方)。"""

    # EclRunHigh.inl:922-935
    distance: FloatOperand


class DeferBulletPattern(EclInstr, frozen=True, tag="defer_bullet_pattern"):
    """弹幕指令延迟到自动射击时重新派发。"""

    # ENEMY_FLAG_DEFER_BULLET_PATTERN(EclRunHigh.inl:174-181)


class DisableDeferBulletPattern(
    EclInstr, frozen=True, tag="disable_defer_bullet_pattern"
):
    """取消弹幕延迟派发。"""


class ClearBulletsForTransition(
    EclInstr, frozen=True, tag="clear_bullets_for_transition"
):
    """符卡转场清弹。"""


class SetShootOffsetV800(EclInstr, frozen=True, tag="set_shoot_offset_v800"):
    """设发射点相对偏移(只有 x/y)。"""

    x: FloatOperand
    y: FloatOperand


class SpawnLaserPatternV800(EclInstr, frozen=True, tag="spawn_laser_pattern_v800"):
    """生成激光(width/计时也可变参; aimed = 出生即瞄自机)。"""

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


class TestLaserInUse(EclInstr, frozen=True, tag="test_laser_in_use"):
    """测激光是否在用, 结果写 extraIntVariables[2]。"""

    # EclRunHigh.inl:385-393
    idx: IntOperand


class SpawnFamiliar(EclInstr, frozen=True, tag="spawn_familiar"):
    """生成使魔: 脚本坐标(sub_id 为 raw)。"""

    # EclRunLow.inl:737-796
    sub_id: int
    x: FloatOperand
    y: FloatOperand
    life: IntOperand
    item_drop: IntOperand
    score: IntOperand


class SpawnFamiliarRel(EclInstr, frozen=True, tag="spawn_familiar_rel"):
    """生成使魔: 父位置偏移(字段同 SpawnFamiliar)。"""

    # EclRunLow.inl:797-856
    sub_id: int
    x: FloatOperand
    y: FloatOperand
    life: IntOperand
    item_drop: IntOperand
    score: IntOperand


class SpawnFamiliarInherit(EclInstr, frozen=True, tag="spawn_familiar_inherit"):
    """生成使魔: 继承父位置(字段同 SpawnFamiliar)。"""

    # EclRunLow.inl:857-929
    sub_id: int
    x: FloatOperand
    y: FloatOperand
    life: IntOperand
    item_drop: IntOperand
    score: IntOperand


class SetMoveAnmSeq(EclInstr, frozen=True, tag="set_move_anm_seq"):
    """设移动 anm 组 = base..base+5 连续 6 脚本。"""

    # SetPrimaryAnmScripts(EclDependencies.cpp:449-460)
    base: IntOperand
    alt_bank: bool


class SetMoveAnmV800(EclInstr, frozen=True, tag="set_move_anm_v800"):
    """设移动 anm 组(6 个可变参脚本号)。"""

    scripts: tuple[IntOperand, ...]
    alt_bank: bool


class SetSpecialAnm(EclInstr, frozen=True, tag="set_special_anm"):
    """主 anm 切到移动组的 special 脚本。"""


class SetHitboxSizeV800(EclInstr, frozen=True, tag="set_hitbox_size_v800"):
    """设判定盒尺寸(只有 x/y)。"""

    x: FloatOperand
    y: FloatOperand


class SetGrazeSizeV800(EclInstr, frozen=True, tag="set_graze_size_v800"):
    """设擦弹判定尺寸(只有 x/y)。"""

    x: FloatOperand
    y: FloatOperand


class SetSpecialInteraction(EclInstr, frozen=True, tag="set_special_interaction"):
    """设 specialInteraction 并归 drawGroup 2(args[0] 低字节)。"""

    value: int


class SetEnemyFlags(EclInstr, frozen=True, tag="set_enemy_flags"):
    """敌人能力标志按掩码直接赋值(前三位反相)。"""

    # EclRunLow.inl:650-658
    mask: IntOperand


class ClearEnemyFlags(EclInstr, frozen=True, tag="clear_enemy_flags"):
    """掩码置位 → 对应能力关。"""

    # EclRunLow.inl:660-673
    mask: IntOperand


class EnableEnemyFlags(EclInstr, frozen=True, tag="enable_enemy_flags"):
    """掩码置位 → 对应能力开。"""

    # EclRunLow.inl:675-688
    mask: IntOperand


class SetFormEffect(EclInstr, frozen=True, tag="set_form_effect"):
    """设 flags2 的 formEffect。"""

    value: IntOperand


class SetTimerCallback(EclInstr, frozen=True, tag="set_timer_callback"):
    """设计时器回调(threshold, sub_id), 计时清零。"""

    threshold: IntOperand
    sub_id: IntOperand


class SetDeathCallbackSubV800(EclInstr, frozen=True, tag="set_death_callback_sub_v800"):
    """设死亡回调 sub(word0 低 i16, -1 = 未设置)。"""

    sub_id: int


class SetVmInterruptV800(EclInstr, frozen=True, tag="set_vm_interrupt_v800"):
    """设次级 anm VM 的 interrupt(idx raw, value = word1 低 u16)。"""

    # EclRunHigh.inl:784-787
    idx: int
    value: int


class SetItemDrop(EclInstr, frozen=True, tag="set_item_drop"):
    """设掉落道具类型。"""

    value: IntOperand


class SetItemDropCounts(EclInstr, frozen=True, tag="set_item_drop_counts"):
    """设掉落数(点道具数/火力或点道具数)。"""

    point_count: IntOperand
    power_or_point_count: IntOperand


class SetDrawGroup(EclInstr, frozen=True, tag="set_draw_group"):
    """设绘制组。"""

    value: IntOperand


class SetNoDamageDuringStop(EclInstr, frozen=True, tag="set_no_damage_during_stop"):
    """设 stop 期间不受击。"""

    value: IntOperand


class SetExtraVmFixedOffset(EclInstr, frozen=True, tag="set_extra_vm_fixed_offset"):
    """设次级 anm VM 固定偏移。"""

    value: IntOperand


class SetPhaseStartLife(EclInstr, frozen=True, tag="set_phase_start_life"):
    """只记 phaseStartingLife 不动当前血。"""

    value: IntOperand


class SpawnAlignmentEffect(EclInstr, frozen=True, tag="spawn_alignment_effect"):
    """生人妖对齐特效(结界光环)。"""

    # EclRunHigh.inl:936-952
    value: IntOperand


class SetEnemyManagerValue(EclInstr, frozen=True, tag="set_enemy_manager_value"):
    """写 EnemyManager.opcode163Value。"""

    value: IntOperand


class BeginSpellcardV800(EclInstr, frozen=True, tag="begin_spellcard_v800"):
    """开符卡(多 bonus/机主名/两行注释)。"""

    # EclSpellCardInstructionArgs(EclDependencies.cpp:18-36):
    # word0 = enemyFace i16|spellCardNumber u16, bonus i32 @word1,
    # name[48] @word2, owner[48] @word14, comment[64]×2 @word26/42;
    # name 是 XOR 0xAA 文本(实测解码正确), owner/comment 编码未核实
    # (旧实现也不消费), 保留原始字
    gui_id: int
    spellcard_idx: int
    bonus: int
    name: str
    owner: tuple[int, ...]
    comment1: tuple[int, ...]
    comment2: tuple[int, ...]


class SetStageScriptLabel(EclInstr, frozen=True, tag="set_stage_script_label"):
    """设场景脚本待跳转 label。"""

    label: IntOperand


class SuppressTimelineSpawns(EclInstr, frozen=True, tag="suppress_timeline_spawns"):
    """全局抑制时间轴生敌。"""

    value: IntOperand


class SetLastSpellFlags(EclInstr, frozen=True, tag="set_last_spell_flags"):
    """置 Last Spell 标志位 + pause timer(rest 收携带的未用字)。"""

    # EclRunHigh.inl:902-919; 真实数据带 1 个参数字, C 不读
    rest: tuple[int, ...] = ()


class SetSpellcardEffectTracking(
    EclInstr, frozen=True, tag="set_spellcard_effect_tracking"
):
    """设符卡特效跟踪。"""

    value: IntOperand
    x: FloatOperand
    y: FloatOperand
    z: FloatOperand


class StartStageBackgroundSequence(
    EclInstr, frozen=True, tag="start_stage_background_sequence"
):
    """启动关卡背景序列(无参数)。"""


class HideClock(EclInstr, frozen=True, tag="hide_clock"):
    """隐藏时刻表盘(无参数)。"""


class AdvanceClock(EclInstr, frozen=True, tag="advance_clock"):
    """时刻 +1 封顶 12(无参数)。"""

    # EclRunHigh.inl:957-967


class SetBonusUpdatesDisabled(EclInstr, frozen=True, tag="set_bonus_updates_disabled"):
    """设符卡分更新禁止。"""

    value: IntOperand


#: th08 的 ECL 指令 union(两作共享 + v800 专属)
Instruction = (
    SharedInstruction
    | RunPendingSub
    | SetChildContext
    | CallSubOnBoss
    | SetBossPendingSub
    | AddAssign
    | SubAssign
    | MulAssign
    | DivAssign
    | ModAssign
    | AddAssignFloat
    | SubAssignFloat
    | MulAssignFloat
    | DivAssignFloat
    | ModAssignFloat
    | VecFromAngleMag
    | Dist
    | SetPosV800
    | MovePosTimeV800
    | MoveAtPlayerTime
    | MoveBoundaryAware
    | MoveRandomBiased
    | SetMovePolar
    | MoveOrbitV800
    | MoveOrbitAroundSelf
    | SetOrbitVels
    | SetMinPlayerDistance
    | DeferBulletPattern
    | DisableDeferBulletPattern
    | ClearBulletsForTransition
    | SetShootOffsetV800
    | SpawnLaserPatternV800
    | TestLaserInUse
    | SpawnFamiliar
    | SpawnFamiliarRel
    | SpawnFamiliarInherit
    | SetMoveAnmSeq
    | SetMoveAnmV800
    | SetSpecialAnm
    | SetHitboxSizeV800
    | SetGrazeSizeV800
    | SetSpecialInteraction
    | SetEnemyFlags
    | ClearEnemyFlags
    | EnableEnemyFlags
    | SetFormEffect
    | SetTimerCallback
    | SetDeathCallbackSubV800
    | SetVmInterruptV800
    | SetItemDrop
    | SetItemDropCounts
    | SetDrawGroup
    | SetNoDamageDuringStop
    | SetExtraVmFixedOffset
    | SetPhaseStartLife
    | SpawnAlignmentEffect
    | SetEnemyManagerValue
    | BeginSpellcardV800
    | SetStageScriptLabel
    | SuppressTimelineSpawns
    | SetLastSpellFlags
    | SetSpellcardEffectTracking
    | StartStageBackgroundSequence
    | HideClock
    | AdvanceClock
    | SetBonusUpdatesDisabled
)
