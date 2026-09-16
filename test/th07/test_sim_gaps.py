"""th07 sim 数值缺口的假数据测试(对照 C++ 逐条, 出处见各用例)。

走 settle/msg/enemies 的作品层入口, 不需真实 th07.dat: 结界中擦弹入账、
奖残上限转换、生存 rank 缓涨、高面清弹转星、bomb 中消弹分值、结算 5 残系数。
"""

from __future__ import annotations

from touhou.engine import FrameContext
from touhou.engine.bullets import BulletGraze
from touhou.engine.events import Event
from touhou.engine.items import ItemCollected
from touhou.games.th07.enemies import Th07EnemyField
from touhou.games.th07.globals import Th07Globals
from touhou.games.th07.items import ItemKind
from touhou.games.th07.msg import apply_stage_results
from touhou.games.th07.player import BorderState
from touhou.games.th07.settle import despawn_bullets_bonus, settle
from touhou.games.th07.world import Th07World
from touhou.utils.math import Vec2


def _settle(w: Th07World, ev: Event) -> None:
    """帧外投递一条结算事件(add_score 要帧上下文; 正常路径在 tick 内 flush)。"""
    w.ctx = FrameContext(w.rng, None)
    settle(w, ev)
    w.ctx = None


def _collect(w: Th07World, kind: ItemKind, **kw: object) -> None:
    _settle(w, ItemCollected(kind, 100.0, 200.0, **kw))  # type: ignore[arg-type]


# ---- 结界中擦弹入账 (Player.cpp:1214-1226) ----


def test_graze_in_border_raises_cherry_max() -> None:
    """结界 ACTIVE 中擦弹: CherryMax/Cherry 低速+30, 高速+80。"""
    w = Th07World()
    g = w.th07
    w.player.border.has_border = BorderState.ACTIVE
    w.player.focus = True
    _settle(w, BulletGraze(100.0, 100.0))
    assert g.cherry_max == 30 and g.cherry == 30
    w.player.focus = False
    _settle(w, BulletGraze(100.0, 100.0))
    assert g.cherry_max == 110 and g.cherry == 110


def test_graze_without_border_leaves_cherry() -> None:
    """无结界擦弹不动樱点(结界分支不触发)。"""
    w = Th07World()
    _settle(w, BulletGraze(100.0, 100.0))
    assert w.th07.cherry_max == 0 and w.th07.cherry == 0


# ---- 奖残/1up 上限 (GameManager.cpp:100-118 + ItemManager.cpp:377-379) ----


def test_point_extend_awards_life_and_subrank() -> None:
    """点道具过奖残门槛: 残机+1 且 subrank+200(点道具自带 +3 不在其内)。"""
    w = Th07World(difficulty=1)
    g = w.th07
    g.initialize_rank(1)
    g.lives = 7.0
    g.point_items_collected_for_extend = 49  # 门槛 50 (extends=0, 难度<4)
    _collect(w, ItemKind.POINT)
    assert g.lives == 8.0 and g.extends_from_point_items == 1
    assert g.rank == 18 and g.subrank == 3  # 200+3 → rank+2
    assert 28 in w.frame_sounds  # SOUND_EXTEND


def test_point_extend_full_lives_converts_to_bomb() -> None:
    """满 8 残时奖残转 bomb。"""
    w = Th07World(difficulty=1)
    g = w.th07
    g.lives = 8.0
    g.bombs = 2.0
    g.point_items_collected_for_extend = 49
    _collect(w, ItemKind.POINT)
    assert g.lives == 8.0 and g.bombs == 3.0
    assert 28 in w.frame_sounds


def test_extend_full_lives_full_bombs_noop() -> None:
    """残机/bomb 双满: 门槛照过但无入账(无分无音)。"""
    w = Th07World(difficulty=1)
    g = w.th07
    g.initialize_rank(1)
    g.lives = 8.0
    g.bombs = 8.0
    g.point_items_collected_for_extend = 49
    _collect(w, ItemKind.POINT)
    assert g.lives == 8.0 and g.bombs == 8.0
    assert g.extends_from_point_items == 1
    assert g.subrank == 3  # 仅点道具自带 +3
    assert 28 not in w.frame_sounds


def test_life_item_goes_through_extend_path() -> None:
    """1up 道具同走 ExtendFromPoints: 未满+1 残, 满 8 残转 bomb。"""
    w = Th07World()
    g = w.th07
    g.lives = 3.0
    _collect(w, ItemKind.LIFE)
    assert g.lives == 4.0 and g.rank == 18  # subrank+200 即 rank+2
    g.lives = 8.0
    g.bombs = 1.0
    _collect(w, ItemKind.LIFE)
    assert g.lives == 8.0 and g.bombs == 2.0


# ---- 生存 rank 缓涨 (EnemyManager.cpp:624-632) ----


def test_survival_rank_tick() -> None:
    """非对话每 (2400-残机*240) 帧 subrank+100(=rank+1); 计数先判后++。"""
    field = Th07EnemyField()
    g = Th07Globals()
    g.initialize_rank(1)  # Normal: rank 16
    g.lives = 2.0  # limit = 1920
    for _ in range(1920):
        field.tick_survival_rank(g, msg_active=False)
    assert g.rank == 16  # 1920 帧还差一拍(timelineTime 0 不计, HasTicked 守卫)
    field.tick_survival_rank(g, msg_active=False)
    assert g.rank == 17


