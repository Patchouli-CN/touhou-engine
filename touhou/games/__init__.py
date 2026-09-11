"""作品实现与发现入口: 显式 import 即"被发现"(import 触发包内向 TouhouRegistry 登记)。"""

from __future__ import annotations

from ..engine import GameAssembly, TouhouRegistry
from . import th07 as th07  # 作品发现清单: 新作品加一行(import 即触发登记)


def available_games() -> dict[str, GameAssembly]:
    """列出已登记的作品, 键 = 作品名。"""
    return {g: TouhouRegistry.create_game(g) for g in TouhouRegistry.registered_games()}
