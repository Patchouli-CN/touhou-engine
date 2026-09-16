"""pygame 后端 headless smoke(SDL dummy): 开窗/渲染 N 帧/输入注入/SE/关闭。"""

from __future__ import annotations

import time

import pygame
import pytest

from touhou.engine import InputFrame, SceneSnapshot, SpriteDraw, TextDraw
from touhou.engine.input import Button
from touhou.games.th07.snapshot import GAME_W, GAME_X, GAME_Y, WIN_H, WIN_W
from touhou.games.th07.view import PygameBackend
from touhou.games.th07.view import backend as backend_mod

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


def test_additive_blend_premultiplies_alpha(backend: PygameBackend) -> None:
    """blend=1 预乘: 透明 texel RGB 零贡献; color/全局 alpha 再折且不串缓存。"""
    img = pygame.Surface((2, 2), pygame.SRCALPHA)
    img.fill((200, 100, 50, 0))  # 透明但 RGB 脏(符卡环透明区实机形态)
    img.set_at((0, 0), (200, 100, 50, 255))
    img.set_at((1, 0), (200, 100, 50, 128))
    out = backend._premul_add(img, (255, 255, 255), 255)
    assert out.get_at((1, 1))[:3] == (0, 0, 0)  # 透明零贡献
    assert out.get_at((0, 0))[:3] == (200, 100, 50)  # 不透明原样
    assert out.get_at((1, 0))[0] == 100  # 200*128/255 ≈ 100
    # 同图不同 color 缓存键不串味
    out2 = backend._premul_add(img, (128, 128, 128), 255)
    assert out2.get_at((0, 0))[:3] == (100, 50, 25)
    out3 = backend._premul_add(img, (255, 255, 255), 128)
    assert out3.get_at((0, 0))[0] == 100  # 全局 alpha 再折
    assert backend._premul_add(img, (255, 255, 255), 255).get_at((0, 0))[:3] == (
        200,
        100,
        50,
    )


def test_playfield_clip(backend: PygameBackend) -> None:
    """世界 sprite 裁进游戏区; 边框/面板贴图在快照 HUD 层, 后端不自绘边框。"""
    # 20x20 兜底块压在游戏区左上角: 区外一半必须被裁掉
    snap = SceneSnapshot(
        0, sprites=(SpriteDraw("item:1", float(GAME_X), float(GAME_Y)),)
    )
    backend._render(snap)
    frame = backend._frame_surf
    assert frame is not None
    sprite_rgb = frame.get_at((GAME_X + 5, GAME_Y + 5))[:3]
    assert sprite_rgb != backend_mod._FIELD_COLOR  # 区内画上了
    # 区外不沾 sprite(含原 2px 色环位 —— 色环已退役, 边框走 front.anm 贴图)
    assert frame.get_at((GAME_X - 5, GAME_Y + 100))[:3] == backend_mod._BG_COLOR
    assert frame.get_at((GAME_X - 5, GAME_Y - 5))[:3] == backend_mod._BG_COLOR
    assert frame.get_at((GAME_X - 1, GAME_Y + 100))[:3] == backend_mod._BG_COLOR
    assert frame.get_at((GAME_X + 100, GAME_Y - 1))[:3] == backend_mod._BG_COLOR
    # 右栏/顶底条无 HUD sprite 时保持窗外区底色
    assert frame.get_at((GAME_X + GAME_W + 30, 100))[:3] == backend_mod._BG_COLOR


def test_playfield_chrome_off_no_clip(backend: PygameBackend) -> None:
    """playfield_chrome=False(菜单画面): 不裁剪, 游戏区外 sprite 照常画。"""
    backend.playfield_chrome = False
    snap = SceneSnapshot(0, sprites=(SpriteDraw("item:1", 4.0, 4.0),))
    backend._render(snap)
    frame = backend._frame_surf
    assert frame is not None
    assert frame.get_at((4, 4))[:3] != backend_mod._BG_COLOR  # 角落兜底块画上


