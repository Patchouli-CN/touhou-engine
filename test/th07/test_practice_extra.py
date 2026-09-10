"""Practice Start / Extra Start 的选择流状态机与 practice 对局语义的 headless 测试。"""

from __future__ import annotations

from touhou.engine import InputFrame
from touhou.engine.input import Button
from touhou.engine.score_store import ScoreStore
from touhou.games.th07.results import practice_pscr_key
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
    _step(scene, _IDLE, 11)  # 进场 10 帧确认门


def _enter_select_input(scene: TitleScene) -> None:
    _step(scene, _IDLE, 31)  # 选择页滑入 30 帧


def _extra_store() -> ScoreStore:
    """全 6 机体 Easy 无续关通关 → Extra Start 解锁(Phantasm 未解锁)。"""
    store = ScoreStore(spellcard_count=141)
    for c in store.clrd:
        c["with_retries"][0] = 6
    return store


def _phantasm_store(*shots: int) -> ScoreStore:
    """Extra 解锁 + 指定机体 Phantasm 解锁(>=60 捕获 + 该机体 Extra 通关)。"""
    store = _extra_store()
    total = store.catk_slot_count - 1
    for e in store.catk[:60]:
        e["successes"][total] = 1
    for s in shots:
        store.clrd[s]["with_retries"][4] = 7
    return store


def _go_to_practice_difficulty(scene: TitleScene) -> None:
    _enter_main_menu(scene)
    scene.step(_press(Button.DOWN))  # 0→2(Extra 锁定滑过)= Practice Start
    assert scene.cursor == 2
    scene.step(_press(Button.SHOT))
    assert scene._state is MenuState.PRACTICE_SELECT_DIFFICULTY
    _enter_select_input(scene)


def _go_to_practice_stage(scene: TitleScene) -> None:
    """走完 难度→机体→装备 落到选面页 INPUT。"""
    _go_to_practice_difficulty(scene)
    scene.step(_press(Button.SHOT))  # 难度(Normal)
    assert scene._state is MenuState.PRACTICE_SELECT_CHARACTER
    _enter_select_input(scene)
    scene.step(_press(Button.SHOT))  # 机体(灵梦)
    assert scene._state is MenuState.PRACTICE_SELECT_SHOTTYPE
    _enter_select_input(scene)
    scene.step(_press(Button.SHOT))  # 装备(A) → 选面页
    assert scene._state is MenuState.SELECT_PRACTICE_STAGE
    _enter_select_input(scene)


def _go_to_extra_difficulty(scene: TitleScene) -> None:
    _enter_main_menu(scene)
    scene.step(_press(Button.DOWN))  # 0→1 = Extra Start
    assert scene.cursor == 1
    scene.step(_press(Button.SHOT))
    assert scene._state is MenuState.EXTRA_SELECT_DIFFICULTY
    _enter_select_input(scene)


# ---- Practice 选择流 ----


def test_practice_flow_full_chain() -> None:
    """Practice Start → 难度→机体→装备→选面 → StartRequest(practice, 选面)。"""
    starts: list[StartRequest] = []
    scene = _scene(on_start=lambda req: starts.append(req) or _scene())
    _go_to_practice_stage(scene)
    scene.step(_press(Button.SHOT))  # Stage1 确认
    assert scene.done
    req = StartRequest(character=0, difficulty=1, stage_no=1, practice=True)
    assert scene.start_request == req
    scene.next_scene()
    assert starts == [req]


def test_practice_stage_unlock_range() -> None:
    """选面范围 = clrd.without_retries[难度](到达面数); 3 → 光标 0..2 环绕。"""
    store = ScoreStore()
    store.clrd[0]["without_retries"][1] = 3  # Normal 到达 3 面
    scene = _scene(store=store)
    _go_to_practice_stage(scene)
    scene.step(_press(Button.DOWN))
    scene.step(_press(Button.DOWN))
    assert scene.cursor == 2
    scene.step(_press(Button.DOWN))  # 环绕回 0
    assert scene.cursor == 0
    scene.step(_press(Button.UP))  # 上环绕到 2
    assert scene.cursor == 2
    scene.step(_press(Button.SHOT))
    assert scene.start_request is not None
    assert scene.start_request.stage_no == 3


