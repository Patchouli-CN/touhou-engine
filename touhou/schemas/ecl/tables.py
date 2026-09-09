"""ECL opcode 表装配: v0/v800 两套 + encode 反查表。"""

from __future__ import annotations

from .base import EclInstr
from .spec import _Entry
from .tables_v0 import _V0
from .tables_v800 import _V800

_TABLES = {0: _V0, 0x800: _V800}
# 反查表: 一个类可挂多个 opcode(弹幕 9 合一/alt_bank 变体/Nop 填充号),
# encode 时按 consts 字段值匹配实例
_REVERSE: dict[int, dict[type[EclInstr], list[tuple[int, _Entry]]]] = {}
for _v, _t in _TABLES.items():
    _r: dict[type[EclInstr], list[tuple[int, _Entry]]] = {}
    for _op, _e in _t.items():
        _r.setdefault(_e.cls, []).append((_op, _e))
    _REVERSE[_v] = _r
