"""异常门面(定义在 schemas 叶子层, 分层守护不允许下层引用包根模块)。"""

from __future__ import annotations

from .schemas.exceptions import ArchiveFormatError, ParseError, TouhouError

__all__ = [
    "ArchiveFormatError",
    "ParseError",
    "TouhouError",
]
