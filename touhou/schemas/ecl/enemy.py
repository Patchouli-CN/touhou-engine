"""ECL 敌人状态指令(生成/anm/判定盒/标志位/回调/道具/特效), 两作共享部分。"""

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


class RemoveAllEnemies(EclInstr, frozen=True, tag="remove_all_enemies"):
    """清全部非 boss 敌(得分 8000/0)。"""


class SetAnm(EclInstr, frozen=True, tag="set_anm"):
    """设主 anm 脚本号(alt_bank = 用备用 anm 银行, 仅 v800 有对应 opcode)。"""

    anm_idx: IntOperand
    alt_bank: bool


class SetSubAnm(EclInstr, frozen=True, tag="set_sub_anm"):
    """设子机 anm 脚本号(idx 槽位)。"""

    idx: IntOperand
    anm_idx: IntOperand
    alt_bank: bool


class SetDeathAnm(EclInstr, frozen=True, tag="set_death_anm"):
    """设死亡 anm: word0 的 3 个打包字节(a/c 有符号)。"""

    a: int
    b: int
    c: int


class SetVmAutoRotate(EclInstr, frozen=True, tag="set_vm_auto_rotate"):
    """设主 anm VM 随移动旋转(args[0] 低字节)。"""

    value: int


class SetIsSurvivalSpellcard(EclInstr, frozen=True, tag="set_is_survival_spellcard"):
    """设生存符(args[0] 低字节; v800 叫 timeoutSpell)。"""

    value: int


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


class SetLifeCallback(EclInstr, frozen=True, tag="set_life_callback"):
    """设血量阈值回调(idx, threshold, sub_id)。"""

    idx: IntOperand
    threshold: IntOperand
    sub_id: IntOperand


class BindTimerCallbackToDeath(
    EclInstr, frozen=True, tag="bind_timer_callback_to_death"
):
    """计时器回调绑到死亡回调 sub, 计时清零。"""


class SetDeathType(EclInstr, frozen=True, tag="set_death_type"):
    """设死亡类型(args[0] 低字节)。"""

    value: int


class SetInvincibilityTimer(EclInstr, frozen=True, tag="set_invincibility_timer"):
    """设无敌帧数(v800 叫 damageReductionTimer)。"""

    frames: IntOperand


class SetPrimaryVmInterrupt(EclInstr, frozen=True, tag="set_primary_vm_interrupt"):
    """设主 anm VM 的 interrupt。"""

    value: IntOperand


class SetPrimaryVmRotZ(EclInstr, frozen=True, tag="set_primary_vm_rot_z"):
    """设主 anm VM 的 z 轴转角。"""

    value: FloatOperand


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
