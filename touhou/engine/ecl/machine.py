"""EclMachine: 单脚本实例的 ECL 虚拟机(C EclManager::RunEcl + Enemy 帧收尾)。

消费 schemas.ecl 的 EclFile/指令 union; handler 按 {指令类: handler} 查表
分派(见 handlers/)。作品专属语义全经 EclHost 注入, 本机只有框架: 主循环/
调用栈/变量槽/移动积分/变量插值/ex 指令分发。

每帧一次 step() = C 的 RunEcl(执行到点指令) + Enemy 帧收尾(移动模式积分
→ 射击/ex/插值 → 位置积分 → timer++); step() 返回 False = 脚本结束, 宿主
应 despawn 该实例。主循环逐句移植 old/touhou/engine/ecl_base.py
(EclMachineBase._run_ecl/_frame_update/_update_movement), 行为语义出处
Reference/th07/src/th07/EclManager.cpp。
"""

from __future__ import annotations

import math

from ...schemas.ecl import (
    EclFile,
    EclInstr,
    FloatOperand,
    ImmFloat,
    ImmInt,
    IntOperand,
    VarRef,
)
from ...utils.logger import LoggerManager
from ..rng import Rng
from .handlers import HANDLERS, Handler, Step
from .host import EclHost
from .num import add_norm_angle, ease, f32, i32
from .state import EclContext, EclEnemyState, Vec3

log = LoggerManager.get_logger("ENGINE")

_MAX_STACK = 15  # C: stackDepth < 15 才压栈(savedContextStack[16])