def test_practice_stage_unlock_clamps() -> None:
    """通关(>=6)可选全 6 面; 无记录(v=0)只能选 Stage1(光标卡 0)。"""
    store = ScoreStore()
    store.clrd[0]["without_retries"][1] = 6  # 通关标记(C++ 99 ↔ 本库 >=6)
    scene = _scene(store=store)
    _go_to_practice_stage(scene)
    assert scene._practice_stages_unlocked() == 6
    for _ in range(5):
        scene.step(_press(Button.DOWN))
    assert scene.cursor == 5

    fresh = _scene()
    _go_to_practice_stage(fresh)
    assert fresh._practice_stages_unlocked() == 1
    fresh.step(_press(Button.DOWN))  # 1 项环绕, 光标不动
    assert fresh.cursor == 0


def test_practice_cancel_chain_back_to_main_menu() -> None:
    """选面→装备→机体→难度→主菜单(光标停 Practice Start, practice 标记清)。"""
    scene = _scene()
    _go_to_practice_stage(scene)
    scene.step(_press(Button.BOMB))
    assert scene._state is MenuState.PRACTICE_SELECT_SHOTTYPE
    assert scene.cursor == scene.memory.shot_type  # :1918
    _enter_select_input(scene)
    scene.step(_press(Button.BOMB))
    assert scene._state is MenuState.PRACTICE_SELECT_CHARACTER
    _enter_select_input(scene)
    scene.step(_press(Button.BOMB))
    assert scene._state is MenuState.PRACTICE_SELECT_DIFFICULTY
    _enter_select_input(scene)
    scene.step(_press(Button.BOMB))
    _step(scene, _IDLE, 29)
    assert scene._state is MenuState.PRACTICE_SELECT_DIFFICULTY
    scene.step(_IDLE)
    assert scene._state is MenuState.PRE_INPUT
    assert scene.cursor == 2  # MENU_CURSOR_PREINPUT_PRACTICE_START (:1276)
    assert not scene._practice  # :1283


def test_practice_stage_page_texts() -> None:
    """选面页文字: 表头 + 6 行 Stage; 光标行白/已解锁灰/未解锁暗灰; 每面 pscr 显示。"""
    store = ScoreStore()
    store.clrd[0]["without_retries"][1] = 3
    store.pscr[practice_pscr_key(1, 0, 2)] = {"play_count": 4, "highscore": 123456}
    scene = _scene(store=store)
    _go_to_practice_stage(scene)
    scene.step(_press(Button.DOWN))  # 光标 0→1(Stage2)
    texts = scene.snapshot().texts
    assert len(texts) == 14  # 7 行 × (影 + 本体)
    body = [t for i, t in enumerate(texts) if i % 2 == 1]
    assert body[0].text == "Stage    HI-Score"
    assert body[1].text == "Stage1         00 (  0)"
    assert body[2].text == "Stage2    1234560 (  4)"
    assert body[2].rgba == (255, 255, 255, 255)  # 光标行白
    assert body[3].rgba == (160, 160, 160, 255)  # 已解锁灰(:2381)
    assert body[5].rgba == (64, 64, 64, 255)  # 未解锁暗灰(:2385)


def test_practice_mode_autowalk_after_game() -> None:
    """练习对局回标题(practice_mode=True): 直跳链落到选面页, 光标=最近练习面-1。"""
    memory = MenuMemory(
        character=1, shot_type=1, default_difficulty=2, practice_stage=3
    )
    store = ScoreStore()
    store.clrd[3]["without_retries"][2] = 3  # 该机体 Hard 到达 3 面(选面不被钳)
    scene = _scene(store=store, memory=memory, practice_mode=True)
    _step(scene, _IDLE, 4)  # PRE_INPUT→难度→机体→装备→选面(每态 INIT 一帧)
    assert scene._state is MenuState.SELECT_PRACTICE_STAGE
    assert scene.cursor == 2  # currentStage-1 (:1697)
    assert not scene._is_practice_mode  # 落地后清(:1696)
    _enter_select_input(scene)
    assert scene._practice  # 选面页 INIT 复位(:1877)
    scene.step(_press(Button.SHOT))
    assert scene.start_request == StartRequest(
        character=3, difficulty=2, stage_no=3, practice=True
    )


# ---- Extra 选择流 ----


