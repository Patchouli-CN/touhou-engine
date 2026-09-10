"""3D 背景场景层: .std 脚本推进(相机/雾/清屏色) + quad VM 生命周期 → 每帧场景描述。

只依赖 schemas/engine.anm/numpy, 不碰渲染库: 产出 BgFrame(投影后的 quad
列表 + 雾/清屏色), 光栅化由 bg3d_raster 消费(未来 GPU 后端可复用本层)。
逐帧行为出处 Stage.cpp::OnUpdate(:158-510)/UpdateObjects(:899-943)/
RenderObjects(:949-1128) 与 AnmManager.cpp Draw3(:1391)/DrawFacingCamera
(:1128)/Draw(2D 全屏 vm, :818 DrawInner)。
"""

from __future__ import annotations

import math

import msgspec
import numpy as np

from ....engine.anm import AnmMachine
from ....engine.rng import Rng
from ....schemas import stage_script as ss
from ....schemas.stage import StdFile
from ..snapshot import GAME_H, GAME_W, GAME_X, GAME_Y, WIN_H, WIN_W

_NEAR, _FAR = 30.0, 1800.0  # UpdateCamera 投影近远面 (Stage.cpp:1176-1179)
_CULL_DIST_SQ = 1690000.0  # RenderObjects: 1300^2 (Stage.cpp:995)
_CULL_NEAR_DOT = 60.0  # dotProd < 60 剔除 (Stage.cpp:1004)
_CULL_RADIUS_PAD = 880.0  # 半径 = |size|/2 + 880 (Stage.cpp:1002)
_ANM_OFFSET_BG1 = 0x300  # ANM_OFFSET_STAGE_BG (AnmIdx.hpp:98)

# StageEaseMode (Stage.cpp:118-140): 1..3 = out quad/cubic/quart,
# 4..6 = in quad/cubic/quart, 7 = hermite 贝塞尔(InterpCubic :148-154)
_EASE_CUBIC_INTERP = 7


class SpriteTex(msgspec.Struct, frozen=True):
    """一个背景 sprite 的贴图定位: texel 角点是 2x2 平铺画布坐标(WRAP 用)。"""

    tex_id: int  # bg3d_raster 的纹理表下标
    x0: float  # 未加 uv 滚动的 texel 角点(画布左上原点)
    y0: float
    x1: float
    y1: float
    w: int  # sprite 像素尺寸(Draw3 的 widthPx/heightPx)
    h: int
    tex_w: float  # 原纹理宽(uv 滚动是归一化单位, 换算 texel 用)
    tex_h: float
    opaque: bool  # 纹理无透明 texel(不透明阶段成员判定)


class QuadCmd(msgspec.Struct, frozen=True):
    """一个待画 quad: 投影后的屏幕角点 + 贴图/颜色/雾/混合状态。"""

    pts: tuple[float, ...]  # 4 角点 (x,y)*4, 游戏区坐标(384x448)
    uv: tuple[float, ...]  # 4 角点 texel 坐标(平铺画布), 与 pts 一一对应
    tex_id: int
    color: tuple[int, int, int, int]
    blend: int  # 0 普通 1 加算
    fog: tuple[float, float, float, float]  # 4 顶点线性雾因子
    sort_z: float  # 排序键(平均 view z)
    zwrite_disable: int
    tex_opaque: bool
    pass_idx: int  # 0 = z_level 0/1 (OnDrawHighPrio), 1 = z_level 2/3


class BgFrame(msgspec.Struct, frozen=True):
    """一帧 3D 背景的场景描述(光栅化器的全部输入)。"""

    fog_rgb: tuple[int, int, int]  # 打底色(雾色)
    clear_color: int  # std 清屏色, 0 = 不清
    quads: tuple[QuadCmd, ...]


def _stage_ease(t: float, mode: int) -> float:
    # ease 变换出处 Stage.cpp:118-140
    if mode == 1:
        t = 1.0 - t
        return 1.0 - t * t
    if mode == 2:
        t = 1.0 - t
        return 1.0 - t * t * t
    if mode == 3:
        t = 1.0 - t
        return 1.0 - t * t * t * t
    if mode == 4:
        return t * t
    if mode == 5:
        return t * t * t
    if mode == 6:
        return t * t * t * t
    return t


