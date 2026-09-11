"""标题/主菜单/开局流状态机的 headless 测试(无数据: VM 无脚本, 状态机照跑)。"""

from __future__ import annotations

from touhou.engine import InputFrame
from touhou.engine.input import Button
from touhou.engine.score_store import ScoreStore
from touhou.games.th07.view.title import (
    MenuMemory,
    MenuState,
    StartRequest,
    TitleScene,
)

from .conftest import needs_data

_IDLE = InputFrame()


def _press(*btns: Button) -> InputFrame:
    s = frozenset(btns)
    return InputFrame(held=s, pressed=s)


def _hold(*btns: Button) -> InputFrame:
    return InputFrame(held=frozenset(btns))


def _scene(
    store: ScoreStore | None = None,
    memory: MenuMemory | None = None,
    **kwargs,
) -> TitleScene:
    scene = TitleScene(None, store or ScoreStore(), memory or MenuMemory(), **kwargs)
    scene.on_enter()
    return scene


def _step(scene: TitleScene, inp: InputFrame = _IDLE, n: int = 1) -> None:
    for _ in range(n):
        scene.step(inp)


def _enter_main_menu(scene: TitleScene) -> None:
    """进场 10 帧确认门后再操作(MainMenu.cpp:330-333)。"""
    _step(scene, _IDLE, 11)


def _enter_select_input(scene: TitleScene) -> None:
    """选择页滑入 30 帧后才吃输入(MainMenu.cpp:1177-1180)。"""
    _step(scene, _IDLE, 31)


def _go_to_difficulty(scene: TitleScene) -> None:
    _enter_main_menu(scene)
    scene.step(_press(Button.SHOT))
    assert scene._state is MenuState.SELECT_DIFFICULTY
    _enter_select_input(scene)


def _go_to_character(scene: TitleScene) -> None:
    _go_to_difficulty(scene)
    scene.step(_press(Button.SHOT))  # 默认 Normal 确认
    assert scene._state is MenuState.SELECT_CHARACTER
    _enter_select_input(scene)


def _unlocked_store() -> ScoreStore:
    """全 6 机体 Easy 无续关通关 → Extra Start 解锁。"""
    store = ScoreStore()
    for c in store.clrd:
        c["with_retries"][0] = 6
    return store


def test_initial_state_and_confirm_gate() -> None:
    """进场在 PRE_INPUT 主菜单; 前 10 帧确认无效, stateTimer≥10 起有效。"""
    scene = _scene()
    _step(scene, _IDLE, 9)
    scene.step(_press(Button.SHOT))
    assert scene._state is MenuState.PRE_INPUT  # stateTimer<10 不吃确认
    scene.step(_press(Button.SHOT))
    assert scene._state is MenuState.SELECT_DIFFICULTY


def test_cursor_wrap_and_extra_locked_skip() -> None:
    """上下环绕; Extra Start 未解锁(无通关记录)时光标直接滑过。"""
    scene = _scene()
    _enter_main_menu(scene)
    scene.step(_press(Button.DOWN))
    assert scene.cursor == 2  # 0→1(Extra 锁定)→2
    scene.step(_press(Button.UP))
    assert scene.cursor == 0  # 2→1(锁定)→0
    scene.step(_press(Button.UP))
    assert scene.cursor == 7  # 上环绕到 Exit


def test_extra_unlocked_cursor_stops() -> None:
    """全机体有通关记录后 Extra Start 可停。"""
    scene = _scene(store=_unlocked_store())
    _enter_main_menu(scene)
    scene.step(_press(Button.DOWN))
    assert scene.cursor == 1


def test_unimplemented_menu_item_is_noop() -> None:
    """未接工厂的菜单项(Replay)confirm 无反应(后续单接缝)。"""
    scene = _scene()
    _enter_main_menu(scene)
    scene.step(_press(Button.DOWN))  # → Practice(2)
    scene.step(_press(Button.DOWN))  # → Replay(3)
    scene.step(_press(Button.SHOT))
    assert scene._state is MenuState.PRE_INPUT
    assert not scene.done
    assert scene.next_scene() is None


