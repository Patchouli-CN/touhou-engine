"""ANM 脚本虚拟机: ExecuteScript 语义的状态机, 纯模拟不碰渲染。"""

from __future__ import annotations

import msgspec

from ...schemas.anm_script import ExitHide, InterruptLabel
from ...utils.logger import LoggerManager
from ..rng import Rng
from .bank import AnmScript
from .handlers import HANDLERS, Step, add_norm_angle

log = LoggerManager.get_logger("ENGINE")


class InterpChannel(msgspec.Struct):
    """一路插值计时: t 从 0 逐帧推进到 duration, duration=0 为未激活。"""

    t: int = 0
    duration: int = 0
    ease: int = 0

    def restart(self, duration: int, ease: int) -> None:
        """以新时长/缓动重新开始。"""
        self.t = 0
        self.duration = duration
        self.ease = ease

    def step(self) -> float | None:
        """推进一帧, 返回缓动后的插值系数; 未激活返回 None。"""
        # 推进/到顶语义出处 AnmManager.cpp:2140-2154
        if self.duration <= 0:
            return None
        self.t += 1
        if self.t >= self.duration:
            self.duration = 0
            return 1.0
        return _ease(self.t / self.duration, self.ease)


def _ease(t: float, mode: int) -> float:
    # ease 曲线出处 AnmManager.cpp:2155-2183(1..3=in, 4..6=out)
    if mode == 1:
        return t * t
    if mode == 2:
        return t * t * t
    if mode == 3:
        t = t * t
        return t * t
    if mode == 4:
        t = 1.0 - t
        return 1.0 - t * t
    if mode == 5:
        t = 1.0 - t
        return 1.0 - t * t * t
    if mode == 6:
        t = 1.0 - t
        t = t * t
        return 1.0 - t * t
    return t


