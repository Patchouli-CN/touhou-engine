"""真 th07.dat 驱动 AnmMachine 的行为测试(needs_data, 仅本地跑)。"""

from __future__ import annotations

import pytest

from touhou.engine.anm import AnmBank, AnmMachine, build_bank
from touhou.engine.rng import Rng
from touhou.schemas.anm import parse_anm
from touhou.schemas.archive import load_entry, open_archive

from .conftest import DATA, needs_data

pytestmark = needs_data


@pytest.fixture(scope="module")
def archive():
    return open_archive(DATA, format_name="pbg4")


def _bank(archive, name: str) -> AnmBank:
    return build_bank(
        parse_anm(load_entry(archive, name), version=2), flat_layout=False
    )


def _run_frames(bank: AnmBank, key: int, frames: int) -> AnmMachine:
    vm = AnmMachine(Rng(0))
    vm.start(bank.scripts[key])
    for _ in range(frames - 1):
        vm.execute()
    return vm


def test_player_idle_script_sways(archive) -> None:
    """自机静止脚本(局部 0): sprite 在若干帧内慢摇, 循环不结束。"""
    bank = _bank(archive, "player00.anm")
    vm = AnmMachine(Rng(0))
    vm.start(bank.scripts[0])
    seen = {vm.active_sprite_idx}
    for _ in range(300):
        vm.execute()
        seen.add(vm.active_sprite_idx)
    assert len(seen) > 1
    assert vm.alive


def test_enemy_animation_frames_advance(archive) -> None:
    """stg1enm 妖精脚本(局部 0/5/10): 逐帧执行 sprite 会切换, 脚本循环不结束。"""
    bank = _bank(archive, "stg1enm.anm")
    animated = 0
    for key in (0, 5, 10):
        vm = AnmMachine(Rng(0))
        vm.start(bank.scripts[key])
        seen = {vm.active_sprite_idx}
        for _ in range(180):
            vm.execute()
            seen.add(vm.active_sprite_idx)
        if len(seen) > 1:
            animated += 1
        assert vm.alive  # 敌动画是循环脚本
    assert animated >= 2


def test_hit_flash_script_is_additive(archive) -> None:
    """自机弹命中脚本(局部 96): 加算 + 淡出, 120 帧内结束。"""
    bank = _bank(archive, "player00.anm")
    vm = _run_frames(bank, 96, 1)
    assert vm.blend_mode == 1
    assert vm.color[3] < 255  # SET_ALPHA 96
    frames = 0
    while vm.alive and frames < 120:
        vm.execute()
        frames += 1
    assert not vm.alive  # FADE 到 0 后 EXIT_HIDE


def test_all_scripts_run_without_error(archive) -> None:
    """三个常用文件的每段脚本跑 60 帧不炸(handler 覆盖的事实核查)。"""
    for name in ("player00.anm", "stg1enm.anm", "etama.anm"):
        bank = _bank(archive, name)
        assert bank.scripts, name
        assert bank.sprites, name
        for key in bank.scripts:
            vm = _run_frames(bank, key, 60)
            assert vm.active_sprite_idx < 0 or vm.active_sprite_idx in bank.sprites
