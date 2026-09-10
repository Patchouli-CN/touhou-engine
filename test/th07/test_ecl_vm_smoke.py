"""真 th07.dat 的 ECL 执行器冒烟(needs_data): ecldata1 时间轴 + 生敌脚本在 stub 宿主下跑通。"""

from __future__ import annotations

from touhou.engine.ecl import EclHost, EclMachine, TimelineRunner
from touhou.engine.ecl.state import EnemySpawn
from touhou.engine.rng import Rng
from touhou.games.th07.ecl_handlers import ECL_EXTRA_HANDLERS
from touhou.games.th07.ecl_table import parse_ecl
from touhou.games.th07.ecl_timeline import TL_HANDLERS
from touhou.schemas.archive import load_entry, open_archive
from touhou.schemas.ecl import EclFile, EclInstr

from .conftest import DATA, needs_data

pytestmark = needs_data

# 局部变量槽 id(变量表出处 EclManager.hpp:362-397; 槽位布局是作品数据,
# 这里是 stub 宿主的最小表, 正式表由 games/th07 组合根注入)
INT_VARS = frozenset(
    {10000, 10001, 10002, 10003, 10012, 10013, 10014, 10015, 10029, 10030, 10031, 10032}
)
FLOAT_VARS = frozenset(
    set(range(10004, 10012)) | {10033, 10034, 10035, 10036, 10072, 10073}
)

_FRAMES = 700


class StubHost(EclHost):
    """stub 宿主: spawn 成真起一台 EclMachine, 其余钩子只计数。"""

    def __init__(self, ecl_file: EclFile, rng: Rng) -> None:
        self.file = ecl_file
        self.rng = rng
        self.machines: list[EclMachine] = []
        self.spawns: list[tuple] = []
        self.enemy_configs: list[str] = []
        self.bullet_calls = 0

    def spawn_enemy(self, spawn: EnemySpawn, m: EclMachine | None) -> object | None:
        self.spawns.append(
            (
                spawn.sub_id,
                spawn.x,
                spawn.y,
                spawn.life,
                spawn.item_drop,
                spawn.score,
                spawn.mirror,
            )
        )
        mach = EclMachine(
            self.file,
            self,
            self.rng,
            int_var_ids=INT_VARS,
            float_var_ids=FLOAT_VARS,
            extra_handlers=ECL_EXTRA_HANDLERS,
        )
        mach.start(spawn.sub_id)
        mach.enemy.life = spawn.life if spawn.life > 0 else 1000
        self.machines.append(mach)
        return mach

    def enemy_config(self, m: EclMachine, instr: EclInstr) -> None:
        self.enemy_configs.append(type(instr).__name__)

    def spawn_bullets(self, m: EclMachine, instr: EclInstr) -> None:
        self.bullet_calls += 1


def run_stage(frames: int) -> StubHost:
    """ecldata1 时间轴 0 驱动 frames 帧(宿主即迷你敌机管理器)。"""
    arc = open_archive(DATA, format_name="pbg4")
    f = parse_ecl(load_entry(arc, "ecldata1.ecl"))
    host = StubHost(f, Rng(0))
    tl = TimelineRunner(f.timelines[0], host, host.rng, TL_HANDLERS)
    for _ in range(frames):
        tl.step()
        for mach in host.machines:
            mach.step()
        host.machines = [m for m in host.machines if not m.finished]
    return host


def test_timeline_spawn_sequence() -> None:
    """前 700 帧生敌回调序列与真机快照一致(10 架一面开幕妖精)。"""
    host = run_stage(_FRAMES)
    assert host.spawns == [
        (3, 334.0, -16.0, 10, -1, 500, 1),
        (3, 294.0, -16.0, 10, -1, 500, 1),
        (3, 344.0, -32.0, 10, -1, 500, 1),
        (3, 304.0, -32.0, 10, -1, 500, 1),
        (3, 354.0, -48.0, 10, -1, 500, 1),
        (3, 314.0, -48.0, 10, -1, 500, 1),
        (3, 334.0, -16.0, 10, -1, 500, 1),
        (3, 294.0, -16.0, 10, -1, 500, 1),
        (3, 344.0, -32.0, 10, -1, 500, 1),
        (3, 304.0, -32.0, 10, -1, 500, 1),
    ]


def test_spawned_machines_run() -> None:
    """生出的脚本实例全部存活推进: 位置随帧移动, 配置类回调有记录。"""
    host = run_stage(_FRAMES)
    assert len(host.machines) == 10
    assert all(m.enemy.timer > 0 for m in host.machines)
    assert all(m.enemy.pos.y > 0.0 for m in host.machines)  # 从屏顶飞进场内
    assert host.enemy_configs  # SetAnm 等敌人配置指令确实到达宿主
    assert len(set(host.enemy_configs)) > 1


def test_deterministic_replay() -> None:
    """同种子两遍跑, 生敌序列逐元组一致。"""
    assert run_stage(_FRAMES).spawns == run_stage(_FRAMES).spawns