class EclMachine:
    """一台 ECL VM: 当前上下文 + 调用栈, 逐帧 step 驱动。"""

    # 变量表是作品数据: int/float 局部槽 id 集合由组合根注入, 集合外的
    # 变量 id 走宿主透出(read_special_*/write_special_*); pos_var_ids 是
    # 位置分量变量 id(插值命中时回算 axis_speed, EclManager.cpp:860-880)
    def __init__(
        self,
        ecl_file: EclFile,
        host: EclHost,
        rng: Rng,
        *,
        int_var_ids: frozenset[int] = frozenset(),
        float_var_ids: frozenset[int] = frozenset(),
        pos_var_ids: frozenset[int] = frozenset(),
        ex_noop_idx: int = 3,
        extra_handlers: dict[type[EclInstr], Handler] | None = None,
    ) -> None:
        self.file = ecl_file
        self.host = host
        self.rng = rng
        self.enemy = EclEnemyState()
        self.int_var_ids = int_var_ids
        self.float_var_ids = float_var_ids
        self.pos_var_ids = pos_var_ids
        self.ex_noop_idx = ex_noop_idx
        # 共享指令的 handler 表 + 作品专属指令的注入绑定(games 侧组装)
        self.handlers: dict[type[EclInstr], Handler] = (
            HANDLERS if extra_handlers is None else {**HANDLERS, **extra_handlers}
        )
        self.framerate_multiplier = 1.0  # g_Supervisor.effectiveFramerateMultiplier
        self.current = EclContext()
        self.stack: list[EclContext] = []
        self.finished = False
        self._offset_maps = [
            {ins.offset: i for i, ins in enumerate(sub.instrs)} for sub in ecl_file.subs
        ]
        self._warned_ex: set[int] = set()

    # ---- 入口/调用栈 ----

    def call_sub(self, sub_id: int) -> bool:
        """把当前上下文切到 sub_id 的首条指令(CallEclSub); sub 越界返回 False。"""
        if not 0 <= sub_id < len(self.file.subs):
            log.error("ECL 调了不存在的 sub: {}", sub_id)
            return False
        ctx = self.current
        ctx.sub_id = sub_id
        ctx.pc = 0
        ctx.time = 0
        ctx.wait_timer = 0
        return True

    def start(self, sub_id: int) -> None:
        """入口: 进 sub; sub 非法则直接结束。"""
        if not self.call_sub(sub_id):
            self.finished = True

    def push_context(self) -> None:
        """压栈保存当前上下文(封顶 _MAX_STACK, 超深丢最老一层)。"""
        self.stack.append(self.current.clone())
        if len(self.stack) > _MAX_STACK:
            self.stack.pop(0)

    # ---- 变量系统(GetVar/GetVarValue/GetFloatVar/GetFloatVarValue) ----
    # 操作数即数据: ImmInt/ImmFloat = 立即数, VarRef = 变量 id
    # (EclManager.hpp:362-397); 局部槽 id 命中本机槽位, 其余透出宿主

    def read_int(self, var_id: int) -> int:
        """按 id 读 int 变量。"""
        if var_id in self.int_var_ids:
            return self.current.int_vars.get(var_id, 0)
        if var_id in self.float_var_ids:
            return int(self.current.float_vars.get(var_id, 0.0))
        return self.host.read_special_int(self, var_id)

    def write_int(self, var_id: int, value: int) -> None:
        """按 id 写 int 变量; float 槽/不可写 id 丢弃(C 写进指令内存)。"""
        if var_id in self.int_var_ids:
            self.current.int_vars[var_id] = i32(value)
        elif var_id not in self.float_var_ids:
            self.host.write_special_int(self, var_id, i32(value))

    def read_float(self, var_id: int) -> float:
        """按 id 读 float 变量(int 槽按 (f32) 转换)。"""
        if var_id in self.float_var_ids:
            return self.current.float_vars.get(var_id, 0.0)
        if var_id in self.int_var_ids:
            return float(self.current.int_vars.get(var_id, 0))
        return self.host.read_special_float(self, var_id)

    def write_float(self, var_id: int, value: float) -> None:
        """按 id 写 float 变量(存 f32 精度); int 槽/不可写 id 丢弃。"""
        if var_id in self.float_var_ids:
            self.current.float_vars[var_id] = f32(value)
        elif var_id not in self.int_var_ids:
            self.host.write_special_float(self, var_id, f32(value))

    def ival(self, op: IntOperand) -> int:
        """解析 int 操作数(立即数或变量读)。"""
        if isinstance(op, ImmInt):
            return op.value
        return self.read_int(op.var_id)

    def fval(self, op: FloatOperand) -> float:
        """解析 float 操作数(立即数或变量读)。"""
        if isinstance(op, ImmFloat):
            return op.value
        return self.read_float(op.var_id)

    def store_int(self, dest: VarRef | None, value: int) -> None:
        """写 int 存储目标(None = 写入丢弃)。"""
        if dest is not None:
            self.write_int(dest.var_id, value)

    def store_float(self, dest: VarRef | None, value: float) -> None:
        """写 float 存储目标(None = 写入丢弃)。"""
        if dest is not None:
            self.write_float(dest.var_id, value)

    # ---- 跳转 ----

    def jump(self, instr: EclInstr, dest: int, set_time: int) -> Step:
        """跳转到 相对 instr 的字节偏移 dest 并重置上下文时刻; 目标非法则结束。"""
        ctx = self.current
        ctx.time = i32(set_time)
        pc = self._offset_maps[ctx.sub_id].get(instr.offset + dest, -1)
        if pc < 0:
            log.error("ECL 跳转目标非法: offset={:#x}", instr.offset + dest)
            return Step.HALT
        ctx.pc = pc
        return Step.JUMPED

    def angle_to_player(self) -> float:
        """自机相对本机的朝向(Player::AngleToPlayer)。"""
        px, py, _ = self.host.player_position(self)
        x = px - self.enemy.pos.x
        y = py - self.enemy.pos.y
        if x == 0.0 and y == 0.0:
            return 1.5707964
        return math.atan2(y, x)

    def exit_angle(self, *, simple: bool = False) -> float:
        """朝屏幕外逃的随机角(带移动边界反弹修正; simple = 只看自机侧/右边缘)。"""
        # EclManager.cpp:1593-1632(GET_EXIT_ANGLE/RAND_EXIT_ANGLE) /
        # EclDependencies.cpp:126-168(BeginBoundaryAwareMove 选角)
        e = self.enemy
        px, _, _ = self.host.player_position(self)
        if simple:
            if (px < e.pos.x and e.pos.x > 96.0) or e.pos.x > 288.0:
                return add_norm_angle(self.rng.unit() * 1.5707964 + 2.3561945, 0.0)
            return f32(self.rng.unit() * 1.5707964 - 0.7853982)
        if px < e.pos.x:
            angle = add_norm_angle(self.rng.unit() * 1.5707964 + 2.3561945, 0.0)
        else:
            angle = f32(self.rng.unit() * 1.5707964 - 0.7853982)
        if e.pos.x < e.lower_move_limit.x + 96.0:
            if angle > 1.5707964:
                angle = f32(3.1415927 - angle)
            elif angle < -1.5707964:
                angle = f32(-3.1415927 - angle)
        if e.upper_move_limit.x - 96.0 < e.pos.x:
            # 原版 bug 照抄: 右边缘修正用朝向而非刚算的 angle;
            # v0 用 enemy->angle, v800 用 movementAngle
            bug = e.move_angle if self.file.version != 0 else e.angle
            if 0.0 <= angle < 1.5707964:
                angle = f32(3.1415927 - bug)
            elif -1.5707964 < angle <= 0.0:
                angle = f32(-3.1415927 - angle)
        if e.lower_move_limit.y + 48.0 > e.pos.y and angle < 0.0:
            angle = -angle
        if e.upper_move_limit.y - 48.0 < e.pos.y and angle > 0.0:
            angle = -angle
        return angle

    # ---- 主循环 ----

    def step(self) -> bool:
        """推进一帧; False = 脚本结束(宿主应 despawn)。"""
        if self.finished:
            return False
        if not self._run():
            self.finished = True
            return False
        # OnUpdate 收尾: ClampPos → Move → ClampPos, timer++/无敌时间--
        e = self.enemy
        if not e.disable_movement:
            e.clamp_pos()
            self._integrate_pos()
            e.clamp_pos()
        e.timer = i32(e.timer + 1)
        if e.invincibility_timer > 0:
            e.invincibility_timer -= 1
        return True

    def _instrs(self, ctx: EclContext) -> tuple[EclInstr, ...] | None:
        if 0 <= ctx.sub_id < len(self.file.subs):
            return self.file.subs[ctx.sub_id].instrs
        return None

    def rerun(self) -> bool:
        """当帧重跑一次主循环(回调切换 sub 后的 goto HUH; False = 脚本结束)。"""
        return self._run()

    def interrupt_call(self, sub_id: int) -> bool:
        """中断调用的公共尾巴: 返回点压栈 + 进中断 sub(宿主回调也用)。"""
        # EclManager.cpp RunEcl 的 runInterrupt 段
        e = self.enemy
        self.current.pc += 1  # 返回点 = 当前指令的下一条
        if not e.no_stack_ret:
            self.push_context()
        if not self.call_sub(sub_id):
            return False
        e.run_interrupt = -1
        return True

    def _run(self) -> bool:
        """执行到第一条 time 未到帧的指令, 然后走帧尾(RunEcl)。"""
        e = self.enemy
        while True:  # restart: sub_call/ret/interrupt 换了上下文后重取
            ctx = self.current
            instrs = self._instrs(ctx)
            if instrs is None or not 0 <= ctx.pc < len(instrs):
                log.error("ECL 指令流跑飞: sub={} pc={}", ctx.sub_id, ctx.pc)
                return False
            instr = instrs[ctx.pc]
            if e.run_interrupt >= 0:
                if not self.interrupt_call(e.interrupts[e.run_interrupt]):
                    return False
                instrs = self._instrs(ctx)
                if instrs is None or not 0 <= ctx.pc < len(instrs):
                    return False
                instr = instrs[ctx.pc]
            if e.periodic_callback_sub >= 0:
                e.periodic_counter += 1
                if e.periodic_counter >= e.periodic_timer:
                    e.periodic_counter = 0
                    self.push_context()
                    ctx.int_vars = dict(e.saved_int_vars)
                    ctx.float_vars = dict(e.saved_float_vars)
                    if not self.call_sub(e.periodic_callback_sub):
                        return False
                    ctx.is_periodic_sub = 1
                    instrs = self._instrs(ctx)
                    if instrs is None or not 0 <= ctx.pc < len(instrs):
                        return False
                    instr = instrs[ctx.pc]

            instr = instrs[ctx.pc]
            exited = False
            while True:
                if ctx.wait_timer > 0:
                    ctx.wait_timer -= 1
                    ctx.time = i32(ctx.time - 1)  # 抵消帧尾 time++, 等待期间时刻冻结
                    exited = True
                    break
                if ctx.time == instr.time:
                    if self.host.skip_instr(self, instr):
                        ctx.pc += 1
                    else:
                        r = self.handlers[type(instr)](self, instr)
                        if r is Step.HALT:
                            return False
                        if r is Step.RESTART:
                            break
                        if r is not Step.JUMPED:
                            ctx.pc += 1
                    if not 0 <= ctx.pc < len(instrs):
                        log.error("ECL 执行越过 sub 终止符 (sub={})", ctx.sub_id)
                        return False
                    instr = instrs[ctx.pc]
                    continue
                exited = True  # time != instr.time → 本帧没活干
                break

            if not exited:
                continue  # RESTART: 重取上下文
            self._frame_update()
            return True

    def _frame_update(self) -> None:
        """帧尾(RunEcl 的 exit 路径): 移动模式积分/自动射击/ex 指令/变量插值。"""
        e, ctx = self.enemy, self.current
        self._update_movement()
        if e.life > 0:
            if e.shoot_interval > 0:
                e.shoot_interval_timer += 1
                if e.shoot_interval_timer >= e.shoot_interval:
                    e.shoot_interval_timer = 0
                    self.host.on_auto_shoot(self)
            if ctx.ex_instr_idx >= 0:
                self.run_ex(ctx.ex_instr_idx, ctx.ex_instr)
            self._step_interps()
        ctx.time = i32(ctx.time + 1)

    def run_ex(self, idx: int, instr: EclInstr | None) -> None:
        """Ex 指令分发框架: 语义在宿主侧(run_ex_instr), VM 只委托。"""
        if idx == self.ex_noop_idx:  # ExInsNoOp(无空槽的作品注入 -1)
            return
        if not self.host.run_ex_instr(self, idx, instr):
            if idx not in self._warned_ex:
                self._warned_ex.add(idx)
                log.warning("ECL ex 指令 {} 未实现, 按无操作处理", idx)

    # ---- 帧尾: 移动积分(Enemy::UpdateMovement/Move) ----

    def _update_movement(self) -> None:
        """移动模式积分(mode 1 极角 / 2 位移插值 / 3 轨道)。"""
        # Enemy::UpdateMovement, 移植自 old/touhou/engine/ecl_base.py:372
        e = self.enemy
        mult = self.framerate_multiplier
        if e.move_mode == 3:
            e.move_angle = add_norm_angle(e.move_angle, mult * e.move_angular_velocity)
            e.move_radius = f32(mult * e.move_radial_velocity + e.move_radius)
            mx = math.cos(e.move_angle) * e.move_radius
            my = math.sin(e.move_angle) * e.move_radius
            e.axis_speed.x = f32(mx + e.move_interp_start_pos.x - e.pos.x)
            e.axis_speed.y = f32(my + e.move_interp_start_pos.y - e.pos.y)
            e.angle = f32(math.atan2(e.axis_speed.y, e.axis_speed.x))
            if e.move_interp_start_time > 0:
                e.move_interp_timer -= 1
                if e.move_interp_timer <= 0:
                    e.move_mode = 0
        elif e.move_mode == 1:
            e.angle = add_norm_angle(e.angle, mult * e.angular_velocity)
            e.move_speed = f32(mult * e.move_acceleration + e.move_speed)
            e.axis_speed.x = f32(math.cos(e.angle) * e.move_speed)
            e.axis_speed.y = f32(math.sin(e.angle) * e.move_speed)
            e.axis_speed.z = 0.0
            if e.move_interp_start_time > 0:
                e.move_interp_timer -= 1
                if e.move_interp_timer <= 0:
                    e.move_mode = 0
        elif e.move_mode == 2:
            e.move_interp_timer -= 1
            t = 1.0 - e.move_interp_timer / e.move_interp_start_time
            if t < 0.0:
                t = 0.0
            t = ease(t, e.interp_easing)
            e.axis_speed.x = f32(
                t * e.move_interp.x + e.move_interp_start_pos.x - e.pos.x
            )
            e.axis_speed.y = f32(
                t * e.move_interp.y + e.move_interp_start_pos.y - e.pos.y
            )
            e.axis_speed.z = f32(
                t * e.move_interp.z + e.move_interp_start_pos.z - e.pos.z
            )
            if e.mirror:
                e.axis_speed.x = -e.axis_speed.x
            e.angle = f32(math.atan2(e.axis_speed.y, e.axis_speed.x))
            if e.move_interp_timer <= 0:
                e.move_mode = 0
                e.pos = Vec3(
                    e.move_interp_start_pos.x + e.move_interp.x,
                    e.move_interp_start_pos.y + e.move_interp.y,
                    e.move_interp_start_pos.z + e.move_interp.z,
                )
                e.axis_speed = Vec3()

    def _integrate_pos(self) -> None:
        """位置积分(Enemy::Move, 含 mirror)。"""
        e = self.enemy
        mult = self.framerate_multiplier
        e.delta_pos = Vec3(
            e.pos.x - e.prev_pos.x,
            e.pos.y - e.prev_pos.y,
            e.pos.z - e.prev_pos.z,
        )
        e.prev_pos = e.pos.copy()
        if not e.mirror:
            e.pos.x = f32(e.pos.x + mult * e.axis_speed.x)
        else:
            e.pos.x = f32(e.pos.x - mult * e.axis_speed.x)
        e.pos.y = f32(e.pos.y + mult * e.axis_speed.y)
        e.pos.z = f32(e.pos.z + mult * e.axis_speed.z)

    def _step_interps(self) -> None:
        """变量插值推进; 命中位置分量时回算 axis_speed 并还原 pos。"""
        # EclManager.cpp:830-880, 移植自 old/touhou/engine/ecl_base.py:465
        e = self.enemy
        pos_modified = False
        old_pos = e.pos.copy()
        for it in self.current.interps:
            if not it.active:
                continue
            it.timer += 1
            if it.timer >= it.duration:
                it.timer = it.duration
            t = ease(it.timer / it.duration if it.duration else 1.0, it.easing)
            p = it.params
            if it.func_idx == 7:  # MathCubicInterp(hermite)
                h00 = (t - 1.0) * (t - 1.0) * (2.0 * t + 1.0)
                h01 = t * t * (3.0 - 2.0 * t)
                h10 = (1.0 - t) * (1.0 - t) * t
                h11 = (t - 1.0) * t * t
                value = h00 * p[0] + h01 * p[1] + h10 * p[2] + h11 * p[3]
            else:  # MathLerp(g_EclInterpFuncs[0..6])
                value = (p[1] - p[0]) * t + p[0]
            self.write_float(it.target_var, value)
            if it.timer >= it.duration:
                it.clear()
            if it.target_var in self.pos_var_ids:
                pos_modified = True
        if pos_modified:
            e.axis_speed.x = f32(e.pos.x - old_pos.x)
            e.axis_speed.y = f32(e.pos.y - old_pos.y)
            e.angle = f32(math.atan2(e.axis_speed.y, e.axis_speed.x))
            e.pos = old_pos
