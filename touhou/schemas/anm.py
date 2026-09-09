"""ANM 贴图包解析(entry/sprite/纹理/脚本)。"""

from __future__ import annotations

import struct

import msgspec
import numpy as np

from .anm_script import Instruction, decode_script
from .exceptions import ParseError

# 纹理 format → 每像素字节数; 格式数学出处 old/touhou/schema/anm.py
# (AnmManager.cpp g_TextureBytesPerPixel): 1=A8R8G8B8, 2=A1R5G5B5, 3=R5G6B5,
# 4=R8G8B8, 5=A4R4G4B4; 文件内字节序均为 D3D 小端
_BYTES_PER_PIXEL = {1: 4, 2: 2, 3: 2, 4: 3, 5: 2}

_ENTRY_HEADER_SIZE = 64  # AnmRawEntry 到 spriteOffsets 之前
_EMBEDDED_HEADER_SIZE = 16  # ZunImageInfoEmbedded 到 data 之前


class AnmSprite(msgspec.Struct, frozen=True):
    """一个 sprite: 纹理内的像素矩形(x/y/w/h 取整, f 前缀为未取整视图)。"""

    id: int
    x: int
    y: int
    w: int
    h: int
    fx: float = 0.0
    fy: float = 0.0
    fw: float = 0.0
    fh: float = 0.0


class AnmEntry(msgspec.Struct):
    """一个 .anm entry: 一张纹理 + 若干 sprite。

    rgba 为整图 RGBA; 外链纹理(hasData=0 且名字非 @ 开头)解析时为 None,
    由调用方按 name/color_key/format 自行取图后回填。
    """

    name: str
    format: int
    color_key: int
    width: int  # 逻辑宽(entry 头), 内嵌纹理时等于纹理宽
    height: int
    tex_width: int
    tex_height: int
    rgba: bytes | None
    sprites: dict[int, AnmSprite] = msgspec.field(default_factory=dict)

    def __repr__(self) -> str:
        # rgba 是整图字节串, 不进 repr
        return (
            f"AnmEntry(name={self.name!r}, format={self.format!r}, "
            f"width={self.width!r}, height={self.height!r}, "
            f"tex_width={self.tex_width!r}, tex_height={self.tex_height!r}, "
            f"sprites={self.sprites!r})"
        )


class AnmFile(msgspec.Struct):
    """解析后的 .anm: entry 链 + 各 entry 的脚本表。"""

    entries: list[AnmEntry]
    scripts: list[dict[int, list[Instruction]]]


def decode_texture(fmt: int, width: int, height: int, data: bytes) -> bytes:
    """把 D3D 小端像素解码成 RGBA 字节串。"""
    # 解码数学出处 old/touhou/schema/anm.py _decode_texture
    n = width * height
    if fmt == 1:  # A8R8G8B8, 文件内 B,G,R,A
        out = bytearray(n * 4)
        out[0::4] = data[2::4]
        out[1::4] = data[1::4]
        out[2::4] = data[0::4]
        out[3::4] = data[3::4]
        return bytes(out)
    if fmt in (2, 3, 5):
        v = np.frombuffer(data, dtype="<u2", count=n).astype(np.uint32)
        if fmt == 5:  # A4R4G4B4: b:4 g:4 r:4 a:4 (低位起)
            r = ((v >> 8) & 0xF) * 17
            g = ((v >> 4) & 0xF) * 17
            b = (v & 0xF) * 17
            a = ((v >> 12) & 0xF) * 17
        elif fmt == 2:  # A1R5G5B5: b:5 g:5 r:5 a:1
            r = ((v >> 10) & 0x1F) * 255 // 31
            g = ((v >> 5) & 0x1F) * 255 // 31
            b = (v & 0x1F) * 255 // 31
            a = np.where(v & 0x8000, 255, 0)
        else:  # fmt == 3, R5G6B5: b:5 g:6 r:5, 无 alpha
            r = ((v >> 11) & 0x1F) * 255 // 31
            g = ((v >> 5) & 0x3F) * 255 // 63
            b = (v & 0x1F) * 255 // 31
            a = np.full(n, 255, dtype=np.uint32)
        return np.stack([r, g, b, a], axis=1).astype(np.uint8).tobytes()
    out = bytearray(n * 4)
    if fmt == 4:  # R8G8B8, 文件内 B,G,R, 无 alpha
        out[0::4] = data[2::3]
        out[1::4] = data[1::3]
        out[2::4] = data[0::3]
        out[3::4] = b"\xff" * n
    else:
        raise ParseError(f"未知 anm 纹理 format: {fmt}")
    return bytes(out)


