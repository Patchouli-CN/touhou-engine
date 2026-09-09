"""ECL 敌人状态指令(生成/anm/判定盒/标志位/回调/道具/特效)。"""

from __future__ import annotations

from .base import EclInstr, FloatOperand, IntOperand

# 编号出处同 control.py 头注; 字节级字段(args[N].b[0] 等)出处
# Reference/th07/src/th07/EclManager.cpp 对应 case


class SpawnEnemyAbs(EclInstr, frozen=True, tag="spawn_enemy_abs"):
    """以脚本坐标生成敌人(sub_id 为 raw)。"""

    sub_id: int
    x: FloatOperand
    y: FloatOperand
    z: FloatOperand
    life: IntOperand
    item_drop: IntOperand
    score: IntOperand


class SpawnEnemyRel(EclInstr, frozen=True, tag="spawn_enemy_rel"):
    """以本机位置偏移生成敌人(字段同 SpawnEnemyAbs)。"""

    sub_id: int
    x: FloatOperand
    y: FloatOperand
    z: FloatOperand
    life: IntOperand
    item_drop: IntOperand
    score: IntOperand


class SpawnFamiliar(EclInstr, frozen=True, tag="spawn_familiar"):
    """生成使魔: 脚本坐标(v800 专属, sub_id 为 raw)。"""

    # EclRunLow.inl:737-796
    sub_id: int
    x: FloatOperand
    y: FloatOperand
    life: IntOperand
    item_drop: IntOperand
    score: IntOperand


class SpawnFamiliarRel(EclInstr, frozen=True, tag="spawn_familiar_rel"):
    """生成使魔: 父位置偏移(字段同 SpawnFamiliar, v800 专属)。"""

    # EclRunLow.inl:797-856
    sub_id: int
    x: FloatOperand
    y: FloatOperand
    life: IntOperand
    item_drop: IntOperand
    score: IntOperand


class SpawnFamiliarInherit(EclInstr, frozen=True, tag="spawn_familiar_inherit"):
    """生成使魔: 继承父位置(字段同 SpawnFamiliar, v800 专属)。"""

    # EclRunLow.inl:857-929
    sub_id: int
    x: FloatOperand
    y: FloatOperand
    life: IntOperand
    item_drop: IntOperand
    score: IntOperand


class RemoveAllEnemies(EclInstr, frozen=True, tag="remove_all_enemies"):
    """清全部非 boss 敌(得分 8000/0)。"""


class SetAnm(EclInstr, frozen=True, tag="set_anm"):
    """设主 anm 脚本号(alt_bank = 用备用 anm 银行, 仅 v800 有对应 opcode)。"""

    anm_idx: IntOperand
    alt_bank: bool


class SetMoveAnm(EclInstr, frozen=True, tag="set_move_anm"):
    """设移动 anm 组(v0 版: 5 个 i16 脚本号, 打包在 3 字里)。"""

    scripts: tuple[int, int, int, int, int]


class SetMoveAnmSeq(EclInstr, frozen=True, tag="set_move_anm_seq"):
    """设移动 anm 组 = base..base+5 连续 6 脚本(v800 专属)。"""

    # SetPrimaryAnmScripts(EclDependencies.cpp:449-460)
    base: IntOperand
    alt_bank: bool


class SetMoveAnmV800(EclInstr, frozen=True, tag="set_move_anm_v800"):
    """设移动 anm 组(v800 版: 6 个可变参脚本号)。"""

    scripts: tuple[IntOperand, ...]
    alt_bank: bool


class SetSubAnm(EclInstr, frozen=True, tag="set_sub_anm"):
    """设子机 anm 脚本号(idx 槽位)。"""

    idx: IntOperand
    anm_idx: IntOperand
    alt_bank: bool


class SetSpecialAnm(EclInstr, frozen=True, tag="set_special_anm"):
    """主 anm 切到移动组的 special 脚本(v800 专属)。"""


class SetDeathAnm(EclInstr, frozen=True, tag="set_death_anm"):
    """设死亡 anm: word0 的 3 个打包字节(a/c 有符号)。"""

    a: int
    b: int
    c: int


class SetHitboxSize(EclInstr, frozen=True, tag="set_hitbox_size"):
    """设判定盒尺寸(x/y/z, v0 专属)。"""

    x: FloatOperand
    y: FloatOperand
    z: FloatOperand


class SetHitboxSizeV800(EclInstr, frozen=True, tag="set_hitbox_size_v800"):
    """设判定盒尺寸(v800 版: 只有 x/y)。"""

    x: FloatOperand
    y: FloatOperand


class SetGrazeSize(EclInstr, frozen=True, tag="set_graze_size"):
    """设擦弹判定尺寸(x/y/z, v0 专属)。"""

    x: FloatOperand
    y: FloatOperand
    z: FloatOperand


class SetGrazeSizeV800(EclInstr, frozen=True, tag="set_graze_size_v800"):
    """设擦弹判定尺寸(v800 版: 只有 x/y)。"""

    x: FloatOperand
    y: FloatOperand


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
    """设可否被击坠(args[0] 低字节, v0 专属)。"""

    value: int


