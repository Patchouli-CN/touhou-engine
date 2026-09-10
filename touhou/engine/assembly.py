"""组合根契约: 一部作品的可运行装配描述(GameAssembly)与装配自检。"""

from __future__ import annotations

import msgspec

from ..schemas.ecl.decode import InstrSet
from .core import World


class GameData(msgspec.Struct, frozen=True):
    """作品数值表/名单, 名单下标语义 = shotType/difficulty。"""

    characters: tuple[str, ...]  # 机体名单
    difficulties: tuple[str, ...]  # 难度名单
    extra_stages: tuple[str, ...] = ()  # Extra Start 后的关卡名单
    stage_count: int = 6  # 本篇面数(practice 选关上限)
    practice_difficulty_count: int = 4  # practice 可选难度数
    character_sht: dict[int, tuple[str, str]] = msgspec.field(
        default_factory=dict
    )  # 机体 → (非 focus, focus) .sht 文件
    spellcard_scores: tuple[int, ...] = ()  # 符卡基础分值(代码值)
    bomb_params: dict[tuple[int, bool], tuple[int, int, int, float]] = msgspec.field(
        default_factory=dict
    )  # (机体, focus) → 炸弹参数原始行
    drop_table: tuple[int, ...] = ()  # 小怪随机掉落表
    power_levels: tuple[int, ...] = ()  # 火力档位阈值
    full_power: int = 128  # 满火力值
    full_power_score_bonus: tuple[int, ...] = ()  # 满火力后小 P 递增分表


class ResourcePaths(msgspec.Struct, frozen=True):
    """作品资源定位: 数据包路径/容器格式 + 关卡文件命名规则。"""

    data_path: str  # 主数据包(.dat)路径
    archive_format: str  # 容器格式名(schemas.archive 已知格式)
    stage_file: str  # 关卡背景/几何文件命名({n} = 关号)
    ecl_file: str  # 关卡 ECL 脚本文件命名
    msg_file: str  # 关卡对话文件命名
    bgm_file: str | None = None  # 高音质 BGM 包名(与 data_path 同目录)


class ScriptSet(msgspec.Struct, frozen=True):
    """ECL/ANM/MSG 指令集与执行器宿主; 作品在 compose 绑定指令表/handler。"""

    anm_version: int  # ANM entry 头版本号(作品差异显式传入, 架构稿 §2.6)
    anm_flat_layout: bool = False  # ANM 脚本表键布局(parse_anm 的 flat_layout)
    ecl_machine: type | None = None  # ECL 虚拟机实现类
    ecl_host: type | None = None  # ECL 宿主回调实现类
    msg_executor: type | None = None  # MSG 对话执行器类
    ecl_instr_set: InstrSet | None = None  # 作品 ECL 指令表(含符卡定制钩子)
    # 作品专属指令类 → handler(EclMachine 的 extra_handlers 注入)
    ecl_extra_handlers: dict | None = None
    # 时间轴指令类 → handler(TimelineRunner 的 handlers 注入)
    ecl_tl_handlers: dict | None = None


class SaveSemantics(msgspec.Struct, frozen=True):
    """存档语义: 分数文件名; 存档结构本体平移是后续单。"""

    score_file: str = "score.dat"


class GameAssembly(msgspec.Struct, frozen=True):
    """一部作品的可运行装配: compose() 的产出, 全维度数据化、无注册表。"""

    name: str  # 作品名
    title: str  # 作品标题
    data: GameData  # 数值表/名单
    resources: ResourcePaths  # 资源路径与命名规则
    scripts: ScriptSet  # 指令集与执行器宿主
    save: SaveSemantics = msgspec.field(default_factory=SaveSemantics)
    world: type[World] | None = None  # 对局实现类(None = 对局未接入, 只能跑脚本层)
    app: type | None = None  # 窗口 App 类(None = 只能 headless)
    mods: type | None = None  # mod 能力提供者类


def check_assembly(assembly: GameAssembly) -> None:
    """装配自检: 名单非空且机体下标与 sht 映射对齐, 不符抛 ValueError。"""
    data = assembly.data
    if not data.characters:
        raise ValueError(f"{assembly.name}: 机体名单为空")
    if not data.difficulties:
        raise ValueError(f"{assembly.name}: 难度名单为空")
    if set(data.character_sht) != set(range(len(data.characters))):
        raise ValueError(
            f"{assembly.name}: character_sht 键 {sorted(data.character_sht)} "
            f"与机体数 {len(data.characters)} 不对齐"
        )
