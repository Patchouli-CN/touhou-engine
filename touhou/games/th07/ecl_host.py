"""th07 的 ECL 宿主: 把 engine EclHost 的钩子接到 th07 的对局状态。

变量透出(EclManager.hpp 变量表)/弹幕发射烹参数(EclManager.cpp 弹幕系 case)/
激光槽/道具掉落/音效/符卡/樱点的语义逐条照抄旧实现
(old/touhou/games/th07/ecl_vm.py + ecl_host.py); 与世界的结算接线走
on_* 钩子属性(由 games/th07/world.py 赋值), 宿主不反向 import world。
"""

from __future__ import annotations

import math
from collections.abc import Callable

from ...engine.bullets import Aim, Burst
from ...engine.bullets.field import BulletField
from ...engine.context import FrameContext
from ...engine.ecl import EclHost, EclMachine
from ...engine.ecl.num import cdiv, f32, i32
from ...engine.ecl.state import EnemySpawn, Vec3
from ...engine.enemies import Enemy, EnemyField, EnemySpawned
from ...engine.items import ItemField
from ...engine.lasers import Laser, LaserField, LaserState
from ...engine.msg import MsgExecutor
from ...engine.registry import TouhouRegistry
from ...engine.rng import Rng
from ...schemas.ecl import (
    AddLaserAngle,
    AimLaserAtPlayer,
    BindTimerCallbackToDeath,
    ClearLasers,
    EclFile,
    EclInstr,
    EndSpellcard,
    FreezeEclDuringBomb,
    GetBossFloat,
    GetBossInt,
    ImmInt,
    InitBulletCmd,
    RemoveAllBullets,
    RemoveBulletsRadius,
    SetAnm,
    SetBoss,
    SetBossHealth,
    SetBulletRankParams,
    SetBulletSound,
    SetDeathAnm,
    SetDeathType,
    SetIsSurvivalSpellcard,
    SetLaserAngle,
    SetLaserHideWarning,
    SetLaserIdx,
    SetLaserOffsets,
    SetLaserPosRel,
    SetLaserStartLen,
    SetLifeCallback,
    SetNumBossLifeMarkers,
    SetShootInterval,
    SetShootIntervalRand,
    SetSubAnm,
    SetTrail,
    SetVmAutoRotate,
    SpawnBulletPattern,
    SpawnItem,
    SpawnItems,
    SpawnPointItems,
    SpawnPrevBulletPattern,
    StopLaser,
)
from ...utils.math import Vec2, angle_to
from . import ex_ins
from .data import ECL_FLOAT_VAR_IDS, ECL_INT_VAR_IDS, ECL_POS_VAR_IDS
from .ecl_handlers import ECL_EXTRA_HANDLERS
from .ecl_instrs import (
    AddCherryPlus,
    BeginSpellcard,
    DisableBullets,
    EnableBullets,
    SetCanBeDamaged,
    SetDeathCallbackSub,
    SetDespawnOnOob,
    SetEnemyCanDie,
    SetGrazeSize,
    SetHasContactHitbox,
    SetHasNoCollision,
    SetHitboxSize,
    SetIsHittable,
    SetIsProjectile,
    SetLifeCallbackSub,
    SetLifeCallbackThreshold,
    SetMoveAnm,
    SetScriptWaitTime,
    SetShootOffset,
    SetTimerCallbackSub,
    SetTimerCallbackThreshold,
    SpawnLaserPattern,
    TestLaserNotInUse,
)
from .ecl_state import BulletShooter, EnemyExtras

#: C 弹幕上限(BulletManager::SpawnBulletPattern 的 bulletCount >= 1024 检查)
_MAX_BULLETS = 1024
#: C 激光上限(SpawnLaserPattern 的槽位数)
_MAX_LASERS = 64

#: 出生时叠加 angle_to_player 的 aim 模式
_AIMED_MODES = (Aim.SPREAD_AIMED, Aim.RING_AIMED, Aim.RING_SHIFT_AIMED)

# th07 变量表特殊 id(EclManager.hpp:362-397; 局部槽 id 见 data.ECL_*_VAR_IDS)
_V_DIFFICULTY = 10016
_V_RANK = 10017
_V_POS_X, _V_POS_Y, _V_POS_Z = 10018, 10019, 10020
_V_PLAYER_POS_X, _V_PLAYER_POS_Y, _V_PLAYER_POS_Z = 10021, 10022, 10023
_V_ANGLE_TO_PLAYER = 10024
_V_CUR_TIME = 10025
_V_DISTANCE_FROM_PLAYER = 10026
_V_LIFE = 10027
_V_PLAYER_SHOTTYPE = 10028
_V_GLOBAL_INT_BASE = 10037  # 10037..10040
_V_GLOBAL_FLOAT_BASE = 10041  # 10041..10044
_V_ANGLE = 10045
_V_ANGULAR_VELOCITY = 10046
_V_MOVE_SPEED = 10047
_V_MOVE_ACCELERATION = 10048
_V_MOVE_RADIUS = 10049
_V_MOVE_INTERP_ORIGIN_X = 10050  # +1 y +2 z
_V_MOVE_ANGLE = 10053
_V_MOVE_ANGULAR_VELOCITY = 10054
_V_RNG = 10055
_V_RNG_CUSTOM_BOUND = 10056
_V_MOVE_INTERP_TARGET_X = 10057  # +1 y +2 z
_V_RNG_RADIAN = 10060
_V_LAST_DAMAGE = 10061
_V_BOSS_ID = 10062
_V_DELTA_POS_X = 10063  # +1 y +2 z
_V_BOSS_LIFE_THRESHOLD_BASE = 10066  # 10066..10069
_V_ITEMDROP = 10070
_V_SCORE = 10071
_V_LOCAL_INT3_BASE = 10029  # ctx 槽: global_ints 快照(RNG_CUSTOM_BOUND 的边界)
_V_LOCAL_FLOAT3_BASE = 10033  # ctx 槽: global_floats 快照


