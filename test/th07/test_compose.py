"""th07 compose 冒烟: 装配能拼出, 名单/难度/路径正确, 归档能打开。"""

from __future__ import annotations

import subprocess
import sys

import msgspec
import pytest

from touhou.engine import GameAssembly, SaveSemantics, World
from touhou.games import available_games
from touhou.games.th07 import compose
from touhou.games.th07.app import Th07App
from touhou.games.th07.compose import DATA_PATH
from touhou.games.th07.ecl_host import Th07EclHost
from touhou.games.th07.world import Th07World, compose_world
from touhou.schemas.archive import open_archive

from .conftest import needs_data


def test_compose_produces_valid_assembly() -> None:
    """compose() 产出的装配通过自检, 世界/ANM 版本/ECL 宿主全绑定。"""
    asm = compose()
    assert isinstance(asm, GameAssembly)
    assert asm.name == "th07"
    assert asm.world is Th07World
    assert asm.anm_version == 2
    assert asm.ecl_host is Th07EclHost
    assert asm.save == SaveSemantics(score_file="score.dat")


def test_app_decorator_registers_th07_window_app() -> None:
    """窗口 App 走装饰器登记: 装配取到 Th07App 类。"""
    assert compose().app is Th07App


def test_world_owns_assembly_contract() -> None:
    """装配契约在 world 类上: compose_world 薄入口经注册表登记的类开局。"""
    # 覆写了基类契约(不是继承的 NotImplementedError 版本)
    assert Th07World.compose.__func__ is not World.compose.__func__
    assert compose().world is Th07World


def test_compose_world_requires_registered_world() -> None:
    """未登记世界的装配开不了局(装配入口不再绕过注册表)。"""
    bare = msgspec.structs.replace(compose(), world=None)
    with pytest.raises(ValueError, match="未登记世界"):
        compose_world(bare, character=0)


#: 探针前导: 作品发现 + 注册表(不动渲染层)
_PROBE_PRELUDE = (
    "import sys\nimport touhou.games.th07\nfrom touhou.engine import TouhouRegistry\n"
)


def _run_probe(body: str) -> str:
    """在干净解释器里跑探针, 返回末行 stdout(pygame 会往 stdout 打横幅)。"""
    out = subprocess.run(
        [sys.executable, "-c", _PROBE_PRELUDE + body],
        capture_output=True,
        text=True,
        check=True,
    )
    return out.stdout.strip().splitlines()[-1]


def test_headless_assembly_does_not_pull_pygame() -> None:
    """作品发现 + 组装不碰渲染层: headless 路径下 pygame 不进 sys.modules。"""
    assert (
        _run_probe(
            "TouhouRegistry.create_game('th07')\nprint('pygame' in sys.modules)\n"
        )
        == "False"
    )


def test_window_shell_pulls_view_layer_on_use() -> None:
    """薄壳在真取用时才拉 view 层(那时 pygame 才到位)。"""
    body = (
        "from touhou.games.th07.app import _view\n"
        "_view()\n"
        "print('pygame' in sys.modules)\n"
    )
    assert _run_probe(body) == "True"


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
