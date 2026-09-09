"""资源包容器解析(认头打开已知格式, 无注册表)。"""

from __future__ import annotations

from pathlib import Path

from ..exceptions import ArchiveFormatError
from .base import Archive, ArchiveEntry, find_entry, load_entry, raw_entry
from .lzss import lzss_decompress
from .pbg4 import parse_pbg4, sniff_pbg4
from .pbgz import parse_pbgz, sniff_pbgz, try_decrypt_signed

__all__ = [
    "Archive",
    "ArchiveEntry",
    "find_entry",
    "load_entry",
    "lzss_decompress",
    "open_archive",
    "parse_pbg4",
    "parse_pbgz",
    "raw_entry",
    "sniff_archive",
    "try_decrypt_signed",
]

# 已知格式: 名字 → (认头, 解析); 作品 → 格式的绑定归 games/compose, 不归这层
_KNOWN = {
    "pbg4": (sniff_pbg4, parse_pbg4),
    "pbgz": (sniff_pbgz, parse_pbgz),
}


def sniff_archive(data: bytes) -> str | None:
    """按文件头在已知格式里认; 都不认返回 None。"""
    for name, (sniff, _parse) in _KNOWN.items():
        if sniff(data[:64]):
            return name
    return None


def open_archive(path: str | Path, *, format_name: str | None = None) -> Archive:
    """打开资源包; 不指定格式时按文件头认, 认不出抛 ArchiveFormatError。"""
    p = Path(path)
    data = p.read_bytes()
    if format_name is not None:
        try:
            parse = _KNOWN[format_name][1]
        except KeyError:
            raise ArchiveFormatError(
                f"未知资源包格式名: {format_name!r} (已知: {sorted(_KNOWN)})"
            ) from None
    else:
        found = sniff_archive(data)
        if found is None:
            raise ArchiveFormatError(
                f"无法识别的资源包格式: {p} (头 {data[:4]!r}; 已知: {sorted(_KNOWN)})"
            )
        parse = _KNOWN[found][1]
    return parse(data, str(p))
