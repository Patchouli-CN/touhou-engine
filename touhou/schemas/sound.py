"""SE 槽位表: 音效 idx → wav 文件名/音量。"""

from __future__ import annotations

import msgspec


class SoundEffect(msgspec.Struct, frozen=True):
    """一个 SE 槽: wav 文件名 + 音量(DirectSound 百分之一分贝, 0=满音量)。"""

    file_name: str
    volume: int


# g_SFXList[30] (Reference/th07/src/th07/SoundPlayer.cpp:14-77):
# 音效 buffer 索引 → wav 文件名
_SFX_LIST = (
    "se_plst00.wav",
    "se_enep00.wav",
    "se_pldead00.wav",
    "se_power0.wav",
    "se_power1.wav",
    "se_tan00.wav",
    "se_tan01.wav",
    "se_tan02.wav",
    "se_ok00.wav",
    "se_cancel00.wav",
    "se_select00.wav",
    "se_gun00.wav",
    "se_cat00.wav",
    "se_lazer00.wav",
    "se_lazer01.wav",
    "se_enep01.wav",
    "se_nep00.wav",
    "se_damage00.wav",
    "se_item00.wav",
    "se_kira00.wav",
    "se_kira01.wav",
    "se_kira02.wav",
    "se_extend.wav",
    "se_timeout.wav",
    "se_graze.wav",
    "se_powerup.wav",
    "se_border.wav",
    "se_bonus.wav",
    "se_bonus2.wav",
    "se_pause.wav",
)

# SOUND_BUFFER_IDX_VOL[38] (SoundPlayer.cpp:10-11): (bufferIdx, 音量/百分贝)
_BUFFER_IDX_VOL = (
    (0, -2000),
    (0, -2500),
    (1, -1200),
    (1, -1500),
    (2, -1000),
    (3, -400),
    (4, -400),
    (5, -1500),
    (6, -1700),
    (7, -1900),
    (8, -1000),
    (9, -1000),
    (10, -1700),
    (11, -1200),
    (12, -900),
    (5, -1500),
    (13, -900),
    (14, -900),
    (15, -900),
    (16, -200),
    (17, -1400),
    (18, -1300),
    (5, -100),
    (6, -1800),
    (7, -1800),
    (19, -800),
    (20, -1000),
    (21, -1300),
    (22, -300),
    (23, -900),
    (24, -900),
    (25, -500),
    (26, -300),
    (27, -300),
    (24, -300),
    (19, 0),
    (28, -300),
    (29, -300),
)

#: SE idx(PlaySoundByIdx 的 idx, SoundPlayer.hpp:20-45 SoundIdx 枚举序)
#: → SoundEffect; 下标即 C 枚举值
SOUND_EFFECTS: tuple[SoundEffect, ...] = tuple(
    SoundEffect(_SFX_LIST[buf], vol) for buf, vol in _BUFFER_IDX_VOL
)

__all__ = ["SOUND_EFFECTS", "SoundEffect"]
