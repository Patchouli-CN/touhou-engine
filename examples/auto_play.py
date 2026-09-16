"""观战/AI 示例: headless 跑一局, 打印流式事件, 并用自定义策略开车。

运行: uv run python examples/auto_play.py

观战变体(窗口里看 AI 打): 去掉 headless=True 改为
``TouhouWorld(..., headless=False, auto_input=my_policy)`` 再 ``tw.run()``
—— 窗口照开但跳过标题菜单直接进游戏, 每帧输入来自策略, Esc 中止观战。
帧数用环境变量 AUTO_PLAY_FRAMES 覆盖(默认 3600 ≈ 1 分钟)。
"""

from __future__ import annotations

import os

from touhou import Game, Input, TouhouWorld


def my_policy(game: Game) -> Input:
    """每帧输入策略(AI 的入口)。这里演示: 按住射击 + 蛇皮走位。"""
    f = game.frame
    return Input(
        left=(f // 90) % 2 == 0,
        right=(f // 90) % 2 == 1,
        up=(f // 150) % 3 == 0,
        shoot=True,
        advance=True,  # 对话自动推进
        bomb=(f % 1800 == 0),  # 每 30 秒扔一发 bomb(壕)
    )


def main() -> None:
    frames = int(os.environ.get("AUTO_PLAY_FRAMES", "3600"))
    tw = TouhouWorld(difficulty="Normal", lives=3, headless=True, seed=42)
    stream = tw.stream(my_policy)
    for ev in stream:
        print(f"[f{ev.frame:6d}] {ev.kind} {ev.name or ''}")
        if tw.game.frame >= frames:
            break
    g = tw.game
    print(f"\nframe={g.frame} lives={g.lives} score={g.score} phase={g.phase.value}")


if __name__ == "__main__":
    main()
