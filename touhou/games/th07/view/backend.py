"""pygame 渲染后端: engine RenderBackend 协议的 th07 实现。

窗口 640x480 逻辑像素 × scale; 每帧 = 事件采集 → 快照合成 → flip → 60fps 帧控。
SE 走 schemas/sound.py 的槽位表(wav 从数据包懒加载, 无声卡/无数据静音降级)。
"""

from __future__ import annotations

import io
import math

import pygame

from ....engine import Event, InputFrame, RenderBackend, SceneSnapshot
from ....engine.input import Button
from ....schemas.archive import Archive, load_entry
from ....schemas.sound import SOUND_EFFECTS
from ..snapshot import GAME_H, GAME_W, GAME_X, GAME_Y, WIN_H, WIN_W
from .bank import SurfaceBank

_BG_COLOR = (8, 12, 30)  # 窗外区底色
_PANEL_COLOR = (14, 18, 42)  # 右栏积分面板底色
_FIELD_COLOR = (10, 14, 36)  # 游戏区底色(3D 背景留待后续单, 纯色占位)
_BORDER_COLOR = (58, 66, 108)  # 游戏区边框(原作为边框贴图, 近似色环)

#: 默认键位(th07 原作: Z=射击 X=炸弹 Shift=低速 Ctrl=快进 Esc=暂停)
_KEYMAP: dict[int, Button] = {
    pygame.K_z: Button.SHOT,
    pygame.K_x: Button.BOMB,
    pygame.K_LSHIFT: Button.FOCUS,
    pygame.K_RSHIFT: Button.FOCUS,
    pygame.K_UP: Button.UP,
    pygame.K_DOWN: Button.DOWN,
    pygame.K_LEFT: Button.LEFT,
    pygame.K_RIGHT: Button.RIGHT,
    pygame.K_LCTRL: Button.SKIP,
    pygame.K_RCTRL: Button.SKIP,
    pygame.K_ESCAPE: Button.PAUSE,
}

_TRANSFORM_CAP = 2048  # 变换缓存上限(满即清, 弹幕量化键复用率高)


def _db_to_gain(db_hundredths: int) -> float:
    """DirectSound 百分之一分贝 → pygame 线性音量。"""
    return max(0.0, min(1.0, 10.0 ** (db_hundredths / 2000.0)))


def _load_font(size: int) -> pygame.font.Font:
    for name in ("msgothic", "meiryo", "microsoft yahei", "simhei", None):
        try:
            return pygame.font.SysFont(name, size)
        except Exception:  # noqa: BLE001 - 字体缺失逐个回退
            continue
    return pygame.font.Font(None, size)


