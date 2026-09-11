"""资源包容器解析: 格式规格 + 纯解析函数。

打开文件与"格式名 → 规格"的登记都在 engine(`engine/archive.py`), 本层只出规格与
纯函数 —— 不碰注册表, 也不做文件 I/O(架构稿 §2.6)。
"""

from __future__ import annotations

from .base import (
    Archive,
    ArchiveEntry,
    ArchiveFormat,
    find_entry,
    load_entry,
    raw_entry,
)
from .lzss import lzss_decompress
from .pbg4 import parse_pbg4, sniff_pbg4
from .pbgz import parse_pbgz, sniff_pbgz, try_decrypt_signed

__all__ = [
    "Archive",
    "ArchiveEntry",
    "ArchiveFormat",
    "find_entry",
    "load_entry",
    "lzss_decompress",
    "parse_pbg4",
    "parse_pbgz",
    "raw_entry",
    "sniff_pbg4",
    "sniff_pbgz",
    "try_decrypt_signed",
]