def test_survival_rank_gate_during_dialog() -> None:
    """对话中判定跳过但计数照走(timelineTime++ 在 msg 门控外); 出对话下一档即补。"""
    field = Th07EnemyField()
    g = Th07Globals()
    g.initialize_rank(1)
    g.lives = 2.0
    for _ in range(1919):
        field.tick_survival_rank(g, msg_active=False)
    field.tick_survival_rank(g, msg_active=True)  # 第 1920 帧在对话中: 不判定
    assert g.rank == 16
    field.tick_survival_rank(g, msg_active=False)  # 计数 1920 → 出对话即入账
    assert g.rank == 17


def test_survival_rank_counter_reset_on_stage_clear() -> None:
    """换关清零(EnemyManager 每面 RegisterChain 重建 → clear 复位计数)。"""
    field = Th07EnemyField()
    g = Th07Globals()
    g.lives = 2.0
    for _ in range(100):
        field.tick_survival_rank(g, msg_active=False)
    field.clear()
    assert field.timeline_time == 0


# ---- 6/Ex/Ph 面清弹转星道具 (Gui.cpp:800/806/811) ----


def test_despawn_bullets_bonus_item_kind_per_stage() -> None:
    """清弹转道具按面切换: 1-5 面弹消点, 6/7/8 面星。"""
    for stage, kind in (
        (5, ItemKind.POINT_BULLET),
        (6, ItemKind.STAR),
        (7, ItemKind.STAR),
        (8, ItemKind.STAR),
    ):
        w = Th07World(stage_no=stage)
        w.bullets.ring(
            Vec2(192.0, 100.0), 3, 1.0, FrameContext(w.rng, None), aimed=False
        )
        despawn_bullets_bonus(w)
        assert [i.kind for i in w.items.alive()] == [kind] * 3


def test_full_power_clear_uses_star_on_late_stages() -> None:
    """满火力道具的清弹同样按面转星 (ItemManager.cpp:381-387 → RemoveAllBullets)。"""
    w = Th07World(stage_no=8)
    w.bullets.ring(Vec2(192.0, 100.0), 2, 1.0, FrameContext(w.rng, None), aimed=False)
    _collect(w, ItemKind.FULL_POWER)
    assert [i.kind for i in w.items.alive()] == [ItemKind.STAR] * 2


# ---- bomb 中消弹分值分支 (ItemManager.cpp:395-421) ----


def test_point_bullet_during_bomb() -> None:
    """Bomb 中弹消点 = 100 分, 樱点按道具槽位奇偶 cherryPlus+10 / cherry+10。"""
    w = Th07World()
    g = w.th07
    g.cherry_max = 100000  # 留出 cherry 空间
    w.bomb.is_in_use = True
    _collect(w, ItemKind.POINT_BULLET, slot=0)
    assert g.cherry_plus == 10 and g.cherry == 10
    _collect(w, ItemKind.POINT_BULLET, slot=1)
    assert g.cherry_plus == 10 and g.cherry == 20
    assert w.globals.score == 20  # 两个 100(代码值), 入账 //10


def test_point_bullet_outside_bomb_unchanged() -> None:
    """非 bomb 中: 擦弹分 + cherryPlus+20(原路径不回归)。"""
    w = Th07World()
    g = w.th07
    g.cherry_max = 100000
    g.graze_in_total = 400
    _collect(w, ItemKind.POINT_BULLET, slot=1)
    assert w.globals.score == (400 // 40 * 10 + 300) // 10
    assert g.cherry_plus == 20


# ---- 每面结算 lifeCount 系数 (Gui.cpp:1413-1421) ----


def test_stage_results_life_count_penalty() -> None:
    """初始 4 残(lifeCount=3)*0.5 / 5 残(lifeCount=4)*0.2 / 默认 3 残无惩罚。"""
    base = 3 * 100000  # stage*100000, 其余计数为 0, Normal 无难度系数
    for lives, expect, line in (
        (3, base, None),
        (4, base * 5 // 10, "Player Penalty*0.5"),
        (5, (base << 1) // 10, "Player Penalty*0.2"),
    ):
        w = Th07World(difficulty=1, stage_no=3, initial_lives=lives)
        w.ctx = FrameContext(w.rng, None)
        apply_stage_results(w)
        w.ctx = None
        r = w.stage_results
        assert r is not None
        assert r.total == expect and r.penalty_line == line


# ---- CHERRY 道具未满樱红字弹分 (ItemManager.cpp:437-443) ----


def test_cherry_item_below_max_red_popup() -> None:
    """樱点道具未满 CherryMax: 弹红字 1000+100×符卡捕获数(不加总分)。"""
    w = Th07World()
    g = w.th07
    g.cherry, g.cherry_max = 0, 200000
    g.spell_cards_captured = 3
    _collect(w, ItemKind.CHERRY)
    assert w.frame_popups == [(100.0, 200.0, 1300, 0xFFFF4040, 1)]
    assert g.cherry_plus == 1300  # 樱点入账同值 (:441-442)


def test_cherry_item_at_max_no_red_popup() -> None:
    """满樱: 弹分数(黄/白)不弹红字。"""
    w = Th07World()
    g = w.th07
    g.cherry = g.cherry_max = 200000
    _collect(w, ItemKind.CHERRY)  # y=200 在 POC 线下 → 白字 50000-(200-poc)*100
    assert w.frame_popups
    assert all(color != 0xFFFF4040 for _, _, _, color, _ in w.frame_popups)
    assert w.globals.score > 0
