"""Player Data 状态机/翻页/数据显示的 headless 测试(无数据: VM 无脚本, 状态机照跑)。"""

from __future__ import annotations

from touhou.engine import InputFrame
from touhou.engine.input import Button
from touhou.engine.score_store import ScoreStore, make_highscore_record
from touhou.games.th07.view.playerdata import PlayerDataScene, _phantasm_unlocked
from touhou.games.th07.view.scene import Scene

from .conftest import needs_data

_IDLE = InputFrame()

#: 符卡名(假数据, 长得像原版)
_CARD_NAME = "凍符「パーフェクトフリーズ」"


def _press(*btns: Button) -> InputFrame:
    s = frozenset(btns)
    return InputFrame(held=s, pressed=s)


def _store() -> ScoreStore:
    """带假战绩的库: 2 条真榜记录 + 3 张符卡战绩 + pscr/plst 计数。"""
    store = ScoreStore(spellcard_count=141)
    store.insert_score(
        make_highscore_record(
            123456789,
            0,
            1,
            3,
            name="TESTER",
            num_retries=1,
            date="2026-09-10T12:00:00+09:00",
        )
    )
    store.insert_score(
        make_highscore_record(
            87654321,
            1,
            1,
            7,
            name="EXTRAAAA",
            num_retries=0,
            date="2026-08-01T00:00:00+09:00",
        )
    )
    # 符卡 0: 灵梦A 挑战 2 取得 1(bonus 50000); 符卡 1: 只挑战未取得; 符卡 2: 只咲夜A 打过
    store.record_spellcard_attempt(0, _CARD_NAME, 0)
    store.record_spellcard_attempt(0, _CARD_NAME, 0)
    store.record_spellcard_success(0, 0, 50000)
    store.record_spellcard_attempt(1, "氷符「アイシクルフォール」", 0)
    store.record_spellcard_attempt(2, "銀符「パーフェクトメイド」", 4)
    store.record_spellcard_success(2, 4, 30000)
    # pscr/plst: 灵梦A Normal 开 2 局, 咲夜A Hard 开 1 局
    store.record_play(0, 1)
    store.record_play(0, 1)
    store.record_play(4, 2)
    store.plst["total_frames"] = 3661 * 60
    store.plst["clear_count"] = 2
    store.plst["retry_count"] = 3
    return store


class _Marker(Scene):
    """next_scene 落点标记。"""

    def step(self, inp: InputFrame) -> None:
        pass

    def snapshot(self):
        raise NotImplementedError

    def next_scene(self):
        return None


def _scene(store: ScoreStore | None = None, **kwargs) -> PlayerDataScene:
    marker = _Marker()
    scene = PlayerDataScene(
        None, store if store is not None else _store(), on_exit=lambda: marker, **kwargs
    )
    scene._marker = marker
    return scene


def _step(scene: PlayerDataScene, inp: InputFrame = _IDLE, n: int = 1) -> None:
    for _ in range(n):
        scene.step(inp)


def _enter(scene: PlayerDataScene) -> None:
    """INIT 20 帧门 + 进门帧(落进 DIFFICULTY_SELECT, ResultScreen.cpp:814-820)。"""
    _step(scene, _IDLE, 21)


def _texts(scene: PlayerDataScene) -> list[str]:
    return [t.text for t in scene.snapshot().texts]


# ---- 难度选择菜单 ----
def test_init_gate_and_first_frame() -> None:
    """光标初值 1(ResultScreen 构造); 帧 0 全阵列 interrupt 1; 20 帧门内不吃输入。"""
    scene = _scene()
    assert scene.cursor == 1
    assert scene._state == 0
    scene.step(_IDLE)  # 帧 0 设置
    assert all(w.vm.pending_interrupt == 1 for w in scene._vms)
    _step(scene, _press(Button.DOWN), 19)  # 门内(ft 1..19)
    assert scene.cursor == 1
    scene.step(_press(Button.DOWN))  # ft 20 落进 SELECT 当帧吃输入
    assert scene.cursor == 2


