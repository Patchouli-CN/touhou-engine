"""th07 应用壳: run_app 完整开局流(标题→菜单→选择→对局→回标题), run_game 直进一局。"""

from __future__ import annotations

from ....engine import GameAssembly, RenderBackend
from ....engine.score_store import ScoreStore
from ....schemas.archive import open_archive
from ..config import Th07Config, load_config, save_config
from ..world import Th07World, compose_world
from .backend import PygameBackend
from .game_scene import GameScene
from .menu_vms import MenuVmSet
from .musicroom import MusicRoomScene
from .option import OptionScene
from .scene import run_scenes
from .title import MenuMemory, StartRequest, TitleScene

#: 成绩库落盘位置(原版 score.dat 的 JSON 简化版, engine/score_store.py)
SCORE_PATH = "score.json"

#: 配置落盘位置(原版 th07.cfg 的 JSON 简化版, games/th07/config.py)
CONFIG_PATH = "config.json"

_MENU_MUSIC_ROOM = 5  # MENU_CURSOR_PREINPUT_MUSICROOM (MainMenu.hpp:47)
_MENU_OPTION = 6  # MENU_CURSOR_PREINPUT_OPTIONS (MainMenu.hpp:48)


def _apply_config(backend: RenderBackend, config: Th07Config) -> None:
    """配置即时生效点: SE 开关同步后端; 其余项见注释(框架能力/后续单留 hook)。"""
    # cfg.playSounds → SE 播放开关(duck-typed, 有该属性的后端才吃)
    setattr(backend, "sounds_enabled", bool(config.play_sounds))
    # cfg.windowed → 全屏切换: RenderBackend 协议未暴露, 框架层 hook 留待
    # cfg.music_mode → BGM 链整体留待后续单
    # cfg.frameskip_config/slow_mode → 引擎主循环无描画间隔/处理落ち概念, 留待


def run_app(
    assembly: GameAssembly,
    *,
    seed: int | None = None,
    scale: int | None = None,
    score_path: str = SCORE_PATH,
    config_path: str = CONFIG_PATH,
    backend: RenderBackend | None = None,
) -> None:
    """开窗口跑完整流程: 标题 → 主菜单 → 难度/机体/装备 → 对局 → 回标题; Quit 退出。

    scene 接缝全在这里显式装配: 后续单加新画面(Replay/MusicRoom 等) = 新
    Scene 子类 + 往 submenus/工厂链里挂一项。
    """
    config = load_config(config_path)
    store = ScoreStore.load(
        score_path, spellcard_count=len(assembly.data.spellcard_scores)
    )
    memory = MenuMemory(default_difficulty=config.default_difficulty)
    archive = open_archive(
        assembly.resources.data_path, format_name=assembly.resources.archive_format
    )
    if backend is None:
        backend = PygameBackend(archive, anm_version=assembly.scripts.anm_version)
    _apply_config(backend, config)

    def make_title(*, cursor: int = 0, vm_set: MenuVmSet | None = None) -> TitleScene:
        return TitleScene(
            archive,
            store,
            memory,
            anm_version=assembly.scripts.anm_version,
            on_start=make_game,
            submenus={_MENU_MUSIC_ROOM: make_musicroom, _MENU_OPTION: make_option},
            vm_set=vm_set,
            cursor=cursor,
        )

    def make_musicroom(title: TitleScene) -> MusicRoomScene:
        return MusicRoomScene(
            archive,
            anm_version=assembly.scripts.anm_version,
            # Music Room 是独立 chain(进它时 MainMenu 已销毁), 返回重建主菜单,
            # 光标停 Music Room(MainMenu.cpp:2630-2631)
            on_exit=lambda: make_title(cursor=_MENU_MUSIC_ROOM),
        )

    def make_option(title: TitleScene) -> OptionScene:
        return OptionScene(
            config,
            title.menu_vms,  # 与主菜单共用同一 VM 阵列(C++ 同一 MainMenu)
            # 返回主菜单, 光标停在 Option(MainMenu.cpp:783)
            on_exit=lambda: make_title(cursor=_MENU_OPTION, vm_set=title.menu_vms),
            on_config_changed=lambda cfg: _apply_config(backend, cfg),
        )

    def make_game(req: StartRequest) -> GameScene:
        world = compose_world(
            assembly,
            character=req.character,
            difficulty=req.difficulty,
            seed=seed,
            store=store,
            life_count=config.life_count,
        )
        return GameScene(
            world,
            on_exit=make_title,  # 结算后回标题(结算画面 ResultScreen 留待后续单)
            on_result=lambda w: store.save(score_path),
        )

    try:
        run_scenes(make_title(), backend, title=assembly.title, scale=scale)
    finally:
        # 进程退出时 cfg 落盘(main.cpp:188); 默认难度随选择记回 cfg
        config.default_difficulty = memory.default_difficulty
        save_config(config, config_path)


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
