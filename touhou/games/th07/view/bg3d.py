"""3D 背景总装: 按关装配 .std + stg{N}bg.anm, worker 线程渲染, 主线程只取帧。

场景层(bg3d_scene)与光栅化器(bg3d_raster)的粘合 + 资源装配; 资源缺失
(无封包/无贴图)时全件静默返回 None, 后端落回纯色占位。贴图键空间沿用
C 全局 id: stg{N}bg.anm 基址 0x300, 4 面追加文件各 +0x10
(AnmIdx.hpp:98-102, AddedCallback Stage.cpp:706-775)。

线程模型: 重载关(5/7 面 ~15ms)光栅化会顶穿 60fps 主循环预算, 故场景推进
+ 光栅化放单 worker 线程(numpy/PIL 重活释放 GIL); 主线程 step() 只投递
"推进 N 帧"任务并取走最新完成的帧字节(追不上时背景滞后一帧, 不拖主循环)。
任务可合并: worker 忙时主线程的推进量累加进待办, 帧序不乱。pygame Surface
只在主线程构造(worker 不碰 pygame)。
"""

from __future__ import annotations

import threading

import numpy as np
import pygame

from ....engine.anm import AnmScript, build_bank
from ....engine.rng import Rng
from ....schemas.anm import parse_anm
from ....schemas.archive import Archive, load_entry
from ....schemas.stage import StdFile, parse_std
from ..snapshot import GAME_H, GAME_W
from ..world import Th07World
from .bg3d_raster import BgRaster
from .bg3d_scene import BgFrame, BgScene, SpriteTex

_BG_OFFSET = 0x300  # ANM_OFFSET_STAGE_BG (AnmIdx.hpp:98)


def _bg_anm_names(stage_no: int) -> list[str]:
    """一关的背景 anm 清单(4 面 5 个文件, 其余 1 个)。"""
    names = [f"stg{stage_no}bg.anm"]
    if stage_no == 4:
        names += [f"stg4bg{k}.anm" for k in range(2, 6)]  # Stage.cpp:727-750
    return names


class _RenderCore:
    """场景 + 光栅化器 + 资源装配(worker 线程独占的那一份状态)。"""

    def __init__(self, archive: Archive, *, anm_version: int) -> None:
        self._archive = archive
        self._anm_version = anm_version
        self.stage_no = -1
        self.scene: BgScene | None = None
        self._raster: BgRaster | None = None
        self.last_frame: BgFrame | None = None  # 最近渲染的场景描述(探针)

    def load(self, stage_no: int) -> None:
        """装配一关: std + bg anm 组; 主背景文件缺失即整件静默。"""
        self.stage_no = stage_no
        self.scene = None
        self._raster = None
        arc = self._archive
        try:
            std: StdFile = parse_std(load_entry(arc, f"stage{stage_no}.std"))
        except (KeyError, ValueError):
            return
        scripts: dict[int, AnmScript] = {}
        sprites: dict[int, SpriteTex] = {}
        textures: list[np.ndarray] = []
        tex_ids: dict[tuple[int, int], int] = {}  # (文件序, entry序) → 纹理表下标
        for k, name in enumerate(_bg_anm_names(stage_no)):
            base = _BG_OFFSET + k * 0x10
            try:
                anm = parse_anm(
                    load_entry(arc, name),
                    version=self._anm_version,
                    flat_layout=False,
                )
            except (KeyError, ValueError):
                if k == 0:
                    return
                break
            bank = build_bank(anm, flat_layout=False)
            for gid, script in bank.scripts.items():
                scripts[base + gid] = AnmScript(
                    script.instrs, base + script.sprite_base, script.offsets
                )
            for ei, entry in enumerate(anm.entries):
                key = (k, ei)
                if key not in tex_ids:
                    tex_ids[key] = len(textures)
                    textures.append(self._entry_pixels(entry))
            for gid, slot in bank.sprites.items():
                entry = anm.entries[slot.entry]
                spr = slot.sprite
                sprites[base + gid] = SpriteTex(
                    tex_ids[(k, slot.entry)],
                    float(spr.x),
                    float(spr.y),
                    float(spr.x + spr.w),
                    float(spr.y + spr.h),
                    spr.w,
                    spr.h,
                    float(entry.tex_width),
                    float(entry.tex_height),
                    self._tex_opaque(textures[tex_ids[(k, slot.entry)]]),
                )
        scene = BgScene(std, scripts, Rng(0))
        scene.sprites = sprites
        self.scene = scene
        self._raster = BgRaster(textures)

    def render_frames(
        self, stage_no: int, frames: int, waits: list[int]
    ) -> bytes | None:
        """推进 frames 帧并渲染一帧 → RGB 字节; 无场景 None。"""
        if stage_no != self.stage_no:
            self.load(stage_no)
        scene = self.scene
        if scene is None or self._raster is None:
            return None
        scene.tick(waits)
        for _ in range(frames - 1):
            scene.tick(())
        self.last_frame = scene.frame()
        return self._raster.render(self.last_frame).tobytes()

    @staticmethod
    def _entry_pixels(entry) -> np.ndarray:
        """Entry 整图 RGBA → (h, w, 4) uint8; 无内嵌纹理给空数组。"""
        if entry.rgba is None:
            return np.zeros((0, 0, 4), dtype=np.uint8)
        return np.frombuffer(entry.rgba, dtype=np.uint8).reshape(
            entry.tex_height, entry.tex_width, 4
        )

    @staticmethod
    def _tex_opaque(tex: np.ndarray) -> bool:
        """纹理是否无透明 texel(不透明阶段成员判定)。"""
        return tex.size > 0 and bool((tex[:, :, 3] == 255).all())