def test_phantasm_locked_skipped() -> None:
    """Phantasm 未解锁: 光标滑过 5, vms[5] 隐藏, 6..8 偏移 -32(ResultScreen.cpp:802-826)。"""
    scene = _scene()
    _enter(scene)
    scene.cursor = 4
    scene.step(_press(Button.DOWN))
    assert scene.cursor == 6
    scene.step(_press(Button.UP))
    assert scene.cursor == 4
    assert not scene._vms[5].active
    assert scene._vms[6].vm.offset[1] == -32.0
    # 亮暗: 选中白不透明, 未选 alpha 0xb0
    assert scene._vms[4].vm.color == [255, 255, 255, 255]
    assert scene._vms[6].vm.color[3] == 0xB0


def test_phantasm_unlocked_by_clear() -> None:
    """Phantasm 通关记录(with_retries[5]>=8) → 菜单项可见可停。"""
    store = _store()
    store.clrd[0]["with_retries"][5] = 8
    scene = _scene(store)
    assert scene._phantasm
    _enter(scene)
    scene.cursor = 4
    scene.step(_press(Button.DOWN))
    assert scene.cursor == 5
    assert scene._vms[5].active


def test_phantasm_unlocked_by_60_cards_and_extra() -> None:
    """60 张捕获 + Extra 通关 → 解锁(GameManager.cpp:1014-1049); 纯查询不 mutate。"""
    store = _store()
    for i in range(60):
        store.record_spellcard_attempt(i, f"卡{i}", 0)
        store.record_spellcard_success(i, 0, 1000)
    assert not _phantasm_unlocked(store)
    store.clrd[1]["with_retries"][4] = 7
    assert _phantasm_unlocked(store)
    assert store.clrd[1]["with_retries"][5] == 0  # 不写库


def test_cancel_jumps_to_exit_then_exits() -> None:
    """取消: 光标不在 8 → 跳 8 + 返回音; 在 8 → 离场 60 帧后 done(:848-924)。"""
    scene = _scene()
    _enter(scene)
    scene.step(_press(Button.BOMB))
    assert scene.cursor == 8
    assert not scene.done
    assert scene.drain_sounds() == [11]
    scene.step(_press(Button.BOMB))
    assert scene._state == 2  # EXITING
    assert all(w.vm.pending_interrupt == 2 for w in scene._vms)
    _step(scene, _IDLE, 59)
    assert not scene.done
    scene.step(_IDLE)
    assert scene.done
    assert scene.next_scene() is scene._marker


# ---- 最高分榜页 ----
def _enter_score(scene: PlayerDataScene, difficulty: int = 1) -> None:
    _enter(scene)
    scene.cursor = difficulty
    scene.step(_press(Button.SHOT))


def test_enter_score_page() -> None:
    """确认难度: state=3+d, interrupt=d+3, cursor=prevCursor, charUsed=-1, 无确认音。"""
    scene = _scene()
    _enter_score(scene)
    assert scene._state == 4  # SCORE_NORMAL
    assert scene._diff_played == 1
    assert scene.cursor == 0  # prevCursor 初值 0
    assert scene._char_used == -1
    assert all(w.vm.pending_interrupt == 4 for w in scene._vms)
    assert scene.drain_sounds() == []  # C++ 进页无确认音


def test_score_page_input_gate_and_char_name() -> None:
    """30 帧输入门; ft==20 时机体名重绘(charUsed=cursor, :995-1001)。"""
    scene = _scene()
    _enter_score(scene)
    _step(scene, _press(Button.RIGHT), 19)
    assert scene.cursor == 0  # 门内左右全挡
    _step(scene, _IDLE, 1)  # ft==20
    assert scene._char_used == 0
    _step(scene, _press(Button.RIGHT), 9)  # ft 21..29 仍挡
    assert scene.cursor == 0
    scene.step(_press(Button.RIGHT))  # ft 30 放行
    assert scene.cursor == 1
    assert scene._frame_timer == 1  # 移动后重新计门(帧尾 +1)
    assert scene.drain_sounds() == [12]


