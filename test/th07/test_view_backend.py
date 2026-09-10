"""pygame 后端 headless smoke(SDL dummy): 开窗/渲染 N 帧/输入注入/SE/关闭。"""

from __future__ import annotations

import time

import pygame
import pytest

from touhou.engine import InputFrame, SceneSnapshot, SpriteDraw, TextDraw
from touhou.engine.input import Button
from touhou.games.th07.view import PygameBackend

from .conftest import needs_data


def _snapshot(frame: int) -> SceneSnapshot:
    """合成一帧: 语义键/anm 键(无数据走兜底)/加算/文本各覆盖一点。"""
    return SceneSnapshot(
        frame,
        sprites=(
            SpriteDraw("item:1", 100.0, 100.0),
            SpriteDraw("etama.anm:120", 200.0, 150.0, rotation=0.5),
            SpriteDraw("enemy:3", 300.0, 200.0, scale_x=-1.0, blend_mode=1, alpha=180),
            SpriteDraw("misc:hitpoint", 224.0, 400.0),
        ),
        texts=(TextDraw("SCORE 000000000", 412.0, 24.0),),
    )


@pytest.fixture
def backend():
    b = PygameBackend(None)
    b.open(title="test", scale=1)
    yield b
    b.close()


def test_render_frames_and_close(backend: PygameBackend) -> None:
    """无数据: 兜底色块渲染 30 帧不炸。"""
    for i in range(30):
        inp = backend.frame((), _snapshot(i))
        assert inp is not None


def test_input_injection(backend: PygameBackend) -> None:
    """KEYDOWN/按住 → InputFrame pressed/held; QUIT → None。"""
    backend.frame((), _snapshot(0))  # 清掉积压事件
    pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_z))
    inp = backend.frame((), _snapshot(1))
    assert inp is not None
    assert Button.SHOT in inp.pressed
    # held 取自 pygame.key.get_pressed()(物理键态), 注入事件改变不了它,
    # dummy 驱动下无法模拟按住 —— held 映射由 _KEYMAP 查表保证, 此处不验
    pygame.event.post(pygame.event.Event(pygame.KEYUP, key=pygame.K_z))
    pygame.event.post(pygame.event.Event(pygame.QUIT))
    assert backend.frame((), _snapshot(2)) is None


def test_play_sounds_no_data_no_crash(backend: PygameBackend) -> None:
    """无数据/无声卡: play_sounds 静默降级, 越界 idx 不炸。"""
    backend.play_sounds([0, 5, 999])


@needs_data
def test_real_data_surfaces_and_fps() -> None:
    """真机: etama 贴图键解出真 surface; 一面 900 帧渲染吞吐记录。"""
    from touhou.games.th07.compose import compose
    from touhou.games.th07.world import compose_world

    w = compose_world(compose(), seed=42)
    b = PygameBackend(w.archive)
    try:
        surf = b.bank.get("etama.anm:120")
        assert surf.get_width() > 0 and surf.get_height() > 0
        assert surf.get_width() != 20  # 不是兜底块
        b.open(title="test", scale=1)
        snap = w.tick(InputFrame())
        t0 = time.perf_counter()
        frames = 900
        for _ in range(frames):
            snap = w.tick(InputFrame())
            b._render(snap)
        dt = time.perf_counter() - t0
        fps = frames / dt
        print(f"\nsim+render {frames} 帧: {dt:.2f}s -> {fps:.0f}fps")
        assert fps > 30.0
    finally:
        b.close()
