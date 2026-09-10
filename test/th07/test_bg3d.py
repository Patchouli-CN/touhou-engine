"""3D 背景测试: std 脚本/相机/雾的单元(合成 std) + 光栅化器合成纹理 + needs_data 全链。"""

from __future__ import annotations

import numpy as np
import pygame
import pytest

from touhou.engine import InputFrame
from touhou.engine.rng import Rng
from touhou.games.th07.view.bg3d_raster import BgRaster, _homography
from touhou.games.th07.view.bg3d_scene import (
    BgFrame,
    BgScene,
    QuadCmd,
    _interp_cubic,
    _stage_ease,
)
from touhou.schemas import stage_script as ss
from touhou.schemas.stage import StdFile

from .conftest import DATA, needs_data


def _std(script: list) -> StdFile:
    """合成最小 std(无物件无实例, 只有脚本)。"""
    return StdFile("t", (), (), [], [], script)


def _scene(script: list) -> BgScene:
    return BgScene(_std(script), {}, Rng(0))


# ---- std 脚本执行(Stage.cpp OnUpdate 口径) ----
def test_ease_modes() -> None:
    assert _stage_ease(0.5, 0) == 0.5
    assert _stage_ease(0.5, 1) == 0.75  # out quad: 1-(1-t)^2
    assert _stage_ease(0.5, 4) == 0.25  # in quad: t^2
    assert _interp_cubic(0.0, 10.0, 0.0, 0.0, 0.5) == 5.0


def test_cam_pos_interp() -> None:
    """CamPos 目标 + CamPosInterp 时长: 相机按 ease 从旧值走向新值。"""
    sc = _scene(
        [
            ss.CamPos(frame=0, x=100.0, y=0.0, z=0.0),
            ss.CamPosInterp(frame=0, duration=10, ease_mode=0),
        ]
    )
    sc.tick(())  # 指令生效, 第 1 步插值
    assert sc.cam_pos[0] == pytest.approx(10.0)
    for _ in range(9):
        sc.tick(())
    assert sc.cam_pos[0] == pytest.approx(100.0)


def test_cam_pos_no_interp_snaps() -> None:
    """无进行中插值时 CamPos 直写相机 (Stage.cpp:237-240)。"""
    sc = _scene([ss.CamPos(frame=0, x=50.0, y=1.0, z=2.0)])
    sc.tick(())
    assert sc.cam_pos == [50.0, 1.0, 2.0]


def test_fog_interp() -> None:
    """SetFog 记目标, FogInterp 从当前值渐变过去 (Stage.cpp:217-227/447-475)。"""
    sc = _scene(
        [
            ss.SetFog(frame=0, color=0xFF000000, near=100.0, far=500.0),
            # 真实 std 是 FogInterp→SetFog 成对(先捕当前值为起点再立目标)
            ss.FogInterp(frame=1, duration=10),
            ss.SetFog(frame=1, color=0xFFFFFFFF, near=200.0, far=600.0),
        ]
    )
    sc.tick(())  # frame 0: 雾立黑
    assert sc.fog_rgba == 0xFF000000
    sc.tick(())  # frame 1: 目标改白, 渐变起步(t=0.1, 非端点)
    assert sc.fog_rgba not in (0xFF000000, 0xFFFFFFFF)
    for _ in range(9):
        sc.tick(())
    assert sc.fog_rgba == 0xFFFFFFFF
    assert sc.fog_near == pytest.approx(200.0)
    assert sc.fog_far == pytest.approx(600.0)


def test_jump_and_halt() -> None:
    """Jump 改指改时刻; Halt 停轴(script_time 冻结)。"""
    sc = _scene(
        [
            ss.CamPos(frame=0, x=1.0, y=0.0, z=0.0),
            ss.Jump(frame=1, instr_idx=3, time=100),
            ss.CamPos(frame=2, x=2.0, y=0.0, z=0.0),
            ss.Halt(frame=100),
            ss.CamPos(frame=101, x=3.0, y=0.0, z=0.0),
        ]
    )
    sc.tick(())  # frame 0: CamPos(1)
    assert sc.cam_pos[0] == 1.0
    sc.tick(())  # frame 1: Jump → idx 3, time 100; Halt 停轴
    assert sc.script_time == 100
    sc.tick(())
    assert sc.script_time == 100  # 停轴冻结
    assert sc.cam_pos[0] == 1.0  # Halt 之后的指令不再执行


def test_wait_label_consumption() -> None:
    """ECL 等待值 → 扫 WaitLabel 跳转并清等待 (Stage.cpp:167-185)。"""
    sc = _scene(
        [
            ss.Halt(frame=0),
            ss.WaitLabel(frame=50, label=7),
            ss.CamPos(frame=50, x=9.0, y=0.0, z=0.0),
        ]
    )
    sc.tick(())
    assert sc.script_time == 0  # Halt 停轴
    sc.tick([7])  # ECL 写 7 → 跳到 label 7 之后(帧尾 script_time++ 与 C 同)
    assert sc.wait_time == 0
    assert sc.script_time == 51
    assert sc.cam_pos[0] == 9.0


