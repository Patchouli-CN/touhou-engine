"""th07(东方妖妖梦)数值表/名单 —— 数值原样照抄反编译源码, 出处见各表头注释。"""

from __future__ import annotations

from ...engine.bullets import BulletTypeSpec
from ...utils.math import Vec2

# ---- 名单(下标语义: shotType / difficulty) ----
# 出处 old/touhou/games/th07/data.py
CHARACTERS = ("ReimuA", "ReimuB", "MarisaA", "MarisaB", "SakuyaA", "SakuyaB")
DIFFICULTIES = ("Easy", "Normal", "Hard", "Lunatic", "Extra", "Phantasm")
EXTRA_STAGES = ("Extra", "Phantasm")  # 简化: 原版 Phantasm 需 Extra 通关后出现
STAGE_COUNT = 6  # 本篇面数(7=Extra 8=Phantasm 不计)
PRACTICE_DIFFICULTY_COUNT = (
    4  # practice 难度页项数(MainMenu.cpp:1210 无 Extra/Phantasm)
)

# 机体 → (非 focus, focus) .sht 文件; 键 = shotType 0..5
CHARACTER_SHT: dict[int, tuple[str, str]] = {
    0: ("ply00a.sht", "ply00as.sht"),
    1: ("ply00b.sht", "ply00bs.sht"),
    2: ("ply01a.sht", "ply01as.sht"),
    3: ("ply01b.sht", "ply01bs.sht"),
    4: ("ply02a.sht", "ply02as.sht"),
    5: ("ply02b.sht", "ply02bs.sht"),
}

# ---- 符卡 ----
# 符卡基础分值(代码值 = 显示分*10), 141 张,
# 原样照抄 EnemyManager.cpp:16-37 的 g_SpellcardScore[141]
SPELLCARD_SCORE = (
    0x1E8480,
    0x1E8480,
    0x2191C0,
    0x2191C0,
    0x249F00,
    0x249F00,
    0x249F00,
    0x249F00,
    0x249F00,
    0x249F00,
    0x27AC40,
    0x27AC40,
    0x27AC40,
    0x27AC40,
    0x27AC40,
    0x27AC40,
    0x27AC40,
    0x27AC40,
    0x27AC40,
    0x27AC40,
    0x27AC40,
    0x27AC40,
    0x27AC40,
    0x27AC40,
    0x27AC40,
    0x27AC40,
    0x2DC6C0,
    0x2DC6C0,
    0x2DC6C0,
    0x2DC6C0,
    0x2DC6C0,
    0x2DC6C0,
    0x2DC6C0,
    0x2DC6C0,
    0x2DC6C0,
    0x2DC6C0,
    0x2DC6C0,
    0x2DC6C0,
    0x2DC6C0,
    0x2DC6C0,
    0x2DC6C0,
    0x2DC6C0,
    0x2DC6C0,
    0x2DC6C0,
    0x3567E0,
    0x3567E0,
    0x3567E0,
    0x3567E0,
    0x3567E0,
    0x3567E0,
    0x3567E0,
    0x3567E0,
    0x3567E0,
    0x3567E0,
    0x3567E0,
    0x3567E0,
    0x3567E0,
    0x3567E0,
    0x3567E0,
    0x3567E0,
    0x3567E0,
    0x3567E0,
    0x3567E0,
    0x3567E0,
    0x3567E0,
    0x3567E0,
    0x3567E0,
    0x3567E0,
    0x3D0900,
    0x3D0900,
    0x3D0900,
    0x3D0900,
    0x3D0900,
    0x3D0900,
    0x3D0900,
    0x3D0900,
    0x3D0900,
    0x3D0900,
    0x3D0900,
    0x3D0900,
    0x3D0900,
    0x3D0900,
    0x3D0900,
    0x3D0900,
    0x3D0900,
    0x3D0900,
    0x3D0900,
    0x3D0900,
    0x4C4B40,
    0x4C4B40,
    0x4C4B40,
    0x4C4B40,
    0x4C4B40,
    0x4C4B40,
    0x4C4B40,
    0x4C4B40,
    0x4C4B40,
    0x4C4B40,
    0x4C4B40,
    0x4C4B40,
    0x4C4B40,
    0x4C4B40,
    0x4C4B40,
    0x4C4B40,
    0x4C4B40,
    0x4C4B40,
    0x4C4B40,
    0x4C4B40,
    0x4C4B40,
    0x4C4B40,
    0x4C4B40,
    0x4C4B40,
    0x2DC6C0,
    0x2DC6C0,
    0x2DC6C0,
    0x2DC6C0,
    0x5B8D80,
    0x5B8D80,
    0x6ACFC0,
    0x6ACFC0,
    0x6ACFC0,
    0x6ACFC0,
    0x6ACFC0,
    0x6ACFC0,
    0x6ACFC0,
    0x6ACFC0,
    0x3D0900,
    0x6ACFC0,
    0x6ACFC0,
    0x6ACFC0,
    0x7A1200,
    0x7A1200,
    0x7A1200,
    0x7A1200,
    0x7A1200,
    0x7A1200,
    0x7A1200,
    0x7A1200,
    0x3D0900,
    0x7A1200,
    0x3D0900,
)

