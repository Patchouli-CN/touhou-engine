"""异常层级(定义放叶子层, 包根 exceptions.py 只做门面导出)。"""

from __future__ import annotations


class TouhouError(Exception):
    """touhou 包语义错误基类。"""


class ParseError(TouhouError, ValueError):
    """游戏资源文件格式解析错误基类。"""


class ArchiveFormatError(ParseError):
    """dat 容器结构损坏/不符。"""


__all__ = [
    "ArchiveFormatError",
    "ParseError",
    "TouhouError",
]
