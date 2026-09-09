"""th07(东方妖妖梦)数值表/名单 —— 全作品数据集中于此, 注册进 registry。

收录(数值全部原样照抄反编译源码, 行号注释保留在各表头):
- SPELLCARD_SCORE:   141 张符卡基础分值(代码值, EnemyManager.cpp:16-37)
- BOMB_PARAMS:       六机体炸弹首帧参数原始行(BombData.cpp 各 *Calc)
- DROP_TABLE:        小怪随机掉落表(ItemManager)
- POWER_LEVELS / FULL_POWER / FULL_POWER_SCORE_BONUS: 火力档与满火力计分
- CHARACTER_SHT:     机体 → .sht 文件名(非 focus / focus)
- CHARACTERS / DIFFICULTIES / EXTRA_STAGES / STAGE_COUNT: 名单与面数
- BULLET_TYPE_SPECS: 弹型模板表 16 槽(BulletManager.cpp g_BulletTypeInfos +
  AddedCallback 判定树 + etama.anm 出生特效脚本时长), 附活动 sprite 基址等
  查询函数; 对局经 ``BulletWorld(type_specs=BULLET_TYPE_SPECS)`` 注入引擎

消费方式(双向皆通, 不传也能跑):
- 同包模块(boss/bomb/items)模块级同名常量 = 本模块的表(import 自这里),
  独立构造 Boss/Bomb/ItemWorld 时默认即 th07 数值;
- 经注册表: TH07_DATA 由 ``register_game_data("th07", ...)`` 登记,
  Game/TouhouWorld 构造对局时经 ``data=`` 注入(world 的 data 参数),
  对局实现内按 ``self.data`` 读(sht 映射/符卡分值/掉落表已接线)。

新作品(th08): 照抄本模块结构出自己的 games/th08/data.py(换数值),
register_game_data + 复用/自实现对局类即可, 引擎模块不用改。
"""

from __future__ import annotations

from ...engine.bullets import BulletTypeSpec
from ...registry import GameData, register_default_game, register_game_data
from ...utils import Vec2

# ---- 名单(下标语义: shotType / difficulty) ----
# 机体名单(shotType: 0=ReimuA 1=ReimuB 2=MarisaA 3=MarisaB 4=SakuyaA 5=SakuyaB)
CHARACTERS = ("ReimuA", "ReimuB", "MarisaA", "MarisaB", "SakuyaA", "SakuyaB")
# 难度名单(0..5; Extra/Phantasm 对应 7/8 面)
DIFFICULTIES = ("Easy", "Normal", "Hard", "Lunatic", "Extra", "Phantasm")
# Extra Start 后的关卡选择(简化: 原版 Phantasm 需 Extra 通关后才会出现)
EXTRA_STAGES = ("Extra", "Phantasm")
STAGE_COUNT = 6  # 本篇面数(7=Extra 8=Phantasm 不计)
PRACTICE_DIFFICULTY_COUNT = (
    4  # practice 难度页项数(MainMenu.cpp:1210 无 Extra/Phantasm)
)

# 角色 -> .sht 文件名(非 focus / focus); 键 = shotType 0..5
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
# 原样照抄 EnemyManager.cpp:16-37 的 g_SpellcardScore[141]。
SPELLCARD_SCORE = [
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
]

# ---- 炸弹 ----
# §D.3 六机体参数表原始行 (数值以 BombData.cpp 为准, 行号见各注释)。
# 键 (character, focus), 值 (duration, invulnerability, drain_min_cost, drain_scale);
# 引擎侧(games/th07/bomb.py)包成 BombParams 后消费。
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
# 小怪掉落表(索引循环, 0=小P 1=点 2=大P 7=樱)
DROP_TABLE = [
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
]

# 火力档位阈值(用于"升级"提示, 及满火力判定)
POWER_LEVELS = [8, 16, 32, 48, 64, 80, 96, 128, 999]
FULL_POWER = 128

# 满火力后吃小 P 的递增分数(代码值: g_FullPowerScoreBonus, 显示分 = 值/10)
FULL_POWER_SCORE_BONUS = [
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
]