# ---- 炸弹 ----
# 六机体炸弹首帧参数原始行(数值以 BombData.cpp 为准, 行号见各注释):
# 键 (character, focus), 值 (duration, invulnerability, drain_min_cost, drain_scale)
BOMB_PARAMS: dict[tuple[int, bool], tuple[int, int, int, float]] = {
    (0, False): (140, 200, 4000, 0.20),  # ReimuA  BombData.cpp:137-151
    (0, True): (300, 360, 5000, 0.22),  # ReimuA 集中 :335-347
    (1, False): (140, 200, 3000, 0.17),  # ReimuB  :534-560
    (1, True): (190, 250, 3000, 0.17),  # ReimuB 集中 :645-656
    (2, False): (200, 250, 8000, 0.30),  # MarisaA :723-739
    (2, True): (260, 310, 9000, 0.33),  # MarisaA 集中 :832-839
    (3, False): (300, 300, 8000, 0.35),  # MarisaB :980-993
    (3, True): (340, 390, 10000, 0.41),  # MarisaB 集中 :1107-1120
    (4, False): (160, 210, 6000, 0.28),  # SakuyaA :1207-1216
    (4, True): (250, 290, 6500, 0.29),  # SakuyaA 集中 :1339-1347
    (5, False): (160, 260, 5500, 0.26),  # SakuyaB :1508-1517
    (5, True): (300, 420, 6000, 0.29),  # SakuyaB 集中 :1633-1659
}

# ---- 道具 / 火力 ----
# 小怪掉落表(索引循环, 0=小P 1=点 2=大P 7=樱), 出处 ItemManager
DROP_TABLE = (
    0,
    0,
    1,
    0,
    1,
    0,
    0,
    7,
    1,
    1,
    0,
    0,
    7,
    1,
    1,
    0,
    1,
    0,
    1,
    0,
    1,
    0,
    1,
    0,
    1,
    0,
    7,
    1,
    1,
    1,
    0,
    2,
)

# 火力档位阈值("升级"提示与满火力判定)
POWER_LEVELS = (8, 16, 32, 48, 64, 80, 96, 128, 999)
FULL_POWER = 128

# 满火力后吃小 P 的递增分(代码值 g_FullPowerScoreBonus, 显示分 = 值/10)
FULL_POWER_SCORE_BONUS = (
    10,
    20,
    30,
    40,
    50,
    60,
    70,
    80,
    90,
    100,
    200,
    300,
    400,
    500,
    600,
    700,
    800,
    900,
    1000,
    2000,
    3000,
    4000,
    5000,
    6000,
    7000,
    8000,
    9000,
    10000,
    11000,
    12000,
)

