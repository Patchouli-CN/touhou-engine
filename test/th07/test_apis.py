"""apis 层 th07 真数据冒烟(needs_data): Game 门面/事件流/命令队列/worker/ModApi/examples。"""

from __future__ import annotations

import runpy
from collections import Counter
from pathlib import Path

import pytest

from touhou import Game, GameEventKind, GamePhase, Input, TouhouWorld
from touhou.apis.modding import ModApi
from touhou.engine import SceneSnapshot

from .conftest import needs_data

pytestmark = needs_data

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"


def _wiggle(g: Game) -> Input:
    """射击 + 40 帧周期左右扫(与 test_world_smoke 同款的走位输入)。"""
    return Input(
        shoot=True,
        advance=True,
        left=(g.frame // 40) % 2 == 0,
        right=(g.frame // 40) % 2 == 1,
    )


def test_game_headless_smoke() -> None:
    """开局 tick 600 帧: 帧推进/标量属性/实体快照/numpy 快路径/SceneSnapshot。"""
    g = Game(character="ReimuA", difficulty="Normal", seed=42)
    assert g.phase == GamePhase.RUNNING
    assert (g.lives, g.power, g.score) == (3, 0, 0)
    for _ in range(600):
        g.step(Input(shoot=True, advance=True))
    assert g.frame == 600
    assert g.phase in (GamePhase.RUNNING, GamePhase.DIALOG)
    x, y = g.player_pos
    assert 0 <= x <= 384 and 0 <= y <= 448
    snap = g.snapshot()
    assert snap.frame == 600 and snap.player.hitbox > 0
    assert snap.player.state == "alive"
    arr = g.bullets_array()
    assert arr.ndim == 2 and arr.shape[1] == 6
    lasers = g.lasers_array()
    assert lasers.ndim == 2 and lasers.shape[1] == 5
    scene = g.scene
    assert isinstance(scene, SceneSnapshot) and scene.frame == 600
    assert isinstance(g.last_events, tuple)


def test_command_queue_and_worker() -> None:
    """写操作命令帧边界生效(queue 返回 Future); submit 重任务上 worker 池。"""
    g = Game(seed=42)
    fut = g.queue(lambda w, ctx: w.stats()["lives"])
    g.step(Input(shoot=True))
    assert fut.result(timeout=5) == 3.0  # 帧边界应用时的读数
    out = g.submit(lambda arr: float(arr.shape[0]), g.bullets_array())
    assert out.result(timeout=5) >= 0.0


def test_event_stream_to_result() -> None:
    """TouhouWorld 事件流: 迭代驱动到 GameOver 自动收尾进总结算。"""
    tw = TouhouWorld(difficulty="Normal", lives=3, headless=True, seed=42)
    stream = tw.stream(_wiggle)
    kinds: Counter[str] = Counter()
    for ev in stream:
        kinds[ev.kind] += 1
    assert kinds[GameEventKind.PLAYER_DEATH] > 0
    assert kinds[GameEventKind.GAME_OVER] == 1
    assert tw.game.phase == GamePhase.RESULT
    assert stream.result is not None


def test_spellcard_events_flow() -> None:
    """符卡事件流出: 一面中超的符卡宣言/结束能映射进 GameEvent(带符卡名)。

    Lunatic + 每帧无敌(不死不冻结, 时间轴准点): 中超符卡约 4347 帧宣言。
    """
    g = Game(difficulty="Lunatic", seed=42)
    mods = ModApi(g)
    kinds: Counter[str] = Counter()
    names: list[str] = []
    for _ in range(4700):
        mods.player.god_mode()
        for ev in g.step(Input(shoot=True, advance=True)):
            kinds[ev.kind] += 1
            if ev.kind == GameEventKind.SPELLCARD_BEGIN and ev.name:
                names.append(ev.name)
        if kinds[GameEventKind.SPELLCARD_BEGIN]:
            break
    assert kinds[GameEventKind.SPELLCARD_BEGIN] > 0
    assert names and all(names)  # 宣言事件带符卡名(world.spellcard_name 透出)


def test_modapi_writes() -> None:
    """ModApi 写操作(命令队列)生效: 火力/分数/自定义弹幕/覆盖层/无敌。"""
    g = Game(seed=42)
    mods = ModApi(g)
    assert mods.player.full_power == 128
    mods.player.set_power(mods.player.full_power)
    mods.score.add(1000)
    mods.player.set_invulnerability_time(999)
    mods.gui.circle(100, 100, 32)
    mods.gui.text(10, 10, "mod")
    before = g.score
    g.step(Input(shoot=True))
    assert g.power == 128
    assert g.score >= before + 1000
    assert g.snapshot().player.invulnerable  # 无敌计时帧边界重置生效
    scene = g.scene
    assert scene is not None
    assert [s.kind for s in scene.shapes] == ["circle"]
    assert [t.text for t in scene.texts] == ["mod"]
    fut = mods.bullets.fire_ring(*mods.player.pos, arms=8)
    g.step(Input(shoot=True))
    assert fut.result(timeout=5) == 8
    # 重生清弹信号期(开局 60 帧)会清掉自定义弹: 等窗口过了再数
    for _ in range(120):
        g.step(Input(shoot=True))
    fut = mods.bullets.fire_ring(*mods.player.pos, arms=8)
    g.step(Input(shoot=True))
    assert fut.result(timeout=5) == 8
    assert mods.bullets.count >= 8
    mods.bullets.clear()
    g.step(Input(shoot=True))
    assert mods.bullets.count == 0
    assert mods.boss.exists is False
    assert mods.is_capabilities_exist("player.set_power")
    assert not mods.is_capabilities_exist("player.nope")
    assert set(mods.available()) == {"player", "boss", "bullets", "score", "gui"}


def test_god_mode_no_death() -> None:
    """无敌挂: policy 每帧重置无敌计时, 站桩 3600 帧(Hard)不中弹。"""
    tw = TouhouWorld(difficulty="Hard", headless=True, seed=42)
    mods = ModApi(tw.game)

    def policy(g: Game) -> Input:
        mods.player.god_mode()
        return Input(shoot=True, advance=True)

    stream = tw.stream(policy)
    deaths = 0
    for ev in stream:
        if ev.kind == GameEventKind.PLAYER_DEATH:
            deaths += 1
        if tw.game.frame >= 3600:
            break
    assert deaths == 0 and tw.game.lives == 3


@pytest.mark.parametrize(
    ("script", "env"),
    [
        ("dodge_ai.py", {"DODGE_AI_HEADLESS": "1", "DODGE_AI_FRAMES": "300"}),
        ("auto_play.py", {"AUTO_PLAY_FRAMES": "300"}),
        ("mod_fun.py", {"MOD_FUN_FRAMES": "300"}),
    ],
)
def test_examples_smoke(
    script: str, env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Examples 三个示例 headless 模式跑数百帧不炸。"""
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    runpy.run_path(str(EXAMPLES / script), run_name="__main__")
