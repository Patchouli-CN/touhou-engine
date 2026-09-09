"""th08 专属 fixture/标记 —— test/th08/ 子树共享。"""

from __future__ import annotations

from pathlib import Path

import pytest

#: 真实游戏数据路径(仅本机)
DATA = Path(r"D:\TOUHOU_GAME\[th08] 东方永夜抄 (日文版)\th08.dat")

#: 需要真实 th08.dat 的用例统一打这个标记(资源缺失环境自动 skip)
needs_data = pytest.mark.skipif(not DATA.exists(), reason="需要真实 th08.dat")