class SetVmAutoRotate(EclInstr, frozen=True, tag="set_vm_auto_rotate"):
    """设主 anm VM 随移动旋转(args[0] 低字节)。"""

    value: int


class SetHasNoCollision(EclInstr, frozen=True, tag="set_has_no_collision"):
    """设无碰撞(args[0] 低字节, v0 专属)。"""

    value: int


class SetIsSurvivalSpellcard(EclInstr, frozen=True, tag="set_is_survival_spellcard"):
    """设生存符(args[0] 低字节; v800 叫 timeoutSpell)。"""

    value: int


class SetIsProjectile(EclInstr, frozen=True, tag="set_is_projectile"):
    """设投射物标记(args[0] 低字节, v0 专属)。"""

    value: int


class SetSpecialInteraction(EclInstr, frozen=True, tag="set_special_interaction"):
    """设 specialInteraction 并归 drawGroup 2(args[0] 低字节, v800 专属)。"""

    value: int


class SetDespawnOnOob(EclInstr, frozen=True, tag="set_despawn_on_oob"):
    """设出屏不消(args[0] 低字节, v0 专属)。"""

    value: int


class SetEnemyFlags(EclInstr, frozen=True, tag="set_enemy_flags"):
    """敌人能力标志按掩码直接赋值(前三位反相, v800 专属)。"""

    # EclRunLow.inl:650-658
    mask: IntOperand


class ClearEnemyFlags(EclInstr, frozen=True, tag="clear_enemy_flags"):
    """掩码置位 → 对应能力关(v800 专属)。"""

    # EclRunLow.inl:660-673
    mask: IntOperand


class EnableEnemyFlags(EclInstr, frozen=True, tag="enable_enemy_flags"):
    """掩码置位 → 对应能力开(v800 专属)。"""

    # EclRunLow.inl:675-688
    mask: IntOperand


class SetFormEffect(EclInstr, frozen=True, tag="set_form_effect"):
    """设 flags2 的 formEffect(v800 专属)。"""

    value: IntOperand


class SetTrail(EclInstr, frozen=True, tag="set_trail"):
    """设拖尾: flags = args[0] 低字节, 之后 count/interval/node_step。"""

    # EclManager.cpp ECL_SET_TRAIL case(trailFlags/trailCount/trailInterval/trailNodeStep)
    flags: int
    count: IntOperand
    interval: IntOperand
    node_step: IntOperand


class SetLife(EclInstr, frozen=True, tag="set_life"):
    """设血量(life = max_life; v800 顺带记 phaseStartingLife)。"""

    life: IntOperand


class SetTimer(EclInstr, frozen=True, tag="set_timer"):
    """设敌机计时器。"""

    value: IntOperand


class SetLifeCallbackThreshold(
    EclInstr, frozen=True, tag="set_life_callback_threshold"
):
    """设血量回调阈值 0 号(v0 专属)。"""

    value: IntOperand


class SetLifeCallbackSub(EclInstr, frozen=True, tag="set_life_callback_sub"):
    """设血量回调 sub 0 号(v0 专属)。"""

    sub_id: IntOperand


class SetTimerCallbackThreshold(
    EclInstr, frozen=True, tag="set_timer_callback_threshold"
):
    """设计时器回调阈值并清零计时(v0 专属)。"""

    value: IntOperand


class SetTimerCallbackSub(EclInstr, frozen=True, tag="set_timer_callback_sub"):
    """设计时器回调 sub(v0 专属)。"""

    sub_id: IntOperand


class SetLifeCallback(EclInstr, frozen=True, tag="set_life_callback"):
    """设血量阈值回调(idx, threshold, sub_id)。"""

    idx: IntOperand
    threshold: IntOperand
    sub_id: IntOperand


class SetTimerCallback(EclInstr, frozen=True, tag="set_timer_callback"):
    """设计时器回调(threshold, sub_id), 计时清零(v800 专属)。"""

    threshold: IntOperand
    sub_id: IntOperand


class SetPeriodicCallback(EclInstr, frozen=True, tag="set_periodic_callback"):
    """设周期回调(timer 帧一次进 sub_id, v0 专属)。"""

    timer: IntOperand
    sub_id: IntOperand


class BindTimerCallbackToDeath(
    EclInstr, frozen=True, tag="bind_timer_callback_to_death"
):
    """计时器回调绑到死亡回调 sub, 计时清零。"""


class SetDeathType(EclInstr, frozen=True, tag="set_death_type"):
    """设死亡类型(args[0] 低字节)。"""

    value: int


class SetDeathCallbackSub(EclInstr, frozen=True, tag="set_death_callback_sub"):
    """设死亡回调 sub(args[0] 低字节, v0 专属)。"""

    sub_id: int


class SetDeathCallbackSubV800(EclInstr, frozen=True, tag="set_death_callback_sub_v800"):
    """设死亡回调 sub(v800 版: word0 低 i16, -1 = 未设置)。"""

    sub_id: int


class SetInvincibilityTimer(EclInstr, frozen=True, tag="set_invincibility_timer"):
    """设无敌帧数(v800 叫 damageReductionTimer)。"""

    frames: IntOperand