def test_score_page_rows_and_defaults() -> None:
    """榜 = 真实记录 + 默认空位补齐; 面数显示/日期格式对照 OnDraw (:2212-2274)。"""
    scene = _scene()
    _enter_score(scene)
    _step(scene, _IDLE, 30)  # 过页门, charUsed=0(灵梦A)
    texts = _texts(scene)
    assert "No  Name      Score(Stage)  Date   Slow" in texts
    assert "博麗 霊夢 (霊)　" in texts
    assert "  TESTER 1234567891(3)" in texts  # name/score/续关/面数
    assert " 09/10   0.00" in texts  # ISO → MM/DD, Slow 缺口恒 0.00
    assert any(t.startswith("--------") and "90000" in t for t in texts)  # 默认空位
    # 灵梦B 榜: stage=7(Extra) → (1) (:2252-2259)
    scene.step(_press(Button.RIGHT))  # ft 已过 30, 直切机体
    _step(scene, _IDLE, 21)
    texts = _texts(scene)
    assert "EXTRAAAA  876543210(1)" in texts
    assert " 08/01   0.00" in texts


def test_score_page_stage_disp_clear() -> None:
    """Stage 9+ → (C) (:2260-2266)。"""
    store = _store()
    store.insert_score(
        make_highscore_record(
            1000, 0, 1, 9, name="CLEAR", date="2026-01-01T00:00:00+09:00"
        )
    )
    scene = _scene(store)
    _enter_score(scene)
    _step(scene, _IDLE, 21)
    assert any(t.startswith("   CLEAR") and t.endswith("0(C)") for t in _texts(scene))


def test_score_page_cancel_back() -> None:
    """取消: 回难度菜单, prevCursor 记忆, cursor=diffPlayed, interrupt 1 (:1015-1028)。"""
    scene = _scene()
    _enter_score(scene)
    _step(scene, _IDLE, 31)
    scene.step(_press(Button.RIGHT))  # 机体 0→1
    assert scene.drain_sounds() == [12]
    _step(scene, _IDLE, 31)
    scene.step(_press(Button.BOMB))
    assert scene._state == 0  # INIT
    assert scene._prev_cursor == 1
    assert scene.cursor == 1  # diffPlayed
    assert scene.drain_sounds() == [11]
    _step(scene, _IDLE, 21)  # 再过 INIT 门
    scene.step(_press(Button.SHOT))  # 再进同一难度
    assert scene.cursor == 1  # 记得上次机体


# ---- 符卡收集表页 ----
def _enter_spells(scene: PlayerDataScene) -> None:
    _enter(scene)
    scene.cursor = 6
    scene.step(_press(Button.SHOT))


def test_enter_spellcard_list() -> None:
    """确认符卡一览: state=9, interrupt 10, cursor=savedCursor, page 初值 6(合计)。"""
    scene = _scene()
    _enter_spells(scene)
    assert scene._state == 9
    assert scene.spellcard_list_page == 6
    assert scene.cursor == 0
    assert scene._last_selected == -1
    assert all(w.vm.pending_interrupt == 10 for w in scene._vms)


def test_spellcard_page_content() -> None:
    """ft==20 重绘: 卡名/？？？？？/取得数/MaxBonus/计数行对照 OnDraw (:2276-2372)。"""
    scene = _scene()
    _enter_spells(scene)
    _step(scene, _IDLE, 21)
    texts = _texts(scene)
    assert "No.01" in texts and "No.10" in texts
    assert _CARD_NAME in texts  # 卡 0 已遇到 → 显示名
    assert "  1/  2" in texts  # 取得/挑战(合计页)
    assert "MaxBonus    50000" in texts
    assert "氷符「アイシクルフォール」" in texts
    assert "  0/  1" in texts  # 遇到未取得
    assert "？？？？？" in texts  # 卡 3 起未遇到
    assert "---/---" in texts
    # 计数行: 合计页取得 2 张(卡 0/2)
    assert any(t.endswith("141枚中  2枚取得（キャラ切り替え↓↑）") for t in texts)
    assert any(t.startswith("全主人公合計") for t in texts)  # page6 显示合计名