class PygameBackend(RenderBackend):
    """RenderBackend 的 pygame 实现(窗口/Surface 合成/键盘/SE)。"""

    def __init__(
        self, archive: Archive | None, *, anm_version: int = 2, scale: int = 2
    ) -> None:
        self.bank = SurfaceBank(archive, anm_version=anm_version)
        self._archive = archive
        self._default_scale = max(1, scale)  # open 未显式传 scale 时的窗口倍率
        self._scr: pygame.Surface | None = None
        self._frame_surf: pygame.Surface | None = None
        self._clock: pygame.time.Clock | None = None
        self._scale = 1
        self._fonts: dict[int, pygame.font.Font] = {}
        self._transforms: dict[tuple, pygame.Surface] = {}
        self._sounds: dict[int, pygame.mixer.Sound | None] = {}
        self._mixer_ok = False
        # 游戏区边框/右栏/裁剪(runner 按 scene.playfield_chrome 同步; 菜单画面关)
        self.playfield_chrome = True

    # ---- 生命周期 ----
    def open(self, *, title: str, scale: int | None = None) -> None:
        pygame.init()
        try:  # 没声卡也能跑, 静音即可
            pygame.mixer.init()
            self._mixer_ok = True
        except pygame.error:
            self._mixer_ok = False
        self._scale = max(1, scale if scale is not None else self._default_scale)
        self._scr = pygame.display.set_mode((WIN_W * self._scale, WIN_H * self._scale))
        pygame.display.set_caption(title)
        self._clock = pygame.time.Clock()
        self._frame_surf = pygame.Surface((WIN_W, WIN_H))

    def close(self) -> None:
        pygame.quit()

    # ---- 每帧 ----
    def frame(
        self, events: tuple[Event, ...], snapshot: SceneSnapshot
    ) -> InputFrame | None:
        inp = self._poll_input()
        if inp is None:
            return None
        self._render(snapshot)
        return inp

    def play_sounds(self, ids: list[int]) -> None:
        if not self._mixer_ok:
            return
        for idx in set(ids):  # 同帧同音去重
            if not 0 <= idx < len(SOUND_EFFECTS):
                continue
            sound = self._sound(idx)
            if sound is not None:
                sound.play()

    # ---- 输入 ----
    def _poll_input(self) -> InputFrame | None:
        pressed: set[Button] = set()
        quit_req = False
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                quit_req = True
            elif ev.type == pygame.KEYDOWN and ev.key in _KEYMAP:
                pressed.add(_KEYMAP[ev.key])
        if quit_req:
            return None
        keys = pygame.key.get_pressed()
        held = {b for code, b in _KEYMAP.items() if keys[code]}
        return InputFrame(held=frozenset(held), pressed=frozenset(pressed))

    # ---- 渲染 ----
    def _render(self, snapshot: SceneSnapshot) -> None:
        assert self._frame_surf is not None
        frame = self._frame_surf
        frame.fill(_BG_COLOR)
        chrome = self.playfield_chrome
        if chrome:
            # 右栏积分面板区(原作右栏贴图背景, 近似纯色)
            pygame.draw.rect(
                frame,
                _PANEL_COLOR,
                (GAME_X + GAME_W, 0, WIN_W - GAME_X - GAME_W, WIN_H),
            )
            pygame.draw.rect(
                frame, _FIELD_COLOR, (GAME_X, GAME_Y, GAME_W, GAME_H)
            )  # 游戏区底色(背景占位)
            # 世界 sprite 裁进游戏区(原作场外包边不露实体)
            frame.set_clip(pygame.Rect(GAME_X, GAME_Y, GAME_W, GAME_H))
        for spr in sorted(snapshot.sprites, key=lambda s: s.z):
            self._blit_sprite(frame, spr)
        frame.set_clip(None)
        if chrome:
            # 游戏区边框环(画在 sprite 之后, 保证边线干净)
            pygame.draw.rect(
                frame,
                _BORDER_COLOR,
                (GAME_X - 2, GAME_Y - 2, GAME_W + 4, GAME_H + 4),
                2,
            )
        for text in snapshot.texts:
            self._blit_text(frame, text.text, text.x, text.y, text.size, text.rgba)
        if self._clock is not None:
            self._blit_text(
                frame,
                f"{self._clock.get_fps():.1f}fps",
                4.0,
                float(WIN_H - 18),
                13,
                (150, 150, 160, 255),
            )
        assert self._scr is not None
        if self._scale == 1:
            self._scr.blit(frame, (0, 0))
        else:
            self._scr.blit(pygame.transform.scale(frame, self._scr.get_size()), (0, 0))
        pygame.display.flip()
        if self._clock is not None:
            self._clock.tick(60)

    def _blit_sprite(self, frame: pygame.Surface, spr) -> None:
        if spr.image == "misc:hitpoint":
            # focus 判定点: 红环白点(程序化, 无贴图)
            x, y = int(spr.x), int(spr.y)
            pygame.draw.circle(frame, (255, 60, 60), (x, y), 5, 1)
            pygame.draw.circle(frame, (255, 255, 255), (x, y), 2)
            return
        img = self.bank.get(spr.image)
        sx = spr.scale * spr.scale_x
        sy = spr.scale * spr.scale_y
        img = self._transform(img, spr.rotation, sx, sy)
        if spr.blend_mode == 1:
            # 加算: src.rgb 按 (color,alpha) 预乘后 BLEND_ADD
            # (AnmManager.cpp:716-722: DESTBLEND=ONE)
            img = self._tint(img, spr.color, spr.alpha)
            frame.blit(
                img, self._dest(img, spr.x, spr.y), special_flags=pygame.BLEND_ADD
            )
        elif spr.color != (255, 255, 255) or spr.alpha < 255:
            img = self._tint(img, spr.color, spr.alpha)
            frame.blit(img, self._dest(img, spr.x, spr.y))
        else:
            frame.blit(img, self._dest(img, spr.x, spr.y))

    @staticmethod
    def _dest(img: pygame.Surface, x: float, y: float) -> tuple[int, int]:
        """中心锚点 → blit 左上角。"""
        return (int(x) - img.get_width() // 2, int(y) - img.get_height() // 2)

    def _transform(
        self, img: pygame.Surface, rotation: float, sx: float, sy: float
    ) -> pygame.Surface:
        """缩放+旋转(量化键缓存; 弧度顺时针为正 → pygame 取负度数)。"""
        flip_x, flip_y = sx < 0, sy < 0
        asx, asy = abs(sx), abs(sy)
        if not rotation and asx == 1.0 and asy == 1.0 and not (flip_x or flip_y):
            return img
        key = (
            id(img),
            round(math.degrees(rotation)),
            round(asx * 16),
            round(asy * 16),
            flip_x,
            flip_y,
        )
        out = self._transforms.get(key)
        if out is None:
            if len(self._transforms) >= _TRANSFORM_CAP:
                self._transforms.clear()
            w = max(1, round(img.get_width() * asx))
            h = max(1, round(img.get_height() * asy))
            out = pygame.transform.scale(img, (w, h))
            if rotation:
                out = pygame.transform.rotozoom(out, -math.degrees(rotation), 1.0)
            if flip_x or flip_y:
                out = pygame.transform.flip(out, flip_x, flip_y)
            self._transforms[key] = out
        return out

    def _tint(
        self, img: pygame.Surface, color: tuple[int, int, int], alpha: int
    ) -> pygame.Surface:
        """颜色/alpha 调制(缓存; alpha 烘焙进像素, 避开 set_alpha 慢路径)。"""
        qa = 255 if alpha >= 248 else alpha & 0xF8
        key = (id(img), color, qa)
        out = self._transforms.get(key)
        if out is None:
            if len(self._transforms) >= _TRANSFORM_CAP:
                self._transforms.clear()
            out = img.copy()
            if color != (255, 255, 255):
                out.fill((*color, 255), special_flags=pygame.BLEND_MULT)
            if qa < 255:
                alpha_px = pygame.surfarray.pixels_alpha(out)
                alpha_px[:] = (alpha_px.astype("uint16") * qa // 255).astype("uint8")
            self._transforms[key] = out
        return out

    def _font(self, size: int) -> pygame.font.Font:
        font = self._fonts.get(size)
        if font is None:
            font = _load_font(size)
            self._fonts[size] = font
        return font

    def _blit_text(
        self,
        frame: pygame.Surface,
        text: str,
        x: float,
        y: float,
        size: int,
        rgba: tuple[int, int, int, int],
    ) -> None:
        surf = self._font(size).render(text, True, rgba[:3])
        if rgba[3] < 255:
            surf.set_alpha(rgba[3])
        frame.blit(surf, (int(x), int(y)))

    # ---- SE ----
    def _sound(self, idx: int) -> pygame.mixer.Sound | None:
        if idx in self._sounds:
            return self._sounds[idx]
        sound: pygame.mixer.Sound | None = None
        if self._archive is not None:
            spec = SOUND_EFFECTS[idx]
            try:
                sound = pygame.mixer.Sound(
                    io.BytesIO(load_entry(self._archive, spec.file_name))
                )
                sound.set_volume(_db_to_gain(spec.volume))
            except (KeyError, pygame.error):
                sound = None
        self._sounds[idx] = sound
        return sound
