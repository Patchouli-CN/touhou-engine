"""th07 一面 msg 集成冒烟(needs_data): 对话驱动全流程打到尾王, 出结算换关。"""

from __future__ import annotations

from touhou.engine import Button, InputFrame, PlayerState
from touhou.engine.enemies import EnemySpawned
from touhou.engine.events import Event
from touhou.engine.msg import MsgNextLevel, MsgStageResults
from touhou.games.th07.compose import compose
from touhou.games.th07.msg import StageResultPanel
from touhou.games.th07.world import Th07World, compose_world

from .conftest import needs_data

pytestmark = needs_data


def _input(i: int) -> InputFrame:
    """站桩按住射击 + Z 脉冲推对话(每 15 帧一次新按下沿)。"""
    return InputFrame(
        held=frozenset({Button.SHOT}),
        pressed=frozenset({Button.SHOT}) if i % 15 == 0 else frozenset(),
    )


class _Run:
    """一次一面全程模拟的采集面: 事件流(带帧号) + msg 状态迁移 + boss 入场。"""

    def __init__(self) -> None:
        self.log: list[tuple[int, Event]] = []
        self.msg_transitions: list[tuple[int, int]] = []  # (frame, new_msg_idx)
        self.boss_arrive: list[tuple[int, bool]] = []  # (frame, msg_active)
        self.panels: list[StageResultPanel | None] = []  # NEXT_LEVEL 当帧的面板


def _run(frames: int) -> tuple[Th07World, _Run]:
    """seed=42 一面(ReimuA/Normal, 夹具续命)跑到换关或帧数上限。"""
    w = compose_world(compose(), character=0, difficulty=1, seed=42)
    w.th07.lives = 99.0  # 夹具续命(看长程流程; 结算逻辑与残机数无关)
    r = _Run()

    def collect(e: Event) -> None:
        r.log.append((w.frame, e))
        if isinstance(e, MsgNextLevel):
            # settle 先于外部订阅: NEXT_LEVEL 到达时面板已建档
            r.panels.append(w.stage_results)

    w.subscribers.append(collect)
    prev_idx, prev_boss = -1, False
    for i in range(frames):
        w.tick(_input(i))
        idx = w.msg_vm.current_msg_idx if w.msg_vm else -9
        if idx != prev_idx:
            r.msg_transitions.append((w.frame, idx))
            prev_idx = idx
        has_boss = w.boss is not None
        if has_boss and not prev_boss:
            r.boss_arrive.append((w.frame, w.msg_active))
        prev_boss = has_boss
        if w.stage_no == 2:
            break
    return w, r


def test_stage_one_msg_chain_to_next_level() -> None:
    """一面打穿: msg0 前置对话(APPEAR_ENEMY 窗) → 尾王击坠 → msg1 结算 → NEXT_LEVEL 换关。"""
    w, r = _run(14000)

    # ---- 对话窗口时序(实跑帧号随注; 旧实现实跑 msg0 = 5518-5835) ----
    msg0_start = r.msg_transitions[0]
    assert msg0_start[1] == 0 and 5400 <= msg0_start[0] <= 5600  # 实跑 5518
    msg0_end = r.msg_transitions[1]
    assert msg0_end[1] == -1
    assert 200 <= msg0_end[0] - msg0_start[0] <= 500  # Z 脉冲推完约 318 帧
    # 尾王入场在 msg0 窗口内且对话仍门控(APPEAR_ENEMY 放行时间轴刷 boss)
    assert len(r.boss_arrive) == 2  # 中超 + 尾王
    final_boss_frame, final_boss_msg_active = r.boss_arrive[1]
    assert final_boss_msg_active
    assert msg0_start[0] < final_boss_frame < msg0_end[0]
    # 对话停轴: msg0 起 → 尾王入场之间无任何刷怪(时间轴被 msg_wait 停住)
    spawns_in_window = [
        f
        for f, e in r.log
        if isinstance(e, EnemySpawned) and msg0_start[0] < f < final_boss_frame
    ]
    assert spawns_in_window == []

    # ---- 结算/换关事件序列: 尾王击坠 → msg1 → STAGERESULTS → NEXT_LEVEL → 二面 ----
    kinds = [type(e).__name__ for _, e in r.log]
    assert kinds.count("MsgStageResults") == 1
    assert kinds.count("MsgNextLevel") == 1
    assert kinds.index("MsgStageResults") < kinds.index("MsgNextLevel")
    results_frame = next(f for f, e in r.log if isinstance(e, MsgStageResults))
    next_frame = next(f for f, e in r.log if isinstance(e, MsgNextLevel))
    assert results_frame > msg0_end[0]  # 结算对话在尾王战之后
    # NEXT_LEVEL 登记后次帧帧首换关
    assert w.stage_no == 2
    assert 1 <= w.frame - next_frame <= 2
    assert w.frame < 14000  # 实跑 13127

    # ---- 换关后状态: 结算面板已清, 场/脚本/玩家重置, 分数经 guiScore 恢复 ----
    assert w.stage_results is None
    assert w.msg_vm is not None and w.msg_vm.current_msg_idx == -1
    assert w.boss is None
    assert w.player.state in (PlayerState.SPAWNING, PlayerState.INVULNERABLE)
    g = w.th07
    assert g.subrank == 0 and g.graze_in_stage == 0
    assert g.point_items_collected_this_stage == 0
    assert w.globals.score > 0
    # 二面脚本已装载并开跑(新时间轴在走)
    assert any(not tl.done for tl in w.timelines)

    # 二面再跑 600 帧: 新关刷怪, 世界继续推进
    spawns_before = sum(1 for _, e in r.log if isinstance(e, EnemySpawned))
    for i in range(600):
        w.tick(_input(i))
    spawns_after = sum(1 for _, e in r.log if isinstance(e, EnemySpawned))
    assert spawns_after > spawns_before
    assert w.stage_no == 2

    # ---- 结算面板数据(NEXT_LEVEL 当帧已建档) ----
    assert len(r.panels) == 1
    panel = r.panels[0]
    assert panel is not None
    assert panel.stage == 1 and not panel.all_clear
    assert panel.rank_line == "Normal Rank  *1.0"
    assert panel.penalty_line == "Player Penalty*0.5"
    assert [name for name, _ in panel.lines] == ["Clear", "Point", "Graze", "Cherry"]
    assert panel.lines[0][1] == 1000000  # Clear 行 = stage * 1000000 (显示值)
    assert panel.total > 0
    assert panel.point_items > 0
