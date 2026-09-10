"""th07 六机体 12 套 bombCalc + 樱点消耗公式 (BombData.cpp 逐函数移植)。

calc 签名统一 (bomb, fctx, bctx): fctx 给 rng (旧 rng_float 注入点, 旧世界层
喂的就是 self.rng.unit), bctx 给每帧外部输入(玩家位置/樱点/难度/追踪目标)。
查表分派见 BOMB_CALCS (g_BombData, BombData.cpp:16-28)。轨迹 trails/AnmVm/
vms offset 为视觉数据源, 不移植(出处注释随各 calc 单行标注)。
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

import msgspec

from ...engine.bomb import ITEM_POINT_BULLET
from ...engine.context import FrameContext
from ...engine.ecl.num import cdiv, cmod
from ...utils.math import Vec2, normalize_angle_diff
from .data import BOMB_PARAMS as _BOMB_PARAMS_RAW

if TYPE_CHECKING:
    from .bomb import Th07BombContext, Th07BombField

# 机体索引 (g_BombData / shotTypeAndCharacter 顺序)
(
    CHAR_REIMU_A,
    CHAR_REIMU_B,
    CHAR_MARISA_A,
    CHAR_MARISA_B,
    CHAR_SAKUYA_A,
    CHAR_SAKUYA_B,
) = range(6)

# 透出事件(世界层 Th07BombSystem 消费; EVENT_END_PLAYER_SPELLCARD 为 GUI 横幅, 逻辑无影响)
EVENT_REMOVE_ALL_ITEMS = "remove_all_items"  # g_ItemManager.RemoveAllItems()
EVENT_END_PLAYER_SPELLCARD = "end_player_spellcard"  # g_Gui.EndPlayerSpellcard()
EVENT_STOP_BULLET_MOVEMENT = (
    "stop_bullet_movement"  # 咲夜B 停时 (BulletManager::StopBulletMovement)
)

# ComputeBombCherryDrain 难度除数 Hard/2 Lunatic/4 Extra·Phantasm/3 (BombData.cpp:91-103)
_DRAIN_DIVISOR = {2: 2, 3: 4, 4: 3, 5: 3}

# 魔理沙B 非集中激光伤害盒间距: vms[0].sprite->heightPx * scale.y / 5 (BombData.cpp:1027);
# sprite 高×缩放属 anm 数据(仓库无此源), 按 256/5 处理 —— 旧移植报告偏差记录
MARISA_B_LASER_STEP = 256.0 / 5.0


class BombParams(msgspec.Struct, frozen=True):
    """单机体单形态炸弹的首帧初始化参数 (BombData.cpp 各 *Calc 的 bombTimer==0 分支)。"""

    duration: int  # bombDuration
    invulnerability: int  # player.invulnerabilityTimer
    drain_min_cost: int  # ComputeBombCherryDrain minCost
    drain_scale: float  # ComputeBombCherryDrain scale


# 六机体参数表(原始行集中在同包 data.BOMB_PARAMS —— 单一来源, 这里只包成 BombParams)
BOMB_PARAMS: dict[tuple[int, bool], BombParams] = {
    key: BombParams(*raw) for key, raw in _BOMB_PARAMS_RAW.items()
}


def compute_bomb_cherry_drain(
    *,
    cherry: float,
    cherry_start: float,
    difficulty: int,
    bomb_duration: int,
    min_cost: int,
    scale: float,
) -> int:
    """BombData::ComputeBombCherryDrain (BombData.cpp:87-112), 照抄 C++ 整数截断顺序。"""
    drain = int((cherry - cherry_start) * scale)  # (i32)(f32) 向零截断
    divisor = _DRAIN_DIVISOR.get(difficulty)
    if divisor is not None:
        drain = cdiv(drain, divisor)
    drain = cdiv(drain, bomb_duration)
    drain -= cmod(drain, 10)
    min_cost = cdiv(min_cost, bomb_duration)
    min_cost -= cmod(min_cost, 10)
    return max(drain, min_cost)


def _in_bounds(x: float, y: float, width: float, height: float) -> bool:
    """GameManager::IsInBounds (GameManager.cpp:42-65), 咲夜A 非集中出界判定。"""
    return not (
        width / 2.0 + x < 0.0
        or x - width / 2.0 > 384.0
        or height / 2.0 + y < 0.0
        or y - height / 2.0 > 448.0
    )


# ---------------------------------------------------------------------------
# ReimuA 「灵符·梦想妙珠」
# ---------------------------------------------------------------------------


def _calc_reimu_a_unfocused(
    bomb: Th07BombField, fctx: FrameContext, bctx: Th07BombContext
) -> None:
    """灵梦A 非集中「梦想妙珠散」 (BombData.cpp:116-256)。"""
    if bomb.timer >= bomb.duration:
        bomb.is_in_use = False
        bomb.events.append(EVENT_END_PLAYER_SPELLCARD)
        return
    if bomb.has_ticked and bomb.timer == 0:
        params = BOMB_PARAMS[(CHAR_REIMU_A, False)]
        bomb.duration = params.duration
        bomb.invulnerability_timer = params.invulnerability
        for sub in bomb.sub_info:
            sub.state = 0
        bomb.events.append(EVENT_REMOVE_ALL_ITEMS)
        bomb._spawn_clear(
            bctx.player_pos,
            radius=32.0,
            growth=8.0,
            lifetime=16,
            item_type=ITEM_POINT_BULLET,
        )
        bomb.start_pos = bctx.player_pos
        bomb.cherry_drain = compute_bomb_cherry_drain(
            cherry=bctx.cherry,
            cherry_start=bctx.cherry_start,
            difficulty=bctx.difficulty,
            bomb_duration=params.duration,
            min_cost=params.drain_min_cost,
            scale=params.drain_scale,
        )
    if bomb.has_ticked and 8 <= bomb.timer < 80 and bomb.timer % 6 == 0:
        i = (bomb.timer - 8) // 6
        sub = bomb.sub_info[i]
        sub.state = 1
        sub.speed = 15.0
        sub.pos = bctx.player_pos
        if bomb.start_pos.x < 192.0:
            angle = i * math.tau / 8.0 - math.pi / 2
        else:
            angle = -i * math.tau / 8.0 - math.pi / 2
        sub.angle = angle % math.tau  # utils::AddNormalizeAngle(angle, 0)
        sub.counter = 0
        bomb.damage_boxes[i].damage = 0
    bomb.invulnerable = True  # playerState = INVULNERABLE (BombData.cpp:182)
    # 注意: C++ 只处理 subInfo[0..7]; spawn 的 i=8..11 静置原地 (ZUN quirk)
    for i in range(8):
        sub = bomb.sub_info[i]
        if sub.state == 0:
            continue
        box = bomb.damage_boxes[i]
        if sub.state == 1:
            sub.speed -= 0.4  # * effectiveFramerateMultiplier(=1.0)
            sub.vel = Vec2.from_angle(sub.angle, sub.speed)
            if sub.speed < -10.0:
                sub.state = 2
                box.pos = sub.pos
                box.size = Vec2(256.0, 256.0)
                box.lifetime = 400
                bomb._spawn_clear(
                    sub.pos,
                    radius=64.0,
                    growth=4.266667,
                    lifetime=30,
                    item_type=ITEM_POINT_BULLET,
                )
                sub.vel = Vec2.zero()
                # 珠爆开震屏 (BombData.cpp:218 RegisterChain(1,16,8,0))
                bomb.shakes.append((16, 8, 0))
            if bomb.has_ticked:
                # C++ 同帧继续执行 (BombData.cpp:220-229): 爆开当帧伤害盒被覆写为 48×48/8
                box.size = Vec2(48.0, 48.0)
                box.pos = sub.pos
                box.lifetime = 8
                bomb._spawn_clear(
                    sub.pos,
                    radius=128.0,
                    growth=0.0,
                    lifetime=0,
                    item_type=ITEM_POINT_BULLET,
                )
        elif bomb.has_ticked:
            box.pos = sub.pos
            box.size = Vec2(256.0, 256.0)
            box.lifetime = 2
            sub.counter += 1
            if sub.counter >= 30:
                sub.state = 0
        sub.pos = sub.pos + sub.vel
    bomb.timer += 1


def _calc_reimu_a_focused(
    bomb: Th07BombField, fctx: FrameContext, bctx: Th07BombContext
) -> None:
    """灵梦A 集中「梦想妙珠集」 (BombData.cpp:310-474); 炸弹中移速 ×0.6。"""
    if bomb.timer >= bomb.duration:
        bomb.is_in_use = False
        bomb.move_speed_multiplier = 1.0
        bomb.events.append(EVENT_END_PLAYER_SPELLCARD)
        return
    if bomb.has_ticked and bomb.timer == 0:
        params = BOMB_PARAMS[(CHAR_REIMU_A, True)]
        bomb.duration = params.duration
        bomb.invulnerability_timer = params.invulnerability
        for sub in bomb.sub_info:
            sub.state = 0
        bomb.events.append(EVENT_REMOVE_ALL_ITEMS)
        bomb._spawn_clear(
            bctx.player_pos,
            radius=32.0,
            growth=8.0,
            lifetime=16,
            item_type=ITEM_POINT_BULLET,
        )
        bomb.cherry_drain = compute_bomb_cherry_drain(
            cherry=bctx.cherry,
            cherry_start=bctx.cherry_start,
            difficulty=bctx.difficulty,
            bomb_duration=params.duration,
            min_cost=params.drain_min_cost,
            scale=params.drain_scale,
        )
        bomb.move_speed_multiplier = 0.6
    if 60 <= bomb.timer < 180 and bomb.timer % 16 == 0:
        i = (bomb.timer - 60) // 16
        if i != 0:
            sub = bomb.sub_info[i]
            sub.state = 1
            sub.counter = 0
            sub.accel = 8.0
            sub.pos = bctx.player_pos
            angle = fctx.rng.unit() * math.tau - math.pi
            sub.vel = Vec2.from_angle(angle, sub.accel)
            bomb.damage_boxes[i].damage = 0
    bomb.invulnerable = True
    for i in range(8):
        sub = bomb.sub_info[i]
        if sub.state == 0:
            continue
        box = bomb.damage_boxes[i]
        if sub.state == 1:
            if bomb.has_ticked:
                # 追踪目标 = positionOfLastEnemyHit, 无效(x<=-100)时追玩家 (BombData.cpp:390)
                if bctx.last_enemy_hit.x > -100.0:
                    target = bctx.last_enemy_hit
                else:
                    target = bctx.player_pos
                dx = target.x - sub.pos.x
                dy = target.y - sub.pos.y
                t = math.sqrt(dx * dx + dy * dy) / (sub.accel / 8.0)
                if t < 1.0:
                    t = 1.0
                vx = dx / t + sub.vel.x
                vy = dy / t + sub.vel.y
                speed = math.sqrt(vx * vx + vy * vy)
                sub.accel = min(speed, 10.0)
                if sub.accel < 1.0:
                    sub.accel = 1.0
                sub.vel = Vec2(vx * sub.accel / speed, vy * sub.accel / speed)
                box.size = Vec2(48.0, 48.0)
                box.pos = sub.pos
                box.lifetime = 8
                bomb._spawn_clear(
                    sub.pos,
                    radius=128.0,
                    growth=0.0,
                    lifetime=0,
                    item_type=ITEM_POINT_BULLET,
                )
                if box.damage >= 100 or bomb.timer >= bomb.duration - 30:
                    sub.state = 2
                    box.size = Vec2(256.0, 256.0)
                    box.lifetime = 400
                    bomb._spawn_clear(
                        sub.pos,
                        radius=32.0,
                        growth=6.6666665,
                        lifetime=15,
                        item_type=ITEM_POINT_BULLET,
                    )
                    # 珠爆开震屏 (BombData.cpp:450 RegisterChain(1,16,8,0))
                    bomb.shakes.append((16, 8, 0))
        elif bomb.has_ticked:
            # 集中版 state=2 不再刷新伤害盒 (BombData.cpp:454-461)
            sub.counter += 1
            if sub.counter >= 30:
                sub.state = 0
        sub.pos = sub.pos + sub.vel
    bomb.timer += 1


# ---------------------------------------------------------------------------
# ReimuB 「灵符·梦想封印」
# ---------------------------------------------------------------------------


def _calc_reimu_b_unfocused(
    bomb: Th07BombField, fctx: FrameContext, bctx: Th07BombContext
) -> None:
    """灵梦B 非集中「梦想封印散」 (BombData.cpp:512-601); 锚点在触发帧定格。"""
    if bomb.timer >= bomb.duration:
        bomb.is_in_use = False
        bomb.events.append(EVENT_END_PLAYER_SPELLCARD)
        return
    if bomb.has_ticked and bomb.timer == 0:
        params = BOMB_PARAMS[(CHAR_REIMU_B, False)]
        bomb.duration = params.duration
        bomb.invulnerability_timer = params.invulnerability
        bomb.events.append(EVENT_REMOVE_ALL_ITEMS)
        # 锚点 (bombRegionPositions; .z=0.42/0.415/0.41/0.405 为视觉深度, 略)
        bomb.sub_info[0].pos = Vec2(bctx.player_pos.x, 224.0)
        bomb.sub_info[1].pos = Vec2(192.0, bctx.player_pos.y)
        bomb.sub_info[2].pos = Vec2(bctx.player_pos.x, 224.0)
        bomb.sub_info[3].pos = Vec2(192.0, bctx.player_pos.y)
        bomb.cherry_drain = compute_bomb_cherry_drain(
            cherry=bctx.cherry,
            cherry_start=bctx.cherry_start,
            difficulty=bctx.difficulty,
            bomb_duration=params.duration,
            min_cost=params.drain_min_cost,
            scale=params.drain_scale,
        )
        # 首帧震屏 (BombData.cpp:559 RegisterChain(1,60,2,6))
        bomb.shakes.append((60, 2, 6))
    else:
        # BombData.cpp:566: bombTimer==60 大震屏 RegisterChain(1,80,20,0)
        if bomb.timer == 60:
            bomb.shakes.append((80, 20, 0))
        projectiles = [
            bomb._spawn_projectile(
                bctx.player_pos, width=62.0, height=448.0, item_type=ITEM_POINT_BULLET
            ),
            bomb._spawn_projectile(
                bctx.player_pos, width=384.0, height=62.0, item_type=ITEM_POINT_BULLET
            ),
            bomb._spawn_projectile(
                bctx.player_pos, width=62.0, height=448.0, item_type=ITEM_POINT_BULLET
            ),
            bomb._spawn_projectile(
                bctx.player_pos, width=384.0, height=62.0, item_type=ITEM_POINT_BULLET
            ),
        ]
        for i in range(4):
            if bomb.has_ticked and bomb.timer % 2 != 0:
                # C++ 段中心另加 vms[0].offset (anm 脚本驱动的光束扫动, 视觉数据源, 略)
                projectiles[i].pos = bomb.sub_info[i].pos
                box = bomb.damage_boxes[i]
                box.size = Vec2(projectiles[i].pos_z, projectiles[i].size.x)
                box.pos = bomb.sub_info[i].pos
                box.lifetime = 16
    bomb.invulnerable = True  # playerState = INVULNERABLE (BombData.cpp:598)
    bomb.timer += 1


def _calc_reimu_b_focused(
    bomb: Th07BombField, fctx: FrameContext, bctx: Th07BombContext
) -> None:
    """灵梦B 集中「梦想封印集」 (BombData.cpp:645-694); 大清弹圆比 bomb 多活 20 帧。"""
    if bomb.timer >= bomb.duration:
        bomb.is_in_use = False
        bomb.move_speed_multiplier = 1.0
        bomb.events.append(EVENT_END_PLAYER_SPELLCARD)
        return
    if bomb.has_ticked and bomb.timer == 0:
        params = BOMB_PARAMS[(CHAR_REIMU_B, True)]
        bomb.duration = params.duration
        bomb.invulnerability_timer = params.invulnerability
        bomb.events.append(EVENT_REMOVE_ALL_ITEMS)
        bomb.start_pos = bctx.player_pos
        bomb.cherry_drain = compute_bomb_cherry_drain(
            cherry=bctx.cherry,
            cherry_start=bctx.cherry_start,
            difficulty=bctx.difficulty,
            bomb_duration=params.duration,
            min_cost=params.drain_min_cost,
            scale=params.drain_scale,
        )
        bomb.move_speed_multiplier = 0.4
        bomb._spawn_clear(
            bctx.player_pos,
            radius=192.0,
            growth=0.384,
            lifetime=210,
            item_type=ITEM_POINT_BULLET,
        )
        # 首帧震屏 (BombData.cpp:654 RegisterChain(1,60,2,6))
        bomb.shakes.append((60, 2, 6))
    else:
        # BombData.cpp:666: bombTimer==60 大震屏 RegisterChain(1,80,20,0)
        if bomb.timer == 60:
            bomb.shakes.append((80, 20, 0))
        box = bomb.damage_boxes[0]
        box.size = Vec2(256.0, 256.0)
        box.pos = bomb.start_pos  # + subInfo[0].vms[0].offset (anm 驱动, 略)
        box.lifetime = 18
    bomb.invulnerable = True
    bomb.timer += 1


# ---------------------------------------------------------------------------
# MarisaA 「魔符·Stardust Reverie / Milky Way」
# ---------------------------------------------------------------------------


def _calc_marisa_a_unfocused(
    bomb: Th07BombField, fctx: FrameContext, bctx: Th07BombContext
) -> None:
    """魔理沙A 非集中「星尘狂欢」 (BombData.cpp:690-770); 每 3 帧停一拍。"""
    if bomb.timer >= bomb.duration:
        bomb.is_in_use = False
        bomb.events.append(EVENT_END_PLAYER_SPELLCARD)
        return
    if bomb.has_ticked and bomb.timer == 0:
        params = BOMB_PARAMS[(CHAR_MARISA_A, False)]
        bomb.duration = params.duration
        bomb.invulnerability_timer = params.invulnerability
        bomb.events.append(EVENT_REMOVE_ALL_ITEMS)
        for i in range(8):
            sub = bomb.sub_info[i]
            sub.pos = bctx.player_pos
            sub.vel = Vec2.from_angle(i * math.tau / 8.0, 2.0)
        bomb.cherry_drain = compute_bomb_cherry_drain(
            cherry=bctx.cherry,
            cherry_start=bctx.cherry_start,
            difficulty=bctx.difficulty,
            bomb_duration=params.duration,
            min_cost=params.drain_min_cost,
            scale=params.drain_scale,
        )
        # 首帧震屏 (BombData.cpp:738 RegisterChain(1,120,4,1))
        bomb.shakes.append((120, 4, 1))
    else:
        for i in range(8):
            sub = bomb.sub_info[i]
            sub.pos = sub.pos + sub.vel  # * effectiveFramerateMultiplier(=1.0)
            if bomb.has_ticked and bomb.timer % 3 != 0:
                bomb._spawn_clear(
                    sub.pos,
                    radius=96.0,
                    growth=0.0,
                    lifetime=0,
                    item_type=ITEM_POINT_BULLET,
                )
                box = bomb.damage_boxes[i]
                box.size = Vec2(128.0, 128.0)
                box.pos = sub.pos
                box.lifetime = 8
    bomb.invulnerable = True
    bomb.timer += 1


def _calc_marisa_a_focused(
    bomb: Th07BombField, fctx: FrameContext, bctx: Th07BombContext
) -> None:
    """魔理沙A 集中「银河」 (BombData.cpp:779-891); 移速 ×0.4。"""
    if bomb.timer >= bomb.duration:
        bomb.is_in_use = False
        bomb.move_speed_multiplier = 1.0
        bomb.events.append(EVENT_END_PLAYER_SPELLCARD)
        return
    if bomb.has_ticked and bomb.timer == 0:
        params = BOMB_PARAMS[(CHAR_MARISA_A, True)]
        bomb.duration = params.duration
        bomb.invulnerability_timer = params.invulnerability
        bomb.events.append(EVENT_REMOVE_ALL_ITEMS)
        for sub in bomb.sub_info:
            sub.state = 0
        bomb.cherry_drain = compute_bomb_cherry_drain(
            cherry=bctx.cherry,
            cherry_start=bctx.cherry_start,
            difficulty=bctx.difficulty,
            bomb_duration=params.duration,
            min_cost=params.drain_min_cost,
            scale=params.drain_scale,
        )
        bomb.move_speed_multiplier = 0.4
    if bomb.has_ticked and bomb.timer % 6 == 0:
        i = bomb.timer // 6
        if i < 24:
            sub = bomb.sub_info[i]
            sub.state = 1
            sub.pos = bctx.player_pos
            angle = fctx.rng.unit() * 0.3926991 - 0.19634955 - 1.5707964
            sub.vel = Vec2.from_angle(angle, -5.0)
            angle = fctx.rng.unit() * 0.3926991 - 0.19634955 - 1.5707964
            sub.accel_vec = Vec2.from_angle(angle, 0.24)
            bomb.damage_boxes[i].damage = 0
            # 每颗星出生震屏 (BombData.cpp:867 RegisterChain(1,120,4,1))
            bomb.shakes.append((120, 4, 1))
    for i in range(24):
        sub = bomb.sub_info[i]
        if sub.state == 0:
            continue
        # 轨迹 trails[8] 为视觉拖尾, 略
        sub.pos = sub.pos + sub.vel
        sub.vel = sub.vel + sub.accel_vec
        if sub.pos.y < -256.0:
            sub.state = 0
        bomb._spawn_clear(
            sub.pos, radius=96.0, growth=0.0, lifetime=0, item_type=ITEM_POINT_BULLET
        )
        box = bomb.damage_boxes[i]
        if box.damage < 80:
            box.size = Vec2(128.0, 128.0)
            box.pos = sub.pos
            box.lifetime = 12
    bomb.invulnerable = True
    bomb.timer += 1


# ---------------------------------------------------------------------------
# MarisaB 「恋符·Non-Directional Laser / Master Spark」
# ---------------------------------------------------------------------------


def _calc_marisa_b_unfocused(
    bomb: Th07BombField, fctx: FrameContext, bctx: Th07BombContext
) -> None:
    """魔理沙B 非集中「非定向激光」 (BombData.cpp:952-1048); 移速 ×0.4。"""
    if bomb.timer >= bomb.duration:
        bomb.is_in_use = False
        bomb.move_speed_multiplier = 1.0
        bomb.events.append(EVENT_END_PLAYER_SPELLCARD)
        return
    if bomb.has_ticked and bomb.timer == 0:
        params = BOMB_PARAMS[(CHAR_MARISA_B, False)]
        bomb.duration = params.duration
        bomb.invulnerability_timer = params.invulnerability
        bomb.events.append(EVENT_REMOVE_ALL_ITEMS)
        bomb.start_pos = bctx.player_pos
        for i in range(3):
            sub = bomb.sub_info[i]
            sub.pos = bctx.player_pos
            sub.accel = i * math.tau / 3.0 - math.pi / 2  # accel 被 ZUN 复用为臂角度
        bomb.move_speed_multiplier = 0.4
        bomb.cherry_drain = compute_bomb_cherry_drain(
            cherry=bctx.cherry,
            cherry_start=bctx.cherry_start,
            difficulty=bctx.difficulty,
            bomb_duration=params.duration,
            min_cost=params.drain_min_cost,
            scale=params.drain_scale,
        )
    else:
        # BombData.cpp:1047/1051: timer==20 渐强震屏 / timer==80 大震屏
        if bomb.timer == 20:
            bomb.shakes.append((60, 1, 7))
        elif bomb.timer == 80:
            bomb.shakes.append((100, 24, 0))
        for i in range(3):
            sub = bomb.sub_info[i]
            delta = bomb.timer * math.pi / 30.0 / bomb.duration
            if bomb.start_pos.x < 192.0:  # AddNormalizeAngle → (-π, π]
                sub.accel = normalize_angle_diff(sub.accel + delta)
            else:
                sub.accel = normalize_angle_diff(sub.accel - delta)
            offset = 32.0
            for j in range(6):
                box = bomb.damage_boxes[i * 6 + j]
                box.pos = bctx.player_pos + Vec2.from_angle(sub.accel, offset)
                box.size = Vec2(128.0, 128.0)
                box.lifetime = 10
                bomb._spawn_clear(
                    box.pos,
                    radius=64.0,
                    growth=0.0,
                    lifetime=0,
                    item_type=ITEM_POINT_BULLET,
                )
                offset += MARISA_B_LASER_STEP
    bomb.invulnerable = True
    bomb.timer += 1


def _calc_marisa_b_focused(
    bomb: Th07BombField, fctx: FrameContext, bctx: Th07BombContext
) -> None:
    """魔理沙B 集中「Master Spark」 (BombData.cpp:1104-1170); 移速 ×0.2, 每 4 帧停一拍。"""
    if bomb.timer >= bomb.duration:
        bomb.is_in_use = False
        bomb.move_speed_multiplier = 1.0
        bomb.events.append(EVENT_END_PLAYER_SPELLCARD)
        return
    if bomb.has_ticked and bomb.timer == 0:
        params = BOMB_PARAMS[(CHAR_MARISA_B, True)]
        bomb.duration = params.duration
        bomb.invulnerability_timer = params.invulnerability
        bomb.events.append(EVENT_REMOVE_ALL_ITEMS)
        bomb.move_speed_multiplier = 0.2
        bomb.cherry_drain = compute_bomb_cherry_drain(
            cherry=bctx.cherry,
            cherry_start=bctx.cherry_start,
            difficulty=bctx.difficulty,
            bomb_duration=params.duration,
            min_cost=params.drain_min_cost,
            scale=params.drain_scale,
        )
    else:
        # BombData.cpp:1126/1130: timer==60 渐强震屏 / timer==120 大震屏
        if bomb.timer == 60:
            bomb.shakes.append((60, 1, 7))
        elif bomb.timer == 120:
            bomb.shakes.append((200, 24, 0))
        if bomb.has_ticked and bomb.timer % 4 != 0:
            box = bomb.damage_boxes[0]
            box.size = Vec2(384.0, bctx.player_pos.y)
            box.pos = Vec2(192.0, bctx.player_pos.y / 2.0)
            box.lifetime = 23
            bomb._spawn_projectile(
                box.pos,
                width=384.0,
                height=bctx.player_pos.y,
                item_type=ITEM_POINT_BULLET,
            )
    bomb.invulnerable = True
    bomb.timer += 1


# ---------------------------------------------------------------------------
# SakuyaA 「幻符·Indiscriminate / Killing Doll」
# ---------------------------------------------------------------------------


def _calc_sakuya_a_unfocused(
    bomb: Th07BombField, fctx: FrameContext, bctx: Th07BombContext
) -> None:
    """咲夜A 非集中「无差别」 (BombData.cpp:1201-1290); timer 60..120 每帧至多 5 把刀。"""
    if bomb.timer >= bomb.duration:
        bomb.is_in_use = False
        bomb.events.append(EVENT_END_PLAYER_SPELLCARD)
        return
    if bomb.has_ticked and bomb.timer == 0:
        params = BOMB_PARAMS[(CHAR_SAKUYA_A, False)]
        bomb.duration = params.duration
        bomb.invulnerability_timer = params.invulnerability
        bomb.events.append(EVENT_REMOVE_ALL_ITEMS)
        bomb.start_pos = bctx.player_pos
        for sub in bomb.sub_info:
            sub.state = 0
        bomb.cherry_drain = compute_bomb_cherry_drain(
            cherry=bctx.cherry,
            cherry_start=bctx.cherry_start,
            difficulty=bctx.difficulty,
            bomb_duration=params.duration,
            min_cost=params.drain_min_cost,
            scale=params.drain_scale,
        )
    if bomb.timer >= 60:
        rng = fctx.rng.unit
        spawns_remaining = 5
        for i in range(96):
            sub = bomb.sub_info[i]
            if sub.state == 0:
                if bomb.timer <= 120 and spawns_remaining != 0:
                    sub.state = 1
                    sub.angle = rng() * math.tau - math.pi
                    sub.speed = rng() * 6.0 + 5.5
                    sub.accel = rng() * 0.1 + 0.1
                    sub.angle_drift = rng() * 0.06283186 - 0.03141593
                    sub.vel = Vec2.from_angle(sub.angle, 24.0)
                    sub.pos = bomb.start_pos + sub.vel
                    bomb.damage_boxes[i].damage = 0
                    spawns_remaining -= 1
                continue
            sub.angle = normalize_angle_diff(sub.angle + sub.angle_drift)
            sub.speed += sub.accel
            sub.vel = Vec2.from_angle(sub.angle, sub.speed)
            box = bomb.damage_boxes[i]
            if box.damage < 30:
                sub.pos = sub.pos + sub.vel
                bomb._spawn_clear(
                    sub.pos,
                    radius=32.0,
                    growth=0.0,
                    lifetime=0,
                    item_type=ITEM_POINT_BULLET,
                )
                box.size = Vec2(24.0, 24.0)
                box.pos = sub.pos
                box.lifetime = 10
            elif box.damage < 999:
                box.damage = 999  # 命中后钉住 (视觉换 anm 1120, 略)
            if not _in_bounds(sub.pos.x, sub.pos.y, 64.0, 64.0):
                sub.state = 0
    bomb.invulnerable = True
    bomb.timer += 1


def _calc_sakuya_a_focused(
    bomb: Th07BombField, fctx: FrameContext, bctx: Th07BombContext
) -> None:
    """咲夜A 集中「杀人玩偶」 (BombData.cpp:1333-1473); 停时悬停后瞄准飞出, 移速 ×0.3。"""
    if bomb.timer >= bomb.duration:
        bomb.is_in_use = False
        bomb.move_speed_multiplier = 1.0
        bomb.events.append(EVENT_END_PLAYER_SPELLCARD)
        return
    if bomb.has_ticked and bomb.timer == 0:
        params = BOMB_PARAMS[(CHAR_SAKUYA_A, True)]
        bomb.duration = params.duration
        bomb.invulnerability_timer = params.invulnerability
        bomb.events.append(EVENT_REMOVE_ALL_ITEMS)
        for sub in bomb.sub_info:
            sub.state = 0
        bomb.cherry_drain = compute_bomb_cherry_drain(
            cherry=bctx.cherry,
            cherry_start=bctx.cherry_start,
            difficulty=bctx.difficulty,
            bomb_duration=params.duration,
            min_cost=params.drain_min_cost,
            scale=params.drain_scale,
        )
        bomb.move_speed_multiplier = 0.3
        # 首帧震屏 (BombData.cpp:1388 RegisterChain(1,120,4,1))
        bomb.shakes.append((120, 4, 1))
    if 20 <= bomb.timer < 116:
        rng = fctx.rng.unit
        for i in range(96):
            if not (bomb.has_ticked and bomb.timer == (i % 48) * 2 + 20):
                continue
            sub = bomb.sub_info[i]
            sub.state = 1
            sub.angle = i * math.tau / 96.0 - math.pi
            sub.speed = rng() * 1.0 + 0.5
            sub.accel = rng() * 0.1 + 0.03
            sub.angle_drift = (
                -0.15707964
            )  # GetRandomU16InRange(1)%1==0 → 恒负支 (ZUN quirk)
            sub.vel = Vec2.from_angle(sub.angle, 24.0)
            sub.pos = bctx.player_pos + sub.vel
            sub.sub_timer = 0
            bomb.damage_boxes[i].damage = 0
    for i in range(96):
        sub = bomb.sub_info[i]
        if sub.state == 0:
            continue
        t = sub.sub_timer
        if t < 30 or t >= 70:
            if t == 70:
                # 瞄 positionOfLastEnemyHit (BombData.cpp:1403), 无效时保持原角
                if bctx.last_enemy_hit.x > -100.0:
                    sub.angle = normalize_angle_diff(
                        math.atan2(
                            bctx.last_enemy_hit.y - sub.pos.y,
                            bctx.last_enemy_hit.x - sub.pos.x,
                        )
                    )
                sub.speed = 14.0
            sub.speed += sub.accel
            sub.vel = Vec2.from_angle(sub.angle, sub.speed)
        else:
            # 停时悬停: vel=0 只转角
            sub.angle = normalize_angle_diff(sub.angle + sub.angle_drift)
            sub.vel = Vec2.zero()
        box = bomb.damage_boxes[i]
        if box.damage == 0:
            sub.pos = sub.pos + sub.vel
            bomb._spawn_clear(
                sub.pos,
                radius=32.0,
                growth=0.0,
                lifetime=0,
                item_type=ITEM_POINT_BULLET,
            )
            box.size = Vec2(24.0, 24.0)
            box.pos = sub.pos
            box.lifetime = 22
        elif box.damage < 999:
            box.damage = 999  # 命中即钉住
        sub.sub_timer += 1
    bomb.invulnerable = True
    bomb.timer += 1


# ---------------------------------------------------------------------------
# SakuyaB 「时符·Perfect Square / Private Square」
# ---------------------------------------------------------------------------


def _calc_sakuya_b_unfocused(
    bomb: Th07BombField, fctx: FrameContext, bctx: Th07BombContext
) -> None:
    """咲夜B 非集中「完美方阵」 (BombData.cpp:1502-1598); 停时 ×3, 移速 ×2.0。"""
    if bomb.timer >= bomb.duration:
        bomb.is_in_use = False
        bomb.move_speed_multiplier = 1.0
        bomb.events.append(EVENT_END_PLAYER_SPELLCARD)
        bomb._spawn_clear(
            bctx.player_pos,
            radius=800.0,
            growth=0.0,
            lifetime=0,
            item_type=ITEM_POINT_BULLET,
        )
        return
    if bomb.has_ticked and bomb.timer == 0:
        params = BOMB_PARAMS[(CHAR_SAKUYA_B, False)]
        bomb.duration = params.duration
        bomb.invulnerability_timer = params.invulnerability
        bomb.events.append(EVENT_REMOVE_ALL_ITEMS)
        for i in range(4):
            bomb.sub_info[i].state = 0
        bomb.cherry_drain = compute_bomb_cherry_drain(
            cherry=bctx.cherry,
            cherry_start=bctx.cherry_start,
            difficulty=bctx.difficulty,
            bomb_duration=params.duration,
            min_cost=params.drain_min_cost,
            scale=params.drain_scale,
        )
        bomb.move_speed_multiplier = 2.0
        bomb.events.append(EVENT_STOP_BULLET_MOVEMENT)
    if bomb.has_ticked and bomb.timer == 60:
        bomb.events.append(EVENT_STOP_BULLET_MOVEMENT)
    if bomb.has_ticked and bomb.timer == 120:
        bomb.events.append(EVENT_STOP_BULLET_MOVEMENT)
    # 停时震屏 (BombData.cpp:1559/:1563 RegisterChain(1,60,1,7) / (1,70,24,0))
    if bomb.has_ticked and bomb.timer == 40:
        bomb.shakes.append((60, 1, 7))
    if bomb.has_ticked and bomb.timer == 100:
        bomb.shakes.append((70, 24, 0))
    if bomb.has_ticked and bomb.timer == 30:
        # vm->pos = (192±128, 224±128) 为视觉方阵锚点, 略
        for i in range(4):
            bomb.sub_info[i].state = 1
    if bomb.timer >= 30 and bomb.has_ticked and bomb.timer % 4 == 0:
        box = bomb.damage_boxes[0]
        box.pos = Vec2(192.0, 224.0)
        box.size = Vec2(352.0, 416.0)
        box.lifetime = 3
    bomb.invulnerable = True
    bomb.timer += 1


def _calc_sakuya_b_focused(
    bomb: Th07BombField, fctx: FrameContext, bctx: Th07BombContext
) -> None:
    """咲夜B 集中「私人方阵」 (BombData.cpp:1633-1724); 时停领域追踪玩家, 移速 ×1.5。"""
    if bomb.timer >= bomb.duration:
        bomb.is_in_use = False
        bomb.move_speed_multiplier = 1.0
        bomb.events.append(EVENT_END_PLAYER_SPELLCARD)
        bomb._spawn_clear(
            bctx.player_pos,
            radius=800.0,
            growth=0.0,
            lifetime=0,
            item_type=ITEM_POINT_BULLET,
        )
        # C++ 无条件写 bombClearBoxes[0] (BombData.cpp:1652-1655):
        # 覆写为 (192,224) 宽448×高512 线性段 (ZUN quirk: 与 800 圆同槽, size.y=800 残留)
        box0 = bomb.clear_boxes[0]
        box0.pos = Vec2(192.0, 224.0)
        box0.pos_z = 448.0
        box0.size = Vec2(512.0, box0.size.y)
        return
    if bomb.has_ticked and bomb.timer == 0:
        params = BOMB_PARAMS[(CHAR_SAKUYA_B, True)]
        bomb.duration = params.duration
        bomb.invulnerability_timer = params.invulnerability
        bomb.events.append(EVENT_REMOVE_ALL_ITEMS)
        # isBombing=0 (BombData.cpp:1648) —— 触发帧即清 isBombing 标记, 属上层状态, 注记
        for i in range(2):
            sub = bomb.sub_info[i]
            sub.state = 1
            sub.pos = bctx.player_pos
            sub.vel = Vec2.zero()
            sub.accel_vec = Vec2(0.0, -0.008)  # 首帧即被追踪公式覆写, 仅初值意义
        bomb.move_speed_multiplier = 1.5
        bomb.cherry_drain = compute_bomb_cherry_drain(
            cherry=bctx.cherry,
            cherry_start=bctx.cherry_start,
            difficulty=bctx.difficulty,
            bomb_duration=params.duration,
            min_cost=params.drain_min_cost,
            scale=params.drain_scale,
        )
    bomb._spawn_clear(
        bomb.sub_info[0].pos,
        radius=96.0,
        growth=0.0,
        lifetime=0,
        item_type=ITEM_POINT_BULLET,
    )
    box = bomb.damage_boxes[0]
    box.pos = bomb.sub_info[0].pos
    box.size = Vec2(160.0, 160.0)
    box.lifetime = 1
    if bomb.has_ticked and bomb.timer == 40:
        bomb.events.append(EVENT_STOP_BULLET_MOVEMENT)
        # 停时震屏 (BombData.cpp:1672 RegisterChain(1,60,1,7))
        bomb.shakes.append((60, 1, 7))
    if bomb.has_ticked and bomb.timer == 100:
        bomb.events.append(EVENT_STOP_BULLET_MOVEMENT)
        # BombData.cpp:1678 RegisterChain(1,70,24,0)
        bomb.shakes.append((70, 24, 0))
    for i in range(2):
        sub = bomb.sub_info[i]
        if sub.state == 0:
            continue
        # 轨迹 trails[32] 为视觉拖尾, 略
        sub.accel_vec = (bctx.player_pos - sub.pos) / 1700.0
        sub.vel = sub.vel + sub.accel_vec
        sub.pos = sub.pos + sub.vel
    bomb.invulnerable = True
    bomb.timer += 1


# (character, focus) → calc (g_BombData, BombData.cpp:16-28)
BOMB_CALCS = {
    (CHAR_REIMU_A, False): _calc_reimu_a_unfocused,
    (CHAR_REIMU_A, True): _calc_reimu_a_focused,
    (CHAR_REIMU_B, False): _calc_reimu_b_unfocused,
    (CHAR_REIMU_B, True): _calc_reimu_b_focused,
    (CHAR_MARISA_A, False): _calc_marisa_a_unfocused,
    (CHAR_MARISA_A, True): _calc_marisa_a_focused,
    (CHAR_MARISA_B, False): _calc_marisa_b_unfocused,
    (CHAR_MARISA_B, True): _calc_marisa_b_focused,
    (CHAR_SAKUYA_A, False): _calc_sakuya_a_unfocused,
    (CHAR_SAKUYA_A, True): _calc_sakuya_a_focused,
    (CHAR_SAKUYA_B, False): _calc_sakuya_b_unfocused,
    (CHAR_SAKUYA_B, True): _calc_sakuya_b_focused,
}
