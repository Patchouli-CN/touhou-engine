"""自机射击数据(.sht)解析: 火力等级表 + 射击条目链。"""

from __future__ import annotations

import struct

import msgspec

from .exceptions import ParseError

# 布局出处 old/touhou/schema/shot_data.py(Reference/th07 Player.hpp ShtData)
# 与 old/touhou/games/th08/shot_data.py(th08-ref Player.hpp:22-56/247-266,
# 转引 scratch_dbg/investigation/th08-ref-facts.md:48)
_HEADER_SIZE = 52  # 基础布局头: i16 + u16 + f32 + i32 + 10×f32
_HEADER_SIZE_EXT = 0x38  # 扩展布局头(字段重排, 见 parse_sht)
_ENTRY_SIZE = 52  # 基础布局 ShtEntry
_ENTRY_SIZE_EXT = 0x38  # 扩展布局 PlayerShotDescriptor


class ShotEntry(msgspec.Struct, frozen=True):
    """一条射击条目(某火力等级下一次发射的若干弹之一)。

    fire_interval < 0 是链尾哨兵; gauge_behavior 仅扩展布局有值(否则 0)。
    """

    fire_interval: int  # 射击周期(帧)
    fire_offset: int  # 周期内偏移
    offset: tuple[float, float]  # 相对发射点偏移
    hitbox: tuple[float, float]  # 弹判定盒(全宽/全高)
    angle: float  # 基准角(弧度)
    speed: float
    damage: int
    option: int  # 0=本体 1/2=子机
    bullet_state2: int  # 3=穿透, 4/5=激光型
    fire_cb: int
    update_cb: int
    draw_cb: int
    hit_cb: int
    anm_file_idx: int = 0
    sound_idx: int = -1  # 发弹音效 idx(Player.cpp:116-119)
    gauge_behavior: int = 0  # extremeGaugeBehavior(扩展布局 @0x1E)


class ShotLevel(msgspec.Struct, frozen=True):
    """一个火力等级: 达到 required_power 时启用, 指向一组射击条目。"""

    required_power: int
    entries: list[ShotEntry]


class ShotData(msgspec.Struct, frozen=True):
    """一份 .sht(某角色单个 focus 状态)的完整射击数据。

    cherry_penalty_multiplier 在扩展布局里不存在, 恒 0。
    """

    initial_bombs: float
    initial_respawn_timer: int  # 决死窗/死亡倒计时初值(i32)
    hitbox_radius: float
    grab_item_radius: float
    item_collect_speed: float
    item_collect_radius: float
    cherry_penalty_multiplier: float
    poc_y: float  # 收点线高度
    speed: float
    speed_focus: float
    speed_diagonal: float
    speed_diagonal_focus: float
    levels: list[ShotLevel]

    def level_for_power(self, power: float) -> ShotLevel:
        """返回满足 power >= required_power 的最高火力等级。"""
        chosen = self.levels[0]
        for lv in self.levels:
            if power >= lv.required_power:
                chosen = lv
        return chosen


def _f32(d: bytes, off: int) -> float:
    v: float = struct.unpack_from("<f", d, off)[0]
    return v


def _i32(d: bytes, off: int) -> int:
    v: int = struct.unpack_from("<i", d, off)[0]
    return v


def _i16(d: bytes, off: int) -> int:
    v: int = struct.unpack_from("<h", d, off)[0]
    return v


def _parse_entry_chain(data: bytes, offset: int, entry_size: int) -> list[ShotEntry]:
    """从 offset 起解析射击条目链, 直到 fire_interval < 0。"""
    ext = entry_size == _ENTRY_SIZE_EXT
    out: list[ShotEntry] = []
    off = offset
    while off + entry_size <= len(data):
        fi = _i16(data, off)
        fo = _i16(data, off + 2)
        ox, oy = _f32(data, off + 4), _f32(data, off + 8)
        hx, hy = _f32(data, off + 12), _f32(data, off + 16)
        angle = _f32(data, off + 20)
        speed = _f32(data, off + 24)
        damage = _i16(data, off + 28)
        if ext:
            # 扩展布局: i16 gauge/option/shotType/anm/sound @30..38, 回调 @40 起
            gauge_behavior = _i16(data, off + 30)
            option = _i16(data, off + 32)
            bs2 = _i16(data, off + 34)
            anm_idx = _i16(data, off + 36)
            snd_idx = _i16(data, off + 38)
            cb = 40
        else:
            gauge_behavior = 0
            option = data[off + 30]
            bs2 = data[off + 31]
            anm_idx = _i16(data, off + 32)
            snd_idx = _i16(data, off + 34)
            cb = 36
        out.append(
            ShotEntry(
                fi,
                fo,
                (ox, oy),
                (hx, hy),
                angle,
                speed,
                damage,
                option,
                bs2,
                _i32(data, off + cb),
                _i32(data, off + cb + 4),
                _i32(data, off + cb + 8),
                _i32(data, off + cb + 12),
                anm_file_idx=anm_idx,
                sound_idx=snd_idx,
                gauge_behavior=gauge_behavior,
            )
        )
        if fi < 0:
            break
        off += entry_size
    return out


def parse_sht(data: bytes, *, extended: bool = False) -> ShotData:
    """解析一个 .sht。

    Args:
        data: .sht 字节
        extended: False = 基础布局(52 字节头 + 52 字节条目);
            True = 扩展布局(0x38 字节头 + 56 字节条目, 多 gauge_behavior 字段;
            无樱点惩罚系数, 恒 0)
    """
    if len(data) < _HEADER_SIZE:
        raise ParseError("sht 过短")
    count = struct.unpack_from("<H", data, 2)[0]  # 火力档数
    initial_bombs = _f32(data, 4)
    initial_respawn_timer = _i32(data, 8)
    if extended:
        (
            hitbox_radius,
            grab_item_radius,
            item_collect_speed,
            item_collect_radius,
            poc_y,
        ) = struct.unpack_from("<5f", data, 0xC)
        # @0x20 是 u32 reserved; @0x24 起 5f, 末项 itemMovementSpeed 无对应字段不取
        speed, speed_focus, speed_diagonal, speed_diagonal_focus = struct.unpack_from(
            "<4f", data, 0x24
        )
        cherry_penalty = 0.0
        lvl_tab = _HEADER_SIZE_EXT
        entry_size = _ENTRY_SIZE_EXT
    else:
        (
            hitbox_radius,
            grab_item_radius,
            item_collect_speed,
            item_collect_radius,
            cherry_penalty,
            poc_y,
            speed,
            speed_focus,
            speed_diagonal,
            speed_diagonal_focus,
        ) = struct.unpack_from("<10f", data, 12)
        lvl_tab = _HEADER_SIZE
        entry_size = _ENTRY_SIZE

    levels: list[ShotLevel] = []
    for i in range(count):
        off = lvl_tab + i * 8
        if off + 8 > len(data):
            raise ParseError(f"sht 火力档表截断 (档 {i})")
        rel, req_power = struct.unpack_from("<Ii", data, off)
        levels.append(ShotLevel(req_power, _parse_entry_chain(data, rel, entry_size)))

    return ShotData(
        initial_bombs,
        initial_respawn_timer,
        hitbox_radius,
        grab_item_radius,
        item_collect_speed,
        item_collect_radius,
        cherry_penalty,
        poc_y,
        speed,
        speed_focus,
        speed_diagonal,
        speed_diagonal_focus,
        levels,
    )