def _parse_entry(data: bytes, base: int, version: int) -> AnmEntry:
    # entry 头字段布局出处 old/touhou/schema/anm.py _parse_entry
    (
        num_sprites,
        _num_scripts,
        _tex_idx,
        width,
        height,
        fmt,
        color_key,
        name_offset,
        _sprite_idx_offset,
        _mipmap_name_offset,
        file_version,
        _priority,
        texture_offset,
    ) = struct.unpack_from("<13i", data, base)
    if file_version != version:
        raise ParseError(f"anm 版本不符: {file_version} (期望 {version})")
    has_data = data[base + 52]  # AnmRawEntry.hasData(13×i32 之后的 u8)
    end = data.index(b"\0", base + name_offset)
    name = data[base + name_offset : end].decode("latin-1")

    if not has_data:
        if name.startswith("@"):
            # CreateEmptyTexture: 按 entry 头宽高建全透明空纹理
            tex_w, tex_h = width, height
            rgba: bytes | None = bytes(width * height * 4)
        else:
            # 外链纹理: 返回数据描述(rgba=None), 由调用方按
            # name/color_key/format 取图回填 —— 不注入 Callable
            tex_w, tex_h = width, height
            rgba = None
    else:
        # ZunImageInfoEmbedded: magic 等 6 个 i16 + i32 unused, 像素从 +16 起
        t = base + texture_offset
        img_fmt, tex_w, tex_h = struct.unpack_from("<3h", data, t + 6)
        bpp = _BYTES_PER_PIXEL.get(img_fmt)
        if bpp is None:
            raise ParseError(f"未知 anm 纹理 format: {img_fmt}")
        raw = data[
            t + _EMBEDDED_HEADER_SIZE : t + _EMBEDDED_HEADER_SIZE + tex_w * tex_h * bpp
        ]
        rgba = decode_texture(img_fmt, tex_w, tex_h, raw)

    sprites: dict[int, AnmSprite] = {}
    # sprite 像素坐标 = 逻辑坐标 * (纹理宽 / entry 逻辑宽)
    sx = tex_w / width
    sy = tex_h / height
    for i in range(num_sprites):
        so = struct.unpack_from("<i", data, base + _ENTRY_HEADER_SIZE + i * 4)[0]
        sid, x, y, w, h = struct.unpack_from("<iffff", data, base + so)
        fx, fy, fw, fh = x * sx, y * sy, w * sx, h * sy
        sprites[sid] = AnmSprite(
            sid, round(fx), round(fy), round(fw), round(fh), fx, fy, fw, fh
        )
    return AnmEntry(name, fmt, color_key, width, height, tex_w, tex_h, rgba, sprites)


def parse_anm(data: bytes, *, version: int, flat_layout: bool = False) -> AnmFile:
    """解析 .anm 整文件(entry 链 + 纹理 + sprite 表 + 脚本指令)。

    Args:
        data: .anm 字节
        version: 期望的 entry 头版本号(作品差异显式传入)
        flat_layout: True 时脚本表键 = entry 内装载序号(文件里存的 id 被忽略);
            False 时键 = 文件里存的 id
    """
    # entry 链 nextOffset 累加出处 old/touhou/schema/anm.py(AnmManager::LoadAnms)
    entries: list[AnmEntry] = []
    scripts: list[dict[int, list[Instruction]]] = []
    offset = 0
    while True:
        entries.append(_parse_entry(data, offset, version))
        num_sprites, num_scripts = struct.unpack_from("<2i", data, offset)
        table = offset + _ENTRY_HEADER_SIZE + num_sprites * 4
        entry_scripts: dict[int, list[Instruction]] = {}
        for i in range(num_scripts):
            sid, soff = struct.unpack_from("<2i", data, table + i * 8)
            key = i if flat_layout else sid
            entry_scripts[key] = decode_script(data, offset + soff)
        scripts.append(entry_scripts)
        next_offset = struct.unpack_from("<i", data, offset + 56)[0]
        if next_offset == 0:
            break
        offset += next_offset
    return AnmFile(entries, scripts)


def sprite_image(
    anm: AnmFile, sprite_id: int, entry: int | None = None
) -> tuple[int, int, bytes]:
    """取 sprite 图像: (w, h, rgba_bytes)。外链纹理未回填的 entry 抛 ParseError。"""
    if entry is None:
        # 默认选 sprite 数最多的 entry(主纹理)
        entry = max(range(len(anm.entries)), key=lambda i: len(anm.entries[i].sprites))
    e = anm.entries[entry]
    if e.rgba is None:
        raise ParseError(f"{e.name}: 外链纹理未解析(需调用方取图回填 rgba)")
    spr = e.sprites[sprite_id]
    out = bytearray(spr.w * spr.h * 4)
    for row in range(spr.h):
        src = ((spr.y + row) * e.tex_width + spr.x) * 4
        out[row * spr.w * 4 : (row + 1) * spr.w * 4] = e.rgba[src : src + spr.w * 4]
    return spr.w, spr.h, bytes(out)
