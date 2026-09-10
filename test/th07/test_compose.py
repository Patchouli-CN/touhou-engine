"""th07 compose 冒烟: 装配能拼出, 名单/难度/路径正确, 归档能打开。"""

from __future__ import annotations

from touhou.engine import GameAssembly
from touhou.engine.ecl import EclMachine
from touhou.games import available_games
from touhou.games.th07 import compose
from touhou.games.th07.compose import DATA_PATH
from touhou.games.th07.ecl_handlers import ECL_EXTRA_HANDLERS
from touhou.games.th07.ecl_host import Th07EclHost
from touhou.games.th07.ecl_table import ECL_INSTR_SET
from touhou.games.th07.ecl_timeline import TL_HANDLERS
from touhou.games.th07.world import Th07World
from touhou.schemas.archive import open_archive

from .conftest import needs_data


def test_compose_produces_valid_assembly() -> None:
    """compose() 产出的装配通过自检, 世界/ECL 执行器/指令表全绑定。"""
    asm = compose()
    assert isinstance(asm, GameAssembly)
    assert asm.name == "th07"
    assert asm.world is Th07World
    assert asm.scripts.ecl_machine is EclMachine
    assert asm.scripts.ecl_host is Th07EclHost
    assert asm.scripts.ecl_instr_set is ECL_INSTR_SET
    assert asm.scripts.ecl_extra_handlers is ECL_EXTRA_HANDLERS
    assert asm.scripts.ecl_tl_handlers is TL_HANDLERS


def test_rosters_and_paths() -> None:
    """名单/难度/资源路径与命名规则正确。"""
    asm = compose()
    assert asm.data.characters == (
        "ReimuA",
        "ReimuB",
        "MarisaA",
        "MarisaB",
        "SakuyaA",
        "SakuyaB",
    )
    assert asm.data.difficulties == (
        "Easy",
        "Normal",
        "Hard",
        "Lunatic",
        "Extra",
        "Phantasm",
    )
    assert asm.data.extra_stages == ("Extra", "Phantasm")
    assert asm.data.stage_count == 6
    assert set(asm.data.character_sht) == set(range(6))
    assert len(asm.data.spellcard_scores) == 141
    res = asm.resources
    assert res.data_path == DATA_PATH
    assert res.archive_format == "pbg4"
    assert res.stage_file.format(n=1) == "stage1.std"
    assert res.ecl_file.format(n=1) == "ecldata1.ecl"
    assert res.msg_file.format(n=1) == "msg1.dat"


def test_available_games_lists_composed() -> None:
    """作品发现走显式 import: available_games 列出 th07。"""
    games = available_games()
    assert set(games) == {"th07"}
    assert games["th07"].name == "th07"


@needs_data
def test_data_archive_opens() -> None:
    """真实 th07.dat 按装配声明的格式打开, 目录非空。"""
    asm = compose()
    arc = open_archive(
        asm.resources.data_path, format_name=asm.resources.archive_format
    )
    assert arc.format_name == "pbg4"
    assert arc.entries
