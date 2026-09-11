"""th07 组合根: import 即向 TouhouRegistry 登记装配件, compose() 为兼容薄入口。"""

from __future__ import annotations

from ...engine import GameAssembly, GameData, ResourcePaths, SaveSemantics
from ...engine.registry import TouhouRegistry
from . import app as app  # 装饰器登记需要(@TouhouRegistry.app 挂在 Th07App)
from . import data
from . import ecl_host as ecl_host  # 装饰器登记需要(@ecl_host 挂在 Th07EclHost)
from . import world as world  # 装饰器登记需要(@TouhouRegistry.world 挂在 Th07World)

#: 本机真实数据包路径(needs_data 测试与此同源)
DATA_PATH = r"D:\TOUHOU_GAME\[th07] 东方妖妖梦 (日文版)\th07.dat"

#: 作品标题, 出处 old/touhou/registry.py GAME_TITLES
TITLE = "東方妖々夢 〜 Perfect Cherry Blossom"

TouhouRegistry.register(
    "th07",
    title=TITLE,
    data=GameData(
        characters=data.CHARACTERS,
        difficulties=data.DIFFICULTIES,
        extra_stages=data.EXTRA_STAGES,
        stage_count=data.STAGE_COUNT,
        practice_difficulty_count=data.PRACTICE_DIFFICULTY_COUNT,
        character_sht=dict(data.CHARACTER_SHT),
        spellcard_scores=data.SPELLCARD_SCORE,
        bomb_params=dict(data.BOMB_PARAMS),
        drop_table=data.DROP_TABLE,
        power_levels=data.POWER_LEVELS,
        full_power=data.FULL_POWER,
        full_power_score_bonus=data.FULL_POWER_SCORE_BONUS,
    ),
    resources=ResourcePaths(
        data_path=DATA_PATH,
        archive_format="pbg4",
        stage_file="stage{n}.std",
        ecl_file="ecldata{n}.ecl",
        msg_file="msg{n}.dat",
        bgm_file="thbgm.dat",
    ),
    anm_version=2,
    save=SaveSemantics(score_file="score.dat"),
)


def compose() -> GameAssembly:
    """拼出 th07 的可运行装配(登记在 import 时发生, 组装在注册表)。"""
    return TouhouRegistry.create_game("th07")
