"""Purity test: src/ai/agents stays game-free (spec decision 3, CLAUDE.md §7)."""

import ast
from pathlib import Path

_PACKAGE = Path(__file__).resolve().parents[3] / "src" / "ai" / "agents"
_FORBIDDEN_ROOTS = {"domain", "application", "interfaces", "infrastructure"}


def test_ai_agents_package_never_imports_game_layers() -> None:
    offenders: list[str] = []
    for path in sorted(_PACKAGE.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                continue
            for name in names:
                if name.split(".")[0] in _FORBIDDEN_ROOTS:
                    offenders.append(f"{path.name}: {name}")
    assert offenders == []