def test_submenu_factory_seam() -> None:
    """Submenus 表挂了工厂的项: confirm → done + 工厂产物(后续单插入 scene 的口)。"""
    marker = TitleScene(None, ScoreStore(), MenuMemory())
    scene = _scene(submenus={6: lambda title: marker})
    _enter_main_menu(scene)
    for _ in range(5):  # 0→2(Extra 锁定滑过)→3→4→5→6
        scene.step(_press(Button.DOWN))
    assert scene.cursor == 6
    scene.step(_press(Button.SHOT))
    assert scene.done
    assert scene.next_scene() is marker


def test_cancel_jumps_cursor_to_exit() -> None:
    """主菜单按取消: 光标跳 Exit + 返回音(MainMenu.cpp:427-438)。"""
    scene = _scene()
    _enter_main_menu(scene)
    scene.step(_press(Button.BOMB))
    assert scene.cursor == 7
    assert 11 in scene.drain_sounds()  # SOUND_BACK


def test_quit_flow() -> None:
    """Exit: 离场动画(interrupt 1)60 帧后 done, next_scene=None(应用退出)。"""
    scene = _scene()
    _enter_main_menu(scene)
    scene.step(_press(Button.BOMB))  # 光标跳 7
    scene.step(_press(Button.SHOT))  # 确认 Exit
    assert not scene.done
    _step(scene, _IDLE, 59)
    assert not scene.done  # inputDelayTimer<60 还没退
    scene.step(_IDLE)
    assert scene.done
    assert scene.next_scene() is None


def test_difficulty_init_and_default_cursor() -> None:
    """难度页: INIT 30 帧不吃输入; 光标初值=默认难度(Normal=1)。"""
    scene = _scene()
    _enter_main_menu(scene)
    scene.step(_press(Button.SHOT))
    _step(scene, _IDLE, 10)
    scene.step(_press(Button.DOWN))  # 还在滑入, 不应动
    assert scene.cursor == 1
    _step(scene, _IDLE, 21)
    scene.step(_press(Button.DOWN))
    assert scene.cursor == 2


def test_difficulty_cancel_back_to_title() -> None:
    """难度页取消: 记默认难度, 30 帧离场后回主菜单光标在 Start。"""
    memory = MenuMemory()
    scene = _scene(memory=memory)
    _go_to_difficulty(scene)
    scene.step(_press(Button.DOWN))  # Normal→Hard
    scene.step(_press(Button.BOMB))
    assert memory.default_difficulty == 2
    _step(scene, _IDLE, 29)
    assert scene._state is MenuState.SELECT_DIFFICULTY
    scene.step(_IDLE)
    assert scene._state is MenuState.PRE_INPUT
    assert scene.cursor == 0


def test_full_start_flow() -> None:
    """全链: 标题→难度(Hard)→机体(魔理沙)→装备(B)→StartRequest(3, 2)。"""
    starts: list[StartRequest] = []
    scene = _scene(on_start=lambda req: starts.append(req) or _scene())
    _go_to_difficulty(scene)
    scene.step(_press(Button.DOWN))  # Normal→Hard
    scene.step(_press(Button.SHOT))
    assert scene._state is MenuState.SELECT_CHARACTER
    _enter_select_input(scene)
    scene.step(_press(Button.LEFT))  # 灵梦→(左环绕)→咲夜? 不, 先右
    assert scene.cursor == 2
    scene.step(_press(Button.RIGHT))
    scene.step(_press(Button.RIGHT))  # → 魔理沙(1)
    assert scene.cursor == 1
    scene.step(_press(Button.SHOT))
    assert scene._state is MenuState.SELECT_SHOTTYPE
    _enter_select_input(scene)
    scene.step(_press(Button.DOWN))  # A→B
    scene.step(_press(Button.SHOT))
    assert scene.done
    assert scene.start_request == StartRequest(character=3, difficulty=2)
    scene.next_scene()
    assert starts == [StartRequest(character=3, difficulty=2)]
    # 全程音效: 移动 se_select00(12), 确认 se_ok00(10)
    # (音效在 drain 后清空, 这里只验链不验序列)


