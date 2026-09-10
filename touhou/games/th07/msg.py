"""th07 的 msg 接线: 对话系统(门控/清场) + STAGERESULTS 结算 + NEXT_LEVEL 换关。

执行器本体在 engine.msg(流派通用); 本模块是作品语义: msg{n}.dat 装载、
过关奖励公式(Gui.cpp:1357-1417)、换关分流(Gui.cpp:1004-1058)、对话中每帧
清道具/结界立即自然破。移植 old/touhou/games/th07/world.py 的
_step_msg/_on_stage_results/_on_next_level/_advance_stage。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import msgspec

from ...engine import (
    Button,
    FrameContext,
    MsgExecutor,
    MsgInput,
    PlayerState,
    System,
)
from ...engine.ecl import TimelineRunner
from ...engine.player import SPAWN_INVULN
from ...schemas.archive import load_entry
from ...schemas.msg import parse_msg
from ...utils.math import Vec2
from .ecl_table import parse_ecl
from .ecl_timeline import TL_HANDLERS
from .player import OPTION_ANGLE_CENTER, Border, BorderState, OptionState

if TYPE_CHECKING:
    from .world import Th07World  # 仅类型检查期(运行时本模块被 world 引用)

#: 结算面板难度行 (Gui::OnDraw finishedStage 段)
_RANK_LINES = (
    "Easy Rank    *0.5",
    "Normal Rank  *1.0",
    "Hard Rank    *1.2",
    "Lunatic Rank *1.5",
    "Extra Rank   *2.0",
    "Phantasm Rank*2.0",
)


class StageResultPanel(msgspec.Struct, frozen=True):
    """关卡结算面板数据(Gui::OnDraw finishedStage 段; 引擎不画, view 消费)。"""

    stage: int
    all_clear: bool  # C: currentStage<6 → "Stage Clear", 否则 All Clear
    lines: tuple[tuple[str, int], ...]  # 面板行(显示值)
    rank_line: str
    penalty_line: str | None
    total: int  # 显示为 f"{total}0" (Gui.cpp "Total = %8d0")
    # ---- 快照(结算时的本关计数) ----
    clear_power: int
    point_items: int
    cherry_range: int  # cherryMax - cherryStart
    graze: int
    lives: int
    bombs: int


class Th07MsgSystem(System["Th07World"]):
    """LOGIC 槽: 推进对话 VM(Gui::OnUpdate → RunMsg), 挂在时间轴后/敌 ECL 前。

    对话中每帧清道具 + 结界立即自然破(Gui.cpp RunMsg: playerState != DEAD 时
    RemoveAllItems; hasBorder != NONE 时 BreakBorderNaturally)。时间轴停轴由
    host.msg_wait(TlMsgWait handler)完成; 射击/炸弹门控用帧首快照
    (Sync/Bomb/PlayerSystem)。
    """

    def tick(self, world: Th07World, ctx: FrameContext) -> None:
        vm = world.msg_vm
        if vm is None:
            return
        vm.step(
            MsgInput(
                advance_pressed=Button.SHOT in ctx.input.pressed,
                skip_held=Button.SKIP in ctx.input.held,
            )
        )
        for ev in vm.take_events():
            ctx.events.emit(ev)
        if not vm.has_current_msg_idx():
            return
        if world.player.state != PlayerState.DEAD:
            world.items.remove_all_items()
        if world.player.border.has_border != BorderState.NONE:
            _break_border_naturally(world)


def _break_border_naturally(world: Th07World) -> None:
    """对话中结界立即自然破(BreakBorderNaturally 入账, 与 BorderSystem 自然破同账)。"""
    # 出处 old/touhou/games/th07/world.py:675 (Player.cpp:2004-2034)
    g = world.th07
    res = world.player.border.break_border_naturally(
        cherry=g.cherry, cherry_start=g.cherry_start, cherry_max=g.cherry_max
    )
    g.cherry = res.cherry
    g.cherry_max = res.cherry_max
    g.cherry_plus = res.cherry_plus
    world.add_score(res.score)
    world.player.state = PlayerState.INVULNERABLE
    world.player.invulnerability_timer = max(
        world.player.invulnerability_timer, res.invulnerability_timer
    )
    world.frame_sounds.append(33)  # se_bonus (BreakBorderNaturally, Player.cpp:2015)


# ---- STAGERESULTS 过关结算 / NEXT_LEVEL 换关 (Gui.cpp RunMsg) ----


def apply_stage_results(w: Th07World) -> None:
    """MSG_STAGERESULTS: 快照本关计数, 算过关奖励并入账, 面板数据留给 view。

    奖励(代码值): Clear=stage*100000 + Graze*50 + Point*5000
    + Cherry(cherryMax-cherryStart); 6/7/8 面追加 Player=lives*2000000
    + Bomb=bombs*400000; 难度修正 Easy*0.5/Hard*1.2/Lunatic*1.5/Extra·
    Phantasm*2; 初始残机 3→*0.5。
    """
    # 出处 old/touhou/games/th07/world.py:1061 (Gui.cpp:972-991 + :1357-1417)
    g = w.th07
    stage = w.stage_no
    snap = dict(
        clear_power=int(g.power),
        point_items=g.point_items_collected_this_stage,
        cherry_range=g.cherry_max - g.cherry_start,
        graze=g.graze_in_stage,
        lives=int(g.lives),
        bombs=int(g.bombs),
    )
    if stage >= 6:
        g.extends_from_point_items = -1  # 奖残封口
    survivor = stage >= 6  # 6/7/8 面: 残机/炸弹奖
    bonus = (
        stage * 100000
        + snap["graze"] * 50
        + snap["point_items"] * 5000
        + snap["cherry_range"]
    )
    if survivor:
        bonus += snap["lives"] * 2000000 + snap["bombs"] * 400000
    d = w.difficulty
    if d == 0:
        bonus //= 2
    elif d == 2:
        bonus = bonus * 12 // 10
    elif d == 3:
        bonus = bonus * 15 // 10
    elif d >= 4:
        bonus <<= 1
    # lifeCount 惩罚 (Gui.cpp:1389-1399): 固定 3(Extra/Phantasm 不受理), 恒 *0.5
    penalty_line = None
    if d < 4:
        bonus = bonus * 5 // 10
        penalty_line = "Player Penalty*0.5"
    # Gui.cpp:1408-1417 ZUN bloat: AddScore ×10 (每次内部 //10, 合计 = bonus)
    for _ in range(10):
        w.add_score(bonus)
    lines = [
        ("Clear", stage * 1000000),
        ("Point", snap["point_items"] * 50000),
        ("Graze", snap["graze"] * 500),
        ("Cherry", snap["cherry_range"] * 10),
    ]
    if survivor:
        lines.append(("Player", snap["lives"] * 20000000))
        lines.append(("Bomb", snap["bombs"] * 4000000))
    w.stage_results = StageResultPanel(
        stage=stage,
        all_clear=stage >= 6,
        lines=tuple(lines),
        rank_line=_RANK_LINES[d],
        penalty_line=penalty_line,
        total=bonus,
        clear_power=snap["clear_power"],
        point_items=snap["point_items"],
        cherry_range=snap["cherry_range"],
        graze=snap["graze"],
        lives=snap["lives"],
        bombs=snap["bombs"],
    )


def apply_next_level(w: Th07World) -> None:
    """MSG_NEXT_LEVEL 分流(Gui.cpp:1004-1058): 1-5 面登记次帧帧首换关。

    6 面 → 结局 / 7-8 面(Extra·Phantasm) → 总结算: ending/result 未接(留待)。
    """
    # 出处 old/touhou/games/th07/world.py:1144
    if w.pending_next_level:
        return
    if w.stage_no < 6:
        w.pending_next_level = True


def advance_stage(w: Th07World) -> None:
    """换关(GameManager::AddedCallback curState==3 分支 + 公共路径)。

    带走(th07/globals 不清): score(经 guiScore 恢复)/lives/bombs/power/cherry 系/
    grazeInTotal/rank/奖残计数/符卡捕获/deaths/bombsUsed。
    重置: subrank/pointItemsCollectedThisStage/grazeInStage; 各 Manager 清场
    (field 原地清, 管线持有引用不重建); 玩家/结界/子机/炸弹回出生点。
    """
    # 出处 old/touhou/games/th07/world.py:1166 (_advance_stage)
    g = w.th07
    w.globals.snap_gui_score()  # NEXT_LEVEL: guiScore 对齐真实分
    w.stage_results = None
    g.subrank = 0
    g.point_items_collected_this_stage = 0
    g.graze_in_stage = 0
    # score=0 但 guiScore 已对齐旧值, 次帧 tick_gui_score 恢复 (GameManager.cpp:235-237)
    w.globals.score = 0
    # ---- 各 Manager 重建(清场) ----
    w.bullets.clear()
    w.bullets.screen_clear_time = 0
    w.lasers.clear()
    w.enemies.clear()
    w.boss = None
    w.boss_enemy = None
    w.rand_spawn_idx = 0
    w.rand_table_idx = 0
    w.border_boxes = []
    w.death_pos = None
    w.spellcard_began_frame = -1
    w.msg_active = False
    # ---- Player::RegisterChain(0): 玩家/结界/子机/炸弹 → SPAWNING 出生点 ----
    p = w.player
    p.pos = Vec2(192.0, 384.0)  # 出生点(AddedCallback: 场心偏下)
    p.velocity = Vec2.zero()
    p.focus = False
    p.firing = False
    p.state = PlayerState.SPAWNING
    p.invulnerability_timer = SPAWN_INVULN
    p.respawn_timer = 0
    p.bullet_grace_period = 0
    p.border = Border()
    w.options.state = OptionState.UNFOCUSED
    w.options.focus_movement_timer = 0
    w.options.option_angle = OPTION_ANGLE_CENTER
    w.options.options = []
    b = w.bomb
    b.is_in_use = False
    b.timer = 0
    b.has_ticked = False
    b.invulnerability_timer = 0
    b.invulnerable = True
    b.move_speed_multiplier = 1.0
    b.damage_boxes = []
    b.clear_boxes = []
    b.sub_info = []
    b.cherry_drain = 0
    b.drain_applied = 0
    b.events = []
    b.shakes = []
    # ---- currentStage++ → EclManager.Load + Gui::LoadMsg ----
    w.stage_no += 1
    w.enemies.stage = w.stage_no
    load_stage(w)


def load_stage(w: Th07World) -> None:
    """装当前关的 ECL/时间轴/msg(缺 msg 资源则不留 VM, 不停轴, 同旧行为)。"""
    # 出处 old/touhou/games/th07/world.py:628 (enter_stage) + :351 (msg 装载)
    assert w.archive is not None and w.resources is not None and w.host is not None
    ecl_file = parse_ecl(
        load_entry(w.archive, w.resources.ecl_file.format(n=w.stage_no))
    )
    w.host.load_stage(ecl_file)
    w.timelines = [
        TimelineRunner(tl, w.host, w.host.rng, TL_HANDLERS) for tl in ecl_file.timelines
    ]
    try:
        msg_data = load_entry(w.archive, w.resources.msg_file.format(n=w.stage_no))
    except KeyError:
        w.msg_vm = None
    else:
        w.msg_vm = MsgExecutor(parse_msg(msg_data))
    w.host.msg_vm = w.msg_vm
