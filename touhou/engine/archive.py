"""资源包打开: 按注册表解析容器格式(认头或按名)。

打开 = 读文件(I/O) + 格式解析, 归 engine; schemas 只出规格与纯解析函数(§2.6)。
"作品 → 格式"的绑定仍归 games/compose(ResourcePaths.archive_format)。
"""

from __future__ import annotations

from pathlib import Path

from ..schemas.archive import (
    Archive,
    ArchiveFormat,
    parse_pbg4,
    parse_pbgz,
    sniff_pbg4,
    sniff_pbgz,
)
from ..schemas.exceptions import ArchiveFormatError
from .registry import TouhouRegistry

# 框架自带的核心容器格式: schemas 出规格(纯函数), 这里登记到注册表。
# 认头按登记序试, 故 pbg4 先于 pbgz。
TouhouRegistry.archive(ArchiveFormat(name="pbg4", sniff=sniff_pbg4, parse=parse_pbg4))
TouhouRegistry.archive(ArchiveFormat(name="pbgz", sniff=sniff_pbgz, parse=parse_pbgz))


def _registered_names() -> str:
    """已登记格式名(错误信息用)。"""
    return ", ".join(sorted(f.name for f in TouhouRegistry.archive_formats()))


def sniff_archive(data: bytes) -> str | None:
    """按文件头在已登记格式里认; 都不认返回 None。"""
    for fmt in TouhouRegistry.archive_formats():
        if fmt.sniff(data[:64]):
            return fmt.name
    return None


def open_archive(path: str | Path, *, format_name: str | None = None) -> Archive:
    """打开资源包; 不指定格式时按文件头认, 认不出抛 ArchiveFormatError。"""
    p = Path(path)
    data = p.read_bytes()
    if format_name is None:
        found = sniff_archive(data)
        if found is None:
            raise ArchiveFormatError(
                f"无法识别的资源包格式: {p} (头 {data[:4]!r}; 已登记: {_registered_names()})"
            )
        fmt = TouhouRegistry.archive_format(found)
    else:
        try:
            fmt = TouhouRegistry.archive_format(format_name)
        except KeyError:
            raise ArchiveFormatError(
                f"未知资源包格式名: {format_name!r} (已登记: {_registered_names()})"
            ) from None
    return fmt.parse(data, str(p))
