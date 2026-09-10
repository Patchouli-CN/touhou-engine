"""th07 专属 fixture/标记 —— test/th07/ 子树共享。"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

# view 层 headless 测试: pygame 导入前钉死 dummy 驱动(有显示环境想真跑时
# 在 shell 里显式覆盖即可, setdefault 不抢)
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

#: 真实游戏数据路径(仅本机)
DATA = Path(r"D:\TOUHOU_GAME\[th07] 东方妖妖梦 (日文版)\th07.dat")

#: 需要真实 th07.dat 的用例统一打这个标记(资源缺失环境自动 skip)
needs_data = pytest.mark.skipif(not DATA.exists(), reason="需要真实 th07.dat")