class StageBg:
    """一局对局的 3D 背景: step(world) 投递推进任务并取最新背景 Surface。

    threaded=False 时同步渲染(测试/调试用); True 时单 worker 线程渲染,
    主线程零阻塞(追不上则背景滞后, 主循环帧率不受影响)。
    """

    def __init__(
        self, archive: Archive | None, *, anm_version: int = 2, threaded: bool = True
    ) -> None:
        self._core = _RenderCore(archive, anm_version=anm_version) if archive else None
        self._threaded = threaded and self._core is not None
        self._frame: BgFrame | None = None  # 同步模式的场景描述(测试探针)
        self._surf: pygame.Surface | None = None
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._stop = False
        # 待办任务(可合并: 推进量累加, 等待值按序追加)
        self._todo_stage = -1
        self._todo_frames = 0
        self._todo_waits: list[int] = []
        # 完成帧(单调序号)
        self._result: bytes | None = None
        self._result_seq = 0
        self._consumed_seq = 0
        self._worker: threading.Thread | None = None
        if self._threaded:
            self._worker = threading.Thread(
                target=self._run, name="bg3d-render", daemon=True
            )
            self._worker.start()

    @property
    def scene(self) -> BgScene | None:
        """当前关场景(同步模式探针; 线程模式属 worker 勿碰)。"""
        return self._core.scene if self._core is not None else None

    def step(self, world: Th07World, frames: int = 1) -> pygame.Surface | None:
        """推进背景 frames 帧(渲染 1 帧), 返回最新完成的背景 Surface。"""
        if self._core is None:
            return None
        if not self._threaded:
            fb = self._core.render_frames(
                world.stage_no, frames, list(world.stage_script_waits)
            )
            if fb is None:
                return None
            self._frame = self._core.last_frame
            img = pygame.image.frombuffer(fb, (GAME_W, GAME_H), "RGB")
            self._surf = img.convert() if pygame.display.get_init() else img
            return self._surf
        with self._lock:
            self._todo_stage = world.stage_no
            self._todo_frames += frames
            self._todo_waits += world.stage_script_waits
            if self._result_seq != self._consumed_seq:
                self._consumed_seq = self._result_seq
                latest = self._result
            else:
                latest = None
        self._wake.set()
        if latest is not None:
            img = pygame.image.frombuffer(latest, (GAME_W, GAME_H), "RGB")
            self._surf = img.convert() if pygame.display.get_init() else img
        return self._surf

    def close(self) -> None:
        """停 worker(daemon 线程, 进程退出也会自动收)。"""
        with self._lock:
            self._stop = True
        self._wake.set()
        if self._worker is not None:
            self._worker.join(timeout=2.0)
            self._worker = None

    def _run(self) -> None:
        """Worker 主循环: 取待办 → 装配/推进/渲染 → 放完成帧。"""
        assert self._core is not None
        while True:
            self._wake.wait()
            self._wake.clear()
            with self._lock:
                if self._stop:
                    return
                stage, frames = self._todo_stage, self._todo_frames
                waits, self._todo_waits = self._todo_waits, []
                self._todo_frames = 0
            if frames <= 0:
                continue
            fb = self._core.render_frames(stage, frames, waits)
            if fb is None:
                continue
            with self._lock:
                self._result = fb
                self._result_seq += 1