def test_spellcard_page_per_shot_view() -> None:
    """↑↓ 换机体页: 只咲夜A 打过的卡 2 在灵梦A 页显示 ??? 名 + ---/---。"""
    scene = _scene()
    _enter_spells(scene)
    _step(scene, _IDLE, 31)
    scene.step(_press(Button.DOWN))  # 合计 6 → 0(环绕, MoveCursor2)
    assert scene.spellcard_list_page == 0
    assert scene._list_scroll_anim == 1
    _step(scene, _IDLE, 21)
    texts = _texts(scene)
    # 灵梦A 页: 卡 2 未遇到(attempts[0]==0)但合计遇到过 → 名显示, 数 ---
    assert "銀符「パーフェクトメイド」" in texts
    assert texts.count("---/---") == 16  # 卡 2..9 该机体都未遇到(本体+影子各一)
    assert any(
        t.startswith("博麗 霊夢 (霊)") and "141枚中  1枚取得" in t for t in texts
    )


def test_spellcard_horizontal_page_turn() -> None:
    """←→ 换 10 张组(15 组环绕): interrupt 10 + 翻页动画; 20 帧后才换新名单。"""
    scene = _scene()
    _enter_spells(scene)
    _step(scene, _IDLE, 31)
    scene.step(_press(Button.LEFT))  # 组 0 → 14(环绕)
    assert scene.cursor == 14
    assert all(w.vm.pending_interrupt == 10 for w in scene._vms)
    assert scene._last_selected == 0  # 名单仍是旧组
    _step(scene, _IDLE, 20)
    assert scene._last_selected == 14
    texts = _texts(scene)
    assert "No.141" in texts and "No.140" not in texts  # 末组只有 1 张


def test_spellcard_cancel_saves_cursor() -> None:
    """取消: savedCursor 记忆, 再进恢复 (:1084-1097/:891)。"""
    scene = _scene()
    _enter_spells(scene)
    _step(scene, _IDLE, 31)
    scene.step(_press(Button.RIGHT))  # 组 0→1
    _step(scene, _IDLE, 31)
    scene.step(_press(Button.BOMB))
    assert scene._state == 0
    assert scene._saved_cursor == 1
    assert scene.cursor == 6  # diffPlayed
    _step(scene, _IDLE, 21)
    scene.cursor = 6
    scene.step(_press(Button.SHOT))
    assert scene.cursor == 1


# ---- 総合データ页 ----
def _enter_stats(scene: PlayerDataScene) -> None:
    _enter(scene)
    scene.cursor = 7
    scene.step(_press(Button.SHOT))


def test_overall_stats_content_and_flow() -> None:
    """14 行内容(pscr/plst 口径) + 淡入 40 帧 + 任一键淡出 20 帧回菜单 (:1728-2007)。"""
    scene = _scene()
    _enter_stats(scene)
    assert scene._state == 19
    assert all(w.vm.pending_interrupt == 9 for w in scene._vms)
    _step(scene, _IDLE, 1)  # ft 0 → 文本已可算
    snap = scene.snapshot()
    stats = [
        t
        for t in snap.texts
        if t.x == 56.0  # 影子在 x+1, 只数本体
        and t.text.startswith(("総", "プ", "博", "霧", "十", "全", "ク", "コ", "リ"))
    ]
    assert len(stats) == 14
    assert stats[0].text == "総起動時間   00:00:00"  # 缺口: 无启动时间字段
    assert stats[1].text == "総プレイ時間 01:01:01"  # 3661 秒
    assert (
        "Easy 　Norm 　Hard 　Luna  Extra  Total" in stats[2].text
    )  # 未解锁无 Phants 列
    assert stats[3].text == "博麗 霊夢 (霊)　      0      2      0      0      0      2"
    assert stats[7].text == "十六夜 咲夜 (幻)      0      0      1      0      0      1"
    assert stats[9].text.startswith("全主人公合計")
    assert stats[10].text.endswith("      2")  # クリア回数 Total=plst.clear_count
    assert stats[11].text.endswith("      3")  # コンティニュー Total=plst.retry_count
    # 淡入: ft<40 alpha 插值
    _step(scene, _IDLE, 19)
    alpha = scene.snapshot().texts[0].rgba[3]
    assert 0 < alpha < 255
    _step(scene, _IDLE, 20)
    assert scene._state == 20  # OVERALL_INPUT
    assert scene.snapshot().texts[0].rgba[3] == 255
    scene.step(_press(Button.SHOT))  # 任一键离场
    assert scene._state == 21
    _step(scene, _IDLE, 10)
    alpha = scene.snapshot().texts[0].rgba[3]
    assert 0 < alpha < 255
    _step(scene, _IDLE, 10)
    assert scene._state == 0  # 回 INIT
    assert scene.cursor == 7  # diffPlayed


