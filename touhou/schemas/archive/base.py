"""容器只读视图的数据结构与取件函数。"""

from __future__ import annotations

import msgspec

from .lzss import lzss_decompress


class ArchiveEntry(msgspec.Struct, frozen=True):
    """容器内一条资源的目录项。"""

    name: str
    offset: int  # 数据在文件中的绝对偏移
    size: int  # 解压后大小
    raw_size: int  # 原始字节切片长度(pbg4 未存压缩长度, 切到文件尾)


class Archive(msgspec.Struct):
    """解析后的资源包: 目录项 + 整包字节。"""

    format_name: str
    entries: list[ArchiveEntry]
    data: bytes
    path: str | None = None
    lzss_dict_bits: int = 13
    lzss_len_bits: int = 4

    def __repr__(self) -> str:
        # data 是整包字节串, 不进 repr
        src = self.path or "<bytes>"
        return f"<Archive {self.format_name} {src} {len(self.entries)} 条目>"


def find_entry(archive: Archive, name: str) -> ArchiveEntry:
    """按名查目录项, 不存在抛 KeyError。"""
    for e in archive.entries:
        if e.name == name:
            return e
    raise KeyError(name)


def raw_entry(archive: Archive, name: str) -> bytes:
    """取条目的原始(可能压缩)字节。"""
    e = find_entry(archive, name)
    return archive.data[e.offset : e.offset + e.raw_size]


def load_entry(archive: Archive, name: str) -> bytes:
    """取条目并解压为最终资源字节。"""
    e = find_entry(archive, name)
    return lzss_decompress(
        archive.data[e.offset : e.offset + e.raw_size],
        e.size,
        dict_bits=archive.lzss_dict_bits,
        len_bits=archive.lzss_len_bits,
    )