def test_wait_label_unmatched_kept() -> None:
    """等待值无匹配 label: 保留待下帧重试 (C scriptWaitTime 不清)。"""
    sc = _scene([ss.CamPos(frame=100, x=1.0, y=0.0, z=0.0)])
    sc.tick([5])
    assert sc.wait_time == 5


def test_poskey_sets_origin() -> None:
    sc = _scene([ss.PosKey(frame=0, x=1.0, y=2.0, z=3.0)])
    sc.tick(())
    assert sc.world_origin == [1.0, 2.0, 3.0]


# ---- 单应(射影映射系数) ----
def test_homography_roundtrip() -> None:
    pts = (10.0, 20.0, 110.0, 25.0, 15.0, 90.0, 105.0, 85.0)
    uv = (0.0, 0.0, 64.0, 0.0, 0.0, 64.0, 64.0, 64.0)
    a, b, c, d, e, f, g, h = _homography(pts, uv)
    for i in range(4):
        x, y = pts[2 * i], pts[2 * i + 1]
        w = g * x + h * y + 1.0
        assert (a * x + b * y + c) / w == pytest.approx(uv[2 * i])
        assert (d * x + e * y + f) / w == pytest.approx(uv[2 * i + 1])


# ---- 光栅化器(合成纹理) ----
def _tex(color: tuple[int, int, int, int], size: int = 8) -> np.ndarray:
    t = np.zeros((size, size, 4), dtype=np.uint8)
    t[:, :] = color
    return t


def _cmd(**kw) -> QuadCmd:
    base = dict(
        pts=(0.0, 0.0, 8.0, 0.0, 0.0, 8.0, 8.0, 8.0),
        uv=(0.0, 0.0, 8.0, 0.0, 0.0, 8.0, 8.0, 8.0),
        tex_id=0,
        color=(255, 255, 255, 255),
        blend=0,
        fog=(1.0, 1.0, 1.0, 1.0),
        sort_z=1.0,
        zwrite_disable=0,
        tex_opaque=True,
        pass_idx=0,
    )
    base.update(kw)
    return QuadCmd(**base)


def _render(r: BgRaster, quads: list[QuadCmd], fog=(10, 20, 30)) -> np.ndarray:
    return r.render(BgFrame(fog, 0, tuple(quads)))


def test_raster_fog_base() -> None:
    r = BgRaster([_tex((200, 0, 0, 255))])
    fb = _render(r, [])
    assert tuple(fb[0, 0]) == (10, 20, 30)  # 雾色打底


def test_raster_opaque_painter() -> None:
    """不透明远→近覆写: 近者胜(等价 zbuffer)。"""
    r = BgRaster([_tex((255, 0, 0, 255)), _tex((0, 0, 255, 255))])
    far = _cmd(tex_id=0, sort_z=500.0)
    near = _cmd(tex_id=1, sort_z=100.0)
    fb = _render(r, [far, near])
    assert tuple(fb[4, 4]) == (0, 0, 255)  # near 蓝盖 far 红


def test_raster_translucent_blend() -> None:
    """半透明 quad: src*a + dst*(1-a)。"""
    r = BgRaster([_tex((255, 255, 255, 255))])
    fb = _render(r, [_cmd(color=(255, 255, 255, 128), tex_opaque=False)])
    exp = 255 * (128 / 255) + 10 * (1 - 128 / 255)
    assert fb[4, 4][0] == pytest.approx(exp, abs=2)
    assert exp > 10  # 语义锚: 比底色亮


def test_raster_additive() -> None:
    r = BgRaster([_tex((100, 100, 100, 255))])
    fb = _render(r, [_cmd(blend=1, tex_opaque=False)])
    assert tuple(fb[4, 4]) == (10 + 100, 20 + 100, 30 + 100)


def test_raster_full_fog_fill() -> None:
    """全雾 quad(不透明): 输出即雾色。"""
    r = BgRaster([_tex((255, 0, 0, 255))])
    fb = _render(r, [_cmd(fog=(0.0, 0.0, 0.0, 0.0))])
    assert tuple(fb[4, 4]) == (10, 20, 30)


def test_raster_clear_color() -> None:
    r = BgRaster([_tex((255, 0, 0, 255))])
    fb = r.render(BgFrame((10, 20, 30), 0xFF000000 | (7 << 16), ()))
    assert tuple(fb[100, 100]) == (7, 0, 0)  # opcode 13 清屏色盖底


def test_raster_persp_quad() -> None:
    """透视 quad: 单应映射采样正确区域(红纹理 → 梯形 quad 内部红)。"""
    r = BgRaster([_tex((255, 0, 0, 255))])
    cmd = _cmd(pts=(0.0, 100.0, 200.0, 100.0, 50.0, 0.0, 150.0, 0.0))
    fb = _render(r, [cmd])
    assert tuple(fb[50, 100]) == (255, 0, 0)  # 梯形内部
    assert tuple(fb[200, 100]) == (10, 20, 30)  # 外部保持雾色