def test_extra_flow_full_chain() -> None:
    """Extra Start(已解锁) → Extra 难度→机体→装备 → StartRequest(difficulty=4, 7 面)。"""
    starts: list[StartRequest] = []
    scene = _scene(
        store=_extra_store(), on_start=lambda req: starts.append(req) or _scene()
    )
    _go_to_extra_difficulty(scene)
    assert scene.cursor == 0  # Phantasm 未解锁: 只有 Extra 一项(:1125-1129)
    scene.step(_press(Button.DOWN))  # 1 项环绕不动
    assert scene.cursor == 0
    scene.step(_press(Button.SHOT))
    assert scene._state is MenuState.EXTRA_SELECT_CHARACTER
    _enter_select_input(scene)
    scene.step(_press(Button.SHOT))
    assert scene._state is MenuState.EXTRA_SELECT_SHOTTYPE
    _enter_select_input(scene)
    scene.step(_press(Button.SHOT))
    assert scene.done
    req = StartRequest(character=0, difficulty=4, stage_no=7)
    assert scene.start_request == req
    scene.next_scene()
    assert starts == [req]


def test_extra_difficulty_cancel_back_to_main_menu() -> None:
    """Extra 难度页取消: 记 cfg.defaultDifficulty=4, 回主菜单光标停 Extra Start。"""
    memory = MenuMemory()
    scene = _scene(store=_extra_store(), memory=memory)
    _go_to_extra_difficulty(scene)
    scene.step(_press(Button.BOMB))
    assert memory.default_difficulty == 4  # cursor+4 (:1254)
    _step(scene, _IDLE, 30)
    assert scene._state is MenuState.PRE_INPUT
    assert scene.cursor == 1  # MENU_CURSOR_PREINPUT_EXTRA_START (:1281)


def test_extra_phantasm_flow() -> None:
    """Phantasm 解锁后: 难度页 2 项, 选 Phantasm → StartRequest(difficulty=5, 8 面)。"""
    scene = _scene(store=_phantasm_store(0))
    _go_to_extra_difficulty(scene)
    scene.step(_press(Button.DOWN))  # Extra → Phantasm
    assert scene.cursor == 1
    scene.step(_press(Button.SHOT))
    assert scene.memory.default_difficulty == 5  # cursor+4 (:1223)
    assert scene._state is MenuState.EXTRA_SELECT_CHARACTER
    _enter_select_input(scene)
    scene.step(_press(Button.SHOT))
    assert scene._state is MenuState.EXTRA_SELECT_SHOTTYPE
    _enter_select_input(scene)
    scene.step(_press(Button.SHOT))
    assert scene.start_request == StartRequest(character=0, difficulty=5, stage_no=8)


def test_extra_phantasm_character_filter() -> None:
    """Phantasm 机体过滤: 只有 Phantasm 解锁的机体可停(:1333-1345)。"""
    scene = _scene(store=_phantasm_store(0))  # 只有灵梦A(shot0)解锁 Phantasm
    _go_to_extra_difficulty(scene)
    scene.step(_press(Button.DOWN))  # Phantasm
    scene.step(_press(Button.SHOT))
    _enter_select_input(scene)
    assert scene.cursor == 0  # 灵梦
    scene.step(_press(Button.RIGHT))  # 魔理沙/咲夜未解锁 → 环绕回灵梦
    assert scene.cursor == 0
    scene.step(_press(Button.SHOT))
    _enter_select_input(scene)
    assert scene.cursor == 0  # 装备过滤: 灵梦B 未解锁 → 停在 A(:1630-1641)
    scene.step(_press(Button.DOWN))
    assert scene.cursor == 0
    scene.step(_press(Button.SHOT))
    assert scene.start_request == StartRequest(character=0, difficulty=5, stage_no=8)


# ---- practice 对局语义(真数据) ----


@needs_data
def test_practice_world_setup() -> None:
    """练习开局: 9 残/满 power/起步樱点按面抬/每面 pscr 计数/关进 clrd 入账。"""
    from touhou.games.th07.compose import compose
    from touhou.games.th07.world import compose_world

    store = ScoreStore()
    world = compose_world(compose(), stage_no=3, seed=42, store=store, practice=True)
    g = world.th07
    assert world.practice
    assert g.lives == 9.0  # lifeCount=8 (GameManager.cpp:521-524)
    assert g.power == 128.0  # 2 面起满 power (:714-725)
    # 3 面: cherryMax = cherryStart+200000+50000, cherry=cherryMax (:611-632)
    assert g.cherry_max == g.cherry_start + 250000
    assert g.cherry == g.cherry_max
    key = practice_pscr_key(1, 0, 3)
    assert store.pscr[key]["play_count"] == 1
    assert store.clrd[0]["without_retries"][1] == 2  # 关进入账 currentStage-1


