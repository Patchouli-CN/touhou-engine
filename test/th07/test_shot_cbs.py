"""th07 exotic 自机弹回调测试 —— parity 判官 + 真一面集成 smoke。

关键用例改写自 old/tests/game_test/th07/test_th07_player_bullets.py。
数值权威: th07 Player.cpp g_ShtFireFuncs/g_ShtUpdateFuncs/g_ShtHitFuncs;
行为出处 old/touhou/games/th07/player.py 的对应回调。
"""

from __future__ import annotations

import math

from touhou.engine import Button, FrameContext, InputFrame, Rng, ShotField, open_archive
from touhou.engine.enemies import EnemyDamaged
from touhou.engine.events import Event
from touhou.games.th07.compose import compose
from touhou.games.th07.player import OPTION_ANGLE_CENTER, OptionMachine, OptionState
from touhou.games.th07.shot_cbs import (
    FIRE_HOMING,
    FIRE_ORB_FOCUSED,
    FIRE_ORB_UNFOCUSED,
    FIRE_ROTATING_ORB,
    HIT_MISSILE,
    UPDATE_HOMING,
    UPDATE_HOMING_FOCUSED,
    UPDATE_ORB_LASER,
    UPDATE_PLAYER_LASER,
    UPDATE_UPWARD_ACCEL,
    Th07ShotHooks,
)
from touhou.games.th07.world import compose_world
from touhou.schemas.archive import load_entry
from touhou.schemas.shot_data import ShotData, ShotEntry, ShotLevel, parse_sht
from touhou.utils.math import Vec2

from .conftest import DATA, needs_data


def _ctx(seed: int = 0) -> FrameContext:
    return FrameContext(Rng(seed))


def E(**kw) -> ShotEntry:
    """构造一条射击条目(默认: 每 5 帧, 朝上直飞, 伤害 10, 全 default 回调)。"""
    d = dict(
        fire_interval=5,
        fire_offset=0,
        offset=(0.0, 0.0),
        hitbox=(12.0, 12.0),
        angle=-math.pi / 2,
        speed=12.0,
        damage=10,
        option=0,
        bullet_state2=0,
        fire_cb=0,
        update_cb=0,
        draw_cb=0,
        hit_cb=0,
    )
    d.update(kw)
    return ShotEntry(**d)


def _shot_data(*entries: ShotEntry) -> ShotData:
    return ShotData(
        3.0,
        30,
        4.0,
        48.0,
        4.0,
        16.0,
        0.5,
        128.0,
        4.0,
        2.0,
        2.8,
        1.4,
        [ShotLevel(0, list(entries))],
    )


def make_field(
    *entries: ShotEntry, rotating: bool = False
) -> tuple[ShotField, Th07ShotHooks]:
    """组一个已注册 th07 回调的弹场 + 状态口(站桩 192,400, 按住射击)。"""
    hooks = Th07ShotHooks(options=OptionMachine(rotating=rotating))
    f = ShotField(
        shot_data=_shot_data(*entries),
        firing=True,
        player_pos=Vec2(192.0, 400.0),
        options=[Vec2(168.0, 400.0), Vec2(216.0, 400.0)],
    )
    hooks.register(f)
    return f, hooks


def tick(f: ShotField, hooks: Th07ShotHooks, ctx: FrameContext, n: int = 1) -> None:
    """推进 n 帧(对齐世界序: 槽清理 → 弹场步进 → 射击发生器)。"""
    for _ in range(n):
        hooks.clear_stale_slots(f)
        f.step(ctx)
        f.fire_pass(ctx)


def live(f: ShotField):
    return [b for b in f.pool if b.bullet_state != 0]


# ---- fire 回调: orb 持续弹(槽占用/中断/状态要求) ----


def test_orb_unfocused_occupies_timer_slot() -> None:
    f, h = make_field(
        E(
            fire_cb=FIRE_ORB_UNFOCUSED,
            fire_interval=100,
            fire_offset=0,
            option=1,
            update_cb=UPDATE_ORB_LASER,
            bullet_state2=4,
            speed=0.0,
        )
    )
    ctx = _ctx()
    tick(f, h, ctx)
    ts = f.timers[0]
    assert ts.shot is not None and ts.timer == 100
    assert ts.shot.option_id == 1 and ts.shot.timer_idx == 0
    tick(f, h, ctx)
    assert len(live(f)) == 1  # 槽占用中不重复发射
    assert ts.timer == 99  # 槽计时每帧递减
    assert f.sht_entries[0] is not None


