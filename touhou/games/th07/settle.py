"""th07 的事件结算: 把引擎事件入账到 globals/items/boss(世界在帧末订阅 EventStream)。

分值/樱点/掉落/奖残语义逐条照抄旧实现(old/touhou/games/th07/world.py +
items.py + player.py; C++ 出处随各函数单行注释)。弹字/横幅/音效是 view 消费面,
本模块不产。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from ...engine.bomb import BombClearedBullet, BombStarted
from ...engine.boss import SpellcardEnded, SpellcardFailed
from ...engine.bullets import BulletGraze, BulletHit
from ...engine.enemies import EnemyDamaged, EnemyDied, EnemyTimerCallback
from ...engine.events import Event
from ...engine.items import STATE_ATTRACT, ItemCollected, ItemDropped
from ...engine.lasers import LaserGraze, LaserHit
from ...engine.msg import MsgNextLevel, MsgStageResults
from ...engine.player import (
    PlayerDeathSettled,
    PlayerDied,
    PlayerGraceClear,
    PlayerGrazed,
    PlayerRespawned,
)
from ...utils.math import Vec2
from .bomb import BOMB_SOUNDS, SE_BOMB
from .data import DROP_TABLE, FULL_POWER, FULL_POWER_SCORE_BONUS
from .items import ItemKind, next_needed_point_items_for_extend
from .msg import apply_next_level, apply_stage_results
from .player import settle_death

if TYPE_CHECKING:
    from .world import Th07World

# 擦弹(old/touhou/games/th07/player.py:57-60)
_GRAZE_SCORE_CODE = 2000  # 显示 200 → AddScore(2000)
_GRAZE_SUBRANK = 6
_GRAZE_STAGE_CAP = 9999
_GRAZE_TOTAL_CAP = 999999

# 小怪随机掉落(itemDrop==-1): 每 3 杀掉 1, 表索引独立递增 (EnemyManager 死亡分支)
_RAND_DROP_EVERY = 3


def _stage_factor(stage: int) -> int:
    """关卡系数 stageFactor (EnemyManager.cpp:624)。"""
    return 10 if stage >= 5 else stage * 2


def _graze_item_score(graze_total: int) -> int:
    """弹消点/STAR 的代码值分: graze/40*10+300 (ItemManager.cpp)。"""
    # 出处 old/touhou/games/th07/items.py:378
    return graze_total // 40 * 10 + 300


# ---- 敌人伤害/击坠 ----


def _on_enemy_damaged(w: Th07World, ev: EnemyDamaged) -> None:
    """伤害入账: 得分 = min(raw,70)/5 (代码值), 樱点按 raw 伤害查公式。"""
    # 出处 old/touhou/engine/enemies.py:71-95 (EnemyManager.cpp:782-890)
    w.add_score(min(ev.raw_damage, 70) // 5 * 10)
    # 樱点: (boss 或未 focus) 且非 bomb 中才产 (settle_damage 的 bomb_in_use 门控)
    if ev.by_bomb or w.bomb.is_in_use:
        return
    if not (ev.is_boss or not w.player.focus):
        return
    sf = _stage_factor(w.stage_no)
    if ev.is_boss and not w.player.focus:
        gain = ev.raw_damage // (10 - sf // 3) * 10
    else:
        gain = ev.raw_damage // (30 - sf) * 10
    if gain > 70:
        gain = 70
    timer = w.enemies.damage_timers.get(ev.enemy_id, 0)
    if gain == 0 and (not w.player.focus or timer & 1):
        gain = 10
    if w.enemies.is_reimu_a and gain in (20, 30) and timer & 1:
        gain -= 10  # ReimuA 机型修正 (EnemyManager.cpp:815-835)
    if gain:
        w.add_cherry_plus(gain)


def _on_enemy_died(w: Th07World, ev: EnemyDied) -> None:
    """击坠入账: 得分 + 掉落(登记号/随机表) + boss 非符卡击坠的清场奖励。"""
    # 出处 old/touhou/games/th07/world.py:1770 (_kill_reward)
    assert w.host is not None
    if ev.scored:
        w.add_score(ev.score)  # AddScore(enemy->score)
    pos = Vec2(ev.x, ev.y)
    d = ev.item_drop
    if 0 <= d <= 9:
        w.items.spawn(pos, d)
    elif d == -1:
        if w.rand_spawn_idx % _RAND_DROP_EVERY == 0:
            w.items.spawn(pos, DROP_TABLE[w.rand_table_idx % len(DROP_TABLE)])
            w.rand_table_idx = (w.rand_table_idx + 1) % len(DROP_TABLE)
        w.rand_spawn_idx += 1
    if ev.is_boss and not w.spellcard_active():
        # boss 击坠且非符卡中: 清弹转道具 + 清场 + 累计分入账
        # (EnemyManager.cpp:1004-1011 → ShowBonusScore)
        removed = despawn_bullets_bonus(w)
        removed = w.host.remove_all_enemies(8000, removed)
        if removed:
            w.add_score(removed)


def despawn_bullets_bonus(w: Th07World) -> int:
    """弹转弹消点(出生即吸附) + 连带激光沿线出点, 返回累计清弹分(代码值)。"""
    # 出处 old/touhou/games/th07/world.py:1735 (BulletManager.cpp:486-553)
    total = 0
    value = 2000
    for b in w.bullets.alive():
        w.items.spawn(b.pos, ItemKind.POINT_BULLET, state=STATE_ATTRACT)
        total += value
        value = min(value + 20, 8000)
        b.dead = True
    for pt in w.lasers.remove_all(
        skip_flag4=False, spawn_items=True, spawn_at_pos=True
    ):
        w.items.spawn(pt, ItemKind.POINT_BULLET, state=STATE_ATTRACT)
    return total


def _on_enemy_timer_callback(w: Th07World, ev: EnemyTimerCallback) -> None:
    """超时回调: 若是当前 boss 的符卡计时(非宣言当帧), 走符卡失败记账。"""
    # 宣言当帧守卫: 触发切 sub 的超时回调与随后宣言的符卡同帧到达, 不算失败
    boss = w.boss
    if boss is None or w.boss_enemy is None:
        return
    if (
        ev.enemy_id == w.boss_enemy.enemy_id
        and boss.is_active == 1
        and w.frame > w.spellcard_began_frame + 1
    ):
        assert w.ctx is not None
        boss.on_timeout(w.ctx)


# ---- 符卡 ----


def _on_spellcard_ended(w: Th07World, ev: SpellcardEnded) -> None:
    """符卡结束入账: 捕获分/计数/catk; 非超时结束清弹转道具 + 清场, 累计分入账。"""
    # 出处 old/touhou/games/th07/world.py:1689 (_apply_spellcard_end)
    assert w.host is not None
    catk_idx = w.catk_idx
    w.catk_idx = None
    if ev.timed_out:
        return  # 超时罚则已在 SpellcardFailed 入账
    if ev.captured:
        w.add_score(ev.score)  # capture+grazeBonus 已是代码值
        w.th07.spell_cards_captured += 1
        if catk_idx is not None:
            # catk: successes++/highscore 取 max (EclManager.cpp EndSpellcard);
            # 只接 ECL 路径(catk_idx 由 begin 登记)
            w.store.record_spellcard_success(catk_idx, w.character, ev.score // 10)
    removed = despawn_bullets_bonus(w)
    removed = w.host.remove_all_enemies(8000, removed)
    if removed:
        w.add_score(removed)


def _on_spellcard_failed(w: Th07World, ev: SpellcardFailed) -> None:
    """符卡超时失败: 樱点罚 25%(向下取整 10) + RemoveAllBullets(10) 连带激光。"""
    # 出处 old/touhou/games/th07/world.py:451-470
    g = w.th07
    penalty = int((g.cherry - g.cherry_start) * 0.25)
    penalty -= penalty % 10
    g.cherry = max(g.cherry_start, g.cherry - penalty)
    w.bullets.clear()
    w.lasers.remove_all(skip_flag4=False)


# ---- 擦弹 ----


def _on_graze(w: Th07World, ev: Event) -> None:
    """擦弹入账: 计数/得分/subrank + 符卡擦弹加成(樱点公式)。"""
    # 出处 old/touhou/games/th07/world.py:1845 + boss.py:82
    g = w.th07
    g.graze_in_stage = min(_GRAZE_STAGE_CAP, g.graze_in_stage + 1)
    g.graze_in_total = min(_GRAZE_TOTAL_CAP, g.graze_in_total + 1)
    w.add_score(_GRAZE_SCORE_CODE)
    g.increase_subrank(_GRAZE_SUBRANK)
    boss = w.boss
    if boss is not None and boss.is_capturing:
        boss.add_graze_bonus(2500 + (g.cherry - g.cherry_start) // 1500 * 20)


# ---- 炸弹 ----


def _on_bomb_started(w: Th07World, ev: BombStarted) -> None:
    """炸弹发声: 机体音 + 横幅音(计数/决死窗/used_bomb 在触发点已同步入账)。"""
    # 出处 old/touhou/games/th07/world.py:1363-1368
    w.frame_sounds.append(BOMB_SOUNDS.get((w.character, ev.focus), 13))
    w.frame_sounds.append(SE_BOMB)


def _on_bomb_cleared_bullet(w: Th07World, ev: BombClearedBullet) -> None:
    """清弹盒消弹 → 弹消点道具, 出生即吸附 (BulletManager.cpp:995/1010)。"""
    # 出处 old/touhou/games/th07/world.py:1414-1422
    w.items.spawn(Vec2(ev.x, ev.y), ev.item_type, state=STATE_ATTRACT)


# ---- 道具收集 ----


def _add_power(w: Th07World, delta: float) -> None:
    """火力累加(封顶满火力); 有增量且触顶时满火力计分计数清零。"""
    g = w.th07
    g.power = min(float(FULL_POWER), g.power + delta)
    if delta > 0 and g.power >= FULL_POWER:
        g.power_overflow = 0


def _reach_full_power(w: Th07World, *, spellcard_exempt: bool) -> None:
    """触达满火力: 场上 P 转樱 + (非符卡豁免时)清弹转弹消点。"""
    # 出处 old/touhou/games/th07/items.py:227/345/381 + world.py:584-595
    w.items.despawn_power_items()
    if spellcard_exempt and w.spellcard_active():
        return
    for b in w.bullets.alive():
        w.items.spawn(b.pos, ItemKind.POINT_BULLET, state=STATE_ATTRACT)
        b.dead = True
    for pt in w.lasers.remove_all(skip_flag4=True, spawn_items=True):
        w.items.spawn(pt, ItemKind.POINT_BULLET, state=STATE_ATTRACT)


def _point_code(w: Th07World, ev: ItemCollected) -> int:
    """POINT 道具代码值分(POC 线上满分/樱差加成)。"""
    # 出处 old/touhou/games/th07/items.py:341 (_point_score)
    g = w.th07
    poc = w.items.poc_y
    if ev.y < poc or ev.auto_collect:
        code = 50000
    else:
        code = 50000 - int(ev.y - poc) * 100
    gap = g.cherry - g.cherry_start
    if code >= 50000:
        if gap > 50000:
            code = gap
    elif gap > 50000:
        code += (gap - 50000) // 5
    return code - code % 10


def _point_extends(w: Th07World) -> None:
    """点道具残机: 累计过门槛可连升 (ItemManager.cpp:285-325)。"""
    g = w.th07
    if g.extends_from_point_items < 0:
        return
    collected = g.point_items_collected_for_extend
    e = g.extends_from_point_items
    n = 0
    while collected >= next_needed_point_items_for_extend(e, w.difficulty):
        n += 1
        e += 1
    if n:
        g.lives += n
        g.extends_from_point_items += n
        g.next_needed_point_items_for_extend = next_needed_point_items_for_extend(
            e, w.difficulty
        )


def _on_item_collected(w: Th07World, ev: ItemCollected) -> None:
    """道具收集结算(分值语义出处 old/touhou/games/th07/items.py:196 collect)。"""
    g = w.th07
    if ev.kind == ItemKind.POWER_SMALL:
        g.increase_subrank(1)
        if g.power >= FULL_POWER:
            # 满火力: 计数+1 封顶 30 查递增分表 (ItemManager.cpp:202-212)
            n = min(g.power_overflow + 1, 30)
            g.power_overflow = n
            code = FULL_POWER_SCORE_BONUS[min(n, len(FULL_POWER_SCORE_BONUS) - 1)]
            w.add_score(code)
        else:
            _add_power(w, 1)
            w.add_score(10)
            g.power_overflow = 0
            if g.power >= FULL_POWER:
                _reach_full_power(w, spellcard_exempt=True)
    elif ev.kind == ItemKind.POWER_BIG:
        if g.power < FULL_POWER:
            _add_power(w, 8)
            w.add_score(10)
            if g.power >= FULL_POWER:
                _reach_full_power(w, spellcard_exempt=True)
    elif ev.kind == ItemKind.BOMB:
        if g.bombs < 8:
            g.bombs += 1
        g.increase_subrank(5)
    elif ev.kind == ItemKind.LIFE:
        g.lives += 1
    elif ev.kind == ItemKind.FULL_POWER:
        if g.power < FULL_POWER:
            _reach_full_power(w, spellcard_exempt=False)
        g.power = float(FULL_POWER)
        w.add_score(1000)
    elif ev.kind == ItemKind.POINT:
        w.add_score(_point_code(w, ev))
        g.point_items_collected_this_stage += 1
        g.point_items_collected_for_extend += 1
        g.increase_subrank(10 if ev.y < 128.0 else 3)  # C++ 硬编码 128.0(非 pocY)
        _point_extends(w)
    elif ev.kind == ItemKind.POINT_BULLET:
        # 非 bomb 中: 擦弹分 + cherryPlus+20 (ItemManager.cpp:397-408)
        w.add_score(_graze_item_score(g.graze_in_total))
        w.add_cherry_plus(20)
    elif ev.kind == ItemKind.CHERRY:
        if g.cherry >= g.cherry_max:
            # 满樱时按 POINT 计分(无樱差加成), ≤5000 显示 (ItemManager.cpp:428-436)
            if ev.y < w.items.poc_y or ev.auto_collect:
                code = 50000
            else:
                code = 50000 - int(ev.y - w.items.poc_y) * 100
            w.add_score(code - code % 10)
        w.add_cherry_plus(1000 + g.spell_cards_captured * 100)
    elif ev.kind == ItemKind.CHERRY_SMALL:
        w.add_cherry_plus(30)
        g.add_cherry(70)
    elif ev.kind == ItemKind.STAR:
        w.add_score(_graze_item_score(g.graze_in_total))
        w.add_cherry_plus(100)


def _on_item_dropped(w: Th07World, ev: ItemDropped) -> None:
    """道具掉出底边: subrank -3。"""
    w.th07.decrease_subrank(3)


# ---- 玩家命中/死亡/重生 ----


def _on_player_hit(w: Th07World, ev: Event) -> None:
    """敌弹/激光命中: 走 take_hit(结界拦截或死亡; PlayerDied 下帧结算)。"""
    assert w.ctx is not None
    w.player.take_hit(w.ctx)


def _on_player_died(w: Th07World, ev: PlayerDied) -> None:
    """死亡: 记死亡点 + 清激光(旧世界层命中即 lasers.clear)。"""
    w.death_pos = Vec2(ev.x, ev.y)
    w.lasers.clear()


def _on_player_death_settled(w: Th07World, ev: PlayerDeathSettled) -> None:
    """死亡结算: power 罚/掉 P/樱罚/subrank + 符卡捕获失败。"""
    # 出处 old/touhou/games/th07/world.py:1861 (_apply_death_settle)
    g = w.th07
    s = settle_death(
        power=g.power,
        lives=g.lives,
        cherry=g.cherry,
        cherry_start=g.cherry_start,
        cherry_penalty_multiplier=w.cherry_penalty_multiplier,
        is_sakuya=w.character in (4, 5),
    )
    g.power = s.new_power
    g.deaths += 1
    pos = w.death_pos if w.death_pos is not None else w.player.pos
    for _ in range(s.drop_power_big):
        w.items.spawn(pos, ItemKind.POWER_BIG)
    for _ in range(s.drop_power_small):
        w.items.spawn(pos, ItemKind.POWER_SMALL)
    for _ in range(s.drop_full_power):
        w.items.spawn(pos, ItemKind.FULL_POWER)
    if s.cherry_penalty:
        g.cherry = max(g.cherry_start, g.cherry - s.cherry_penalty)
    if s.activate_all_items:
        w.items.activate_all_items()
    if s.subrank_delta:
        g.decrease_subrank(-s.subrank_delta)
    if w.boss is not None:
        w.boss.mark_death()  # 死亡 → 捕获失败 (Player.cpp:1782-1783)


def _on_player_respawned(w: Th07World, ev: PlayerRespawned) -> None:
    """重生: 扣残机 + bomb 回满; 无残机 → game_over。"""
    # 出处 old/touhou/games/th07/world.py:1834
    g = w.th07
    if g.lives > 0:
        g.lives -= 1
        g.bombs = w.initial_bombs
    else:
        w.game_over = True


def _on_grace_clear(w: Th07World, ev: PlayerGraceClear) -> None:
    """重生清弹期每帧: RemoveAllBullets(0) 连带激光(flags&4 豁免, 无道具)。"""
    # 出处 old/touhou/games/th07/world.py:1855
    w.bullets.clear()
    w.lasers.remove_all(skip_flag4=True)


# ---- msg(对话控制事件 → 结算/换关, 作品语义在 msg.py) ----


def _on_msg_stage_results(w: Th07World, ev: MsgStageResults) -> None:
    """MSG_STAGERESULTS: 过关结算(快照/奖励入账/面板数据)。"""
    apply_stage_results(w)


def _on_msg_next_level(w: Th07World, ev: MsgNextLevel) -> None:
    """MSG_NEXT_LEVEL: 登记次帧帧首换关(分流规则见 msg.py)。"""
    apply_next_level(w)


#: 事件类 → 结算 handler(未登记的事件类忽略); handler 按 Any 收(同指令 VM 表)
_HANDLERS: dict[type[Event], Callable[[Th07World, Any], None]] = {
    EnemyDamaged: _on_enemy_damaged,
    EnemyDied: _on_enemy_died,
    EnemyTimerCallback: _on_enemy_timer_callback,
    SpellcardEnded: _on_spellcard_ended,
    SpellcardFailed: _on_spellcard_failed,
    BulletGraze: _on_graze,
    PlayerGrazed: _on_graze,
    LaserGraze: _on_graze,
    ItemCollected: _on_item_collected,
    ItemDropped: _on_item_dropped,
    BulletHit: _on_player_hit,
    LaserHit: _on_player_hit,
    PlayerDied: _on_player_died,
    PlayerDeathSettled: _on_player_death_settled,
    PlayerRespawned: _on_player_respawned,
    PlayerGraceClear: _on_grace_clear,
    BombStarted: _on_bomb_started,
    BombClearedBullet: _on_bomb_cleared_bullet,
    MsgStageResults: _on_msg_stage_results,
    MsgNextLevel: _on_msg_next_level,
}


def settle(w: Th07World, ev: Event) -> None:
    """帧末事件结算入口(world 订阅 EventStream)。"""
    h = _HANDLERS.get(type(ev))
    if h is not None:
        h(w, ev)
