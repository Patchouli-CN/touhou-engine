"""th07 的 view 层: pygame 后端(渲染/输入/SE) + scene 应用壳。"""

from __future__ import annotations

from .app import run_app, run_game
from .backend import PygameBackend
from .bank import SurfaceBank
from .game_scene import GameScene
from .option import OptionScene
from .scene import Scene, run_scenes
from .title import MenuMemory, StartRequest, TitleScene

__all__ = [
    "GameScene",
    "MenuMemory",
    "OptionScene",
    "PygameBackend",
    "Scene",
    "StartRequest",
    "SurfaceBank",
    "TitleScene",
    "run_app",
    "run_game",
    "run_scenes",
]