def test_orb_requires_matching_option_state() -> None:
    # FOCUSED 型在 UNFOCUSED 时不发射
    f, h = make_field(
        E(
            fire_cb=FIRE_ORB_FOCUSED,
            fire_interval=4,
            fire_offset=2,
            option=0,
            update_cb=UPDATE_PLAYER_LASER,
            bullet_state2=5,
            draw_cb=1,
        )
    )
    tick(f, h, _ctx(), 5)
    assert not live(f)
    # UNFOCUSED 型在 FOCUSED 时不发射
    f2, h2 = make_field(
        E(
            fire_cb=FIRE_ORB_UNFOCUSED,
            fire_interval=100,
            fire_offset=0,
            option=1,
            update_cb=UPDATE_ORB_LASER,
            bullet_state2=4,
        )
    )
    h2.options.state = OptionState.FOCUSED
    tick(f2, h2, _ctx(), 5)
    assert not live(f2)


def test_orb_entry_change_interrupts_old_shot() -> None:
    e1 = E(
        fire_cb=FIRE_ORB_UNFOCUSED,
        fire_interval=100,
        fire_offset=0,
        option=1,
        update_cb=UPDATE_ORB_LASER,
        bullet_state2=4,
        speed=0.0,
    )
    f, h = make_field(e1)
    ctx = _ctx()
    tick(f, h, ctx)
    old = f.timers[0].shot
    # 换 entry(同槽): 旧弹中断, 本帧不发射, 下一帧发新弹
    e2 = E(
        fire_cb=FIRE_ORB_UNFOCUSED,
        fire_interval=80,
        fire_offset=0,
        option=1,
        update_cb=UPDATE_ORB_LASER,
        bullet_state2=4,
        speed=0.0,
    )
    f.shot_data = _shot_data(e2)
    tick(f, h, ctx)
    assert old is not None and old.bullet_state == 0
    assert len(live(f)) == 0
    tick(f, h, ctx)
    assert len(live(f)) == 1
    assert f.timers[0].timer == 80


def test_focus_transition_kills_unfocused_orbs() -> None:
    f, h = make_field(
        E(
            fire_cb=FIRE_ORB_UNFOCUSED,
            fire_interval=100,
            fire_offset=0,
            option=1,
            update_cb=UPDATE_ORB_LASER,
            bullet_state2=4,
            speed=0.0,
        )
    )
    ctx = _ctx()
    tick(f, h, ctx)
    b = f.timers[0].shot
    h.options.state = OptionState.FOCUSING  # != UNFOCUSED → 槽 0/1 立即中断
    tick(f, h, ctx)
    assert b is not None and b.bullet_state == 0
    assert f.timers[0].shot is None


def test_unfocus_kills_focused_laser_slot2() -> None:
    f, h = make_field(
        E(
            fire_cb=FIRE_ORB_FOCUSED,
            fire_interval=4,
            fire_offset=2,
            option=0,
            update_cb=UPDATE_PLAYER_LASER,
            bullet_state2=5,
            draw_cb=1,
            speed=0.0,
        )
    )
    h.options.state = OptionState.FOCUSED
    ctx = _ctx()
    tick(f, h, ctx)
    assert f.timers[2].shot is not None
    b = f.timers[2].shot
    h.options.state = OptionState.UNFOCUSING  # != FOCUSED → 槽 2 立即消
    tick(f, h, ctx)
    assert b is not None and b.bullet_state == 0
    assert f.timers[2].shot is None


def test_orb_timer_expires_shot_dies() -> None:
    f, h = make_field(
        E(
            fire_cb=FIRE_ORB_UNFOCUSED,
            fire_interval=10,
            fire_offset=0,
            option=1,
            update_cb=UPDATE_ORB_LASER,
            bullet_state2=4,
            speed=0.0,
        )
    )
    ctx = _ctx()
    tick(f, h, ctx)
    assert len(live(f)) == 1
    # 松开射击且一轮计时结束(fireBulletTimer=-1)后不再补发
    f.firing = False
    f.fire_time = -1
    tick(f, h, ctx, 10)  # 槽计时 10→0, update 回调收尸
    assert not live(f)
    assert f.timers[0].shot is None


