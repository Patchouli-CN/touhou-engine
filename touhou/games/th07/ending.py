"""th07 的结局文件选择与装载(资源缺失时退化为通用通关画面)。

结局文件命名是本作约定 (Ending.cpp g_BadEndingPaths/g_NormalEndingPaths);
staff roll 由结局文件末尾的 @F 自动衔接, 播放状态机在 engine.ending。
"""

from __future__ import annotations

from ...schemas.archive import Archive, load_entry
from ...schemas.ending import End, EndingFile, EndingSegment, Text, Wait, parse_end


def ending_path(character: int, *, bad: bool) -> str:
    """结局文件名 (Ending.cpp:499-505): bad 结局按自机(//2)共用一份。"""
    if bad:
        return f"end{character // 2}0b.end"
    return f"end{character // 2}{character % 2}.end"


def load_ending(archive: Archive, character: int, *, bad: bool) -> EndingFile:
    """按机体/好坏装载结局脚本; 资源缺失抛 KeyError(调用方退化处理)。"""
    return parse_end(load_entry(archive, ending_path(character, bad=bad)))


def generic_ending() -> EndingFile:
    """结局资源缺失时的通用通关画面(简化兜底, 出处 old EndingData.generic)。"""
    return EndingFile(
        ops=(
            Wait(60, 60),
            Text("ALL CLEAR!!"),
            Text("感谢游玩！"),
            Wait(600, 60),
            End(),
        ),
        segments=(EndingSegment(None, ("ALL CLEAR!!", "感谢游玩！")),),
    )
