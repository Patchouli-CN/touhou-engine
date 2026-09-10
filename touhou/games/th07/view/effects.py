"""战斗特效粒子层: EffectManager 子集 (EffectManager.cpp g_EffectMapping + 物理回调)。

触发面 = 敌击坠爆散 (EnemyManager.cpp:951-1020 deathAnm1/deathAnm2+4)、
玩家死亡大爆 (Player.cpp:1233-1234)、符卡环 (EclManager.cpp:701)。
粒子 = 一台 etama.anm 脚本 VM + 物理回调, 回收口径 = OnUpdate 的
ExecuteScript 结束即释放 (EffectManager.cpp:708-712)。

近似项: 特效原为世界空间 3D quad, 按游戏平面 1:1 映射成 2D; orbit(13-15)/
weather(20,26,27,30,31)/attach(23,24) 类本单触发不到, 按 static 处理;
eff/背景文件的特效(16,23)不走本层(符卡背景见 spellcard.py)。
"""

from __future__ import annotations

import math

from ....engine import SpriteDraw
from ....engine.anm import AnmBank, AnmMachine
from ....engine.rng import Rng
from ..snapshot import GAME_X, GAME_Y

# 物理回调种类 (EffectManager.cpp g_EffectMapping 的 init/update 对)
_ST, _BURST, _BURST_FAST, _GATHER60, _GATHER240, _BURST30, _BURST_EASE30 = range(7)

# effectId → (etama 链式脚本键 = C 全局 id - 0x200, 物理); 出处 EffectManager.cpp:15-78
FX_TABLE: dict[int, tuple[int, int]] = {
    0: (0x2AB - 0x200, _ST),  # 击坠爆风环 (deathAnm1 默认)
    1: (0x2AC - 0x200, _ST),
    2: (0x2AD - 0x200, _ST),
    3: (0x2AE - 0x200, _BURST),  # InitDeceleratingBurst
    4: (0x2B3 - 0x200, _BURST_FAST),  # deathAnm2+4 默认
    5: (0x2B4 - 0x200, _BURST_FAST),  # 自机弹命中火花 (Player.cpp:895)
    6: (0x2B5 - 0x200, _BURST_FAST),  # 玩家死亡 ×16 (Player.cpp:1234)
    7: (0x2B6 - 0x200, _BURST_FAST),  # 道具爆皮
    8: (0x2B7 - 0x200, _BURST_FAST),  # 擦弹 (Player.cpp:1196)
    9: (0x2B8 - 0x200, _BURST_FAST),
    10: (0x2B9 - 0x200, _BURST_FAST),
    11: (0x2BA - 0x200, _BURST_FAST),
    12: (0x2BB - 0x200, _ST),  # 玩家死亡大爆风 (Player.cpp:1233)
    13: (0x2BC - 0x200, _ST),  # 原为 orbit (UpdateOrbitEffect), 本单近似静止
    14: (0x2BC - 0x200, _ST),
    15: (0x2BC - 0x200, _ST),
    17: (0x2AF - 0x200, _GATHER60),  # 收束 60 帧
    18: (0x2B0 - 0x200, _GATHER240),  # 收束 240 帧
    19: (0x2BD - 0x200, _ST),
    21: (0x2C3 - 0x200, _ST),
    22: (0x2C0 - 0x200, _BURST_EASE30),
    25: (0x2DA - 0x200, _ST),  # 符卡环 (EclManager.cpp:701)
    28: (0x2DB - 0x200, _ST),  # 结界展示
    29: (0x2B2 - 0x200, _BURST30),  # 结界破裂樱点 (Player.cpp:2185)
    32: (0x2C1 - 0x200, _BURST_EASE30),
    33: (0x2B1 - 0x200, _GATHER60),
}

FX_Z = 28.0  # Effect draw prio 9 < Bullet 10: 弹(30)之下、自机弹(25)之上


class _Particle:
    """一个特效粒子 (EffectManager.hpp Effect 的 2D 子集)。"""

    __slots__ = (
        "vm",
        "kind",
        "x",
        "y",
        "vx",
        "vy",
        "ax",
        "ay",
        "dx",
        "dy",
        "ex",
        "ey",
        "timer",
    )

    def __init__(self, vm: AnmMachine, kind: int, x: float, y: float) -> None:
        self.vm = vm
        self.kind = kind
        self.x, self.y = x, y
        self.vx = self.vy = self.ax = self.ay = 0.0
        self.dx = self.dy = 0.0  # direction (gather/burst30 系)
        self.ex, self.ey = x, y  # emitterPosition
        self.timer = 0


