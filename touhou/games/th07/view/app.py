"""th07 应用壳: run_app 完整开局流(标题→菜单→选择→对局→回标题), run_game 直进一局。"""

from __future__ import annotations

from ....engine import GameAssembly, RenderBackend
from ....engine.score_store import ScoreStore
from ....schemas.archive import open_archive
from ..world import Th07World, compose_world
from .backend import PygameBackend
from .game_scene import GameScene
from .scene import run_scenes
from .title import MenuMemory, StartRequest, TitleScene

#: 成绩库落盘位置(原版 score.dat 的 JSON 简化版, engine/score_store.py)
SCORE_PATH = "score.json"


def run_app(
    assembly: GameAssembly,
    *,
    seed: int | None = None,
    scale: int | None = None,
    score_path: str = SCORE_PATH,
    backend: RenderBackend | None = None,
) -> None:
    """开窗口跑完整流程: 标题 → 主菜单 → 难度/机体/装备 → 对局 → 回标题; Quit 退出。

    scene 接缝全在这里显式装配: 后续单加新画面(Option/Replay 等) = 新
    Scene 子类 + 往 submenus/工厂链里挂一项。
    """
    store = ScoreStore.load(
        score_path, spellcard_count=len(assembly.data.spellcard_scores)
    )
    memory = MenuMemory()
    archive = open_archive(
        assembly.resources.data_path, format_name=assembly.resources.archive_format
    )
    if backend is None:
        backend = PygameBackend(archive, anm_version=assembly.scripts.anm_version)

    def make_title() -> TitleScene:
        return TitleScene(archive, store, memory, on_start=make_game)

    def make_game(req: StartRequest) -> GameScene:
        world = compose_world(
            assembly,
            character=req.character,
            difficulty=req.difficulty,
            seed=seed,
            store=store,
        )
        return GameScene(
            world,
            on_exit=make_title,  # 结算后回标题(结算画面 ResultScreen 留待后续单)
            on_result=lambda w: store.save(score_path),
        )

    run_scenes(make_title(), backend, title=assembly.title, scale=scale)


def run_game(
    assembly: GameAssembly,
    *,
    character: int = 0,
    difficulty: int = 1,
    stage_no: int = 1,
    seed: int | None = None,
    scale: int | None = None,
    backend: RenderBackend | None = None,
    world: Th07World | None = None,
) -> Th07World:
    """开窗口直进一局(跳过标题); 返回打完的世界。"""
    if world is None:
        world = compose_world(
            assembly,
            character=character,
            difficulty=difficulty,
            stage_no=stage_no,
            seed=seed,
        )
    if backend is None:
        backend = PygameBackend(world.archive, anm_version=assembly.scripts.anm_version)
    scene = GameScene(world, on_exit=lambda: None)
    run_scenes(scene, backend, title=assembly.title, scale=scale)
    return world
