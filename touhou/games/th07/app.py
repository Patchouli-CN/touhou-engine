"""th07 窗口 App: 薄壳, 真实现延迟到 view 层(headless 路径不引 pygame)。"""

from __future__ import annotations

from importlib import import_module
from typing import cast

from ...engine import GameAssembly, TouhouRegistry, WindowApp


def _view() -> WindowApp:
    """取真窗口层模块(调用时才 import, 那时才拉 pygame)。"""
    return cast(WindowApp, import_module(".view.app", __package__))


@TouhouRegistry.app("th07")
class Th07App:
    """th07 窗口 App: 完整流程与直进一局两个入口。"""

    def run_app(
        self,
        assembly: GameAssembly,
        *,
        seed: int | None = None,
        scale: int | None = None,
    ) -> None:
        """开窗口跑完整流程: 标题 → 菜单 → 选择 → 对局 → 回标题。"""
        _view().run_app(assembly, seed=seed, scale=scale)

    def run_game(
        self,
        assembly: GameAssembly,
        *,
        character: int = 0,
        difficulty: int = 1,
        stage_no: int = 1,
        seed: int | None = None,
        scale: int | None = None,
    ) -> object:
        """开窗口直进一局(跳过标题), 返回打完的世界。"""
        return _view().run_game(
            assembly,
            character=character,
            difficulty=difficulty,
            stage_no=stage_no,
            seed=seed,
            scale=scale,
        )