def test_orb_refires_when_slot_freed_while_firing() -> None:
    """Orb 发射不看 fireTime: 按住射击时槽一空立即补发(C++ FireOrbBulletUnfocused)。"""
    f, h = make_field(
        E(
            fire_cb=FIRE_ORB_UNFOCUSED,
            fire_interval=10,
            fire_offset=0,
            option=1,
            update_cb=UPDATE_ORB_LASER,
            bullet_state2=4,
            speed=0.0,
        )
    )
    ctx = _ctx()
    tick(f, h, ctx)
    tick(f, h, ctx, 10)  # 旧弹计时归 0 死亡, 同帧补发新弹
    assert len(live(f)) == 1
    assert f.timers[0].timer == 10


# ---- update 回调: orbLaser / playerLaser 几何 ----


def test_orb_laser_follows_option_geometry() -> None:
    f, h = make_field(
        E(
            fire_cb=FIRE_ORB_UNFOCUSED,
            fire_interval=100,
            fire_offset=0,
            option=2,
            update_cb=UPDATE_ORB_LASER,
            bullet_state2=4,
            speed=0.0,
        )
    )
    ctx = _ctx()
    tick(f, h, ctx)
    b = f.timers[0].shot
    tick(f, h, ctx)  # 这一帧跑 update 回调
    opt = f.options[1]  # option=2 → 右子机
    assert b is not None
    assert b.pos.x == opt.x
    assert b.pos.y == opt.y / 2  # pos.y /= 2
    assert b.hitbox == (12.0, opt.y)  # hitbox 高 = 子机 y(到版顶)


def test_player_laser_follows_player_and_history_shifts() -> None:
    f, h = make_field(
        E(
            fire_cb=FIRE_ORB_FOCUSED,
            fire_interval=4,
            fire_offset=2,
            option=0,
            update_cb=UPDATE_PLAYER_LASER,
            bullet_state2=5,
            draw_cb=1,
            speed=0.0,
            offset=(0.0, -24.0),
        )
    )
    h.options.state = OptionState.FOCUSED
    ctx = _ctx()
    tick(f, h, ctx)
    b = f.timers[2].shot
    assert b is not None
    assert f.timers[2].timer == 999  # focus 型槽计时恒 999
    assert b.trail_length == 4  # trailLength = fireInterval
    tick(f, h, ctx)
    # 跟随本体: hitbox 高 = 本体 y+64, pos.y = 本体 y/2-32, x 加 offset.x
    assert b.hitbox == (12.0, f.player_pos.y + 64.0)
    assert abs(b.pos.y - (f.player_pos.y / 2 - 32.0)) < 1e-9
    assert b.pos.x == f.player_pos.x + 0.0
    # pos_history 每帧右移, [0] 是上一帧弹位
    tick(f, h, ctx)
    assert b.pos_history[0].x != -999.0


def test_dialog_and_bomb_clamp_persistent_timer_to_20() -> None:
    for flag in ("dialog_active", "bomb_active"):
        f, h = make_field(
            E(
                fire_cb=FIRE_ORB_UNFOCUSED,
                fire_interval=100,
                fire_offset=0,
                option=1,
                update_cb=UPDATE_ORB_LASER,
                bullet_state2=4,
                speed=0.0,
            )
        )
        ctx = _ctx()
        tick(f, h, ctx)
        old = f.timers[0].shot
        setattr(f, flag, True)
        tick(f, h, ctx)  # 槽计时 99 → 压到 20
        assert f.timers[0].timer == 20
        f.firing = False  # 停止补发后数完 20 帧
        f.fire_time = -1
        tick(f, h, ctx, 20)
        assert old is not None and old.bullet_state == 0, flag


# ---- fire/update 回调: homing(咲夜A 发射 + 灵梦A 更新) ----


