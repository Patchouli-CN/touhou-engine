"""PBG4 容器解析。"""

from __future__ import annotations

import struct

from ..exceptions import ArchiveFormatError
from .base import Archive, ArchiveEntry
from .lzss import lzss_decompress

MAGIC = b"PBG4"
DICT_BITS = 13
LEN_BITS = 4


def sniff_pbg4(header: bytes) -> bool:
    """凭文件头判断是不是 PBG4。"""
    return header[:4] == MAGIC


def parse_pbg4(data: bytes, path: str | None = None) -> Archive:
    """解析 PBG4 整包字节; 头不对抛 ArchiveFormatError。"""
    # 布局出处 old/touhou/schema/archive/pbg4.py: 头 MAGIC + u32 条目数 +
    # u32 目录偏移 + u32 目录解压后大小; 尾部 LZSS 条目表(名字\0 + u32 offset
    # + u32 size + u32 不读), 每条数据同为 LZSS(13/4)
    if not sniff_pbg4(data):
        raise ArchiveFormatError(f"不是 PBG4 容器，识别到的格式：{data[:4]!r}")
    num_entries, header_size, decompressed_size = struct.unpack_from("<III", data, 4)
    table = lzss_decompress(
        data[header_size:], decompressed_size, dict_bits=DICT_BITS, len_bits=LEN_BITS
    )
    entries: list[ArchiveEntry] = []
    pos = 0
    for _ in range(num_entries):
        end = table.index(b"\x00", pos)
        name = table[pos:end].decode("latin-1")
        pos = end + 1
        offset, size, _ = struct.unpack_from("<III", table, pos)
        pos += 12
        # pbg4 不存单条压缩长度: raw_size 切到文件尾, lzss 解压到
        # out_len/EOD 即停, 多读进下一条的字节不会被消费
        entries.append(ArchiveEntry(name, offset, size, len(data) - offset))
    return Archive("pbg4", entries, data, path=path)
