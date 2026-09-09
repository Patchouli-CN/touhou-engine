"""musiccmt.txt 解析: Music Room 曲目名与评论。"""

from __future__ import annotations

import msgspec

# 解析语义出处 old/touhou/schema/musiccmt.py(Reference/th07/src/th07/
# MusicRoom.cpp:233-383 AddedCallback): 首个 '@' 前内容忽略; 块 = '@' 路径行
# → 曲名行 → 评论行(≤8, 空行跳过); 播放路径即 '@' 行原文
MAX_COMMENT_LINES = 8  # TrackDescriptor.description[8]


class TrackDescriptor(msgspec.Struct, frozen=True):
    """Music Room 一首曲目。"""

    path: str  # '@' 行原文, 形如 "bgm/<作品>_<编号>.mid"
    title: str
    comment: tuple[str, ...] = msgspec.field(default_factory=tuple)

    @property
    def file_name(self) -> str:
        """播放用文件名(去目录前缀)。"""
        return self.path.replace("\\", "/").split("/")[-1]


def parse_musiccmt(data: bytes) -> list[TrackDescriptor]:
    """解析 musiccmt.txt 字节流(Shift-JIS), 返回曲目表(文件序)。"""
    text = data.decode("shift_jis", errors="replace")
    tracks: list[TrackDescriptor] = []
    path: str | None = None
    title: str | None = None
    comment: list[str] = []

    def flush() -> None:
        nonlocal path, title, comment
        if path is not None:
            tracks.append(TrackDescriptor(path, title or "", tuple(comment)))
        path = title = None
        comment = []

    for line in text.splitlines():
        if line.startswith("@"):
            flush()
            path = line[1:].strip()
        elif path is None:
            continue  # 首个 '@' 前的占位内容
        elif title is None:
            title = line.strip()
        elif len(comment) < MAX_COMMENT_LINES:
            line = line.strip()
            if line:  # 空行只是块间分隔, 不入评论
                comment.append(line)
    flush()
    return tracks