def test_homing_fire_redirects_to_sakuya_target() -> None:
    f, h = make_field(E(fire_cb=FIRE_HOMING, speed=10.0))
    h.sakuya_target_position = f.player_pos + Vec2(100, -100)
    tick(f, h, _ctx())
    b = f.pool[0]
    # 朝目标重定向, 速度×1.5
    want = (h.sakuya_target_position - b.pos).normalized() * 15.0
    assert b.velocity.distance(want) < 1e-6
    assert b.speed == 10.0  # shot.speed 字段保持 entry 值(C++ 行为)
    # 无目标(x<=-100)时直飞
    f2, h2 = make_field(E(fire_cb=FIRE_HOMING, speed=10.0))
    tick(f2, h2, _ctx())
    assert f2.pool[0].velocity.distance(Vec2(0, -10)) < 1e-9


def test_homing_update_steers_toward_last_enemy_hit() -> None:
    f, h = make_field(E(update_cb=UPDATE_HOMING, speed=4.0))
    ctx = _ctx()
    tick(f, h, ctx)
    b = f.pool[0]
    h.position_of_last_enemy_hit = b.pos + Vec2(100, 0)  # 正右方
    tick(f, h, ctx)
    assert b.velocity.x > 0  # 向右转向
    assert b.speed <= 10.0  # 转向分支 cap 10
    # 无目标时沿当前方向 +0.3333 加速; 达到 cap 后停止(注意 C++ 加速分支不夹 cap)
    h.position_of_last_enemy_hit = Vec2(-999.0, -999.0)
    s0 = b.speed
    tick(f, h, ctx)
    assert abs(b.speed - (s0 + 0.33333334)) < 1e-6
    assert abs(b.velocity.length - b.speed) < 1e-6
    for _ in range(25):  # 4.1 + n*0.333 ≥ 10 → 约 18 帧
        tick(f, h, ctx)
        if b.speed >= 10.0:
            break
    assert b.bullet_state == 1 and b.speed >= 10.0
    s1 = b.speed
    tick(f, h, ctx)
    assert b.speed == s1  # ≥cap 后不再加速


def test_homing_update_focused_cap_18() -> None:
    f, h = make_field(E(update_cb=UPDATE_HOMING_FOCUSED, speed=17.0))
    ctx = _ctx()
    tick(f, h, ctx)
    b = f.pool[0]
    tick(f, h, ctx)
    assert abs(b.speed - 17.6) < 1e-6  # +0.6
    tick(f, h, ctx)
    assert abs(b.speed - 18.2) < 1e-6  # 超过 cap 即停(C++ 加速分支不把速度夹回 cap)
    tick(f, h, ctx)
    assert abs(b.speed - 18.2) < 1e-6


def test_upward_accel_deterministic() -> None:
    """魔理沙A 导弹: 每帧 vy -= rng(0..0.1)+0.27; 同种子两场逐帧一致。"""
    vys: list[list[float]] = []
    for _ in range(2):
        f, h = make_field(E(update_cb=UPDATE_UPWARD_ACCEL, speed=0.0, angle=0.0))
        ctx = _ctx(7)
        tick(f, h, ctx)
        b = f.pool[0]
        seq = []
        for _ in range(5):
            tick(f, h, ctx)
            seq.append(b.velocity.y)
        vys.append(seq)
    assert vys[0] == vys[1]  # 确定性(ctx.rng)
    for prev, cur in zip(vys[0], vys[0][1:]):
        delta = prev - cur
        assert 0.27 <= delta < 0.37  # 每帧增量在 [0.27, 0.37)


# ---- fire 回调: rotatingOrb(咲夜B) ----


def test_rotating_orb_angle_follows_option_angle() -> None:
    f, h = make_field(
        E(fire_cb=FIRE_ROTATING_ORB, angle=0.0, speed=12.0, option=0),
        rotating=True,
    )
    assert h.options.option_angle == OPTION_ANGLE_CENTER  # -pi/2
    ctx = _ctx()
    tick(f, h, ctx)
    b = f.pool[0]
    # 发射角 = optionAngle + entry.angle + pi/2 = 0 → 朝 +x
    assert b.velocity.distance(Vec2(12, 0)) < 1e-4
    assert abs(b.angle - 0.0) < 1e-4
    # optionAngle 摆动后跟随
    h.options.option_angle = -1.0
    f.fire_time = -1  # 强制从 0 重启, 本帧即发射
    tick(f, h, ctx)
    b2 = live(f)[-1]
    want = h.options.option_angle + 0.0 + math.pi / 2  # entry.angle = 0
    assert b2.velocity.distance(Vec2.from_angle(want, 12.0)) < 1e-4


