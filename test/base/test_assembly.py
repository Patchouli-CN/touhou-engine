"""组合根契约测试: GameAssembly 形状 + check_assembly 自检。"""

from __future__ import annotations

import msgspec
import pytest

from touhou.engine import (
    GameAssembly,
    GameData,
    ResourcePaths,
    SaveSemantics,
    ScriptSet,
    check_assembly,
)


def _asm(**overrides) -> GameAssembly:
    kwargs = {
        "name": "testgame",
        "title": "Test Game",
        "data": GameData(
            characters=("A", "B"),
            difficulties=("Easy", "Normal"),
            character_sht={0: ("a.sht", "as.sht"), 1: ("b.sht", "bs.sht")},
        ),
        "resources": ResourcePaths(
            data_path="/x/test.dat",
            archive_format="pbg4",
            stage_file="stage{n}.std",
            ecl_file="ecldata{n}.ecl",
            msg_file="msg{n}.dat",
        ),
        "scripts": ScriptSet(anm_version=2),
    }
    kwargs.update(overrides)
    return GameAssembly(**kwargs)


def test_assembly_is_frozen_struct() -> None:
    """装配是 msgspec 值对象: 字段不可改, 相等按值。"""
    a, b = _asm(), _asm()
    assert isinstance(a, msgspec.Struct)
    assert a == b
    with pytest.raises(AttributeError):
        a.name = "other"  # type: ignore[misc]


def test_executor_fields_default_none() -> None:
    """VM 执行器/模拟件平移前允许 None 占位, 但字段形状在契约里。"""
    asm = _asm()
    assert asm.scripts.ecl_machine is None
    assert asm.scripts.ecl_host is None
    assert asm.scripts.msg_executor is None
    assert asm.world is None
    assert asm.app is None
    assert asm.mods is None
    assert asm.save == SaveSemantics()


def test_check_assembly_accepts_valid() -> None:
    check_assembly(_asm())


def test_check_assembly_rejects_empty_rosters() -> None:
    """机体/难度名单为空 fail fast。"""
    with pytest.raises(ValueError, match="机体名单为空"):
        check_assembly(_asm(data=GameData(characters=(), difficulties=("Easy",))))
    with pytest.raises(ValueError, match="难度名单为空"):
        check_assembly(_asm(data=GameData(characters=("A",), difficulties=())))


def test_check_assembly_rejects_sht_misalignment() -> None:
    """Sht 映射键必须覆盖全部机体下标(下标语义 = shotType)。"""
    bad = GameData(
        characters=("A", "B"),
        difficulties=("Easy",),
        character_sht={0: ("a.sht", "as.sht")},
    )
    with pytest.raises(ValueError, match="不对齐"):
        check_assembly(_asm(data=bad))
