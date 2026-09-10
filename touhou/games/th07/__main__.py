"""``python -m touhou.games.th07``: 标题画面进 th07。"""

from .compose import compose
from .view.app import run_app

if __name__ == "__main__":
    run_app(compose())