def _i16(x: int) -> int:
    """i16 回绕(弹幕 count 的 rank 加减, C short 语义)。"""
    return ((x + 0x8000) & 0xFFFF) - 0x8000


def _add3(a: Vec3, b: Vec3) -> Vec3:
    """Vec3 分量相加(发射点 = 敌位置 + shoot_offset)。"""
    return Vec3(a.x + b.x, a.y + b.y, a.z + b.z)


@TouhouRegistry.ecl_host("th07")
class Th07EclHost(EclHost):
    """th07 的 ECL 宿主实现: 一关一份(换关随 ECL 文件重建)。"""

    def __init__(
        self,
        ecl_file: EclFile,
        *,
        bullets: BulletField,
        lasers: LaserField,
        items: ItemField,
        enemies: EnemyField,
        rng: Rng,
    ) -> None:
        self.file = ecl_file
        self.bullets = bullets
        self.lasers = lasers
        self.items = items
        self.enemies = enemies
        self.rng = rng
        # ---- 每帧同步(world 的 sync system 写入) ----
        self.ctx: FrameContext | None = None  # 当前帧上下文(生敌/生激光事件用)
        self.player_pos = Vec3(192.0, 400.0, 0.0)
        self.difficulty = 1
        self.rank = 16
        self.power = 0.0
        self.shottype = 0
        self.spellcard_active = False
        # ---- 账本 ----
        self.extras: dict[int, EnemyExtras] = {}  # id(machine) → 作品状态
        self.machine_enemy: dict[int, Enemy] = {}  # id(machine) → 敌人
        self.bosses: list[EclMachine | None] = [None] * 8  # boss 槽(C bosses[8])
        self.global_ints: list[int] = [0] * 4  # GLOBAL_INT_1..4(跨机共享)
        self.global_floats: list[float] = [0.0] * 4
        self.last_msg_id = -1
        # 消息系统(world 装入): msg_vm 为 None 时维持旧行为(仅记录, 不停轴)
        self.msg_vm: MsgExecutor | None = None
        self.msg_character = 0  # C g_GameManager.character (0=灵梦 1=魔理沙 2=咲夜)
        self.boss_health: tuple[int, int, int, int] = (0, 0, 0, 0)
        self.boss_life_markers = 0
        self.framerate_multiplier = 1.0  # ex10/11 游戏速度(world 每帧同步给各 VM)
        # ---- 世界接线(world 赋值; None = 未接) ----
        self.on_sound: Callable[[int], None] | None = None
        self.on_bgm: Callable[[tuple], None] | None = None
        self.on_script_wait: Callable[[int], None] | None = None
        self.on_set_power: Callable[[int], None] | None = None
        self.on_add_cherry_plus: Callable[[int], None] | None = None
        self.on_set_boss: Callable[[int, EclMachine | None], None] | None = None
        self.on_begin_spellcard: Callable[[EclMachine, int, int, str], None] | None = (
            None
        )
        self.on_end_spellcard: Callable[[EclMachine], None] | None = None
        self.on_spellcard_timeout: Callable[[EclMachine], None] | None = None

    # ---- 账本访问 ----
    def extras_of(self, m: EclMachine) -> EnemyExtras:
        return self.extras[id(m)]

    def enemy_of(self, m: EclMachine) -> Enemy:
        return self.machine_enemy[id(m)]

    def sweep(self) -> None:
        """每帧清账: 摘掉的敌人销账本, boss 槽联动(时间轴等退场用)。"""
        live = {id(e.machine) for e in self.enemies.alive()}
        for key in [k for k in self.extras if k not in live]:
            del self.extras[key]
        for key in [k for k in self.machine_enemy if k not in live]:
            del self.machine_enemy[key]
        for i, b in enumerate(self.bosses):
            if b is not None and id(b) not in live:
                self.bosses[i] = None

    def _copy_global_snapshot(self, m: EclMachine) -> None:
        """把宿主全局变量快照拷进当前上下文的 LOCAL_INT3/FLOAT3 槽。"""
        ctx = m.current
        for i in range(4):
            ctx.int_vars[_V_LOCAL_INT3_BASE + i] = self.global_ints[i]
            ctx.float_vars[_V_LOCAL_FLOAT3_BASE + i] = self.global_floats[i]

    # ---- 特殊变量透出(EclManager::GetVar/GetVarValue/GetFloatVar/GetFloatVarValue) ----

    def read_special_int(self, m: EclMachine, var_id: int) -> int:
        e = m.enemy
        if var_id == _V_DIFFICULTY:
            return self.difficulty
        if var_id == _V_RANK:
            return self.rank
        if var_id == _V_CUR_TIME:
            return e.timer
        if var_id == _V_LIFE:
            return e.life
        if var_id == _V_ITEMDROP:
            return self.enemy_of(m).item_drop
        if var_id == _V_SCORE:
            return self.enemy_of(m).score
        if var_id == _V_PLAYER_SHOTTYPE:
            return self.shottype
        if var_id == _V_BOSS_ID:
            return self.extras_of(m).boss_id
        if var_id == _V_LAST_DAMAGE:
            return self.extras_of(m).last_damage
        if var_id == _V_RNG:
            return m.rng.u32()
        if var_id == _V_RNG_CUSTOM_BOUND:
            return m.rng.int_below(m.current.int_vars.get(_V_LOCAL_INT3_BASE, 0)) + (
                m.current.int_vars.get(_V_LOCAL_INT3_BASE + 1, 0)
            )
        if _V_GLOBAL_INT_BASE <= var_id < _V_GLOBAL_INT_BASE + 4:
            return self.global_ints[var_id - _V_GLOBAL_INT_BASE]
        if _V_BOSS_LIFE_THRESHOLD_BASE <= var_id < _V_BOSS_LIFE_THRESHOLD_BASE + 4:
            return self.enemy_of(m).life_callback_threshold[
                var_id - _V_BOSS_LIFE_THRESHOLD_BASE
            ]
        if 10000 <= var_id <= 10073:
            return int(self.read_special_float(m, var_id))  # C: f32→i32 截断
        return var_id  # C default: 原样返回

    def write_special_int(self, m: EclMachine, var_id: int, value: int) -> None:
        if var_id == _V_DIFFICULTY:
            self.difficulty = value
        elif var_id == _V_RANK:
            self.rank = value
        elif var_id == _V_CUR_TIME:
            m.enemy.timer = value
        elif var_id == _V_LIFE:
            m.enemy.life = value
        elif var_id == _V_ITEMDROP:
            self.enemy_of(m).item_drop = value
        elif var_id == _V_SCORE:
            self.enemy_of(m).score = value
        elif _V_GLOBAL_INT_BASE <= var_id < _V_GLOBAL_INT_BASE + 4:
            self.global_ints[var_id - _V_GLOBAL_INT_BASE] = value
        # default: 丢弃(C 写进指令内存, 无意义)

    def read_special_float(self, m: EclMachine, var_id: int) -> float:
        e = m.enemy
        if var_id == _V_POS_X:
            return e.pos.x
        if var_id == _V_POS_Y:
            return e.pos.y
        if var_id == _V_POS_Z:
            return e.pos.z
        if var_id == _V_PLAYER_POS_X:
            return self.player_pos.x
        if var_id == _V_PLAYER_POS_Y:
            return self.player_pos.y
        if var_id == _V_PLAYER_POS_Z:
            return self.player_pos.z
        if var_id == _V_ANGLE_TO_PLAYER:
            return m.angle_to_player()
        if var_id == _V_DISTANCE_FROM_PLAYER:
            dx = self.player_pos.x - e.pos.x
            dy = self.player_pos.y - e.pos.y
            dz = self.player_pos.z - e.pos.z
            return math.sqrt(dx * dx + dy * dy + dz * dz)
        if var_id == _V_ANGLE:
            return e.angle
        if var_id == _V_ANGULAR_VELOCITY:
            return e.angular_velocity
        if var_id == _V_MOVE_SPEED:
            return e.move_speed
        if var_id == _V_MOVE_ACCELERATION:
            return e.move_acceleration
        if var_id == _V_MOVE_RADIUS:
            return e.move_radius
        if var_id == _V_MOVE_ANGLE:
            return e.move_angle
        if var_id == _V_MOVE_ANGULAR_VELOCITY:
            return e.move_angular_velocity
        if _V_MOVE_INTERP_ORIGIN_X <= var_id <= _V_MOVE_INTERP_ORIGIN_X + 2:
            i = var_id - _V_MOVE_INTERP_ORIGIN_X
            return (
                e.move_interp_start_pos.x,
                e.move_interp_start_pos.y,
                e.move_interp_start_pos.z,
            )[i]
        if _V_MOVE_INTERP_TARGET_X <= var_id <= _V_MOVE_INTERP_TARGET_X + 2:
            i = var_id - _V_MOVE_INTERP_TARGET_X
            return (e.move_interp.x, e.move_interp.y, e.move_interp.z)[i]
        if _V_DELTA_POS_X <= var_id <= _V_DELTA_POS_X + 2:
            i = var_id - _V_DELTA_POS_X
            return (e.delta_pos.x, e.delta_pos.y, e.delta_pos.z)[i]
        if var_id == _V_RNG:
            return m.rng.unit()
        if var_id == _V_RNG_CUSTOM_BOUND:
            return m.rng.unit() * m.current.float_vars.get(
                _V_LOCAL_FLOAT3_BASE, 0.0
            ) + (m.current.float_vars.get(_V_LOCAL_FLOAT3_BASE + 1, 0.0))
        if var_id == _V_RNG_RADIAN:
            return m.rng.unit() * math.tau - math.pi
        if _V_GLOBAL_FLOAT_BASE <= var_id < _V_GLOBAL_FLOAT_BASE + 4:
            return self.global_floats[var_id - _V_GLOBAL_FLOAT_BASE]
        if _V_BOSS_LIFE_THRESHOLD_BASE <= var_id < _V_BOSS_LIFE_THRESHOLD_BASE + 4:
            return float(
                self.enemy_of(m).life_callback_threshold[
                    var_id - _V_BOSS_LIFE_THRESHOLD_BASE
                ]
            )
        return float(self.read_special_int(m, var_id))  # int 变量按 (f32) 转换

    def write_special_float(self, m: EclMachine, var_id: int, value: float) -> None:
        e = m.enemy
        value = f32(value)
        if var_id == _V_POS_X:
            e.pos.x = value
        elif var_id == _V_POS_Y:
            e.pos.y = value
        elif var_id == _V_POS_Z:
            e.pos.z = value
        elif var_id == _V_PLAYER_POS_X:
            self.player_pos.x = value
        elif var_id == _V_PLAYER_POS_Y:
            self.player_pos.y = value
        elif var_id == _V_PLAYER_POS_Z:
            self.player_pos.z = value
        elif var_id == _V_ANGLE:
            e.angle = value
        elif var_id == _V_ANGULAR_VELOCITY:
            e.angular_velocity = value
        elif var_id == _V_MOVE_SPEED:
            e.move_speed = value
        elif var_id == _V_MOVE_ACCELERATION:
            e.move_acceleration = value
        elif var_id == _V_MOVE_RADIUS:
            e.move_radius = value
        elif var_id == _V_MOVE_ANGLE:
            e.move_angle = value
        elif var_id == _V_MOVE_ANGULAR_VELOCITY:
            e.move_angular_velocity = value
        elif _V_MOVE_INTERP_ORIGIN_X <= var_id <= _V_MOVE_INTERP_ORIGIN_X + 2:
            i = var_id - _V_MOVE_INTERP_ORIGIN_X
            p = e.move_interp_start_pos
            if i == 0:
                p.x = value
            elif i == 1:
                p.y = value
            else:
                p.z = value
        elif _V_MOVE_INTERP_TARGET_X <= var_id <= _V_MOVE_INTERP_TARGET_X + 2:
            i = var_id - _V_MOVE_INTERP_TARGET_X
            p = e.move_interp
            if i == 0:
                p.x = value
            elif i == 1:
                p.y = value
            else:
                p.z = value
        elif _V_GLOBAL_FLOAT_BASE <= var_id < _V_GLOBAL_FLOAT_BASE + 4:
            self.global_floats[var_id - _V_GLOBAL_FLOAT_BASE] = value
        # default: 丢弃

    # ---- 帧流程 ----

    def player_position(self, m: EclMachine) -> tuple[float, float, float]:
        return (self.player_pos.x, self.player_pos.y, self.player_pos.z)

    def on_sub_call(self, m: EclMachine) -> None:
        # SUB_CALL 进新 sub: 拷全局变量快照(旧 _op_sub_call 的 global_ints 拷贝)
        self._copy_global_snapshot(m)

    def on_auto_shoot(self, m: EclMachine) -> None:
        """自动射击到点: 用持久射手参数发射(th07 语义, 旧 _auto_shoot)。"""
        ex = self.extras_of(m)
        self._fire_shooter(m, ex, _add3(m.enemy.pos, ex.shoot_offset))

    def run_ex_instr(self, m: EclMachine, idx: int, instr: EclInstr | None) -> bool:
        return ex_ins.run_ex(self, m, idx, instr)

    # ---- 生敌(EnemyManager::SpawnEnemyEx) ----

    def spawn_enemy(self, spawn: EnemySpawn, m: EclMachine | None) -> Enemy | None:
        """生敌: 建机 → 入场前先跑一帧主循环, 失败不登记(C RunEcl 出错 → active=0)。"""
        machine = EclMachine(
            self.file,
            self,
            self.rng,
            int_var_ids=ECL_INT_VAR_IDS,
            float_var_ids=ECL_FLOAT_VAR_IDS,
            pos_var_ids=ECL_POS_VAR_IDS,
            ex_noop_idx=3,
            extra_handlers=ECL_EXTRA_HANDLERS,
        )
        st = machine.enemy
        st.mirror = spawn.mirror
        st.life = spawn.life if spawn.life >= 0 else 1  # enemyTemplate 默认 life=1
        st.pos = Vec3(spawn.x, spawn.y, spawn.z)
        st.prev_pos = st.pos.copy()
        if not machine.call_sub(spawn.sub_id):
            return None
        if m is not None:
            # 生敌指令: 拷调用方上下文变量(旧 args.clone())
            machine.current.int_vars = dict(m.current.int_vars)
            machine.current.float_vars = dict(m.current.float_vars)
        else:
            # 时间轴生敌: 全局变量快照
            self._copy_global_snapshot(machine)
        enemy = Enemy(machine=machine, enemy_id=self.enemies.next_id)
        self.enemies.next_id += 1
        # 先登记: 首帧 sub 可能即 SET_BOSS/配置指令
        self.extras[id(machine)] = EnemyExtras()
        self.machine_enemy[id(machine)] = enemy
        if not machine.rerun():
            del self.extras[id(machine)]
            del self.machine_enemy[id(machine)]
            self.enemies.next_id -= 1
            return None
        enemy.item_drop = spawn.item_drop
        if spawn.score >= 0:
            enemy.score = spawn.score
        st.max_life = st.life
        self.enemies.enemies.append(enemy)
        if self.ctx is not None:
            self.ctx.events.emit(
                EnemySpawned(enemy.enemy_id, st.pos.x, st.pos.y, spawn.sub_id)
            )
        return enemy

    def clear_enemies(self, m: EclMachine, instr: EclInstr) -> None:
        self.remove_all_enemies(8000, 0)

    def remove_all_enemies(self, score_max: int, score_min: int) -> int:
        """RemoveAllEnemies: 跳过 boss; isProjectile 掉弹消点并累计弹字分。

        # 出处 old/touhou/games/th07/ecl_host.py:336 (EnemyManager.cpp:1484-1490)
        """
        total = score_min
        popup = 2000
        for e in self.enemies.alive():
            if not e.active or e.is_boss:
                continue
            e.machine.enemy.life = 0
            if e.is_projectile:
                self.spawn_item_at(Vec2(e.pos2[0], e.pos2[1]), 6, attract=True)
                total += popup
                popup = min(popup + 30, score_max)
        return total

    # ---- 弹幕 ----

    def spawn_bullets(self, m: EclMachine, instr: EclInstr) -> None:
        e = m.enemy
        if e.life <= 0:
            return
        ex = self.extras_of(m)
        p = ex.shooter
        if isinstance(instr, SpawnPrevBulletPattern):
            self._fire_shooter(m, ex, _add3(e.pos, ex.shoot_offset))
            return
        assert isinstance(instr, SpawnBulletPattern)
        p.sprite = m.ival(instr.sprite)
        p.aim_mode = instr.aim_mode
        p.count1 = m.ival(instr.count1)
        p.count2 = m.ival(instr.count2)
        p.speed1 = m.fval(instr.speed1)
        p.speed2 = m.fval(instr.speed2)
        p.angle1 = m.fval(instr.angle1)
        p.angle2 = m.fval(instr.angle2)
        p.flags = instr.flags
        p.sprite_offset = m.ival(instr.sprite_offset)
        if not self.spellcard_active:
            # rank 缩放(符卡中不做, EclManager.cpp 弹幕系 case)
            p.count1 = _i16(p.count1 + ex.bullet_rank_amount1(self.rank))
            if p.count1 <= 0:
                p.count1 = 1
            p.count2 = _i16(p.count2 + ex.bullet_rank_amount2(self.rank))
            if p.count2 <= 0:
                p.count2 = 1
            if p.speed1 != 0.0:
                p.speed1 = f32(p.speed1 + ex.bullet_rank_speed(float(self.rank)))
                if p.speed1 < 0.3:
                    p.speed1 = 0.3
            p.speed2 = f32(p.speed2 + ex.bullet_rank_speed(float(self.rank)) / 2.0)
            if p.speed2 < 0.3:
                p.speed2 = 0.3
        if not ex.disable_bullets:
            self._fire_shooter(m, ex, _add3(e.pos, ex.shoot_offset))

    def _fire_shooter(self, m: EclMachine, ex: EnemyExtras, pos: Vec3) -> None:
        """按持久射手参数发一波(BulletManager::SpawnBulletPattern)。"""
        self._fire_props(ex.shooter, pos)

    def fire_temp_shooter_at(
        self, m: EclMachine, props: BulletShooter, pos: Vec3
    ) -> None:
        """按临时射手参数发一波(ex 指令用, 不动持久射手)。"""
        self._fire_props(props, pos)

    def _fire_props(self, p: BulletShooter, pos: Vec3) -> None:
        """展开一份射手参数进 BulletField(BulletManager::SpawnBulletPattern)。"""
        if p.count1 <= 0 or p.count2 <= 0:
            return
        if len(self.bullets) >= _MAX_BULLETS:
            return
        if self.ctx is None:
            return
        at = Vec2(pos.x, pos.y)
        try:
            aim = Aim(p.aim_mode)
        except ValueError:
            aim = Aim.RING_ABSOLUTE
        base = p.angle1
        if aim in _AIMED_MODES:
            base += angle_to(at, self.bullets.player_pos)
        self.bullets.fire(
            Burst(
                at,
                base,
                aim,
                p.count1,
                p.count2,
                p.speed1,
                p.speed2,
                p.angle2,
                sprite=p.sprite,
                sprite_offset=p.sprite_offset,
                commands=p.cooked_commands(),
                flags=p.flags,
            ),
            self.ctx,
        )
        if p.flags & 0x200:
            self._play_sound(p.sound_idx)  # 发弹音(BulletManager.cpp:611-615)

    def bullet_setup(self, m: EclMachine, instr: EclInstr) -> None:
        e = m.enemy
        ex = self.extras_of(m)
        if isinstance(instr, InitBulletCmd):
            cmd = ex.shooter.commands[m.ival(instr.slot)]
            cmd.type = m.ival(instr.type)
            cmd.flag = m.ival(instr.flag)
            cmd.duration = m.ival(instr.duration)
            cmd.loop_count = m.ival(instr.loop_count)
            cmd.speed = m.fval(instr.speed)
            cmd.angle = m.fval(instr.angle)
        elif isinstance(instr, (SetShootInterval, SetShootIntervalRand)):
            e.shoot_interval = m.ival(instr.interval)
            if e.shoot_interval != 0:
                # Enemy::ShootInterval: low=interval/5, high=-interval/5 的 rank 插值
                low = cdiv(e.shoot_interval, 5)
                e.shoot_interval = i32(
                    e.shoot_interval + cdiv(self.rank * (-low - low), 32) + low
                )
                if isinstance(instr, SetShootIntervalRand):
                    e.shoot_interval_timer = m.rng.int_below(e.shoot_interval)
                else:
                    e.shoot_interval_timer = 0
        elif isinstance(instr, DisableBullets):
            ex.disable_bullets = 1
        elif isinstance(instr, EnableBullets):
            ex.disable_bullets = 0
        elif isinstance(instr, SetBulletSound):
            idx = m.ival(instr.sound_idx)
            if idx >= 0:
                ex.shooter.sound_idx = idx
                ex.shooter.flags |= 0x200
            else:
                ex.shooter.flags &= 0xFFFFFDFF
            ex.shooter.sound_override = m.ival(instr.sound_override)
        elif isinstance(instr, SetBulletRankParams):
            ex.bullet_rank_speed_low = m.fval(instr.speed_low)
            ex.bullet_rank_speed_high = m.fval(instr.speed_high)
            ex.bullet_rank_amount1_low = m.ival(instr.amount1_low)
            ex.bullet_rank_amount1_high = m.ival(instr.amount1_high)
            ex.bullet_rank_amount2_low = m.ival(instr.amount2_low)
            ex.bullet_rank_amount2_high = m.ival(instr.amount2_high)
        elif isinstance(instr, SetShootOffset):
            ex.shoot_offset.set(m.fval(instr.x), m.fval(instr.y), m.fval(instr.z))
        # DeferBulletPattern 系是 v800 专属, th07 数据不出现

    # ---- 清弹(弹转弹消点, 出生即吸附) ----

    def spawn_item_at(self, pos: Vec2, kind: int, *, attract: bool = False) -> None:
        """统一的道具生成口(满火力 P 转樱在 world 的 spawn hook 里做, 见 items.py)。"""
        self.items.spawn(pos, kind, state=1 if attract else 0)

    def remove_all_bullets(self, spawn_items: bool) -> None:
        """RemoveAllBullets: 弹转弹消点(可选) + 连带激光 + screenClearTime=10。"""
        # 出处 old/touhou/games/th07/ecl_host.py:381 (BulletManager.cpp:423-480)
        for b in self.bullets.alive():
            if spawn_items:
                self.spawn_item_at(b.pos, 6, attract=True)
            b.dead = True
        points = self.lasers.remove_all(skip_flag4=True, spawn_items=spawn_items)
        if spawn_items:
            for pt in points:
                self.spawn_item_at(pt, 6, attract=True)
        self.bullets.screen_clear_time = 10

    def remove_bullets_in_radius(self, pos: Vec3, radius: float) -> None:
        """RemoveBulletsInRadius: 半径内弹转弹消点(BulletManager.cpp:581)。"""
        r2 = radius * radius
        for b in self.bullets.alive():
            dx = b.pos.x - pos.x
            dy = b.pos.y - pos.y
            if dx * dx + dy * dy <= r2:
                self.spawn_item_at(b.pos, 6, attract=True)
                b.dead = True

    def clear_bullets(self, m: EclMachine, instr: EclInstr) -> None:
        if isinstance(instr, RemoveAllBullets):
            self.remove_all_bullets(bool(instr.mode))
        elif isinstance(instr, RemoveBulletsRadius):
            self.remove_bullets_in_radius(m.enemy.pos, m.fval(instr.radius))
        # ClearBulletsForTransition 是 v800 专属

    # ---- 激光 ----

    def spawn_laser(self, m: EclMachine, instr: EclInstr) -> None:
        assert isinstance(instr, SpawnLaserPattern)
        ex = self.extras_of(m)
        e = m.enemy
        if len(self.lasers.lasers) >= _MAX_LASERS:
            ex.lasers[ex.laser_idx & 31] = None
            return
        # screenClearTime 窗口内不带 flag 4 的激光不生成(C 返回假句柄)
        if self.bullets.screen_clear_time != 0 and not (instr.flags & 4):
            ex.lasers[ex.laser_idx & 31] = None
            return
        pos = _add3(e.pos, ex.shoot_offset)
        at = Vec2(pos.x, pos.y)
        angle = m.fval(instr.angle)
        if not instr.moving:  # C: type 0 (FIXED opcode) 出生即瞄玩家
            angle = angle_to(at, self.bullets.player_pos) + angle
        laser = Laser(
            pos=at,
            angle=angle,
            width=instr.width,
            speed=m.fval(instr.speed),
            start_time=instr.start_time,
            hitbox_start_time=instr.hitbox_start_time,
            duration=instr.duration,
            end_time=instr.end_time,
            hitbox_end_time=instr.hitbox_end_time,
            start_length=m.fval(instr.start_length),
            flags=instr.flags,
            color=m.ival(instr.sprite_offset),
        )
        laser.offset_a = m.fval(instr.start_offset)
        laser.offset_b = m.fval(instr.end_offset)
        self.lasers.lasers.append(laser)
        ex.lasers[ex.laser_idx & 31] = laser

    def laser_control(self, m: EclMachine, instr: EclInstr) -> None:
        ex = self.extras_of(m)
        e = m.enemy
        if isinstance(instr, SetLaserIdx):
            ex.laser_idx = m.ival(instr.idx)
            return
        if isinstance(instr, ClearLasers):
            ex.lasers = [None] * 32
            return
        idx = m.ival(getattr(instr, "idx", ImmInt(0))) & 31
        h = ex.lasers[idx]
        if isinstance(instr, TestLaserNotInUse):
            # 结果写上下文标记? v0: ctx.laser_not_in_use —— 见 get_boss 系外的
            # 条件跳转读法; th07 用变量读, 这里按旧实现写回 extras 供条件跳查询
            ex.laser_not_in_use = 0 if (h is not None and h.in_use) else 1
            return
        if h is None:
            return
        if isinstance(instr, AddLaserAngle):
            h.angle += m.fval(instr.delta)
        elif isinstance(instr, SetLaserAngle):
            h.angle = m.fval(instr.angle)
        elif isinstance(instr, AimLaserAtPlayer):
            h.angle = angle_to(h.pos, self.bullets.player_pos) + m.fval(
                instr.aim_offset
            )
        elif isinstance(instr, SetLaserPosRel):
            h.pos = Vec2(
                m.fval(instr.x) + e.pos.x,
                m.fval(instr.y) + e.pos.y,
            )
        elif isinstance(instr, StopLaser):
            h.state = LaserState.DESPAWNING
            h.timer = 0
        elif isinstance(instr, SetLaserHideWarning):
            h.hide_warning = bool(m.ival(instr.value))
        elif isinstance(instr, SetLaserStartLen):
            h.start_length = m.fval(instr.value)
        elif isinstance(instr, SetLaserOffsets):
            h.offset_a = m.fval(instr.start)
            h.offset_b = m.fval(instr.end)

    # ---- 敌人配置 ----

    def enemy_config(self, m: EclMachine, instr: EclInstr) -> None:
        e = self.machine_enemy.get(id(m))
        if e is None:
            return
        ex = self.extras_of(m)
        st = m.enemy
        if isinstance(instr, SetAnm):
            e.anm_idx = m.ival(instr.anm_idx)
        elif isinstance(instr, SetHitboxSize):
            e.hitbox_size.set(m.fval(instr.x), m.fval(instr.y), m.fval(instr.z))
        elif isinstance(instr, SetGrazeSize):
            e.graze_size.set(m.fval(instr.x), m.fval(instr.y), m.fval(instr.z))
        elif isinstance(instr, SetHasContactHitbox):
            e.has_contact_hitbox = instr.value
        elif isinstance(instr, SetCanBeDamaged):
            e.can_be_damaged = instr.value
        elif isinstance(instr, SetIsHittable):
            e.is_hittable = instr.value
        elif isinstance(instr, SetEnemyCanDie):
            e.can_die = instr.value
        elif isinstance(instr, SetHasNoCollision):
            e.has_no_collision = instr.value
        elif isinstance(instr, SetIsProjectile):
            e.is_projectile = instr.value
        elif isinstance(instr, SetIsSurvivalSpellcard):
            ex.is_survival_spellcard = instr.value
        elif isinstance(instr, SetDespawnOnOob):
            ex.disable_oob_despawn = instr.value
        elif isinstance(instr, SetDeathType):
            e.death_type = instr.value
        elif isinstance(instr, SetDeathCallbackSub):
            e.death_callback_sub = instr.sub_id
        elif isinstance(instr, SetLifeCallbackThreshold):
            e.life_callback_threshold[0] = m.ival(instr.value)
        elif isinstance(instr, SetLifeCallbackSub):
            e.life_callback_sub[0] = m.ival(instr.sub_id)
        elif isinstance(instr, SetLifeCallback):
            idx = m.ival(instr.idx) & 3
            e.life_callback_threshold[idx] = m.ival(instr.threshold)
            e.life_callback_sub[idx] = m.ival(instr.sub_id)
        elif isinstance(instr, SetTimerCallbackThreshold):
            e.timer_callback_threshold = m.ival(instr.value)
            st.timer = 0
        elif isinstance(instr, SetTimerCallbackSub):
            e.timer_callback_sub = m.ival(instr.sub_id)
        elif isinstance(instr, BindTimerCallbackToDeath):
            e.timer_callback_sub = e.death_callback_sub
            st.timer = 0
        elif isinstance(instr, SetTrail):
            e.trail = [
                instr.flags,
                m.ival(instr.count),
                m.ival(instr.interval),
                m.ival(instr.node_step),
                0,
            ]
        elif isinstance(instr, SetSubAnm):
            idx = m.ival(instr.idx)
            if 0 <= idx < len(ex.sub_anm_idx):
                ex.sub_anm_idx[idx] = m.ival(instr.anm_idx)
        elif isinstance(instr, SetMoveAnm):
            ex.move_anm = tuple(instr.scripts)
        elif isinstance(instr, SetDeathAnm):
            ex.death_anm = (instr.a, instr.b, instr.c)
        elif isinstance(instr, SetVmAutoRotate):
            ex.primary_vm_auto_rotate = instr.value
        # 其余(SetVmInterrupt/SetPrimaryVmInterrupt/SetDrawGroup/特效/粒子等):
        # 渲染侧语义, 逻辑层不接

    # ---- 道具掉落 ----

    def _jitter_pos(self, m: EclMachine) -> Vec3:
        e = m.enemy
        return Vec3(
            e.pos.x + m.rng.unit() * 128.0 - 64.0,
            e.pos.y + m.rng.unit() * 128.0 - 64.0,
            e.pos.z,
        )

    def spawn_items(self, m: EclMachine, instr: EclInstr) -> None:
        if isinstance(instr, SpawnItem):
            self.spawn_item_at(
                Vec2(m.enemy.pos.x, m.enemy.pos.y), m.ival(instr.item_type)
            )
        elif isinstance(instr, SpawnItems):
            # 火力未满第一个掉大P其余小P, 满火力全掉点(旧 _spawn_items)
            for i in range(m.ival(instr.count)):
                pos = self._jitter_pos(m)
                if self.power < 128:
                    self.spawn_item_at(Vec2(pos.x, pos.y), 2 if i == 0 else 0)
                else:
                    self.spawn_item_at(Vec2(pos.x, pos.y), 1)
        elif isinstance(instr, SpawnPointItems):
            for _ in range(m.ival(instr.count)):
                pos = self._jitter_pos(m)
                self.spawn_item_at(Vec2(pos.x, pos.y), 1)

    # ---- 音效 ----

    def _play_sound(self, idx: int) -> None:
        if self.on_sound is not None:
            self.on_sound(idx)

    def play_sound(self, m: EclMachine, sound_id: int) -> None:
        self._play_sound(sound_id)

    # ---- boss/符卡/作品机制 ----

    def boss_control(self, m: EclMachine, instr: EclInstr) -> None:
        e = self.machine_enemy.get(id(m))
        ex = self.extras_of(m)
        if isinstance(instr, SetBoss):
            idx = m.ival(instr.idx)
            if idx >= 0:
                if e is not None:
                    e.is_boss = 1
                ex.boss_id = idx
                self.bosses[idx & 7] = m
                if self.on_set_boss is not None:
                    self.on_set_boss(idx, m)
            else:
                if 0 <= ex.boss_id < 8:
                    self.bosses[ex.boss_id] = None
                    if self.on_set_boss is not None:
                        self.on_set_boss(ex.boss_id, None)
                if e is not None:
                    e.is_boss = 0
                ex.boss_id = -1
        elif isinstance(instr, BeginSpellcard):
            # 宣告瞬间全屏弹转弹消点(EclManager.cpp:673, 在 isActive=1 之前)
            self.remove_all_bullets(True)
            # C 侧顺带重置 boss rank 参数
            ex.bullet_rank_speed_low = -0.5
            ex.bullet_rank_speed_high = 0.5
            ex.bullet_rank_amount1_low = ex.bullet_rank_amount1_high = 0
            ex.bullet_rank_amount2_low = ex.bullet_rank_amount2_high = 0
            self.spellcard_active = True
            if self.on_begin_spellcard is not None:
                self.on_begin_spellcard(
                    m, instr.gui_id, instr.spellcard_idx, instr.name
                )
        elif isinstance(instr, EndSpellcard):
            self.spellcard_active = False
            if self.on_end_spellcard is not None:
                self.on_end_spellcard(m)
        elif isinstance(instr, SetBossHealth):
            self.boss_health = (
                m.ival(instr.idx),
                m.ival(instr.current),
                m.ival(instr.max),
                m.ival(instr.color),
            )
        elif isinstance(instr, SetNumBossLifeMarkers):
            self.boss_life_markers = m.ival(instr.count)
        elif isinstance(instr, FreezeEclDuringBomb):
            if e is not None:
                e.freeze_ecl_during_bombs = m.ival(instr.value)
        elif isinstance(instr, AddCherryPlus):
            if self.on_add_cherry_plus is not None:
                self.on_add_cherry_plus(m.ival(instr.value))
        elif isinstance(instr, SetScriptWaitTime):
            # g_Stage.scriptWaitTime = value (EclManager.cpp:1821-1823)
            if self.on_script_wait is not None:
                self.on_script_wait(m.ival(instr.frames))

    def get_boss_int(self, m: EclMachine, instr: EclInstr) -> int | None:
        assert isinstance(instr, GetBossInt)
        boss = self.bosses[m.ival(instr.boss_idx) & 7]
        if boss is None:
            return None
        return boss.ival(instr.var)  # 以 boss 机器为上下文读(EclManager.cpp:998-1002)

    def get_boss_float(self, m: EclMachine, instr: EclInstr) -> float | None:
        assert isinstance(instr, GetBossFloat)
        boss = self.bosses[m.ival(instr.boss_idx) & 7]
        if boss is None:
            return None
        return boss.fval(instr.var)

    # ---- 时间轴 ----

    def boss_present(self) -> bool:
        return any(b is not None for b in self.bosses)

    def boss_active(self, idx: int) -> bool:
        b = self.bosses[idx & 7]
        return b is not None and not b.finished

    def set_boss_interrupt(self, boss_idx: int, interrupt: int) -> None:
        boss = self.bosses[boss_idx & 7]
        if boss is not None:
            boss.enemy.run_interrupt = interrupt

    def msg_read(self, msg_id: int) -> None:
        """时间轴 op8 (EnemyManager.cpp:332): MsgRead(arg0 + character*10)。

        C MsgRead 同时清场: RemoveAllBullets(1) → 弹转弹消点、
        RemoveAllEnemies(0,0)(跳过 boss)、RemoveAllItems()。
        """
        # 出处 old/touhou/games/th07/ecl_host.py:454
        self.last_msg_id = msg_id
        vm = self.msg_vm
        if vm is None:
            return
        vm.read(msg_id + self.msg_character * 10)
        if vm.has_current_msg_idx():
            self.remove_all_bullets(True)  # 弹转道具…
            self.remove_all_enemies(0, 0)  # …随即被下一行清掉(同 C 顺序)
            self.items.remove_all_items()

    def msg_wait(self) -> bool:
        """时间轴 op9: 消息未读完则停轴 (Gui::MsgWait, 含 APPEAR_ENEMY 放行窗)。"""
        if self.msg_vm is None:
            return False
        return self.msg_vm.msg_wait()

    def load_stage(self, ecl_file: EclFile) -> None:
        """换关装新 ECL(EclManager.Load): 换脚本 + 清账本(field 引用不动)。"""
        self.file = ecl_file
        self.extras.clear()
        self.machine_enemy.clear()
        self.bosses = [None] * 8
        self.global_ints = [0] * 4
        self.global_floats = [0.0] * 4
        self.boss_health = (0, 0, 0, 0)
        self.boss_life_markers = 0
        self.last_msg_id = -1

    def set_power(self, value: int) -> None:
        if self.on_set_power is not None:
            self.on_set_power(value)
