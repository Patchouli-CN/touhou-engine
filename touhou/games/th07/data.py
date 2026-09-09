"""th07(东方妖妖梦)数值表/名单 —— 数值原样照抄反编译源码, 出处见各表头注释。"""

from __future__ import annotations

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