# ---- facade 静默降级 ----
def test_stage_bg_no_archive_silent() -> None:
    from touhou.games.th07.view.bg3d import StageBg

    class W:
        stage_no = 1
        stage_script_waits: list[int] = []

    bg = StageBg(None)
    assert bg.step(W()) is None  # 无封包: 整件静默


# ---- needs_data 全链 ----
class _W:
    """world duck(背景只读 stage_no/stage_script_waits)。"""

    stage_no = 1
    stage_script_waits: list[int] = []


@needs_data
def test_stage1_bg_content() -> None:
    """一面背景: 装配成功且产出非纯色帧(雾中道路场景)。"""
    from touhou.games.th07.view.bg3d import StageBg
    from touhou.schemas.archive import open_archive

    bg = StageBg(open_archive(str(DATA)), threaded=False)
    w = _W()
    w.stage_no = 1
    surf = None
    for _ in range(400):
        surf = bg.step(w)
    assert surf is not None
    arr = np.asarray(pygame.surfarray.pixels3d(surf))
    assert len(np.unique(arr.reshape(-1, 3), axis=0)) > 500  # 非纯色
    assert bg._frame is not None and len(bg._frame.quads) > 0


@needs_data
def test_stage2_bg_content() -> None:
    """二面背景: 装配成功且产出非纯色帧(樱并木场景)。"""
    from touhou.games.th07.view.bg3d import StageBg
    from touhou.schemas.archive import open_archive

    bg = StageBg(open_archive(str(DATA)), threaded=False)
    w = _W()
    w.stage_no = 2
    surf = None
    for _ in range(400):
        surf = bg.step(w)
    assert surf is not None
    arr = np.asarray(pygame.surfarray.pixels3d(surf))
    assert len(np.unique(arr.reshape(-1, 3), axis=0)) > 500


@needs_data
def test_stage6_wait_label_jump() -> None:
    """六面: ECL 等待值驱动 std 脚本跳 WaitLabel(真数据 label 1 → 2000)。"""
    from touhou.games.th07.view.bg3d import StageBg
    from touhou.schemas.archive import open_archive

    bg = StageBg(open_archive(str(DATA)), threaded=False)
    w = _W()
    w.stage_no = 6
    bg.step(w)
    sc = bg.scene
    assert sc is not None
    pre_idx = sc.instr_idx
    w.stage_script_waits = [1]  # 真 stage6.std 有 WaitLabel(2000, 1)
    bg.step(w)
    assert sc.instr_idx > pre_idx  # 已跳过 WaitLabel
    assert sc.script_time in (2000, 2001)  # 帧尾 ++ 与否取决于后续指令
    assert sc.wait_time == 0


@needs_data
def test_game_scene_bg_chain() -> None:
    """全链: 世界 + GameScene(同步背景) → frame_bg → 后端合成像素。"""
    from touhou.engine import InputFrame
    from touhou.games.th07.compose import compose
    from touhou.games.th07.view import PygameBackend
    from touhou.games.th07.view.bg3d import StageBg
    from touhou.games.th07.view.game_scene import GameScene
    from touhou.games.th07.world import compose_world

    w = compose_world(compose(), character=0, difficulty=1, seed=42)
    bg = StageBg(w.archive, threaded=False)
    scene = GameScene(w, on_exit=lambda: None, bg=bg)
    backend = PygameBackend(w.archive, scale=1)
    backend.open(title="t", scale=1)
    for _ in range(120):
        scene.step(InputFrame())
        backend.set_background(scene.frame_bg)
        backend._render(scene.snapshot())
    surf = scene.frame_bg
    assert surf is not None
    arr = pygame.surfarray.pixels3d(backend._frame_surf)
    # 游戏区不再是纯色占位 (10,14,36)
    region = arr[32 : 32 + 384, 16 : 16 + 448]
    assert len(np.unique(region.reshape(-1, 3), axis=0)) > 100
    backend.close()
    bg.close()


@needs_data
def test_threaded_bg_produces() -> None:
    """Worker 模式: 投递推进任务后拿到完成帧, close 干净。"""
    import time

    from touhou.games.th07.view.bg3d import StageBg
    from touhou.schemas.archive import open_archive

    bg = StageBg(open_archive(str(DATA)), threaded=True)
    w = _W()
    w.stage_no = 1
    surf = None
    for _ in range(600):
        surf = bg.step(w)
        if surf is not None:
            break
        time.sleep(0.001)
    assert surf is not None
    arr = np.asarray(pygame.surfarray.pixels3d(surf))
    assert len(np.unique(arr.reshape(-1, 3), axis=0)) > 100
    bg.close()


@needs_data
def test_script_wait_wiring() -> None:
    """ECL SET_SCRIPT_WAIT_TIME → world.stage_script_waits 透出(每 tick 清)。"""
    from touhou.games.th07.compose import compose
    from touhou.games.th07.world import compose_world

    w = compose_world(compose(), character=0, difficulty=1, seed=42)
    assert w.host is not None
    assert w.host.on_script_wait == w.stage_script_waits.append
    w.stage_script_waits.append(3)
    w.tick(InputFrame())
    assert w.stage_script_waits == []  # 帧首清空
