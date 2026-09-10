"""贴图面库: 快照 image 键 → pygame.Surface(带缓存与无数据兜底)。

键两种形态(生产侧见 games/th07/snapshot.py 模块头):
- ``<anm文件名>:<链式全局sprite id>``: 经 schemas parse_anm + engine build_bank
  寻址切图; entry 纹理缺失/键越界一律落兜底。
- 语义键(``enemy:3``/``item:1``/``shot:5``/``misc:hitpoint``): 无 anm 数据时的
  占位, 画按 key 哈希取色的色块(hitpoint 为程序化红点, 在 backend 特判)。
另支持整图键(``title00.jpg`` 等封包内图片文件名): 整图不解包直接当 Surface,
标题/选择页背景用。
"""

from __future__ import annotations

import io

import pygame

from ....engine.anm import AnmBank, build_bank
from ....schemas.anm import AnmFile, parse_anm
from ....schemas.archive import Archive, load_entry


def _fallback_surface(key: str) -> pygame.Surface:
    """按 key 哈希取色的占位块(无数据也能看见场上有什么)。"""
    h = hash(key) & 0xFFFFFF
    surf = pygame.Surface((20, 20), pygame.SRCALPHA)
    surf.fill(((h >> 16) & 0xFF | 0x40, (h >> 8) & 0xFF | 0x40, h & 0xFF | 0x40, 220))
    pygame.draw.rect(surf, (255, 255, 255, 255), surf.get_rect(), 1)
    return surf


class SurfaceBank:
    """anm 文件 → AnmBank → (全局 sprite id → Surface) 二级缓存。"""

    def __init__(self, archive: Archive | None, *, anm_version: int = 2) -> None:
        self._archive = archive
        self._anm_version = anm_version
        self._anms: dict[str, tuple[AnmFile, AnmBank] | None] = {}
        self._surfs: dict[str, pygame.Surface] = {}

    def _anm(self, name: str) -> tuple[AnmFile, AnmBank] | None:
        if name in self._anms:
            return self._anms[name]
        loaded: tuple[AnmFile, AnmBank] | None = None
        if self._archive is not None:
            try:
                anm = parse_anm(
                    load_entry(self._archive, name),
                    version=self._anm_version,
                    flat_layout=False,
                )
                loaded = (anm, build_bank(anm, flat_layout=False))
            except (KeyError, ValueError):
                loaded = None
        self._anms[name] = loaded
        return loaded

    def get(self, key: str) -> pygame.Surface:
        """Image 键 → Surface; 解析失败给占位色块(永不抛)。"""
        surf = self._surfs.get(key)
        if surf is not None:
            return surf
        surf = self._load(key)
        self._surfs[key] = surf
        return surf

    def _load(self, key: str) -> pygame.Surface:
        name, sep, gid_s = key.rpartition(":")
        if sep and name.endswith(".anm") and gid_s.lstrip("-").isdigit():
            loaded = self._anm(name)
            if loaded is not None:
                anm, bank = loaded
                slot = bank.sprites.get(int(gid_s))
                if slot is not None:
                    surf = self._cut(anm, slot.entry, slot.sprite)
                    if surf is not None:
                        return surf
        if self._archive is not None and key.lower().endswith((".jpg", ".png")):
            try:
                surf = pygame.image.load(io.BytesIO(load_entry(self._archive, key)))
                return surf.convert() if pygame.display.get_init() else surf
            except (KeyError, pygame.error):
                pass
        return _fallback_surface(key)

    @staticmethod
    def _cut(anm: AnmFile, entry_idx: int, sprite) -> pygame.Surface | None:
        """从 entry 整图 RGBA 切出 sprite 矩形转 Surface。"""
        entry = anm.entries[entry_idx]
        if entry.rgba is None:
            return None  # 外链纹理未回填(th07 实装数据不存在, 见调查库)
        spr = sprite
        rows = bytearray(spr.w * spr.h * 4)
        for row in range(spr.h):
            src = ((spr.y + row) * entry.tex_width + spr.x) * 4
            rows[row * spr.w * 4 : (row + 1) * spr.w * 4] = entry.rgba[
                src : src + spr.w * 4
            ]
        surf = pygame.image.frombuffer(bytes(rows), (spr.w, spr.h), "RGBA")
        return surf.convert_alpha() if pygame.display.get_init() else surf
