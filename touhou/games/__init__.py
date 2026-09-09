"""作品实现与发现入口: 显式 import 即"被发现", 无装饰器注册。"""

from __future__ import annotations

from ..engine import GameAssembly
from . import th07  # 作品发现清单: 新作品在此加一行显式 import


def available_games() -> dict[str, GameAssembly]:
    """列出已 compose 的作品, 键 = 作品名。"""
    assemblies = (th07.compose(),)
    return {a.name: a for a in assemblies}
