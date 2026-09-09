"""架构守护测试: 函数内 import / 绝对自导入 / 分层方向 / 作品名泄漏。

守护范围是 touhou/ 包本体, test/ 豁免(测试夹具有意打破常规写法)。
"""

import ast
import re
from pathlib import Path

PKG = Path(__file__).resolve().parents[2] / "touhou"

# 分层方向(架构讨论稿 §1/§2): 只允许 games → apis → engine → {utils, schemas},
# schemas/utils 是叶子; 同层互导合法; 包根 __init__ 是公共门面, 不被下层引用。
ALLOWED = {
    "games": {"games", "apis", "engine", "utils", "schemas"},
    "apis": {"apis", "engine", "utils", "schemas"},
    "engine": {"engine", "utils", "schemas"},
    "utils": {"utils"},
    "schemas": {"schemas"},
}
# 框架层(作品名红线范围): 作品差异只能走 hook/注册表/子类多态, 不许按名分派。
FRAMEWORK = ("engine", "apis", "utils", "schemas")

_GAME_STR = re.compile(r"^th\d{2}$", re.IGNORECASE)  # 字符串全匹配
_GAME_IDENT = re.compile(r"^th\d{2}", re.IGNORECASE)  # 标识符前缀匹配


def _py_files() -> list[Path]:
    return sorted(f for f in PKG.rglob("*.py") if "__pycache__" not in f.parts)


def _layer_of(f: Path) -> str:
    rel = f.relative_to(PKG)
    return rel.parts[0] if len(rel.parts) > 1 else "root"


def _resolve_relative(f: Path, node: ast.ImportFrom) -> str:
    """把相对 import 解析成包内分层名(越出包根的相对导入返回 root)。"""
    here = f.relative_to(PKG).parent.parts  # 文件所在包的层级
    kept = here[: max(0, len(here) - (node.level - 1))]
    parts = [*kept, *((node.module or "").split("."))]
    return parts[0] if parts else "root"


def test_no_function_level_imports() -> None:
    """函数/方法体内禁 import: 导入一律在模块顶部。"""
    offenders = []
    for f in _py_files():
        tree = ast.parse(f.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                offenders += [
                    f"{f.relative_to(PKG)}:{sub.lineno}"
                    for sub in ast.walk(node)
                    if isinstance(sub, (ast.Import, ast.ImportFrom))
                ]
    assert not offenders, offenders


def test_no_absolute_self_import() -> None:
    """包内禁绝对自导入(import touhou.../from touhou...), 一律相对导入。"""
    offenders = []
    for f in _py_files():
        tree = ast.parse(f.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                hit = any(
                    a.name == "touhou" or a.name.startswith("touhou.")
                    for a in node.names
                )
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                mod = node.module or ""
                hit = mod == "touhou" or mod.startswith("touhou.")
            else:
                continue
            if hit:
                offenders.append(f"{f.relative_to(PKG)}:{node.lineno}")
    assert not offenders, offenders


def test_layer_import_direction() -> None:
    """分层方向 games → apis → engine → {utils, schemas}。

    下层禁 import 上层, 叶子(schemas/utils)禁出层, 下层禁回头引用包根门面。
    """
    offenders = []
    for f in _py_files():
        src = _layer_of(f)
        if src == "root":
            continue  # 包根是门面, 可导出任意层
        tree = ast.parse(f.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            # 绝对自导入已被上一条守护禁掉, 这里只看相对导入
            if not (isinstance(node, ast.ImportFrom) and node.level >= 1):
                continue
            tgt = _resolve_relative(f, node)
            if tgt == "root" or tgt not in ALLOWED[src]:
                offenders.append(f"{f.relative_to(PKG)}:{node.lineno} {src} -> {tgt}")
    assert not offenders, offenders


def test_framework_has_no_game_names() -> None:
    """框架层(engine/apis/utils/schemas)可执行代码禁作品名(thNN, 大小写不敏感)。

    注释/docstring 提及不算; 规则:
    - R1 禁作品名比较分支(``if game == "th08"`` 之类按名分派)。
    - R2 禁作品名前缀标识符(Th08Xxx 类 / th08_foo 函数·参数·属性)。
    - R3 禁作品名字符串字面量; 唯一豁免是 register_* 注册调用的直接参数
      (注册表就是作品名与实现的绑定地)。
    """
    offenders = []
    for sub in FRAMEWORK:
        for f in sorted((PKG / sub).rglob("*.py")):
            if "__pycache__" in f.parts:
                continue
            tree = ast.parse(f.read_text(encoding="utf-8"))
            # R3 豁免区: register_* 调用/装饰器的直接常量参数
            exempt = set()
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                func = node.func
                fname = (
                    func.id
                    if isinstance(func, ast.Name)
                    else func.attr
                    if isinstance(func, ast.Attribute)
                    else ""
                )
                if fname.startswith("register_"):
                    exempt.update(
                        id(a)
                        for a in (*node.args, *(kw.value for kw in node.keywords))
                        if isinstance(a, ast.Constant)
                    )
            for node in ast.walk(tree):
                loc = f"{f.relative_to(PKG)}:{getattr(node, 'lineno', 0)}"
                if isinstance(node, ast.Compare):
                    for c in (node.left, *node.comparators):
                        if (
                            isinstance(c, ast.Constant)
                            and isinstance(c.value, str)
                            and _GAME_STR.match(c.value)
                        ):
                            offenders.append(f"R1 比较分支 {loc} == {c.value!r}")
                elif isinstance(
                    node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
                ):
                    if _GAME_IDENT.match(node.name):
                        offenders.append(f"R2 定义名 {loc} {node.name}")
                elif isinstance(node, ast.arg) and _GAME_IDENT.match(node.arg):
                    offenders.append(f"R2 参数名 {loc} {node.arg}")
                elif isinstance(node, ast.Attribute) and _GAME_IDENT.match(node.attr):
                    offenders.append(f"R2 属性名 {loc} .{node.attr}")
                elif (
                    isinstance(node, ast.Constant)
                    and isinstance(node.value, str)
                    and _GAME_STR.match(node.value)
                    and id(node) not in exempt
                ):
                    offenders.append(f"R3 字符串 {loc} {node.value!r}")
    assert not offenders, offenders
