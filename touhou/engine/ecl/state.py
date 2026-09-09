"""ECL 执行器的状态结构: 向量/上下文/脚本实例状态/生敌描述。"""

from __future__ import annotations

import msgspec

from ...schemas.ecl import EclInstr

#: 游戏可视区(g_GameManager.playerMovementAreaSize), 随机坐标/边界逃角用
PLAYFIELD_W = 384.0
PLAYFIELD_H = 448.0


class Vec3(msgspec.Struct):
    """可变三维向量(C Float3), 屏幕系 y 向下。"""

    x: float = 0.0
    y: float = 0.0
    z: float = 0.0

    def set(self, x: float, y: float, z: float) -> None:
        """三分量一起设。"""
        self.x, self.y, self.z = x, y, z

    def copy(self) -> Vec3:
        """值拷贝。"""
        return Vec3(self.x, self.y, self.z)


class VarInterp(msgspec.Struct):
    """一路跨帧变量插值(C EclInterp): INIT_INTERP 注册, 帧尾推进。"""

    # 语义出处 EclManager.cpp:811-880 (EclInterp 推进/清除)
    active: bool = False
    timer: int = 0
    duration: int = 0
    func_idx: int = 0  # 0..6 = lerp, 7 = cubic hermite
    easing: int = 0
    params: list[float] = msgspec.field(default_factory=lambda: [0.0] * 4)
    target_var: int = 0

    def clear(self) -> None:
        """到顶后停用时复位。"""
        self.active = False
        self.timer = 0

    def clone(self) -> VarInterp:
        """值拷贝(调用栈保存用)。"""
        return VarInterp(
            self.active,
            self.timer,
            self.duration,
            self.func_idx,
            self.easing,
            list(self.params),
            self.target_var,
        )


class EclContext(msgspec.Struct):
    """一层 sub 调用的执行现场(C EnemyEclContext): pc/时刻/局部变量/插值槽。"""

    # 局部变量槽按 var_id 字典存(槽位布局是作品数据, 由组合根注入 id 集合,
    # 见 EclMachine 构造参数); C 的 eclContextArgs 出处 EclManager.hpp:197-213
    sub_id: int = -1
    pc: int = 0  # sub 内指令下标
    time: int = 0
    wait_timer: int = 0
    int_vars: dict[int, int] = msgspec.field(default_factory=dict)
    float_vars: dict[int, float] = msgspec.field(default_factory=dict)
    interps: list[VarInterp] = msgspec.field(
        default_factory=lambda: [VarInterp() for _ in range(8)]
    )
    ex_instr_idx: int = -1  # SET_EX_INS 登记的每帧宿主回调(-1 = 无)
    ex_instr: EclInstr | None = None
    is_periodic_sub: int = 0

    def clone(self) -> EclContext:
        """值拷贝(压栈保存)。"""
        return EclContext(
            self.sub_id,
            self.pc,
            self.time,
            self.wait_timer,
            dict(self.int_vars),
            dict(self.float_vars),
            [i.clone() for i in self.interps],
            self.ex_instr_idx,
            self.ex_instr,
            self.is_periodic_sub,
        )


class EclEnemyState(msgspec.Struct):
    """一台 EclMachine 驱动的脚本实例状态(C Enemy 中被通用指令触碰的字段)。

    只有移动/生命周期/调用机制字段; 弹幕/激光/anm/符卡等作品语义状态全在宿主侧。
    """

    # 字段集出处 EclManager.hpp Enemy 结构 + Enemy::UpdateMovement/ClampPos
    # (EclManager.cpp:2288-2400 一带)
    pos: Vec3 = msgspec.field(default_factory=Vec3)
    axis_speed: Vec3 = msgspec.field(default_factory=Vec3)
    prev_pos: Vec3 = msgspec.field(default_factory=Vec3)
    delta_pos: Vec3 = msgspec.field(default_factory=Vec3)
    move_interp: Vec3 = msgspec.field(default_factory=Vec3)
    move_interp_start_pos: Vec3 = msgspec.field(default_factory=Vec3)
    lower_move_limit: Vec3 = msgspec.field(default_factory=Vec3)
    upper_move_limit: Vec3 = msgspec.field(default_factory=Vec3)
    angle: float = 0.0
    angular_velocity: float = 0.0
    move_angle: float = 0.0
    move_angular_velocity: float = 0.0
    move_speed: float = 0.0
    move_acceleration: float = 0.0
    move_radius: float = 0.0
    move_radial_velocity: float = 0.0
    move_interp_timer: int = 0
    move_interp_start_time: int = 0
    move_mode: int = 0  # 0 轴向 / 1 极角 / 2 位移插值 / 3 轨道
    interp_easing: int = 0
    mirror: int = 0  # 镜像 X(宿主在 spawn 时按描述符置位)
    disable_movement: int = 0
    has_movement_bounds: int = 0
    life: int = 0
    max_life: int = 0
    timer: int = 0  # 每帧 +1(C enemy->timer)
    invincibility_timer: int = 0
    no_stack_ret: int = 0
    interrupts: list[int] = msgspec.field(default_factory=lambda: [0] * 32)
    run_interrupt: int = -1
    periodic_timer: int = 0
    periodic_callback_sub: int = -1
    periodic_counter: int = 0
    saved_int_vars: dict[int, int] = msgspec.field(default_factory=dict)
    saved_float_vars: dict[int, float] = msgspec.field(default_factory=dict)
    shoot_interval: int = 0
    shoot_interval_timer: int = 0
    min_player_dist_sq: float = 0.0  # v800 SET_MIN_PLAYER_DISTANCE, 宿主压弹用

    def clamp_pos(self) -> None:
        """移动范围内夹位置(Enemy::ClampPos)。"""
        if self.has_movement_bounds:
            p = self.pos
            if p.x < self.lower_move_limit.x:
                p.x = self.lower_move_limit.x
            elif p.x > self.upper_move_limit.x:
                p.x = self.upper_move_limit.x
            if p.y < self.lower_move_limit.y:
                p.y = self.lower_move_limit.y
            elif p.y > self.upper_move_limit.y:
                p.y = self.upper_move_limit.y


class EnemySpawn(msgspec.Struct, frozen=True):
    """生敌请求描述(时间轴/生敌指令 → 宿主; engine 不持有敌人概念)。"""

    # 字段对齐 C SpawnEnemyEx 参数面(EnemyManager.hpp:340-360 一带);
    # drops 两槽是 v800 带掉落数生敌的扩展(EnemyTimeline.cpp:165-185), 不用时 0
    sub_id: int
    x: float
    y: float
    z: float = 0.0
    life: int = -1
    item_drop: int = -1
    score: int = -1
    mirror: int = 0
    point_drops: int = 0
    power_or_point_drops: int = 0