# ---- 敌弹弹型模板 ----
# 16 槽(g_BulletTypeInfos + AddedCallback), 出处 old/touhou/games/th07/data.py:306
# anm_file_idx = etama 活动脚本基址; spawn_t = 出生特效脚本时长(三档, 0x212-0x218/0x2aa)
BULLET_TYPE_SPECS: tuple[BulletTypeSpec, ...] = (
    BulletTypeSpec(0x200, 8.0, 8.0, Vec2(4, 4), 5, spawn_t=(10, 16, 32)),  # 0: 小弹
    BulletTypeSpec(0x201, 16.0, 16.0, Vec2(6, 6), 3, spawn_t=(10, 16, 32)),  # 1: 中弹
    BulletTypeSpec(0x202, 14.0, 16.0, Vec2(4, 4), 4, spawn_t=(10, 16, 32)),  # 2: 米弹
    BulletTypeSpec(0x203, 16.0, 16.0, Vec2(6, 6), 3, spawn_t=(10, 16, 32)),  # 3
    BulletTypeSpec(0x204, 14.0, 16.0, Vec2(4, 4), 4, spawn_t=(10, 16, 32)),  # 4
    BulletTypeSpec(0x205, 14.0, 16.0, Vec2(4, 4), 4, spawn_t=(10, 16, 32)),  # 5
    BulletTypeSpec(0x206, 14.0, 16.0, Vec2(4, 4), 4, spawn_t=(10, 16, 32)),  # 6
    BulletTypeSpec(0x207, 32.0, 32.0, Vec2(10, 10), 2, spawn_t=(32, 32, 32)),  # 7: 大弹
    BulletTypeSpec(0x208, 32.0, 32.0, Vec2(5, 5), 1, spawn_t=(32, 32, 32)),  # 8: 刀弹
    BulletTypeSpec(0x209, 32.0, 32.0, Vec2(8, 8), 2, spawn_t=(32, 32, 32)),  # 9: 札弹
    BulletTypeSpec(0x2A8, 8.0, 8.0, Vec2(4, 4), 5, spawn_t=(24, 24, 24)),  # 10: 光弹
    # 11..15: TH07 未初始化(AddedCallback 只循环 i<11)
    BulletTypeSpec(0, 0.0, 0.0, Vec2(0, 0), 0),
    BulletTypeSpec(0, 0.0, 0.0, Vec2(0, 0), 0),
    BulletTypeSpec(0, 0.0, 0.0, Vec2(0, 0), 0),
    BulletTypeSpec(0, 0.0, 0.0, Vec2(0, 0), 0),
    BulletTypeSpec(0, 0.0, 0.0, Vec2(0, 0), 0),
)

_DEFAULT_BULLET_SIZE = Vec2(16, 16)


def bullet_type_size(bullet_type: int) -> Vec2:
    """弹型 → 精灵尺寸(出界/反弹判定用); 未知弹型给 16px 默认。"""
    if 0 <= bullet_type < len(BULLET_TYPE_SPECS):
        spec = BULLET_TYPE_SPECS[bullet_type]
        if spec.width > 0:
            return Vec2(spec.width, spec.height)
    return _DEFAULT_BULLET_SIZE


# 弹型模板的活动 sprite 基址(etama.anm 全局索引, 链式加载首个 set-sprite)
_BULLET_BASE_SPRITE_IDX: tuple[int, ...] = (
    512,
    528,
    544,
    560,
    576,
    592,
    608,
    624,
    632,
    640,
    680,
)


def bullet_active_sprite_idx(sprite: int, sprite_offset: int) -> int:
    """活动 sprite 索引(SpawnSingleBullet: 基址 + spriteOffset)。"""
    if 0 <= sprite < len(_BULLET_BASE_SPRITE_IDX):
        return _BULLET_BASE_SPRITE_IDX[sprite] + sprite_offset
    return -1


def bullet_sprite_height(sprite: int, sprite_offset: int) -> float:
    """活动 sprite 高(ExIns 大弹判定用); 模板 10 的 offset 0..3 是 64px 大玉。"""
    if sprite == 10:
        return 64.0 if 0 <= sprite_offset <= 3 else 16.0
    return bullet_type_size(sprite).y


# ---- ECL 变量槽 id(变量表出处 EclManager.hpp:362-397, 10000~10073) ----
#: int 局部槽: LOCAL_INT1(10000-03) + LOCAL_INT2(10012-15) + LOCAL_INT3/global_ints(10029-32)
ECL_INT_VAR_IDS = frozenset(
    set(range(10000, 10004)) | set(range(10012, 10016)) | set(range(10029, 10033))
)
#: float 局部槽: LOCAL_FLOAT1(10004-11) + LOCAL_FLOAT3/global_floats(10033-36) + LOCAL_FLOAT2(10072-73)
ECL_FLOAT_VAR_IDS = frozenset(
    set(range(10004, 10012)) | set(range(10033, 10037)) | {10072, 10073}
)
#: 位置分量变量 id(插值命中时回算 axis_speed, EclManager.cpp:860-880)
ECL_POS_VAR_IDS = frozenset({10018, 10019, 10020})

# LOCAL_INT3/global_ints 与 LOCAL_FLOAT3/global_floats 的起始 id
# (SUB_CALL/生敌时从宿主全局快照拷入上下文, 旧 a.global_ints/global_floats)
GLOBAL_INT_VAR_BASE = 10029
GLOBAL_FLOAT_VAR_BASE = 10033