class AnmMachine:
    """一台 ANM VM: 挂一段脚本逐帧 execute, 公开字段即渲染方要的 sprite 状态。"""

    # 状态字段与逐帧行为出处 AnmManager.cpp:1633-2280(ExecuteScript);
    # 变量 id 表(10000..10009)出处 AnmManager.hpp:16-28
    def __init__(self, rng: Rng) -> None:
        self.rng = rng
        self.reset()

    def reset(self) -> None:
        """回初始态(注入的 rng 不动, 随机序列保持连续)。"""
        self.rotation = [0.0, 0.0, 0.0]
        self.angle_vel = [0.0, 0.0, 0.0]
        self.scale = [1.0, 1.0]
        self.scale_growth = [0.0, 0.0]
        self.uv_scroll = [0.0, 0.0]
        self.uv_scroll_vel = [0.0, 0.0]
        self.time = 0
        self.wait_timer = 0
        self.pos_interp = InterpChannel()
        self.color_interp = InterpChannel()
        self.alpha_interp = InterpChannel()
        self.rot_interp = InterpChannel()
        self.scale_interp = InterpChannel()
        self.pos_initial = [0.0, 0.0, 0.0]
        self.pos_final = [0.0, 0.0, 0.0]
        self.rot_initial = [0.0, 0.0, 0.0]
        self.rot_final = [0.0, 0.0, 0.0]
        self.scale_initial = [1.0, 1.0]
        self.scale_final = [1.0, 1.0]
        self.color_initial = [255, 255, 255, 255]  # r,g,b,a
        self.color_final = [255, 255, 255, 255]
        self.int_vars1 = [0] * 4
        self.float_vars = [0.0] * 4
        self.int_vars2 = [0] * 2
        self.color = [255, 255, 255, 255]
        self.visible = False
        self.blend_mode = 0
        self.use_offset = False
        self.anchor = 0
        self.zwrite_disable = 0
        self.is_stopped = False
        self.auto_rotate = 0
        self.pending_interrupt = 0
        self.pos = [0.0, 0.0, 0.0]
        self.offset = [0.0, 0.0, 0.0]
        self.active_sprite_idx = -1
        self.sprite_base = 0
        self.offsets: dict[int, int] = {}
        self.script: AnmScript | None = None
        self.pc = -1  # 当前指令下标, -1 = 脚本结束

    @property
    def alive(self) -> bool:
        """脚本未结束(STOP 等 interrupt 也算活着)。"""
        return self.script is not None and self.pc >= 0

    def start(self, script: AnmScript | None) -> None:
        """重置并挂脚本, 立即执行一帧。"""
        # SetAndExecuteScript 出处 AnmManager.cpp:681-698
        self.reset()
        if script is None:
            return
        self.script = script
        self.sprite_base = script.sprite_base
        self.offsets = script.offsets
        self.pc = 0
        self.execute()

    def execute(self) -> None:
        """执行到第一条 time 未到帧的指令, 然后走帧尾(角速度/插值/滚动/time++)。"""
        # 主循环出处 AnmManager.cpp:1652-1673(WHY_NOT_JUST_CONTINUE 段)
        script = self.script
        if script is None or self.pc < 0:
            return
        instrs = script.instrs
        if self.pending_interrupt != 0 and self.handle_interrupt() is Step.YIELD:
            self._epilogue()
            return
        while 0 <= self.pc < len(instrs) and instrs[self.pc].time <= self.time:
            ins = instrs[self.pc]
            step = HANDLERS[type(ins)](self, ins)
            if step is Step.HALT:
                return
            if step is Step.YIELD:
                break
            if step is not Step.JUMPED:
                self.pc += 1
        self._epilogue()

    def jump_to(self, dest: int, set_time: int) -> None:
        """跳转到字节偏移 dest 并重置脚本时间; dest 不在跳转表内则终止脚本。"""
        self.time = set_time
        self.pc = self.offsets.get(dest, -1)
        if self.pc < 0:
            log.warning("anm 跳转目标不在脚本内, 终止脚本: dest={}", dest)

    def handle_interrupt(self) -> Step:
        """pending_interrupt 跳标号: 命中(或 -1 兜底标号)则跳, 都找不到停脚本尾。"""
        # 搜索/跳转语义出处 AnmManager.cpp:1812-1842(handle_interrupt 段)
        script = self.script
        assert script is not None
        instrs = script.instrs
        target = self.pending_interrupt
        fallback = -1
        idx = 0
        while idx < len(instrs) and not isinstance(instrs[idx], ExitHide):
            ins = instrs[idx]
            if isinstance(ins, InterruptLabel):
                if ins.label == target:
                    break
                if ins.label == -1:
                    fallback = idx
            idx += 1
        self.pending_interrupt = 0
        self.is_stopped = False
        if idx >= len(instrs) or not isinstance(instrs[idx], InterruptLabel):
            if fallback < 0:
                self.time -= 1
                self.pc = idx  # 指向收尾的 ExitHide, 下一帧结束脚本
                return Step.YIELD
            idx = fallback
        self.pc = idx + 1
        if self.pc < len(instrs):
            self.time = instrs[self.pc].time
        self.visible = True
        return Step.JUMPED

    # ---- 变量寻址(flags 第 idx 位置位时对应参数是变量 id) ----
    def ivar(self, arg: int, flags: int, idx: int) -> int:
        """读整数值。"""
        # GetVarValue 出处 AnmManager.cpp:1552-1579
        if not (flags >> idx) & 1:
            return arg
        if 10000 <= arg <= 10003:
            return self.int_vars1[arg - 10000]
        if 10004 <= arg <= 10007:
            return int(self.float_vars[arg - 10004])
        if 10008 <= arg <= 10009:
            return self.int_vars2[arg - 10008]
        return arg

    def fvar(self, arg: float, flags: int, idx: int) -> float:
        """读浮点值。"""
        # GetFloatVarValue 出处 AnmManager.cpp:1522-1549
        if not (flags >> idx) & 1:
            return arg
        a = int(arg)
        if 10000 <= a <= 10003:
            return float(self.int_vars1[a - 10000])
        if 10004 <= a <= 10007:
            return self.float_vars[a - 10004]
        if 10008 <= a <= 10009:
            return float(self.int_vars2[a - 10008])
        return arg

    def istore(self, arg: int, flags: int, idx: int, value: int) -> None:
        """写整型变量: 仅 int 变量 id 可写, 其余丢弃(原作写进指令本地参数)。"""
        # GetVar 出处 AnmManager.cpp:1605-1629
        if not (flags >> idx) & 1:
            return
        if 10000 <= arg <= 10003:
            self.int_vars1[arg - 10000] = value
        elif 10008 <= arg <= 10009:
            self.int_vars2[arg - 10008] = value

    def iptr(self, arg: int, flags: int, idx: int) -> int:
        """读整型变量(GetVar 读侧): 仅 int 变量 id 间接, 其余读字面量。"""
        if not (flags >> idx) & 1:
            return arg
        if 10000 <= arg <= 10003:
            return self.int_vars1[arg - 10000]
        if 10008 <= arg <= 10009:
            return self.int_vars2[arg - 10008]
        return arg

    def fstore(self, arg: float, flags: int, idx: int, value: float) -> None:
        """写浮点变量: 仅 float 变量 id 可写, 其余丢弃。"""
        # GetFloatVar 出处 AnmManager.cpp:1582-1602
        if not (flags >> idx) & 1:
            return
        a = int(arg)
        if 10004 <= a <= 10007:
            self.float_vars[a - 10004] = value

    def _epilogue(self) -> None:
        """帧尾: 角速度归一化累加 + 5 路插值推进 + 缩放增速 + uv 滚动 + time++。"""
        # stop 段出处 AnmManager.cpp:2118-2279
        for k in range(3):
            if self.angle_vel[k] != 0.0:
                self.rotation[k] = add_norm_angle(self.rotation[k], self.angle_vel[k])
        t = self.pos_interp.step()
        if t is not None:
            dst = self.offset if self.use_offset else self.pos
            for k in range(3):
                dst[k] = (
                    self.pos_final[k] - self.pos_initial[k]
                ) * t + self.pos_initial[k]
        t = self.color_interp.step()
        if t is not None:
            for c in range(3):
                self.color[c] = int(
                    (self.color_final[c] - self.color_initial[c]) * t
                    + self.color_initial[c]
                )
        t = self.alpha_interp.step()
        if t is not None:
            self.color[3] = int(
                (self.color_final[3] - self.color_initial[3]) * t
                + self.color_initial[3]
            )
        t = self.rot_interp.step()
        if t is not None:
            for c in range(3):
                self.rotation[c] = add_norm_angle(
                    (self.rot_final[c] - self.rot_initial[c]) * t, self.rot_initial[c]
                )
        t = self.scale_interp.step()
        if t is not None:
            for c in range(2):
                self.scale[c] = (
                    self.scale_final[c] - self.scale_initial[c]
                ) * t + self.scale_initial[c]
        if self.scale_growth[1] != 0.0:
            self.scale[1] += self.scale_growth[1]
        if self.scale_growth[0] != 0.0:
            self.scale[0] += self.scale_growth[0]
        self.uv_scroll[0] = (self.uv_scroll[0] + self.uv_scroll_vel[0]) % 1.0
        self.uv_scroll[1] = (self.uv_scroll[1] + self.uv_scroll_vel[1]) % 1.0
        self.time += 1