def _interp_cubic(p0: float, p1: float, p2: float, p3: float, t: float) -> float:
    # Stage.cpp InterpCubic(hermite), 公式 :82-89 转引
    v0 = (t - 1.0) * (t - 1.0) * (2.0 * t + 1.0)
    v2 = t * t * (3.0 - 2.0 * t)
    v1 = (1.0 - t) * (1.0 - t) * t
    v3 = (t - 1.0) * t * t
    return v0 * p0 + v2 * p1 + v1 * p2 + v3 * p3


class _Channel:
    """相机一路(pos/lookAt/up/fov)的插值状态(UpdateScriptAndCamera)。"""

    __slots__ = ("start", "end", "tan_start", "tan_end", "timer", "timer_max", "ease")

    def __init__(self) -> None:
        self.start = [0.0, 0.0, 0.0]
        self.end = [0.0, 0.0, 0.0]
        self.tan_start = [0.0, 0.0, 0.0]
        self.tan_end = [0.0, 0.0, 0.0]
        self.timer = 0
        self.timer_max = 0
        self.ease = 0


def _look_at_lh(
    pos: list[float], direction: list[float], up: list[float]
) -> tuple[np.ndarray, np.ndarray]:
    """D3DXMatrixLookAtLH(方向版): 返回 (view 4x4, cam_right)。"""
    z = np.array(direction)
    n = float(np.linalg.norm(z))
    z = z / n if n > 1e-12 else z * 0.0
    x = np.cross(up, z)
    n = float(np.linalg.norm(x))
    x = x / n if n > 1e-12 else x * 0.0
    y = np.cross(z, x)
    v = np.identity(4)
    v[0, :3] = [x[0], y[0], z[0]]
    v[1, :3] = [x[1], y[1], z[1]]
    v[2, :3] = [x[2], y[2], z[2]]
    v[3, :3] = [-float(np.dot(x, pos)), -float(np.dot(y, pos)), -float(np.dot(z, pos))]
    return v, x  # cam_right = normalize(cross(z, up)) = view 的 -x 轴


def _perspective_fov_lh(
    fov: float, aspect: float, near: float, far: float
) -> np.ndarray:
    """D3DXMatrixPerspectiveFovLH(左手系)。"""
    tan = math.tan(fov / 2.0)
    p = np.zeros((4, 4))
    p[0, 0] = 1.0 / (tan * aspect)
    p[1, 1] = 1.0 / tan
    p[2, 2] = far / (far - near)
    p[2, 3] = 1.0
    p[3, 2] = -near * far / (far - near)
    return p


def _rotation_coff(hw: float, hh: float, rot: list[float]) -> tuple[float, ...]:
    """Draw3 角点偏移: world = diag(hw,hh) · Rx·Ry·Rz 的 4 角点(12 元组)。"""
    # 旋序/零角优化出处 AnmManager.cpp:1417-1444
    if rot[0] == 0.0 and rot[1] == 0.0 and rot[2] == 0.0:
        return (-hw, -hh, 0.0, hw, -hh, 0.0, -hw, hh, 0.0, hw, hh, 0.0)
    cx_, sx_ = math.cos(rot[0]), math.sin(rot[0])
    cy_, sy_ = math.cos(rot[1]), math.sin(rot[1])
    cz_, sz_ = math.cos(rot[2]), math.sin(rot[2])
    m00, m01, m02 = cy_ * cz_, cy_ * sz_, -sy_
    m10 = sx_ * sy_ * cz_ - cx_ * sz_
    m11 = sx_ * sy_ * sz_ + cx_ * cz_
    m12 = sx_ * cy_
    out: list[float] = []
    for bx, by in ((-hw, -hh), (hw, -hh), (-hw, hh), (hw, hh)):
        out += [bx * m00 + by * m10, bx * m01 + by * m11, bx * m02 + by * m12]
    return tuple(out)


def _fog_factor(view_z: float, near: float, far: float) -> float:
    """D3D 线性雾因子: f = (far - z)/(far - near) 夹取 [0,1]。"""
    f = (far - view_z) / max(1e-6, far - near)
    return 0.0 if f < 0.0 else (1.0 if f > 1.0 else f)


