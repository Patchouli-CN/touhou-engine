"""作品解析: 注册表取装配(默认作品/资源路径覆盖) + 名单名 → 内部 id 映射。"""

from __future__ import annotations

import msgspec

from ..engine import GameAssembly, TouhouRegistry


def _resolve_assembly(game: str | None, data_path: str | None) -> GameAssembly:
    """按作品名取装配(None = 默认作品); data_path 覆盖注册的资源包路径。"""
    name = game if game is not None else TouhouRegistry.default_game()
    assembly = TouhouRegistry.create_game(name)
    if data_path is not None:
        res = msgspec.structs.replace(assembly.resources, data_path=str(data_path))
        assembly = msgspec.structs.replace(assembly, resources=res)
    return assembly


def _resolve_ids(
    assembly: GameAssembly, character: str | int | None, difficulty: str | int | None
) -> tuple[int, int]:
    """角色/难度名 → 内部 int id(名单下标; 大小写不敏感; None = 首机体/次难度)。

    int 入参直接透传并校验下标域; str 入参不在名单报 ValueError。
    """
    data = assembly.data
    ci_characters = {c.casefold(): i for i, c in enumerate(data.characters)}
    ci_difficulties = {d.casefold(): i for i, d in enumerate(data.difficulties)}

    def resolve(value: str | int | None, ci: dict[str, int], default: int) -> int:
        if value is None:
            return default if default < len(ci) else 0
        if isinstance(value, str):
            if value.casefold() not in ci:
                raise ValueError(
                    f"{assembly.name} 不支持 {value!r}，可选: "
                    f"{list(data.characters if ci is ci_characters else data.difficulties)}"
                )
            return ci[value.casefold()]
        if not 0 <= value < len(ci):
            raise ValueError(f"{assembly.name} 下标 {value} 越界(0..{len(ci) - 1})")
        return value

    # 难度缺省取下标 1(Normal 位; 单难度作品回落 0)
    return (
        resolve(character, ci_characters, 0),
        resolve(difficulty, ci_difficulties, 1),
    )