class FxParticles:
    """特效粒子池: spawn(EffectManager::SpawnEffect 子集) + 每帧 step 出 SpriteDraw。"""

    def __init__(self, *, seed: int = 0) -> None:
        self._rng = Rng(seed)  # view 专用, 不碰 sim rng
        self._alive: list[_Particle] = []

    def __len__(self) -> int:
        return len(self._alive)

    def _rand128(self) -> float:
        return self._rng.unit() * 256.0 - 128.0

    def spawn(
        self,
        bank: AnmBank | None,
        effect_id: int,
        x: float,
        y: float,
        count: int = 1,
        color: int = 0xFFFFFFFF,
    ) -> None:
        """SpawnEffect(effectId, pos, count, color) 子集; 坐标为游戏区坐标。"""
        spec = FX_TABLE.get(effect_id)
        if spec is None or bank is None:
            return
        key, kind = spec
        script = bank.scripts.get(key)
        if script is None:
            return
        cr, cg, cb, ca = (
            (color >> 16) & 255,
            (color >> 8) & 255,
            color & 255,
            (color >> 24) & 255,
        )
        for _ in range(count):
            vm = AnmMachine(self._rng)
            vm.start(script)
            vm.color = [cr, cg, cb, ca]  # start 后设置(同 C++ 顺序)
            p = _Particle(vm, kind, x, y)
            if kind == _BURST:
                # InitDeceleratingBurst (EffectManager.cpp:126-137)
                p.vx = self._rand128() * 4.0 / 33.0
                p.vy = self._rand128() * 4.0 / 33.0
                p.ax, p.ay = -p.vx / 20.0, -p.vy / 20.0
            elif kind == _BURST_FAST:
                # InitDeceleratingBurstFast (EffectManager.cpp:106-115)
                p.vx = self._rand128() / 12.0
                p.vy = self._rand128() / 12.0
                p.ax, p.ay = -p.vx / 19.0, -p.vy / 19.0
            elif kind in (_GATHER60, _GATHER240, _BURST30):
                # InitRandomDir (EffectManager.cpp:204-215)
                ang = self._rng.unit() * 2.0 * math.pi - math.pi
                p.dx, p.dy = math.cos(ang), math.sin(ang)
            elif kind == _BURST_EASE30:
                # InitRandomDirWithSpeed (EffectManager.cpp:468-488)
                ang = self._rng.unit() * 2.0 * math.pi - math.pi
                spd = self._rng.unit() * 1.5 + 1.0
                p.dx, p.dy = math.cos(ang) * spd, math.sin(ang) * spd
            self._alive.append(p)

    def step(self) -> list[SpriteDraw]:
        """推进一帧(物理 + VM), 返回本帧粒子的 SpriteDraw(窗口坐标)。"""
        out: list[SpriteDraw] = []
        alive: list[_Particle] = []
        for p in self._alive:
            if p.kind in (_BURST, _BURST_FAST):
                # UpdatePhysics (EffectManager.cpp:118-123)
                p.x += p.vx
                p.y += p.vy
                p.vx += p.ax
                p.vy += p.ay
            elif p.kind == _GATHER60 or p.kind == _GATHER240:
                # UpdateGather60/240Frames (EffectManager.cpp:218-224/:239-244)
                span = 60.0 if p.kind == _GATHER60 else 240.0
                d = 256.0 - p.timer * 256.0 / span
                p.x = p.dx * d + p.ex
                p.y = p.dy * d + p.ey
            elif p.kind == _BURST30:
                # UpdateBurst30Frames (EffectManager.cpp:247-252)
                d = p.timer * 256.0 / 30.0
                p.x = p.dx * d + p.ex
                p.y = p.dy * d + p.ey
            elif p.kind == _BURST_EASE30:
                # UpdateBurstEaseOut30Frames (EffectManager.cpp:491-500)
                t = p.timer / 90.0
                f = 1.0 - (1.0 - t) * (1.0 - t)
                p.x = f * p.dx * 128.0 + p.ex
                p.y = f * p.dy * 128.0 + p.ey
            p.timer += 1
            p.vm.execute()
            if not p.vm.alive:
                continue
            alive.append(p)
            vm = p.vm
            if not vm.visible or vm.active_sprite_idx < 0:
                continue
            out.append(
                SpriteDraw(
                    f"etama.anm:{vm.active_sprite_idx}",
                    GAME_X + p.x + vm.offset[0],
                    GAME_Y + p.y + vm.offset[1],
                    z=FX_Z,
                    rotation=vm.rotation[2],
                    alpha=vm.color[3],
                    scale_x=vm.scale[0],
                    scale_y=vm.scale[1],
                    color=(vm.color[0], vm.color[1], vm.color[2]),
                    blend_mode=vm.blend_mode,
                )
            )
        self._alive = alive
        return out