# ---- hit 回调: 魔理沙A 导弹 ----


def test_missile_hit_transforms_then_decays_every_other_frame() -> None:
    f, h = make_field(
        E(hit_cb=HIT_MISSILE, bullet_state2=3, anm_file_idx=1090, speed=0.0, damage=9)
    )
    ctx = _ctx()
    tick(f, h, ctx)
    b = f.pool[0]
    f.step(ctx)  # timer=1
    # 首中: 判定盒扩到 42x42, 速度改为爆炸速度 4(上向), 全额伤害, 穿透不减速
    assert f.calc_damage_to_enemy(b.pos, (20.0, 20.0), ctx) == 9
    assert b.bullet_state == 2
    assert b.hitbox == (42.0, 42.0)
    assert abs(b.velocity.length - 4.0) < 1e-6
    assert b.velocity.y < 0.0  # 爆炸角 ∈ [-3pi/4, -pi/4] 恒朝上
    f.step(ctx)  # timer=2 (偶): 伤害 9//3=3, 速度×0.88
    assert f.calc_damage_to_enemy(b.pos, (60.0, 60.0), ctx) == 3
    assert abs(b.velocity.length - 4.0 * 0.88) < 1e-6
    f.step(ctx)  # timer=3 (奇): 隔帧跳过
    assert f.calc_damage_to_enemy(b.pos, (60.0, 60.0), ctx) == 0
    f.step(ctx)  # timer=4 (偶): 3//3=1 (最低 1)
    assert f.calc_damage_to_enemy(b.pos, (60.0, 60.0), ctx) == 1


def test_player_laser_trail_segments_add_damage() -> None:
    f, h = make_field(
        E(
            fire_cb=FIRE_ORB_FOCUSED,
            fire_interval=4,
            fire_offset=2,
            option=0,
            update_cb=UPDATE_PLAYER_LASER,
            bullet_state2=5,
            draw_cb=1,
            speed=0.0,
            damage=2,
        )
    )
    h.options.state = OptionState.FOCUSED
    ctx = _ctx()
    tick(f, h, ctx)
    b = f.timers[2].shot
    assert b is not None
    # 往右移动若干帧, 留下横向拖尾
    for _ in range(6):
        f.player_pos = f.player_pos + Vec2(8.0, 0.0)
        tick(f, h, ctx)
    # 在拖尾历史点放敌人: 主激光(细条)打不到, 历史段补 1 点/段
    hp = [p for p in b.pos_history[: b.trail_length] if p.x >= -900.0]
    assert hp, "拖尾历史应已填上真实位置"
    target = hp[-1]
    # 敌人偏离主激光条(主条在弹 x 附近, 宽 12): 用窄判定盒避开主条
    hits = f.iter_hits(Vec2(target.x, target.y), (4.0, 4.0), ctx)
    assert any(d == 1 for _, d in hits)


# ---- 真实 .sht: 回调索引分布核对(g_ShtFireFuncs 等数组下标) ----


