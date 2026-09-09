"""th07 组合根: compose() 一个函数拼出完整作品装配。"""

from __future__ import annotations

from ...engine import (
    GameAssembly,
    GameData,
    ResourcePaths,
    SaveSemantics,
    ScriptSet,
    check_assembly,
)
from . import data

#: 本机真实数据包路径(needs_data 测试与此同源)
DATA_PATH = r"D:\TOUHOU_GAME\[th07] 东方妖妖梦 (日文版)\th07.dat"

#: 作品标题, 出处 old/touhou/registry.py GAME_TITLES
TITLE = "東方妖々夢 〜 Perfect Cherry Blossom"


def compose(data_path: str = DATA_PATH) -> GameAssembly:
    """拼出 th07 的可运行装配; VM 执行器/模拟件未平移, 对应字段 None 占位。"""
    assembly = GameAssembly(
        name="th07",
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
            data_path=data_path,
            archive_format="pbg4",
            stage_file="stage{n}.std",
            ecl_file="ecldata{n}.ecl",
            msg_file="msg{n}.dat",
            bgm_file="thbgm.dat",
        ),
        scripts=ScriptSet(anm_version=2),
        save=SaveSemantics(score_file="score.dat"),
    )
    check_assembly(assembly)
    return assembly