# ---- 弹型模板表 (BulletManager.cpp AddedCallback + g_BulletTypeInfos) ----
# 16 个模板槽。TH07 只初始化前 11 个(g_BulletTypeInfos), 后 5 个槽未用(全 0)。
# 精灵尺寸提取自游戏数据 data/etama.anm(th07.dat):
#   0x200→8px, 0x201→16, 0x202→16, 0x203→16, 0x204→16, 0x205→16, 0x206→16,
#   0x207→32, 0x208→32, 0x209→32, 0x2a8(=chunk2, 链式偏移 168)→8
# graze/collision 按 AddedCallback 判定树: ≤8→(4,4,type5); ≤16→514/516/517/518
# 特判(4,4,type4)否则(6,6,type3); ≤32→520:(5,5,type1) 521:(8,8,type2)
# 否则(10,10,type2); >32→(24,24,type0)。
# spawn_t = etama.anm 出生特效脚本时长 T(脚本 t=T 时 EXIT_HIDE2; 转变帧=T+1),
# 从真实 th07.dat 解出(脚本 0x212-0x218 / 0x2aa):
#   弹型 0: 0x212/0x213/0x214 → 10/16/32; 弹型 1-6: 0x215/0x216/0x217 → 10/16/32;
#   弹型 7-9: 0x218 三态共用 → 32; 弹型 10: 0x2aa 三态共用 → 24
BULLET_TYPE_SPECS: tuple[BulletTypeSpec, ...] = (
    BulletTypeSpec(0x200, 8.0, 8.0, Vec2(4, 4), 5, spawn_t=(10, 16, 32)),  # 0: 小弹
    BulletTypeSpec(0x201, 16.0, 16.0, Vec2(6, 6), 3, spawn_t=(10, 16, 32)),  # 1: 中弹
    BulletTypeSpec(
        0x202, 14.0, 16.0, Vec2(4, 4), 4, spawn_t=(10, 16, 32)
    ),  # 2: 米弹(514 特判)
    BulletTypeSpec(0x203, 16.0, 16.0, Vec2(6, 6), 3, spawn_t=(10, 16, 32)),  # 3
    BulletTypeSpec(
        0x204, 14.0, 16.0, Vec2(4, 4), 4, spawn_t=(10, 16, 32)
    ),  # 4 (516 特判)
    BulletTypeSpec(
        0x205, 14.0, 16.0, Vec2(4, 4), 4, spawn_t=(10, 16, 32)
    ),  # 5 (517 特判)
    BulletTypeSpec(
        0x206, 14.0, 16.0, Vec2(4, 4), 4, spawn_t=(10, 16, 32)
    ),  # 6 (518 特判)
    BulletTypeSpec(0x207, 32.0, 32.0, Vec2(10, 10), 2, spawn_t=(32, 32, 32)),  # 7: 大弹
    BulletTypeSpec(
        0x208, 32.0, 32.0, Vec2(5, 5), 1, spawn_t=(32, 32, 32)
    ),  # 8: 刀弹(520 特判)
    BulletTypeSpec(
        0x209, 32.0, 32.0, Vec2(8, 8), 2, spawn_t=(32, 32, 32)
    ),  # 9: 札弹(521 特判)
    BulletTypeSpec(
        0x2A8, 8.0, 8.0, Vec2(4, 4), 5, spawn_t=(24, 24, 24)
    ),  # 10: 光弹(链式 chunk)
    # 11..15: TH07 未初始化(AddedCallback 只循环 i<11)
    BulletTypeSpec(0, 0.0, 0.0, Vec2(0, 0), 0),
    BulletTypeSpec(0, 0.0, 0.0, Vec2(0, 0), 0),
    BulletTypeSpec(0, 0.0, 0.0, Vec2(0, 0), 0),
    BulletTypeSpec(0, 0.0, 0.0, Vec2(0, 0), 0),
    BulletTypeSpec(0, 0.0, 0.0, Vec2(0, 0), 0),
)

_DEFAULT_BULLET_SIZE = Vec2(16, 16)


def bullet_type_size(bullet_type: int) -> Vec2:
    """弹型 → 精灵尺寸(出界/反弹判定用)。未知弹型给 16px 默认。"""
    if 0 <= bullet_type < len(BULLET_TYPE_SPECS):
        spec = BULLET_TYPE_SPECS[bullet_type]
        if spec.width > 0:
            return Vec2(spec.width, spec.height)
    return _DEFAULT_BULLET_SIZE


# 弹型模板的活动 sprite 基址 (etama.anm 全局 sprite 索引)。
# 提取口径: LoadAnms(11, "data/etama.anm", ANM_OFFSET_BULLETS=0x200) 链式加载,
# 每条脚本(0x200..0x209, 0x2a8)的首个 set-sprite + 链式偏移;
# C++ SpawnSingleBullet 的活动 sprite = 基址 + spriteOffset (直接相加, 无分辨率映射)。
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
    """活动 sprite 索引 (SpawnSingleBullet: template.activeSpriteIdx + spriteOffset)。"""
    if 0 <= sprite < len(_BULLET_BASE_SPRITE_IDX):
        return _BULLET_BASE_SPRITE_IDX[sprite] + sprite_offset
    return -1


def bullet_sprite_height(sprite: int, sprite_offset: int) -> float:
    """活动 sprite 的 heightPx —— ExIns 大弹判定(C++ spriteBullet.sprite->heightPx)。

    与 BULLET_TYPE_SPECS 的差异只在模板 10 (脚本 0x2a8): 其 offset 0..3 是
    64px 大玉(sprite 680-683), offset 4+ 是 16px(684-695); 其余模板的
    offset 变体同尺寸(实测 608-647 区间等宽等高)。
    """
    if sprite == 10:
        return 64.0 if 0 <= sprite_offset <= 3 else 16.0
    return bullet_type_size(sprite).y


# ---- 注册(导入本模块即登记 th07 数值表; touhou/__init__ 保证导入) ----
TH07_DATA = register_game_data(
    "th07",
    GameData(
        characters=CHARACTERS,
        difficulties=DIFFICULTIES,
        extra_stages=EXTRA_STAGES,
        stage_count=STAGE_COUNT,
        practice_difficulty_count=PRACTICE_DIFFICULTY_COUNT,
        character_sht=dict(CHARACTER_SHT),
        spellcard_scores=tuple(SPELLCARD_SCORE),
        bomb_params=dict(BOMB_PARAMS),
        drop_table=tuple(DROP_TABLE),
        power_levels=tuple(POWER_LEVELS),
        full_power=FULL_POWER,
        full_power_score_bonus=tuple(FULL_POWER_SCORE_BONUS),
    ),
)
# 框架默认作品(Game()/TouhouWorld() 不传 game= 的构造对象; 显式声明制,
# 见 registry.register_default_game)
register_default_game("th07")