@needs_data
def test_real_sht_callback_index_distribution() -> None:
    arch = open_archive(DATA)
    expect = {
        # shotType: 0/1=ReimuA/B, 2/3=MarisaA/B, 4/5=SakuyaA/B; s 后缀=focus
        "ply00a.sht": {"upd": {UPDATE_HOMING}},  # 灵梦A 追踪符
        "ply00as.sht": {"upd": {UPDATE_HOMING_FOCUSED}},
        "ply00b.sht": {"upd": set()},  # 灵梦B 全 default
        "ply00bs.sht": {"upd": set()},
        "ply01a.sht": {
            "upd": {UPDATE_UPWARD_ACCEL},
            "hit": {HIT_MISSILE},
        },  # 魔理沙A 导弹
        "ply01as.sht": {
            "upd": {UPDATE_UPWARD_ACCEL},
            "hit": {HIT_MISSILE},
            "fire": {0, 1},
        },  # 含显式 default(1)
        "ply01b.sht": {"fire": {0, FIRE_ORB_UNFOCUSED}, "upd": {0, UPDATE_ORB_LASER}},
        "ply01bs.sht": {
            "fire": {0, FIRE_ORB_FOCUSED},
            "upd": {0, UPDATE_PLAYER_LASER},
            "draw": {0, 1},
        },  # 拖尾
        "ply02a.sht": {"fire": {0}},
        "ply02as.sht": {"fire": {FIRE_HOMING}},  # 咲夜A focus 追踪
        "ply02b.sht": {"fire": {FIRE_ROTATING_ORB}},  # 咲夜B 旋转子机
        "ply02bs.sht": {"fire": {0, FIRE_ROTATING_ORB}},
    }
    for name, want in expect.items():
        sd = parse_sht(load_entry(arch, name))
        got: dict[str, set[int]] = {
            "fire": set(),
            "upd": set(),
            "draw": set(),
            "hit": set(),
        }
        for lv in sd.levels:
            for e in lv.entries:
                if e.fire_interval < 0:  # 链尾哨兵
                    continue
                got["fire"].add(e.fire_cb)
                got["upd"].add(e.update_cb)
                got["draw"].add(e.draw_cb)
                got["hit"].add(e.hit_cb)
        for kind, keys in want.items():
            assert keys <= got[kind], f"{name} {kind}: {got[kind]}"
        # 所有索引都在已注册/已知范围内
        assert got["fire"] <= {0, 1, 2, 3, 4, 5}, name
        assert got["upd"] <= {0, 1, 2, 3, 4, 5}, name
        assert got["draw"] <= {0, 1}, name
        assert got["hit"] <= {0, 1, 2}, name


@needs_data
def test_real_sht_marisa_b_persistent_slots() -> None:
    """魔理沙B: 非 focus 两条 orb 激光占槽 0/1(周期=持续时间), focus 激光占槽 2。"""
    arch = open_archive(DATA)
    sd = parse_sht(load_entry(arch, "ply01b.sht"))
    orbs = [
        e
        for lv in sd.levels
        for e in lv.entries
        if e.fire_interval >= 0 and e.fire_cb == FIRE_ORB_UNFOCUSED
    ]
    assert orbs and all(e.fire_offset in (0, 1) for e in orbs)
    assert all(e.option in (1, 2) and e.bullet_state2 == 4 for e in orbs)
    sdf = parse_sht(load_entry(arch, "ply01bs.sht"))
    lasers = [
        e
        for lv in sdf.levels
        for e in lv.entries
        if e.fire_interval >= 0 and e.fire_cb == FIRE_ORB_FOCUSED
    ]
    assert lasers and all(e.fire_offset == 2 for e in lasers)
    assert all(e.bullet_state2 == 5 and e.draw_cb == 1 for e in lasers)


# ---- 集成 smoke: ReimuA 追踪弹在真一面命中移动目标 ----


@needs_data
def test_reimu_a_homing_curves_and_hits_in_stage_one() -> None:
    """真一面(seed=42): 追踪符札朝索敌目标转向(轨迹弯曲), 命中结算出 EnemyDamaged。"""
    w = compose_world(compose(), character=0, difficulty=1, seed=42)
    log: list[Event] = []
    w.subscribers.append(log.append)
    homing_seen = 0
    curved = 0
    target_seen = False
    last: dict[int, tuple[int, float]] = {}  # 池位 → (timer, 航向角)
    for _ in range(1200):
        w.tick(InputFrame(held=frozenset({Button.SHOT})))
        if w.shot_hooks.position_of_last_enemy_hit.x > -100.0:
            target_seen = True  # 索敌目标同步进回调状态口
        for idx, s in enumerate(w.shots.pool):
            if s.bullet_state == 0 or s.update_cb != UPDATE_HOMING:
                continue
            homing_seen += 1
            heading = math.atan2(s.velocity.y, s.velocity.x)
            prev = last.get(idx)
            # 同一段生命(连续帧)航向变化 > 0.05 rad 记一次转向
            if prev is not None and prev[0] == s.timer - 1:
                if abs(heading - prev[1]) > 0.05:
                    curved += 1
            last[idx] = (s.timer, heading)
    assert homing_seen > 0  # 追踪弹确实在飞
    assert target_seen  # position_of_last_enemy_hit 经 world 同步
    assert curved > 0  # 轨迹不是 .sht 角度直飞: 发生转向
    assert any(isinstance(e, EnemyDamaged) for e in log)  # 命中移动目标