class BgScene:
    """一关的 3D 背景场景: std 脚本 + quad VM + 每帧场景描述。

    VM 用注入的 rng(与 sim rng 隔离); 相机/雾/清屏色/世界原点由 std
    脚本指令改写, ECL 的 SET_SCRIPT_WAIT_TIME 经 world 透出由 tick 消费。
    """

    def __init__(self, std: StdFile, scripts: dict, rng: Rng) -> None:
        self._std = std
        self._scripts = scripts  # 全局 id → AnmScript(0x300 基址重键后)
        self._rng = rng
        self.sprites: dict[int, SpriteTex] = {}  # facade 装配(facade 拥有贴图)
        self._instrs = std.script
        self.script_time = 0
        self.instr_idx = 0
        self.wait_time = 0  # C scriptWaitTime (Stage.cpp:167)
        # 相机初值 (AddedCallback, Stage.cpp:782-795)
        self.cam_pos = [0.0, 0.0, 1000.0]
        self.cam_lookat = [0.0, 0.0, 0.0]
        self.cam_up = [0.0, 1.0, 0.0]
        self.cam_fov = math.pi / 6.0
        self._ch = [_Channel() for _ in range(4)]
        self._ch[0].start = self._ch[0].end = list(self.cam_pos)
        self._ch[1].start = self._ch[1].end = list(self.cam_lookat)
        self._ch[2].start = self._ch[2].end = list(self.cam_up)
        self._ch[3].start = self._ch[3].end = [self.cam_fov, 0.0, 0.0]
        # 雾(AddedCallback:782-784) + 插值状态(:217-227)
        self.fog_rgba = 0xFF000000
        self.fog_near = 200.0
        self.fog_far = 500.0
        self._fog_start = (0xFF000000, 200.0, 500.0)  # 插值目标
        self._fog_end = (0xFF000000, 200.0, 500.0)  # 插值起点(命名沿 C)
        self._fog_interp_duration = 0
        self._fog_interp_timer = 0
        self.world_origin = [0.0, 0.0, 0.0]  # std PosKey(C 的 pos)
        self.clear_color = 0
        # quad VM(LoadStageData: ExecuteAnmIdx(anmScript+0x300), Stage.cpp:881-894)
        self._obj_vms: list[list[AnmMachine]] = []
        self._obj_active: list[bool] = []
        for obj in std.objects:
            vms = []
            for quad in obj.quads:
                vm = AnmMachine(rng)
                vm.start(scripts.get(quad.anm_script + _ANM_OFFSET_BG1))
                vms.append(vm)
            self._obj_vms.append(vms)
            self._obj_active.append(True)
        self.vm1 = AnmMachine(rng)  # 全屏 2D VM(opcode 29/30)
        self.vm2 = AnmMachine(rng)
        # 投影派生缓存(frame() 重建; 单位阵保证随时可投影)
        self._vp = tuple(
            tuple(1.0 if r == c else 0.0 for c in range(4)) for r in range(4)
        )
        self._vz = (0.0, 0.0, 1.0, 0.0)
        self._look_dir = [0.0, 0.0, 1.0]
        self._cam_right = (1.0, 0.0, 0.0)

    # ---- 每帧推进(Stage::OnUpdate) ----
    def tick(self, waits: list[int]) -> None:
        """推进一帧: ECL 等待值 → 脚本扫描 → 相机/雾插值 → VM 帧。"""
        for w in waits:  # ECL 写 g_Stage.scriptWaitTime (EclManager.cpp:1822)
            self.wait_time = w
        instrs = self._instrs
        if self.wait_time != 0:
            # 找 WaitLabel 跳转 (Stage.cpp:167-185); 找不到保留待下帧重试
            for i, ins in enumerate(instrs):
                if isinstance(ins, ss.WaitLabel) and ins.label == self.wait_time:
                    self.instr_idx = i + 1
                    self.script_time = ins.frame
                    self.wait_time = 0
                    break
        while (
            self.instr_idx < len(instrs)
            and self.script_time >= instrs[self.instr_idx].frame
        ):
            ins = instrs[self.instr_idx]
            if isinstance(ins, ss.Halt) and self.wait_time == 0:
                break  # goto LAB(脚本停轴, Stage.cpp:289-295)
            self._dispatch(ins)
            self.instr_idx += 1
        # 相机 4 路插值 (Stage.cpp:377-445)
        for idx in range(4):
            if self._ch[idx].timer_max != 0:
                self._update_channel(idx)
        # 雾插值 (Stage.cpp:447-475)
        if self._fog_interp_duration != 0:
            self._fog_interp_timer += 1
            t = min(1.0, self._fog_interp_timer / self._fog_interp_duration)
            c0, n0, f0 = self._fog_start
            c1, n1, f1 = self._fog_end
            rgba = 0
            for shift in (24, 16, 8, 0):
                a = (c0 >> shift) & 255
                b = (c1 >> shift) & 255
                rgba |= (int((a - b) * t + b) & 255) << shift
            self.fog_rgba = rgba
            self.fog_near = (n0 - n1) * t + n1
            self.fog_far = (f0 - f1) * t + f1
            if self._fog_interp_timer >= self._fog_interp_duration:
                self._fog_interp_duration = 0
        # 脚本时间(当前指令是 Halt 则停轴, Stage.cpp:476-479)
        cur = instrs[self.instr_idx] if self.instr_idx < len(instrs) else None
        if not isinstance(cur, ss.Halt):
            self.script_time += 1
        # UpdateObjects (Stage.cpp:899-943)
        for oi in range(len(self._std.objects)):
            if not self._obj_active[oi]:
                continue
            alive = 0
            for vm in self._obj_vms[oi]:
                vm.execute()
                if vm.alive:
                    alive += 1
            if alive == 0:
                self._obj_active[oi] = False
        # 全屏 VM (Stage.cpp:493-500)
        if self.vm1.active_sprite_idx > 0:
            self.vm1.execute()
        if self.vm2.active_sprite_idx > 0:
            self.vm2.execute()

    def _dispatch(self, ins: ss.Instruction) -> None:
        """单条 std 指令生效 (Stage.cpp:190-373 的 switch)。"""
        ch = self._ch
        if isinstance(ins, ss.PosKey):
            # C 还会前扫下一对 PosKey 记插值区间, 但插值字段全代码无消费
            # (Stage.cpp:192-215, 实装各关 PosKey 值全 (0,0,0)) → 直接写
            self.world_origin = [ins.x, ins.y, ins.z]
        elif isinstance(ins, ss.SetFog):
            self.fog_rgba = ins.color & 0xFFFFFFFF
            self.fog_near = ins.near
            self.fog_far = ins.far
            self._fog_start = (self.fog_rgba, ins.near, ins.far)
        elif isinstance(ins, ss.FogInterp):
            self._fog_end = (self.fog_rgba, self.fog_near, self.fog_far)
            self._fog_interp_duration = ins.duration
            self._fog_interp_timer = 0
        elif isinstance(ins, ss.Halt):
            # scriptWaitTime != 0 时清等待并放行 (Stage.cpp:290-293)
            self.wait_time = 0
        elif isinstance(ins, ss.Jump):
            self.instr_idx = ins.instr_idx - 1  # tick 循环统一 +1
            self.script_time = ins.time
            ch[0].timer_max = 0
            # C 置 cameraTeleported=1 → EffectManager 特效随相机瞬移平移
            # (Stage.cpp:229-234), 本仓特效层无此联动(已知偏差)
        elif isinstance(ins, ss.CamPos):
            ch[0].start = list(ch[0].end)
            ch[0].end = [ins.x, ins.y, ins.z]
            if ch[0].timer_max == 0:
                self.cam_pos = [ins.x, ins.y, ins.z]
        elif isinstance(ins, ss.CamPosInterp):
            ch[0].timer_max, ch[0].timer, ch[0].ease = ins.duration, 0, ins.ease_mode
        elif isinstance(ins, ss.CamLookAt):
            ch[1].start = list(ch[1].end)
            ch[1].end = [ins.x, ins.y, ins.z]
            if ch[1].timer_max == 0:
                self.cam_lookat = [ins.x, ins.y, ins.z]
        elif isinstance(ins, ss.CamLookAtInterp):
            ch[1].timer_max, ch[1].timer, ch[1].ease = ins.duration, 0, ins.ease_mode
        elif isinstance(ins, ss.CamUp):
            ch[2].start = list(ch[2].end)
            ch[2].end = [ins.x, ins.y, ins.z]
            if ch[2].timer_max == 0:
                self.cam_up = [ins.x, ins.y, ins.z]
        elif isinstance(ins, ss.CamUpInterp):
            ch[2].timer_max, ch[2].timer, ch[2].ease = ins.duration, 0, ins.ease_mode
        elif isinstance(ins, ss.CamFov):
            ch[3].start = list(ch[3].end)
            ch[3].end = [ins.fov, 0.0, 0.0]
            if ch[3].timer_max == 0:
                self.cam_fov = ins.fov
        elif isinstance(ins, ss.CamFovInterp):
            ch[3].timer_max, ch[3].timer, ch[3].ease = ins.duration, 0, ins.ease_mode
        elif isinstance(ins, ss.ClearColor):
            self.clear_color = ins.color & 0xFFFFFFFF
        elif isinstance(
            ins, (ss.CamPosBezierStart, ss.CamLookAtBezierStart, ss.CamUpBezierStart)
        ):
            ch[
                {
                    ss.CamPosBezierStart: 0,
                    ss.CamLookAtBezierStart: 1,
                    ss.CamUpBezierStart: 2,
                }[type(ins)]
            ].start = [ins.x, ins.y, ins.z]
        elif isinstance(
            ins, (ss.CamPosBezierEnd, ss.CamLookAtBezierEnd, ss.CamUpBezierEnd)
        ):
            ch[
                {ss.CamPosBezierEnd: 0, ss.CamLookAtBezierEnd: 1, ss.CamUpBezierEnd: 2}[
                    type(ins)
                ]
            ].end = [ins.x, ins.y, ins.z]
        elif isinstance(
            ins,
            (
                ss.CamPosBezierTanStart,
                ss.CamLookAtBezierTanStart,
                ss.CamUpBezierTanStart,
            ),
        ):
            ch[
                {
                    ss.CamPosBezierTanStart: 0,
                    ss.CamLookAtBezierTanStart: 1,
                    ss.CamUpBezierTanStart: 2,
                }[type(ins)]
            ].tan_start = [ins.x, ins.y, ins.z]
        elif isinstance(
            ins,
            (ss.CamPosBezierTanEnd, ss.CamLookAtBezierTanEnd, ss.CamUpBezierTanEnd),
        ):
            ch[
                {
                    ss.CamPosBezierTanEnd: 0,
                    ss.CamLookAtBezierTanEnd: 1,
                    ss.CamUpBezierTanEnd: 2,
                }[type(ins)]
            ].tan_end = [ins.x, ins.y, ins.z]
        elif isinstance(ins, (ss.CamPosBezier, ss.CamLookAtBezier, ss.CamUpBezier)):
            idx = {ss.CamPosBezier: 0, ss.CamLookAtBezier: 1, ss.CamUpBezier: 2}[
                type(ins)
            ]
            ch[idx].timer_max, ch[idx].timer = ins.duration, 0
            ch[idx].ease = _EASE_CUBIC_INTERP
        elif isinstance(ins, ss.BgScript1):
            self._bg_vm(self.vm1, ins.script)
        elif isinstance(ins, ss.BgScript2):
            # C 负值分支误写 vm1 (Stage.cpp:369-371), 按语义作用于 vm2(已知偏差)
            self._bg_vm(self.vm2, ins.script)

    def _bg_vm(self, vm: AnmMachine, script: int) -> None:
        """Opcode 29/30: 全屏 VM 换脚本(负 = 隐藏)。"""
        if script >= 0:
            vm.start(self._scripts.get(script + _ANM_OFFSET_BG1))
        else:
            vm.active_sprite_idx = -1

    def _update_channel(self, idx: int) -> None:
        """一路相机插值推进 (UpdateScriptAndCamera, Stage.cpp:104-155)。"""
        ch = self._ch[idx]
        if ch.timer < ch.timer_max:
            ch.timer += 1
            t = ch.timer / ch.timer_max
        else:
            ch.timer = ch.timer_max
            t = 1.0
            ch.timer_max = 0
        if ch.ease != _EASE_CUBIC_INTERP:
            t = _stage_ease(t, ch.ease)
            cur = [(ch.end[k] - ch.start[k]) * t + ch.start[k] for k in range(3)]
        else:
            cur = [
                _interp_cubic(ch.start[k], ch.end[k], ch.tan_start[k], ch.tan_end[k], t)
                for k in range(3)
            ]
        if idx == 0:
            self.cam_pos = cur
        elif idx == 1:
            self.cam_lookat = cur
        elif idx == 2:
            self.cam_up = cur
        else:
            self.cam_fov = cur[0]

    # ---- 每帧场景描述(RenderObjects + Draw3/DrawFacingCamera/Draw) ----
    def frame(self) -> BgFrame:
        """投影本帧全部存活 quad, 返回光栅化输入(渲染序已排好)。"""
        view, cam_right = _look_at_lh(self.cam_pos, self.cam_lookat, self.cam_up)
        proj = _perspective_fov_lh(self.cam_fov, WIN_W / WIN_H, _NEAR, _FAR)
        vp = view @ proj
        self._vp = tuple(tuple(float(vp[r, c]) for c in range(4)) for r in range(4))
        self._vz = (
            float(view[0, 2]),
            float(view[1, 2]),
            float(view[2, 2]),
            float(view[3, 2]),
        )
        n = float(np.linalg.norm(self.cam_lookat))
        self._look_dir = (
            [v / n for v in self.cam_lookat] if n > 1e-12 else [0.0, 0.0, 0.0]
        )
        self._cam_right = (
            float(cam_right[0]),
            float(cam_right[1]),
            float(cam_right[2]),
        )
        quads: list[QuadCmd] = []
        # vm1/vm2(屏幕空间 2D, 画在 3D 场景之前, OnDrawHighPrio:575-588)
        for vm in (self.vm1, self.vm2):
            cmd = self._prepare_2d(vm)
            if cmd is not None:
                quads.append(cmd)
        wo = self.world_origin
        cp = self.cam_pos
        for pass_idx, levels in enumerate(((0, 1), (2, 3))):
            for inst in self._std.instances:
                obj = self._std.objects[inst.object_idx]
                if obj.z_level not in levels:
                    continue
                # 实例剔除 (Stage.cpp:989-1008)
                cx = obj.pos[0] + inst.pos[0] - wo[0] + obj.size[0] / 2.0 - cp[0]
                cy = obj.pos[1] + inst.pos[1] - wo[1] + obj.size[1] / 2.0 - cp[1]
                cz = obj.pos[2] + inst.pos[2] - wo[2] + obj.size[2] / 2.0 - cp[2]
                if cx * cx + cy * cy + cz * cz > _CULL_DIST_SQ:
                    continue
                ld = self._look_dir
                dot = cx * ld[0] + cy * ld[1] + cz * ld[2]
                radius = (
                    math.sqrt(obj.size[0] ** 2 + obj.size[1] ** 2 + obj.size[2] ** 2)
                    / 2.0
                    + _CULL_RADIUS_PAD
                )
                if dot > radius or dot < _CULL_NEAR_DOT:
                    continue
                for qi, quad in enumerate(obj.quads):
                    vm = self._obj_vms[inst.object_idx][qi]
                    cmd = self._prepare_quad(vm, quad, inst.pos, pass_idx)
                    if cmd is not None:
                        quads.append(cmd)
        return BgFrame(
            (
                (self.fog_rgba >> 16) & 255,
                (self.fog_rgba >> 8) & 255,
                self.fog_rgba & 255,
            ),
            self.clear_color,
            tuple(quads),
        )

    def _project(self, x: float, y: float, z: float) -> tuple[float, float, float]:
        """世界点 → (游戏区 x, y, clip_w); w<1(穿近面)抛 ValueError。"""
        m = self._vp
        c3 = m[3][3] + x * m[0][3] + y * m[1][3] + z * m[2][3]
        if c3 < 1.0:
            raise ValueError("near clip")
        c0 = m[3][0] + x * m[0][0] + y * m[1][0] + z * m[2][0]
        c1 = m[3][1] + x * m[0][1] + y * m[1][1] + z * m[2][1]
        return (
            (c0 / c3 + 1.0) * (WIN_W / 2.0) - GAME_X,
            (1.0 - c1 / c3) * (WIN_H / 2.0) - GAME_Y,
            c3,
        )

    def _view_z(self, x: float, y: float, z: float) -> float:
        vz = self._vz
        return vz[0] * x + vz[1] * y + vz[2] * z + vz[3]

    def _sprite_of(self, vm: AnmMachine) -> SpriteTex | None:
        """Draw3 前置检查: 可见/已挂脚本(active)/有 alpha/有 sprite。

        C 的 ANM_EXIT 只停脚本(visible/active 不变, AnmManager.cpp:1669-1673),
        静态背景 quad 的脚本一帧即 Exit, 之后按最后状态常驻绘制——不能以
        脚本存活当绘制条件。
        """
        if not vm.visible or vm.script is None or vm.color[3] == 0:
            return None
        return self.sprites.get(vm.active_sprite_idx)

    def _uv(self, spr: SpriteTex, vm: AnmMachine) -> tuple[float, ...]:
        """4 角点 texel 坐标(平铺画布): 角点基址 + 归一化滚动 × 纹理尺寸。"""
        su = vm.uv_scroll[0] * spr.tex_w
        sv = vm.uv_scroll[1] * spr.tex_h
        x0, y0, x1, y1 = spr.x0 + su, spr.y0 + sv, spr.x1 + su, spr.y1 + sv
        return (x0, y0, x1, y0, x0, y1, x1, y1)

    def _prepare_quad(
        self, vm: AnmMachine, quad, ipos: tuple[float, float, float], pass_idx: int
    ) -> QuadCmd | None:
        """RenderObjects case 0 (Stage.cpp:1016-1116): 定位 + 投影 + 雾。"""
        spr = self._sprite_of(vm)
        if spr is None:
            return None
        wo = self.world_origin
        px = vm.offset[0] + quad.pos[0] + ipos[0] - wo[0]
        py = vm.offset[1] + quad.pos[1] + ipos[1] - wo[1]
        pz = vm.offset[2] + quad.pos[2] + ipos[2] - wo[2]
        sx, sy = vm.scale
        if quad.size[0] != 0.0:
            sx = quad.size[0] / spr.w
        if quad.size[1] != 0.0:
            sy = quad.size[1] / spr.h
        if vm.auto_rotate == 2:
            return self._prepare_billboard(vm, quad, (px, py, pz), spr, sx, pass_idx)
        hw = spr.w * sx / 2.0
        hh = spr.h * sy / 2.0
        ax = abs(hw) if vm.anchor & 1 else 0.0
        ay = abs(hh) if vm.anchor & 2 else 0.0
        coff = _rotation_coff(hw, hh, vm.rotation)
        tx, ty = px + ax, py + ay
        pts: list[float] = []
        fogs: list[float] = []
        zsum = 0.0
        try:
            for i in range(0, 12, 3):
                x = coff[i] + tx
                y = coff[i + 1] + ty
                z = coff[i + 2] + pz
                sx_p, sy_p, _w = self._project(x, y, z)
                pts += [sx_p, sy_p]
                zv = self._view_z(x, y, z)
                zsum += zv
                fogs.append(_fog_factor(zv, self.fog_near, self.fog_far))
        except ValueError:
            return None  # 顶点穿近面, 整只丢弃
        xs = pts[0::2]
        ys = pts[1::2]
        if max(xs) < 0 or min(xs) >= GAME_W or max(ys) < 0 or min(ys) >= GAME_H:
            return None
        return QuadCmd(
            tuple(pts),
            self._uv(spr, vm),
            spr.tex_id,
            (vm.color[0], vm.color[1], vm.color[2], vm.color[3]),
            vm.blend_mode,
            (fogs[0], fogs[1], fogs[2], fogs[3]),
            zsum * 0.25,
            vm.zwrite_disable,
            spr.opaque,
            pass_idx,
        )

    def _prepare_billboard(
        self,
        vm: AnmMachine,
        quad,
        pos: tuple[float, float, float],
        spr: SpriteTex,
        sx: float,
        pass_idx: int,
    ) -> QuadCmd | None:
        """autoRotate==2: 面向相机 quad (Stage.cpp:1032-1102 + DrawFacingCamera)。"""
        x, y, z = pos
        try:
            cx, cy, clip_w = self._project(x, y, z)
        except ValueError:
            return None
        var_98 = quad.size[0] if quad.size[0] != 0.0 else spr.w
        off = var_98 * sx
        cr = self._cam_right
        m = self._vp
        x2, y2, z2 = x + cr[0] * off, y + cr[1] * off, z + cr[2] * off
        c3 = m[3][3] + x2 * m[0][3] + y2 * m[1][3] + z2 * m[2][3]
        c0 = m[3][0] + x2 * m[0][0] + y2 * m[1][0] + z2 * m[2][0]
        c1 = m[3][1] + x2 * m[0][1] + y2 * m[1][1] + z2 * m[2][1]
        ex = (c0 / c3 + 1.0) * (WIN_W / 2.0) - GAME_X
        ey = (1.0 - c1 / c3) * (WIN_H / 2.0) - GAME_Y
        scale = math.hypot(ex - cx, ey - cy) / var_98
        hw = spr.w * scale / 2.0
        hh = spr.h * scale / 2.0
        # 手动雾(3D 距离, rgb 向雾色收敛 + alpha 衰减, Stage.cpp:1065-1082)
        color = [vm.color[0], vm.color[1], vm.color[2], vm.color[3]]
        cam = self.cam_pos
        dist = math.sqrt((x - cam[0]) ** 2 + (y - cam[1]) ** 2 + (z - cam[2]) ** 2)
        if self.fog_near < dist:
            f = (self.fog_near - dist) / (self.fog_near - self.fog_far)
            if f >= 1.0:
                return None
            fr = (self.fog_rgba >> 16) & 255
            fg_ = (self.fog_rgba >> 8) & 255
            fb_ = self.fog_rgba & 255
            color = [
                int(color[0] - (color[0] - fr) * f),
                int(color[1] - (color[1] - fg_) * f),
                int(color[2] - (color[2] - fb_) * f),
                int(color[3] * (1.0 - f)),
            ]
        if color[3] == 0:
            return None
        if vm.anchor & 1:
            cx += hw
        if vm.anchor & 2:
            cy += hh
        pts = (cx - hw, cy - hh, cx + hw, cy - hh, cx - hw, cy + hh, cx + hw, cy + hh)
        return QuadCmd(
            pts,
            self._uv(spr, vm),
            spr.tex_id,
            (color[0], color[1], color[2], color[3]),
            vm.blend_mode,
            (1.0, 1.0, 1.0, 1.0),  # 雾已烘焙进 color
            self._view_z(x, y, z),
            vm.zwrite_disable,
            spr.opaque,
            pass_idx,
        )

    def _prepare_2d(self, vm: AnmMachine) -> QuadCmd | None:
        """全屏 2D quad(vm1/vm2): AnmManager::Draw 口径, rotation.z + scale。"""
        if vm.active_sprite_idx <= 0:
            return None
        spr = self._sprite_of(vm)
        if spr is None:
            return None
        hw = spr.w * vm.scale[0] / 2.0
        hh = spr.h * vm.scale[1] / 2.0
        zrot = vm.rotation[2]
        c, s = math.cos(zrot), math.sin(zrot)
        x0 = vm.pos[0] - GAME_X
        y0 = vm.pos[1] - GAME_Y
        pts: list[float] = []
        for wx, wy in ((-hw, -hh), (hw, -hh), (-hw, hh), (hw, hh)):
            pts += [wx * c - wy * s + x0, wx * s + wy * c + y0]
        if vm.anchor & 1:
            for i in range(0, 8, 2):
                pts[i] += hw
        if vm.anchor & 2:
            for i in range(1, 8, 2):
                pts[i] += hh
        return QuadCmd(
            tuple(pts),
            self._uv(spr, vm),
            spr.tex_id,
            (vm.color[0], vm.color[1], vm.color[2], vm.color[3]),
            vm.blend_mode,
            (1.0, 1.0, 1.0, 1.0),  # 2D 全屏 VM 不吃场景雾(画前 fog 已禁)
            1.0,
            vm.zwrite_disable,
            spr.opaque,
            0,
        )
