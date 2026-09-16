"""结局/staff roll 画面: EndingPlayer(engine/ending.py)的 scene 化驱动。

布局对照 Ending.cpp: 背景 @b 整图按源矩形 (0, bg_y, 640, 480) 滚动
(DrawEndingRect, :72-74); 立绘 @a = staff01.anm VM; 文本行 (64, i*16+392)
(:496-497); 淡色覆盖 FadingEffect 由 backend 的 misc:overlay 键画。
"""

from __future__ import annotations

import io
from collections.abc import Callable

import pygame

from ....engine import InputFrame, SceneSnapshot, SpriteDraw, TextDraw
from ....engine.anm import AnmBank, AnmMachine, build_bank
from ....engine.ending import EndingPlayer
from ....engine.input import Button
from ....engine.rng import Rng
from ....schemas.anm import parse_anm
from ....schemas.archive import Archive, load_entry
from .. import result as result_flow
from ..world import Th07World
from .music import BgmPlayer
from .scene import Scene

_STAFF_ANM = "staff01.anm"  # Ending.cpp:468 (ANM_OFFSET_STAFF 0x600 ↔ 链式基址 0)

_TEXT_X = 64.0  # Ending.cpp:496-497
_TEXT_Y0 = 392.0
_TEXT_STEP = 16.0
_TEXT_SLOTS = 15  # MAX_ENDING_SPRITES (Ending.hpp:15)
_TEXT_SIZE = 15

_SKIP_LOOP_CAP = 100000  # 确认跳过的逐帧排空上限(防坏脚本死循环)