def test_character_and_shot_memory() -> None:
    """机体/装备选择跨页记忆(C++ GameManager.character/shotType)。"""
    memory = MenuMemory()
    scene = _scene(memory=memory)
    _go_to_character(scene)
    scene.step(_press(Button.RIGHT))
    scene.step(_press(Button.RIGHT))  # → 咲夜(2)
    scene.step(_press(Button.SHOT))
    assert memory.character == 2
    _enter_select_input(scene)
    scene.step(_press(Button.DOWN))  # B
    scene.step(_press(Button.BOMB))  # 取消回机体页
    assert memory.shot_type == 1  # 取消也记装备
    assert scene._state is MenuState.SELECT_CHARACTER
    _step(scene, _IDLE, 1)  # INIT 重读记忆
    assert scene.cursor == 2


def test_character_cancel_returns_to_difficulty() -> None:
    """机体页取消 → 难度页, 光标停在之前确认的难度。"""
    memory = MenuMemory()
    scene = _scene(memory=memory)
    _go_to_difficulty(scene)
    scene.step(_press(Button.DOWN))  # Hard
    scene.step(_press(Button.SHOT))
    _enter_select_input(scene)
    scene.step(_press(Button.RIGHT))  # 魔理沙
    scene.step(_press(Button.BOMB))
    assert memory.character == 1  # 取消也记机体
    assert scene._state is MenuState.SELECT_DIFFICULTY
    _step(scene, _IDLE, 1)
    assert scene.cursor == 2  # defaultDifficulty=Hard


def test_eighth_frame_hold_repeat() -> None:
    """按住方向: 沿触发一次, 之后 32 帧起每 8 帧重复(Supervisor.cpp:177-196)。"""
    scene = _scene()
    _enter_main_menu(scene)
    scene.step(_press(Button.DOWN))  # 沿: 0→2(Extra 锁定滑过)
    assert scene.cursor == 2
    _step(scene, _hold(Button.DOWN), 32)
    assert scene.cursor == 2  # 还不到第 32 帧
    scene.step(_hold(Button.DOWN))
    assert scene.cursor == 3  # 第一次重复
    _step(scene, _hold(Button.DOWN), 8)
    assert scene.cursor == 4  # 8 帧后第二次重复
    sounds = scene.drain_sounds()
    assert sounds.count(12) == 3  # SOUND_MOVE_MENU ×3


def test_description_text_without_data_is_empty() -> None:
    """无数据: 说明文字 VM 无脚本不可见, texts 为空(状态机不受影响)。"""
    scene = _scene()
    _enter_main_menu(scene)
    assert scene.snapshot().texts == ()


@needs_data
def test_real_data_title_and_select_layout() -> None:
    """真机: 标题有背景/logo/菜单贴图; 进难度页背景换 select00.jpg。"""
    from touhou.engine import open_archive
    from touhou.games.th07.compose import DATA_PATH

    archive = open_archive(DATA_PATH, format_name="pbg4")
    scene = TitleScene(archive, ScoreStore(), MenuMemory())
    scene.on_enter()
    _step(scene, _IDLE, 90)  # 滑入动画跑完
    snap = scene.snapshot()
    images = [s.image for s in snap.sprites]
    assert images[0] == "title00.jpg"
    anm_sprites = [s for s in snap.sprites if s.image.startswith("title01.anm:")]
    assert len(anm_sprites) > 8  # logo + 菜单 8 项等
    assert scene.snapshot().texts  # 说明文字(ゲームを開始します)
    # 菜单 8 项: 选中项亮(base), 其余暗(base+1)
    menu_gids = [scene.menu_vms.vms[i + 1].vm.active_sprite_idx for i in range(8)]
    bases = [scene.menu_vms.vms[i + 1].base_sprite_idx for i in range(8)]
    assert menu_gids[0] == bases[0]
    assert all(menu_gids[i] == bases[i] + 1 for i in range(1, 8))
    # 全链走到开局
    _enter_main_menu(scene)
    scene.step(_press(Button.SHOT))
    _enter_select_input(scene)
    assert scene._background == "select00.jpg"
    snap = scene.snapshot()
    assert snap.sprites[0].image == "select00.jpg"
    scene.step(_press(Button.SHOT))
    _enter_select_input(scene)
    scene.step(_press(Button.SHOT))
    _enter_select_input(scene)
    scene.step(_press(Button.SHOT))
    assert scene.done
    assert scene.start_request == StartRequest(character=0, difficulty=1)
