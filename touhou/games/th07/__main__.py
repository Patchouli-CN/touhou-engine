"""``python -m touhou.games.th07``: 直进 th07 一面。"""

from __future__ import annotations

from .compose import compose
from .view.app import run_game

if __name__ == "__main__":
    run_game(compose())
