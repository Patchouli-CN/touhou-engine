"""th07 的 24 条 ExIns(boss 特技, EnemyEclInstr.cpp g_EclExInstr)。

语义逐条照抄旧实现 old/touhou/games/th07/ecl_host.py 的 run_ex_instr 分派;
闪屏/特效/换皮等纯视觉不接(震屏事件后续单接; BGM 指令经 host.on_bgm 透出)。
instr 是 SetExIns/RunExIns 原指令(args = idx 之后的原始载荷字; C 直接读
args[1].i = 本模块 _arg1)。
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from ...engine.bullets import BulletCommand, CmdFlag
from ...engine.ecl.num import add_norm_angle
from ...engine.ecl.state import EnemySpawn, Vec3
from ...engine.lasers import LaserState
from ...schemas.ecl import EclInstr
from ...utils.math import Vec2, angle_to
from .data import bullet_active_sprite_idx, bullet_sprite_height, bullet_type_size
from .ecl_state import BulletShooter

if TYPE_CHECKING:
    from ...engine.ecl import EclMachine
    from .ecl_host import Th07EclHost

# ctx 局部槽 id(浮点变量 float_vars1[0..7] = 10004..10011, int_vars1[0] = 10000)
_FV = 10004
_IV = 10000


def _arg1(instr: EclInstr | None, default: int = 0) -> int:
    """C 直接读 instr->args[1].i(不做变量解析); args[0] 是 idx 之后的第一个字。"""
    args = getattr(instr, "args", ())
    return args[0] if args else default


def _ex0_set_pos_to_boss(
    host: Th07EclHost, m: EclMachine, instr: EclInstr | None
) -> None:
    # EnemyEclInstr.cpp:55 ExInsSetPosToBoss
    boss = host.bosses[_arg1(instr) & 7]
    if boss is None:
        return
    e, b = m.enemy, boss.enemy
    e.pos = b.pos.copy()
    e.axis_speed = b.axis_speed.copy()
    e.angle = b.angle
    e.disable_movement = 1


def _ex1_alice_curve_bullets(
    host: Th07EclHost, m: EclMachine, instr: EclInstr | None
) -> None:
    # EnemyEclInstr.cpp:66 ExInsAliceCurveBullets(同帧震屏 (30,12,0) 后续单接)
    sel = _arg1(instr)
    rng = m.rng
    for b in host.bullets.alive():
        if b.state2 != 0:
            continue
        if sel == 1 and b.sprite_offset != 8:
            continue
        if sel == 2 and b.sprite_offset != 4:
            continue
        if b.sprite_offset == 2:
            turn = -math.pi / (rng.in_range(0.0, 60.0) + 180.0)
        elif b.sprite_offset in (6, 8):
            turn = math.pi / (rng.in_range(0.0, 60.0) + 180.0)
        elif b.sprite_offset == 4:
            turn = -math.pi / (rng.in_range(0.0, 60.0) + 180.0)
        else:
            continue  # C 里 local_10 未初始化(ZUN bloat), 按跳过处理
        b.speed = 0.3
        b.commands = []
        b.cur_cmd_idx = 0
        if host.difficulty < 3:
            b.set_command(
                0,
                BulletCommand(
                    CmdFlag.TARGET_ANGLE, speed=0.016666668, angle=turn, duration=60
                ),
            )
        else:
            b.set_command(
                0,
                BulletCommand(
                    CmdFlag.TARGET_ANGLE,
                    speed=0.005263158,
                    angle=turn,
                    duration=240,
                ),
            )
        b.state2 = 1


def _ex2_turn_bullets_into_other_bullets(
    host: Th07EclHost, m: EclMachine, instr: EclInstr | None
) -> None:
    # EnemyEclInstr.cpp:127 ExInsTurnBulletsIntoOtherBullets(sel==0 震屏 (32,12,0) 不接)
    sel = _arg1(instr)
    radius = (128.0, 192.0, 256.0, 999.0)[sel & 3]
    rng = m.rng
    e = m.enemy
    for b in list(host.bullets.alive()):  # 快照: 循环内 spawn
        if b.sprite_offset != 2:
            continue
        dx = e.pos.x - b.pos.x
        dy = e.pos.y - b.pos.y
        if math.sqrt(dx * dx + dy * dy) >= radius:
            continue
        props = BulletShooter(
            sprite=0,
            sprite_offset=6,
            angle1=0.0,
            angle2=-math.pi,
            speed1=0.7,
            count1=2,
            count2=1,
            flags=2,
            aim_mode=6,
        )
        props.commands[0].type = int(CmdFlag.TARGET_VEL)
        props.commands[0].duration = 180
        props.commands[0].speed = rng.in_range(0.0, 0.005) + 0.013
        props.commands[0].angle = 1.5707964
        host.fire_temp_shooter_at(m, props, Vec3(b.pos.x, b.pos.y, 0.0))
        b.dead = True


def _ex4_despawn_large_bullet_and_save_pos(
    host: Th07EclHost, m: EclMachine, instr: EclInstr | None
) -> None:
    # EnemyEclInstr.cpp:196 ExInsDespawnLargeBulletAndSavePos
    ctx = m.current
    ctx.float_vars[_FV] = -999.0
    for b in host.bullets.alive():
        if bullet_sprite_height(b.sprite, b.sprite_offset) >= 60.0:
            ctx.float_vars[_FV] = b.pos.x
            ctx.float_vars[_FV + 1] = b.pos.y
            # C 另有 SpawnParticles(2, pos, 1, white), 视觉不接
            b.dead = True
            break


def _ex5_copy_main_boss_movement(
    host: Th07EclHost, m: EclMachine, instr: EclInstr | None
) -> None:
    # EnemyEclInstr.cpp:227 ExInsCopyMainBossMovement
    boss = host.bosses[0]
    if boss is None:
        return
    e = m.enemy
    e.move_interp_start_pos = boss.enemy.pos.copy()
    e.move_radius = boss.enemy.move_radius
    e.move_angular_velocity = boss.enemy.move_angular_velocity


def _ex6_split_bullets_or_shoot_backwards(
    host: Th07EclHost, m: EclMachine, instr: EclInstr | None
) -> None:
    # EnemyEclInstr.cpp:242 ExInsSplitBulletsOrShootBackwards
    sel = _arg1(instr)
    diff = host.difficulty
    for b in list(host.bullets.alive()):
        if not (
            (sel == 0 and b.sprite_offset == 6)
            or (sel == 1 and b.sprite_offset == 15)
            or (sel == 2 and b.sprite_offset == 2)
        ):
            continue
        props = BulletShooter(
            sprite=6,
            sprite_offset=15,
            angle1=add_norm_angle(b.angle, math.pi),
            angle2=0.5235988,
            speed1=b.speed * 1.1,
            count1=4 if diff < 3 else 2,
            count2=1,
            flags=2,
            aim_mode=1,
        )
        if diff >= 3:
            props.angle2 = 1.5707964
        props.commands[0].type = int(CmdFlag.SPAWN_DELAY)
        props.commands[0].duration = 130
        if sel == 0:
            props.flags = 0x2002
        elif sel == 1:
            props.flags = 2 if diff != 3 else 0x2002
            props.sprite_offset = 2
        elif sel == 2:
            props.flags = 2
            props.sprite_offset = 10
        at = Vec3(b.pos.x, b.pos.y, 0.0)
        host.fire_temp_shooter_at(m, props, at)
        props.angle2 = 1.0471976
        if sel == 0:
            props.flags = 0x2000
        elif sel == 1:
            props.flags = 0 if diff != 3 else 0x2000
        else:
            props.flags = 0
        props.speed1 = b.speed * 0.7
        props.count1 = 2
        host.fire_temp_shooter_at(m, props, at)
        props.speed1 = b.speed * 0.85
        props.count1 = 1
        host.fire_temp_shooter_at(m, props, at)
        b.dead = True


def _point_in_rotated_rect(
    px: float,
    py: float,
    cx: float,
    cy: float,
    sx: float,
    sy: float,
    pivot: Vec2,
    sine: float,
    cosine: float,
) -> bool:
    # EnemyEclInstr.cpp:336 IsPointInRotatedRect
    dx = px - pivot.x
    dy = py - pivot.y
    rx = dx * cosine + dy * sine + pivot.x
    ry = dy * cosine - dx * sine + pivot.y
    return cx - sx / 2.0 <= rx <= cx + sx / 2.0 and cy - sy / 2.0 <= ry <= cy + sy / 2.0


def _ex7_reflect_bullets_from_lasers(
    host: Th07EclHost, m: EclMachine, instr: EclInstr | None
) -> None:
    # EnemyEclInstr.cpp:366 ExInsReflectBulletsFromLasers
    e = m.enemy
    for i, laser in enumerate(host.lasers.lasers):
        if not laser.in_use or e.timer % 2 != i:
            continue
        if laser.state >= LaserState.DESPAWNING:
            continue
        size_x = laser.offset_b - laser.offset_a
        cx = size_x / 2.0 + laser.offset_a + laser.pos.x
        cy = laser.pos.y
        sine, cosine = math.sin(laser.angle), math.cos(laser.angle)
        for b in host.bullets.alive():
            if not _point_in_rotated_rect(
                b.pos.x, b.pos.y, cx, cy, size_x, laser.width, laser.pos, sine, cosine
            ):
                continue
            if b.state2 > 0:
                b.state2 -= 1
            if b.state2 != 0:
                continue
            if b.speed > 0.5:
                b.speed -= 0.1
            dot = cosine * b.vel.y + sine * b.vel.x
            b.angle = add_norm_angle(
                laser.angle, 1.5707964 if dot >= 0.0 else -1.5707964
            )
            b.vel = Vec2.from_angle(b.angle, host.framerate_multiplier * b.speed)
            b.state2 = 10
            b.sprite = 5  # bulletTypeTemplates[5]; C 另 SetActiveSprite 换皮
            b.size = bullet_type_size(5)


def _ex8_shoot_bullets_along_laser(
    host: Th07EclHost, m: EclMachine, instr: EclInstr | None
) -> None:
    # EnemyEclInstr.cpp:454 ExInsShootBulletsAlongLaser
    rng = m.rng
    diff = host.difficulty
    e = m.enemy
    for i, laser in enumerate(host.lasers.lasers):
        if not laser.in_use or e.timer % 3 != i % 3:
            continue
        if laser.state >= LaserState.DESPAWNING:
            continue
        size_x = laser.offset_b - laser.offset_a
        cx = size_x / 2.0 + laser.offset_a + laser.pos.x
        cy = laser.pos.y
        sine, cosine = math.sin(laser.angle), math.cos(laser.angle)
        dir_x, dir_y = -sine, cosine
        for b in host.bullets.alive():
            if b.state2 == i + 1 or b.state2 < 0:
                continue
            if not _point_in_rotated_rect(
                b.pos.x,
                b.pos.y,
                cx,
                cy,
                size_x,
                laser.width * 1.5,
                laser.pos,
                sine,
                cosine,
            ):
                continue
            if diff < 2:
                b.speed *= rng.in_range(0.0, 0.3) + 0.7
            else:
                b.speed *= rng.in_range(0.0, 0.4) + 0.8
            dot = dir_x * b.vel.x + dir_y * b.vel.y
            if dot >= 0.0:
                b.vel = Vec2(dir_x, dir_y)
            else:
                b.vel = Vec2(-dir_x, -dir_y)
            b.sprite = 5  # bulletTypeTemplates[5], 换皮注释同 ex7
            b.size = bullet_type_size(5)
            b.angle = math.atan2(b.vel.y, b.vel.x)
            b.vel = Vec2.from_angle(b.angle, b.speed)
            b.state2 = -1 if diff < 2 else i + 1


def _ex9_effect1e_accel(
    host: Th07EclHost, m: EclMachine, instr: EclInstr | None
) -> None:
    # EnemyEclInstr.cpp:549 ExInsEffect1eAccel —— 特效系统表现, 无逻辑效果(震屏 (80,8,0) 不接)
    pass


def _ex10_youmu_set_game_speed(
    host: Th07EclHost, m: EclMachine, instr: EclInstr | None
) -> None:
    # EnemyEclInstr.cpp:556 ExInsYoumuSetGameSpeed(spellcardVms/换帧为表现侧, 不接)
    mult = 1.0 / float(_arg1(instr, 1) or 1)
    host.framerate_multiplier = mult
    host.bullets.time_scale = mult
    for b in host.bullets.alive():
        b.vel = b.vel * mult


def _ex11_youmu_restore_game_speed(
    host: Th07EclHost, m: EclMachine, instr: EclInstr | None
) -> None:
    # EnemyEclInstr.cpp:585 ExInsYoumuRestoreGameSpeed(终值恒 1.0)
    mult = host.framerate_multiplier
    fps = 1.0 / mult if mult else 1.0
    for b in host.bullets.alive():
        b.vel = b.vel * fps
    host.framerate_multiplier = 1.0
    host.bullets.time_scale = 1.0


def _burst_large_bullets(
    host: Th07EclHost,
    m: EclMachine,
    instr: EclInstr | None,
    count_by_diff: tuple[int, ...],
    y_range: float,
    sprite_table: tuple[tuple[int, int], ...],
) -> None:
    # EnemyEclInstr.cpp:621/853 ExInsBurstLargeBullets{,2} 公共部分(BombEffects 不接)
    rng = m.rng
    n = count_by_diff[min(host.difficulty, 3)]
    sel = _arg1(instr)
    e = m.enemy
    for b in list(host.bullets.alive()):
        if bullet_sprite_height(b.sprite, b.sprite_offset) <= 48.0:
            continue
        if not (e.pos.y - y_range < b.pos.y < e.pos.y + y_range):
            continue
        for j in range(n):
            sprite, offset = sprite_table[rng.int_below(3)]
            if sel == 0:
                angle1 = rng.in_range(0.0, 4.712389) - 1.5707964
            else:
                angle1 = add_norm_angle(rng.in_range(0.0, 4.712389), 0.7853982)
            props = BulletShooter(
                sprite=sprite,
                sprite_offset=offset,
                angle1=angle1,
                speed1=0.1,
                count1=1,
                count2=1,
                flags=2 if j & 1 else 0,
                aim_mode=1,
            )
            props.commands[0].type = int(CmdFlag.TARGET_ANGLE)
            props.commands[0].duration = 100
            props.commands[0].angle = 0.0
            props.commands[0].speed = rng.in_range(0.0, 0.008) + 0.01
            host.fire_temp_shooter_at(
                m,
                props,
                Vec3(
                    b.pos.x + rng.in_range(0.0, 32.0) - 16.0,
                    b.pos.y + rng.in_range(0.0, 32.0) - 16.0,
                    0.0,
                ),
            )
        b.dead = True


def _ex12_burst_large_bullets(
    host: Th07EclHost, m: EclMachine, instr: EclInstr | None
) -> None:
    # EnemyEclInstr.cpp:621: 数量 10/18/22/25, y 窗 ±64(H/L ±48)
    _burst_large_bullets(
        host,
        m,
        instr,
        (10, 18, 22, 25),
        64.0 if host.difficulty < 2 else 48.0,
        ((0, 2), (3, 2), (7, 1)),
    )


def _ex13_youmu_curve_bullets_below(
    host: Th07EclHost, m: EclMachine, instr: EclInstr | None
) -> None:
    # EnemyEclInstr.cpp:696 ExInsYoumuCurveBulletsBelow
    # (C 用弹槽下标 i 的奇偶选转向; Python 弹池无空槽, 用存活序号代替)
    e = m.enemy
    for i, b in enumerate(host.bullets.alive()):
        if b.state2 != 0:
            continue
        if not (
            e.pos.y < b.pos.y < 352.0 and e.pos.x - 16.0 < b.pos.x < e.pos.x + 16.0
        ):
            continue
        b.set_command(
            0,
            BulletCommand(
                CmdFlag.TARGET_ANGLE,
                duration=160,
                angle=0.05235988 if i & 1 else -0.05235988,
                speed=-b.speed / 180.0,
            ),
        )
        b.state2 = 1


def _ex14_youmu_redirect_bullets_to_player(
    host: Th07EclHost, m: EclMachine, instr: EclInstr | None
) -> None:
    # EnemyEclInstr.cpp:725 ExInsYoumuRedirectBulletsToPlayer(BombEffects 不接)
    for b in host.bullets.alive():
        if b.state2 != 1:
            continue
        b.set_command(
            0,
            BulletCommand(
                CmdFlag.TARGET_VEL,
                duration=90,
                speed=0.026666667,
                angle=angle_to(b.pos, host.bullets.player_pos),
            ),
        )
        b.clear_command(1)
        b.state2 = 2


def _ex15_flash_screen(
    host: Th07EclHost, m: EclMachine, instr: EclInstr | None
) -> None:
    # EnemyEclInstr.cpp:751 ExInsFlashScreen —— BombEffects 闪屏, 纯视觉不接
    pass


def _ex16_yuyuko_transform_butterfly_bullets(
    host: Th07EclHost, m: EclMachine, instr: EclInstr | None
) -> None:
    # EnemyEclInstr.cpp:757 ExInsYuyukoTransformButterflyBullets
    # 蝶弹 = sprite 8(活动 sprite 632-639, etama.anm 实测)
    speed = m.current.float_vars.get(_FV + 1, 0.0)
    for b in list(host.bullets.alive()):
        if b.state2 != 0 or b.sprite != 8 or not 0 <= b.sprite_offset <= 7:
            continue
        props = BulletShooter(
            sprite=0,
            sprite_offset=6,
            angle1=add_norm_angle(b.angle, math.pi),
            angle2=0.3926991,
            speed1=speed,
            count1=5,
            count2=1,
            flags=2,
            aim_mode=1,
        )
        host.fire_temp_shooter_at(m, props, Vec3(b.pos.x, b.pos.y, 0.0))


def _ex17_yuyuko_butterfly_spawn_enemy(
    host: Th07EclHost, m: EclMachine, instr: EclInstr | None
) -> None:
    # EnemyEclInstr.cpp:791 ExInsYuyukoButterflySpawnEnemy(BombEffects 不接)
    ctx = m.current
    angle_offset = -math.pi
    for b in list(host.bullets.alive()):
        idx632 = bullet_active_sprite_idx(b.sprite, b.sprite_offset)
        if b.state2 == 0 and idx632 == 636:
            spawned = host.spawn_enemy(
                EnemySpawn(
                    sub_id=ctx.sub_id + 1,
                    x=b.pos.x,
                    y=b.pos.y,
                    life=1,
                    item_drop=-2,
                    score=10,
                ),
                m,
            )
            if spawned is not None:
                new_ctx = spawned.machine.current
                new_ctx.float_vars[_FV] = b.angle
                new_ctx.float_vars[_FV + 7] = angle_offset
            angle_offset += 0.7853982
            b.dead = True
        elif 632 <= idx632 <= 639:
            b.dead = True


def _ex18_yuyuko_count_butterfly_bullets(
    host: Th07EclHost, m: EclMachine, instr: EclInstr | None
) -> None:
    # EnemyEclInstr.cpp:829 ExInsYuyukoCountButterflyBullets
    n = 0
    for b in host.bullets.alive():
        if b.state2 == 0 and bullet_active_sprite_idx(b.sprite, b.sprite_offset) == 636:
            n += 1
    m.current.int_vars[_IV] = n


def _ex19_yuyuko_fade_out_music(
    host: Th07EclHost, m: EclMachine, instr: EclInstr | None
) -> None:
    # EnemyEclInstr.cpp:919 —— Supervisor::FadeOutMusic(3.0)
    if host.on_bgm is not None:
        host.on_bgm(("fadeout", 3.0))


def _ex20_yuyuko_play_resurrection_bgm(
    host: Th07EclHost, m: EclMachine, instr: EclInstr | None
) -> None:
    # EnemyEclInstr.cpp:925 —— PlayLoadedAudio(2), 槽 2 = "bgm/th07_13b.mid"
    # (GameManager.cpp:787 6 面装载时预载)
    if host.on_bgm is not None:
        host.on_bgm(("play", "bgm/th07_13b.mid"))


def _ex21_burst_large_bullets2(
    host: Th07EclHost, m: EclMachine, instr: EclInstr | None
) -> None:
    # EnemyEclInstr.cpp:853: 数量恒 15, y 窗 Hard ±128, 其余 ±180
    _burst_large_bullets(
        host,
        m,
        instr,
        (15, 15, 15, 15),
        128.0 if host.difficulty == 2 else 180.0,
        ((0, 4), (3, 4), (7, 2)),
    )


def _ex22_spawn_bullets_with_dir_change(
    host: Th07EclHost, m: EclMachine, instr: EclInstr | None
) -> None:
    # EnemyEclInstr.cpp:936 ExInsSpawnBulletsWithDirChange
    e = m.enemy
    if e.timer % 3 == 0:
        return
    rng = m.rng
    odd = e.timer % 2 != 0
    for b in list(host.bullets.alive()):
        if (
            (b.ex_flags & 0x40)
            or b.pos.y >= 320.0
            or bullet_sprite_height(b.sprite, b.sprite_offset) <= 60.0
        ):
            continue
        props = BulletShooter(
            sprite=1 if odd else 3,
            sprite_offset=6 if b.sprite_offset == 1 else 2,
            angle1=rng.in_range(0.0, 6.2831855) - math.pi,
            angle2=-math.pi,
            speed1=1.2 if odd else 0.8,
            count1=1 if odd else 2,
            count2=1,
            flags=0x208,
            aim_mode=3,
        )
        if odd:
            props.commands[0].type = int(CmdFlag.DIR_CHANGE_AIM)
            props.commands[0].duration = 60
            props.commands[0].loop_count = 1
            props.commands[0].speed = 0.0
            props.commands[0].angle = 3.1
        host.fire_temp_shooter_at(m, props, Vec3(b.pos.x, b.pos.y, 0.0))


def _ex23_spawn_bullets_with_dir_change2(
    host: Th07EclHost, m: EclMachine, instr: EclInstr | None
) -> None:
    # EnemyEclInstr.cpp:1005 ExInsSpawnBulletsWithDirChange2
    e = m.enemy
    if e.timer % 3 == 2:
        return
    rng = m.rng
    mod3 = e.timer % 3
    for b in list(host.bullets.alive()):
        if (
            (b.ex_flags & 0x40)
            or b.pos.y >= 320.0
            or bullet_sprite_height(b.sprite, b.sprite_offset) <= 60.0
        ):
            continue
        props = BulletShooter(
            sprite=1 if mod3 else 3,
            sprite_offset=10 if b.sprite_offset == 2 else 13,
            angle1=rng.in_range(0.0, 6.2831855) - math.pi,
            angle2=-math.pi,
            speed1=1.2 if mod3 else 0.8,
            count1=1,
            count2=1,
            flags=0x208,
            aim_mode=3,
        )
        if mod3:
            props.commands[0].type = int(CmdFlag.DIR_CHANGE_AIM)
            props.commands[0].duration = 40
            props.commands[0].loop_count = 1
            props.commands[0].speed = 0.0
            props.commands[0].angle = 2.9
        host.fire_temp_shooter_at(m, props, Vec3(b.pos.x, b.pos.y, 0.0))


#: idx → 实现(g_EclExInstr 下标; idx 3 NoOp 在 EclMachine.run_ex 已短路)
EX_DISPATCH = {
    0: _ex0_set_pos_to_boss,
    1: _ex1_alice_curve_bullets,
    2: _ex2_turn_bullets_into_other_bullets,
    4: _ex4_despawn_large_bullet_and_save_pos,
    5: _ex5_copy_main_boss_movement,
    6: _ex6_split_bullets_or_shoot_backwards,
    7: _ex7_reflect_bullets_from_lasers,
    8: _ex8_shoot_bullets_along_laser,
    9: _ex9_effect1e_accel,
    10: _ex10_youmu_set_game_speed,
    11: _ex11_youmu_restore_game_speed,
    12: _ex12_burst_large_bullets,
    13: _ex13_youmu_curve_bullets_below,
    14: _ex14_youmu_redirect_bullets_to_player,
    15: _ex15_flash_screen,
    16: _ex16_yuyuko_transform_butterfly_bullets,
    17: _ex17_yuyuko_butterfly_spawn_enemy,
    18: _ex18_yuyuko_count_butterfly_bullets,
    19: _ex19_yuyuko_fade_out_music,
    20: _ex20_yuyuko_play_resurrection_bgm,
    21: _ex21_burst_large_bullets2,
    22: _ex22_spawn_bullets_with_dir_change,
    23: _ex23_spawn_bullets_with_dir_change2,
}


def run_ex(host: Th07EclHost, m: EclMachine, idx: int, instr: EclInstr | None) -> bool:
    """Ex 指令分派; 返回 True = 已处理。"""
    fn = EX_DISPATCH.get(idx)
    if fn is None:
        return False
    fn(host, m, instr)
    return True