@needs_data
def test_practice_stage1_world_setup() -> None:
    """练习 1 面: power=0, 樱点不抬(cherry=cherryStart)。"""
    from touhou.games.th07.compose import compose
    from touhou.games.th07.world import compose_world

    world = compose_world(compose(), seed=42, store=ScoreStore(), practice=True)
    g = world.th07
    assert g.lives == 9.0
    assert g.power == 0.0
    assert g.cherry == g.cherry_start
    assert g.cherry_max == g.cherry_start + 200000  # Normal 上限照旧


@needs_data
def test_practice_result_not_ranked() -> None:
    """练习结算: 不入榜/不记通关/无续关; 每面 pscr 最高分取 max。"""
    from touhou.games.th07.compose import compose
    from touhou.games.th07.result import continue_available, final_result
    from touhou.games.th07.world import compose_world

    store = ScoreStore()
    world = compose_world(compose(), stage_no=2, seed=42, store=store, practice=True)
    world.game_over = True
    assert not continue_available(world)  # 练习无续关(AsciiManager.cpp:826-832)
    world.globals.score = 12345
    result = final_result(world, cleared=True)
    assert store.highscores == {}  # 不入榜(ResultScreen.cpp:2690 PRACTICE_END)
    assert store.plst["clear_count"] == 0  # 不记通关
    key = practice_pscr_key(1, 0, 2)
    assert store.pscr[key]["highscore"] == 12345  # 每面最高分(:2603-2615)
    assert result["rank"] == -1
    # 幂等: 再结算不重复记账
    final_result(world, cleared=True)
    assert store.pscr[key]["play_count"] == 1


@needs_data
def test_practice_next_level_goes_straight_to_result() -> None:
    """练习过关(NEXT_LEVEL)直进总结算: 不换关/不进结局(Gui.cpp:1032-1037)。"""
    from touhou.games.th07.compose import compose
    from touhou.games.th07.msg import apply_next_level
    from touhou.games.th07.world import compose_world

    world = compose_world(
        compose(), stage_no=2, seed=42, store=ScoreStore(), practice=True
    )
    apply_next_level(world)
    assert world.result is not None
    assert world.cleared
    assert not world.pending_next_level
    assert world.ending is None
    assert world.stage_no == 2


@needs_data
def test_run_app_practice_chain(tmp_path) -> None:
    """run_app 全链: 主菜单→Practice→难度→机体→装备→选面→进对局。"""
    from touhou.engine import Event, RenderBackend, SceneSnapshot
    from touhou.games.th07.compose import compose
    from touhou.games.th07.view.app import run_app

    class _StubBackend(RenderBackend):
        def __init__(self, inputs: list[InputFrame | None]) -> None:
            self._inputs = list(inputs)
            self.closed = False

        def open(self, *, title: str, scale: int = 1) -> None:
            pass

        def frame(
            self, events: tuple[Event, ...], snapshot: SceneSnapshot
        ) -> InputFrame | None:
            return self._inputs.pop(0) if self._inputs else None

        def play_sounds(self, ids: list[int]) -> None:
            pass

        def close(self) -> None:
            self.closed = True

    def press(b: Button) -> InputFrame:
        return InputFrame(held=frozenset({b}), pressed=frozenset({b}))

    shot = press(Button.SHOT)
    inputs: list[InputFrame | None] = (
        [_IDLE] * 11
        + [press(Button.DOWN)]  # 0→2(Extra 锁定滑过)= Practice Start
        + [shot]
        + [_IDLE] * 31
        + [shot]  # 难度 Normal
        + [_IDLE] * 31
        + [shot]  # 机体 灵梦
        + [_IDLE] * 31
        + [shot]  # 装备 A → 选面页
        + [_IDLE] * 31
        + [shot]  # Stage1 → 进对局
        + [_IDLE] * 30  # 对局跑 30 帧
        + [None]  # 关窗
    )
    backend = _StubBackend(inputs)
    run_app(
        compose(),
        seed=42,
        score_path=str(tmp_path / "score.json"),
        config_path=str(tmp_path / "config.json"),
        backend=backend,
    )
    assert not backend._inputs  # 输入序列正好喂完
    assert backend.closed
