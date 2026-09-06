"""src/ai/memory must stay game-free: no domain/application/infrastructure imports."""

import ast
from pathlib import Path

_PACKAGE = Path(__file__).resolve().parents[3] / "src" / "ai" / "memory"
_FORBIDDEN_ROOTS = {"domain", "application", "interfaces", "infrastructure"}


def _imported_roots(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            roots.add(node.module.split(".")[0])
    return roots


def test_memory_package_imports_only_ai_and_stdlib() -> None:
    offenders = {
        f"{path.name}: {sorted(roots & _FORBIDDEN_ROOTS)}"
        for path in _PACKAGE.glob("*.py")
        if (roots := _imported_roots(path)) & _FORBIDDEN_ROOTS
    }
    assert offenders == set()