# ---- 全链 ----
@needs_data
def test_run_app_playerdata_chain(tmp_path) -> None:
    """run_app 全链: 主菜单→Player Data→看榜→返回(光标停 4)→Quit。"""
    from touhou.engine import Event, RenderBackend, SceneSnapshot
    from touhou.games.th07.compose import compose
    from touhou.games.th07.view.app import run_app

    class _StubBackend(RenderBackend):
        def __init__(self, inputs: list[InputFrame | None]) -> None:
            self._inputs = list(inputs)
            self.sounds: list[int] = []
            self.closed = False

        def open(self, *, title: str, scale: int = 1) -> None:
            pass

        def frame(
            self, events: tuple[Event, ...], snapshot: SceneSnapshot
        ) -> InputFrame | None:
            return self._inputs.pop(0) if self._inputs else None

        def play_sounds(self, ids: list[int]) -> None:
            self.sounds.extend(ids)

        def close(self) -> None:
            self.closed = True

    def press(b: Button) -> InputFrame:
        return InputFrame(held=frozenset({b}), pressed=frozenset({b}))

    down = press(Button.DOWN)
    inputs: list[InputFrame | None] = (
        [_IDLE] * 11
        + [down] * 3  # 0→2(Extra 锁定滑过)→3→4(Player Data)
        + [press(Button.SHOT)]  # 进 Player Data
        + [_IDLE] * 21  # INIT 20 帧门 + 进门帧
        + [press(Button.UP)]  # cursor 1→0(Easy)
        + [press(Button.SHOT)]  # 进 Easy 榜
        + [_IDLE] * 31  # 30 帧页门
        + [press(Button.RIGHT)]  # 换机体
        + [_IDLE] * 30  # 移动后重新计门
        + [press(Button.BOMB)]  # 回难度菜单
        + [_IDLE] * 21  # INIT 门
        + [press(Button.BOMB)]  # cursor 0→8(终了)
        + [press(Button.BOMB)]  # 离场
        + [_IDLE] * 61  # 60 帧离场 → 回主菜单(光标停 4)
        + [_IDLE] * 11  # 主菜单确认门
        + [down] * 3  # 4→5→6→7(Exit)
        + [press(Button.SHOT)]  # Quit
        + [_IDLE] * 60  # 离场 60 帧后退出
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
    # SE: 确认 10 ×2(都在主菜单, Result 内进页无确认音), 移动 12 ×8, 返回 11 ×3
    assert backend.sounds.count(10) == 2
    assert backend.sounds.count(12) == 8
    assert backend.sounds.count(11) == 3


# ---- 真数据: 资源/布局 ----
@needs_data
def test_real_data_layout() -> None:
    """真机: result.jpg 底 + result00.anm 41 台 VM 跑脚本, 榜/符卡页有贴图。"""
    from touhou.engine import open_archive
    from touhou.games.th07.compose import DATA_PATH

    archive = open_archive(DATA_PATH, format_name="pbg4")
    scene = PlayerDataScene(archive, _store(), on_exit=lambda: _Marker())
    assert sum(1 for w in scene._vms if w.vm.alive) == 41
    _enter(scene)
    snap = scene.snapshot()
    assert snap.sprites[0].image == "result.jpg"
    assert any(s.image.startswith("result00.anm:") for s in snap.sprites)
    # 进 Easy 榜: 面板 VM 滑入后表格文字出现
    scene.cursor = 0
    scene.step(_press(Button.SHOT))
    _step(scene, _IDLE, 90)
    texts = _texts(scene)
    assert "No  Name      Score(Stage)  Date   Slow" in texts
