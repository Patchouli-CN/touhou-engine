"""命令行入口: ``python -m touhou --game <作品名>`` 开窗口进标题画面。

作品发现走 ``touhou/games`` 的显式清单(import 即触发向 TouhouRegistry 登记);
装配体与窗口层一律从注册表取, 入口不认任何作品目录布局。
"""

from __future__ import annotations

import argparse

from . import games as games  # 作品发现清单: import 即触发登记
from .engine.registry import TouhouRegistry


def main() -> None:
    parser = argparse.ArgumentParser(prog="touhou")
    parser.add_argument("--game", required=True, help="作品名(如 th07)")
    parser.add_argument(
        "--direct", action="store_true", help="跳过标题直进一局(调试入口)"
    )
    parser.add_argument("--character", type=int, default=0)
    parser.add_argument("--difficulty", type=int, default=1)
    parser.add_argument("--stage", type=int, default=1)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument(
        "--scale", type=int, default=None, help="窗口缩放倍率(缺省用后端的默认)"
    )
    args = parser.parse_args()
    assembly = TouhouRegistry.create_game(args.game)
    app_cls = assembly.app
    if app_cls is None:
        raise SystemExit(f"作品 {args.game!r} 未登记窗口层, 只能 headless 运行")
    app = app_cls()
    if args.direct:
        app.run_game(
            assembly,
            character=args.character,
            difficulty=args.difficulty,
            stage_no=args.stage,
            seed=args.seed,
            scale=args.scale,
        )
    else:
        app.run_app(assembly, seed=args.seed, scale=args.scale)


if __name__ == "__main__":
    main()