def test_window_scale_configurable() -> None:
    """Scale 构造参数默认 2; open 显式传参可覆盖。"""
    b = PygameBackend(None)
    b.open(title="t")
    assert b._scr is not None and b._scr.get_size() == (WIN_W * 2, WIN_H * 2)
    b.close()
    b = PygameBackend(None, scale=3)
    b.open(title="t")
    assert b._scr is not None and b._scr.get_size() == (WIN_W * 3, WIN_H * 3)
    b.close()
    b = PygameBackend(None)
    b.open(title="t", scale=1)
    assert b._scr is not None and b._scr.get_size() == (WIN_W, WIN_H)
    b.close()


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


def test_text_z_below_overlay(backend: PygameBackend) -> None:
    """sprite/text 统一 z 序: 低 z 文本被高 z 覆盖层压住(结局 FadingEffect 序)。"""
    overlay = SpriteDraw(
        "misc:overlay", 320.0, 240.0, z=300.0, alpha=255, color=(10, 20, 30)
    )

    def _has_white() -> bool:
        frame = backend._frame_surf
        assert frame is not None
        for x in range(100, 150):
            for y in range(100, 116):
                if frame.get_at((x, y))[:3] == (255, 255, 255):
                    return True
        return False

    # 低 z 文本(250)在覆盖层(300)之下: 白字像素被盖
    backend._render(
        SceneSnapshot(
            0,
            sprites=(overlay,),
            texts=(TextDraw("ABC", 100.0, 100.0, 15, (255, 255, 255, 255), z=250.0),),
        )
    )
    assert not _has_white()
    frame = backend._frame_surf
    assert frame is not None and frame.get_at((105, 105))[:3] == (10, 20, 30)
    # 缺省 z(1e9): 文本恒在覆盖层之上(旧行为)
    backend._render(
        SceneSnapshot(
            1,
            sprites=(overlay,),
            texts=(TextDraw("ABC", 100.0, 100.0, 15, (255, 255, 255, 255)),),
        )
    )
    assert _has_white()


def test_bossseg_gradient(backend: PygameBackend) -> None:
    """misc:bossseg: 顶=sprite color, 底=各通道>>2 的 4px 竖渐变 (Gui.cpp:1863-1868)。"""
    backend._render(
        SceneSnapshot(
            0,
            sprites=(
                SpriteDraw(
                    "misc:bossseg",
                    64.0,
                    19.0,
                    z=104.0,
                    scale_x=160.0,
                    scale_y=4.0,
                    color=(255, 128, 128),
                ),
            ),
        )
    )
    frame = backend._frame_surf
    assert frame is not None
    assert frame.get_at((100, 19))[:3] == (255, 128, 128)  # 顶行
    assert frame.get_at((100, 22))[:3] == (63, 32, 32)  # 底行 (>>2)
    assert frame.get_at((100, 24))[:3] != (63, 32, 32)  # 条外(高 4px)


def test_home_screenshot(backend: PygameBackend, tmp_path, monkeypatch) -> None:
    """Home 截图: snapshot/th%03d.bmp 首个空位, 640x480 BMP (GameWindow.cpp:107-119)。"""
    monkeypatch.chdir(tmp_path)
    pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_HOME))
    inp = backend.frame((), _snapshot(0))
    assert inp is not None and Button.HOME in inp.pressed
    first = tmp_path / "snapshot" / "th000.bmp"
    assert first.exists()
    assert pygame.image.load(str(first)).get_size() == (WIN_W, WIN_H)
    # 再按一次 → 下一空位 th001.bmp
    pygame.event.post(pygame.event.Event(pygame.KEYUP, key=pygame.K_HOME))
    pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_HOME))
    backend.frame((), _snapshot(1))
    assert (tmp_path / "snapshot" / "th001.bmp").exists()