class EndingScene(Scene):
    """结局画面: 包 EndingPlayer 逐帧播 world.ending; 播完/确认跳过进结算。

    确认(SHOT)按下 = 跳过整段(简化: 原版只支持按住快进/跳行,
    Ending.cpp:57-61/200-205); 看过结局后按住 SKIP(Ctrl) 4 倍快进
    (hasSeenEnding, :475-490)。
    """

    def __init__(
        self,
        world: Th07World,
        *,
        anm_version: int = 2,
        music: BgmPlayer | None = None,
        on_done: Callable[[Th07World], Scene],
    ) -> None:
        super().__init__()
        assert world.ending is not None  # 只在 world.ending 出现时进本画面
        self._world = world
        self._on_done = on_done
        self._music = music
        self._archive: Archive | None = world.archive
        self._player = EndingPlayer(world.ending.ops, loader=self._load_end_file)
        # hasSeenEnding (Ending.cpp:475-490): 本机体本难度已有通关记录
        row = world.store.clrd[world.character]
        d = world.difficulty
        if world.th07.num_retries == 0:
            self._has_seen = row["with_retries"][d] >= 6  # 6 = 通过面数(99 ↔ >=6)
        else:
            self._has_seen = row["without_retries"][d] >= 6
        self._bank = self._load_staff_bank(anm_version)
        self._face_vms: dict[int, AnmMachine] = {}
        self._face_keys: dict[int, tuple[int, int]] = {}
        self._faces_version = -1
        self._bg_heights: dict[str, int | None] = {}
        self._frame = 0

    # ---- 资源 ----
    def _load_end_file(self, name: str) -> bytes | None:
        """@F 续载(LoadEnding, Ending.cpp:272-276); 失败 = 结局结束。"""
        if self._archive is None:
            return None
        try:
            return load_entry(self._archive, name)
        except (KeyError, ValueError, OSError):
            return None

    def _load_staff_bank(self, anm_version: int) -> AnmBank | None:
        if self._archive is None:
            return None
        try:
            return build_bank(
                parse_anm(
                    load_entry(self._archive, _STAFF_ANM),
                    version=anm_version,
                    flat_layout=False,
                ),
                flat_layout=False,
            )
        except (KeyError, ValueError):
            return None

    def _bg_height(self, name: str | None) -> int | None:
        """背景整图高(滚动源矩形换算用); 取不到 = 不画该背景。"""
        if name is None:
            return None
        if name not in self._bg_heights:
            h: int | None = None
            if self._archive is not None:
                try:
                    h = pygame.image.load(
                        io.BytesIO(load_entry(self._archive, name))
                    ).get_height()
                except (KeyError, ValueError, pygame.error):
                    h = None
            self._bg_heights[name] = h
        return self._bg_heights[name]

    # ---- Scene 接口 ----
    def step(self, inp: InputFrame) -> None:
        p = self._player
        if Button.SHOT in inp.pressed:
            for _ in range(_SKIP_LOOP_CAP):
                if p.done:
                    break
                p.tick()  # 确认跳过: 原地排空到 @z
        else:
            steps = 4 if self._has_seen and Button.SKIP in inp.held else 1
            for _ in range(steps):
                if p.done:
                    break
                # 按住确认 = 行间隔换 topLineDelay (ParseEndFile, Ending.cpp:400-404)
                p.tick(advance_held=Button.SHOT in inp.held)
        self._drain_music()
        self._sync_faces()
        for vm in self._face_vms.values():
            vm.execute()  # OnUpdate 的 ExecuteScript (Ending.cpp:52-55)
        if p.done and not self.done:
            result_flow.finish_ending(self._world)  # DeletedCallback → 结算 (:520)
            self.done = True
        self._frame += 1

    def snapshot(self) -> SceneSnapshot:
        p = self._player
        sprites: list[SpriteDraw] = []
        h = self._bg_height(p.bg_name)
        if h is not None and p.bg_name is not None:
            # DrawEndingRect 源矩形 (0, bg_y) ↔ 整图上移 bg_y (中心锚换算)
            sprites.append(SpriteDraw(p.bg_name, 320.0, h / 2 - p.bg_y, z=-1.0))
        for idx in sorted(self._face_vms):
            vm = self._face_vms[idx]
            if not vm.visible or vm.active_sprite_idx < 0 or vm.color[3] <= 0:
                continue
            x, y = vm.pos[0], vm.pos[1]
            if vm.anchor & 3 and self._bank is not None:
                slot = self._bank.sprites.get(vm.active_sprite_idx)
                if slot is not None:  # 左/顶缘 → 中心锚 (AnmManager.cpp:1011-1041)
                    if vm.anchor & 1:
                        x += slot.sprite.w * vm.scale[0] / 2
                    if vm.anchor & 2:
                        y += slot.sprite.h * vm.scale[1] / 2
            sprites.append(
                SpriteDraw(
                    f"{_STAFF_ANM}:{vm.active_sprite_idx}",
                    x,
                    y,
                    z=float(idx),
                    rotation=vm.rotation[2],
                    alpha=vm.color[3],
                    scale_x=vm.scale[0],
                    scale_y=vm.scale[1],
                    color=(vm.color[0], vm.color[1], vm.color[2]),
                    blend_mode=vm.blend_mode,
                )
            )
        overlay = p.fade_overlay()
        if overlay is not None:
            # FadingEffect 全屏覆盖, 最顶(压住文本层, Ending.cpp:99-165);
            # 后端 sprite/text 统一按 z 排序, 文本 z=250 < 覆盖层 300
            sprites.append(
                SpriteDraw(
                    "misc:overlay",
                    320.0,
                    240.0,
                    z=300.0,
                    alpha=overlay[3],
                    color=overlay[:3],
                )
            )
        texts = [
            TextDraw(
                line.text,
                _TEXT_X,
                _TEXT_Y0 + i * _TEXT_STEP,
                _TEXT_SIZE,
                (
                    (line.color >> 16) & 255,
                    (line.color >> 8) & 255,
                    line.color & 255,
                    255,
                ),
                z=250.0,
            )
            for i, line in enumerate(p.texts[:_TEXT_SLOTS])
        ]
        return SceneSnapshot(self._frame, tuple(sprites), tuple(texts))

    def next_scene(self) -> Scene | None:
        return self._on_done(self._world)

    # ---- 内部 ----
    def _drain_music(self) -> None:
        """@m/@M 音乐事件 → BgmPlayer (Ending.cpp:299-307)。"""
        events, self._player.music_events = self._player.music_events, []
        if self._music is None:
            return
        for kind, arg in events:
            if kind == "play":
                self._music.play(arg)
            else:
                self._music.fadeout(arg)

    def _sync_faces(self) -> None:
        """@a/@R/@F 立绘槽位同步(faces_version 边沿才动)。"""
        p = self._player
        if p.faces_version == self._faces_version:
            return
        self._faces_version = p.faces_version
        for vm_idx in set(self._face_vms) - set(p.faces):
            del self._face_vms[vm_idx]
            self._face_keys.pop(vm_idx, None)
        scripts = self._bank.scripts if self._bank is not None else {}
        for vm_idx, (script, sprite) in p.faces.items():
            if self._face_keys.get(vm_idx) == (script, sprite):
                continue
            m = AnmMachine(Rng(0))  # view VM 专用, 与 sim 无关
            m.start(scripts.get(script))  # ExecuteAnmIdx (Ending.cpp:259)
            m.active_sprite_idx = sprite  # SetActiveSprite (:260)
            self._face_vms[vm_idx] = m
            self._face_keys[vm_idx] = (script, sprite)