class SetPrimaryVmInterrupt(EclInstr, frozen=True, tag="set_primary_vm_interrupt"):
    """设主 anm VM 的 interrupt。"""

    value: IntOperand


class SetVmInterrupt(EclInstr, frozen=True, tag="set_vm_interrupt"):
    """设次级 anm VM 的 interrupt(v0 版: idx raw, value = word1 低 i16)。"""

    idx: int
    value: int


class SetVmInterruptV800(EclInstr, frozen=True, tag="set_vm_interrupt_v800"):
    """设次级 anm VM 的 interrupt(v800 版: idx raw, value = word1 低 u16)。"""

    # EclRunHigh.inl:784-787
    idx: int
    value: int


class SetPrimaryVmRotZ(EclInstr, frozen=True, tag="set_primary_vm_rot_z"):
    """设主 anm VM 的 z 轴转角。"""

    value: FloatOperand


class SetItemDrop(EclInstr, frozen=True, tag="set_item_drop"):
    """设掉落道具类型(v800 专属)。"""

    value: IntOperand


class SetItemDropCounts(EclInstr, frozen=True, tag="set_item_drop_counts"):
    """设掉落数(点道具数/火力或点道具数, v800 专属)。"""

    point_count: IntOperand
    power_or_point_count: IntOperand


class SetDrawGroup(EclInstr, frozen=True, tag="set_draw_group"):
    """设绘制组(v800 专属)。"""

    value: IntOperand


class SetNoDamageDuringStop(EclInstr, frozen=True, tag="set_no_damage_during_stop"):
    """设 stop 期间不受击(v800 专属)。"""

    value: IntOperand


class SetExtraVmFixedOffset(EclInstr, frozen=True, tag="set_extra_vm_fixed_offset"):
    """设次级 anm VM 固定偏移(v800 专属)。"""

    value: IntOperand


class SetPhaseStartLife(EclInstr, frozen=True, tag="set_phase_start_life"):
    """只记 phaseStartingLife 不动当前血(v800 专属)。"""

    value: IntOperand


class PlaySound(EclInstr, frozen=True, tag="play_sound"):
    """播放音效。"""

    sound_idx: IntOperand


class SpawnItem(EclInstr, frozen=True, tag="spawn_item"):
    """在敌机位置掉一个道具。"""

    item_type: IntOperand


class SpawnItems(EclInstr, frozen=True, tag="spawn_items"):
    """掉 count 个道具(火力未满第一个大 P, 满火力全点)。"""

    count: IntOperand


class SpawnPointItems(EclInstr, frozen=True, tag="spawn_point_items"):
    """掉 count 个点道具(位置随机抖动)。"""

    count: IntOperand


class SpawnEffect(EclInstr, frozen=True, tag="spawn_effect"):
    """生方向性特效(全 raw: color 索引 + 方向向量 + 距离)。"""

    # v0=100(EclManager.cpp:1530-1537); v800=128(实测数据逐字同型)
    color: int
    dx: float
    dy: float
    dz: float
    distance: float


class SpawnParticles(EclInstr, frozen=True, tag="spawn_particles"):
    """生一次性粒子(effect_idx/count/color)。"""

    # v0=117(EclManager.cpp:1750-1756); v800=139(布局按 v0 同型推定, 实测同型)
    effect_idx: IntOperand
    count: IntOperand
    color: IntOperand


class SpawnMovingParticles(EclInstr, frozen=True, tag="spawn_moving_particles"):
    """生带速度粒子(v800 叫 SPAWN_EFFECT_VELOCITY)。"""

    # v0=118(EclManager.cpp:1758-1768); v800=140(布局按 v0 同型推定,
    # 实测 mask=8 例证明 word3 起是可变参 float)
    effect_idx: IntOperand
    count: IntOperand
    color: IntOperand
    vx: FloatOperand
    vy: FloatOperand
    vz: FloatOperand


class SpawnAlignmentEffect(EclInstr, frozen=True, tag="spawn_alignment_effect"):
    """生人妖对齐特效(结界光环, v800 专属)。"""

    # EclRunHigh.inl:936-952
    value: IntOperand


class Idfk(EclInstr, frozen=True, tag="idfk"):
    """写 world 的 unused_9545f0(用途不明, v0 专属)。"""

    value: IntOperand


class SetEnemyManagerValue(EclInstr, frozen=True, tag="set_enemy_manager_value"):
    """写 EnemyManager.opcode163Value(v800 专属)。"""

    value: IntOperand


class SetSpecialEffectPos(EclInstr, frozen=True, tag="set_special_effect_pos"):
    """设自定义特效位置(enabled = 0 时取用 x/y/z, v0 专属)。"""

    # EclManager.cpp:1947-1954
    enabled: IntOperand
    x: FloatOperand
    y: FloatOperand
    z: FloatOperand


class SetGlobalEffectColorMul(EclInstr, frozen=True, tag="set_global_effect_color_mul"):
    """设全局特效颜色乘数(v0 专属)。"""

    # EclManager.cpp:1921-1930
    r: FloatOperand
    g: FloatOperand
    b: FloatOperand
    a: FloatOperand
