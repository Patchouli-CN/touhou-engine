"""命令行入口: ``python -m touhou --game <作品名>`` 开窗口打一局。

作品分发走 importlib 动态 import(包根不出现作品名, 分层红线);
约定作品包提供 ``games/<名>/compose.py: compose`` 与 ``games/<名>/view/app.py: run_game``。
"""

from __future__ import annotations

import argparse
import importlib


def main() -> None:
    parser = argparse.ArgumentParser(prog="touhou")
    parser.add_argument("--game", required=True, help="作品目录名(如 games/ 下的包名)")
    parser.add_argument("--character", type=int, default=0)
    parser.add_argument("--difficulty", type=int, default=1)
    parser.add_argument("--stage", type=int, default=1)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--scale", type=int, default=1)
    args = parser.parse_args()
    compose = importlib.import_module(
        f".games.{args.game}.compose", __package__
    ).compose
    app = importlib.import_module(f".games.{args.game}.view.app", __package__)
    app.run_game(
        compose(),
        character=args.character,
        difficulty=args.difficulty,
        stage_no=args.stage,
        seed=args.seed,
        scale=args.scale,
    )


if __name__ == "__main__":
    main()
