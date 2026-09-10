"""th07 配置持久化: th07.cfg(GameConfiguration)的 JSON 简化版。

字段取 C++ cfg 与菜单/读档校验相关的子集(Supervisor.hpp:75-115);
默认值照无 cfg 文件时的初始化(Supervisor.cpp:1170-1202);
读档任一字段越界/缺字段/版本不对整组回退默认(Supervisor.cpp:1221-1236)。
落盘时机同原版: 应用退出时写(main.cpp:188)。
"""

from __future__ import annotations

from pathlib import Path

import msgspec

#: cfg.version 期望值(Supervisor.cpp:1174)
CONFIG_VERSION = 0x70002

# BGM 模式(Supervisor.hpp:33-36)
MUSIC_OFF = 0
MUSIC_WAV = 1
MUSIC_MIDI = 2

#: 读档校验范围(Supervisor.cpp:1221-1233); 值 = (字段名, 上限(不含))
_VALIDATED = (
    ("life_count", 5),
    ("bomb_count", 4),
    ("color_mode16bit", 2),
    ("music_mode", 3),
    ("default_difficulty", 6),
    ("play_sounds", 2),
    ("windowed", 2),
    ("frameskip_config", 3),
    ("effect_quality", 3),
    ("slow_mode", 2),
    ("shot_slow", 2),
)


class Th07Config(msgspec.Struct):
    """th07 运行配置(C++ GameConfiguration 子集, 值为各选项的档位下标)。"""

    version: int = CONFIG_VERSION
    life_count: int = 2  # 初始残机 0..4 ↔ 1~5 人(初期設定３, Supervisor.cpp:1171)
    bomb_count: int = 3
    color_mode16bit: int = (
        0  # C++ 缺省 255=自动且渲染固定 32bit, 落 32bit 档(GameWindow.cpp:347)
    )
    music_mode: int = MUSIC_WAV  # C++ 无 thbgm.dat 回退 MIDI(Supervisor.cpp:1188-1193)
    play_sounds: int = 1
    default_difficulty: int = 1  # DIFF_NORMAL(Supervisor.cpp:1196)
    windowed: int = 0
    frameskip_config: int = 0  # 描画间隔 0..2
    effect_quality: int = 2  # QUALITY_BEAUTIFUL(Supervisor.hpp:52-54)
    slow_mode: int = 0
    shot_slow: int = 1


def load_config(path: str | Path) -> Th07Config:
    """读配置; 文件缺失/损坏/字段越界一律回退默认值(不抛异常)。"""
    try:
        data = msgspec.json.decode(Path(path).read_bytes())
    except (OSError, ValueError):
        return Th07Config()
    if not isinstance(data, dict):
        return Th07Config()
    if data.get("version") != CONFIG_VERSION:
        return Th07Config()
    values = {}
    for field, limit in _VALIDATED:
        v = data.get(field)
        if not isinstance(v, int) or isinstance(v, bool) or not 0 <= v < limit:
            return Th07Config()  # 任一项越界整组初始化(:1221-1236 goto init)
        values[field] = v
    return Th07Config(**values)


def save_config(config: Th07Config, path: str | Path) -> None:
    """原子落盘(与 score_store 同款的 tmp + replace)。"""
    path = Path(path)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(msgspec.json.format(msgspec.json.encode(config), indent=1))
    tmp.replace(path)
