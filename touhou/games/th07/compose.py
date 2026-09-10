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
from ...engine.ecl import EclMachine
from ...engine.msg import MsgExecutor
from . import data
from .ecl_handlers import ECL_EXTRA_HANDLERS
from .ecl_host import Th07EclHost
from .ecl_table import ECL_INSTR_SET
from .ecl_timeline import TL_HANDLERS
from .world import Th07World

#: 本机真实数据包路径(needs_data 测试与此同源)
DATA_PATH = r"D:\TOUHOU_GAME\[th07] 东方妖妖梦 (日文版)\th07.dat"

#: 作品标题, 出处 old/touhou/registry.py GAME_TITLES
TITLE = "東方妖々夢 〜 Perfect Cherry Blossom"


def compose(data_path: str = DATA_PATH) -> GameAssembly:
    """拼出 th07 的可运行装配(世界/ECL/MSG 执行器/指令表全绑定; 渲染留待)。"""
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
        scripts=ScriptSet(
            anm_version=2,
            ecl_machine=EclMachine,
            ecl_host=Th07EclHost,
            msg_executor=MsgExecutor,
            ecl_instr_set=ECL_INSTR_SET,
            ecl_extra_handlers=ECL_EXTRA_HANDLERS,
            ecl_tl_handlers=TL_HANDLERS,
        ),
        save=SaveSemantics(score_file="score.dat"),
        world=Th07World,
    )
    check_assembly(assembly)
    return assembly
