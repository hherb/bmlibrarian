"""Guard: Flet stays retired.

Dependabot's oauthlib 4.0 bump pulled flet 1.0, whose API changes broke every
GUI that imported it, and the Flet GUI was then retired (October 2026). These
tests keep it from coming back unnoticed:

- no source file imports ``flet``, and no ``bmlibrarian.*`` import points at a
  module that no longer exists (lazily imported modules would otherwise only
  fail when a user opens that tool);
- every ``bmlibrarian.gui`` and ``bmlibrarian.lab`` module imports in a fresh
  interpreter with ``flet`` blocked;
- ``flet`` is not a project dependency.
"""

import ast
import os
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Iterator, List, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_ROOT = REPO_ROOT / "src"
# Source trees scanned for imports (tests/ is skipped: it may name flet in
# guards like this one)
SCANNED_DIRS = (SRC_ROOT / "bmlibrarian", REPO_ROOT / "scripts", REPO_ROOT / "examples")
# Seconds allowed for importing every GUI/lab module in a subprocess
IMPORT_SWEEP_TIMEOUT_S = 300

IMPORT_SWEEP = """
import importlib, pkgutil, sys
sys.modules['flet'] = None  # any 'import flet' now raises ImportError
failures = []
for package_name in ('bmlibrarian.gui', 'bmlibrarian.lab'):
    package = importlib.import_module(package_name)
    for info in pkgutil.walk_packages(package.__path__, package_name + '.'):
        try:
            importlib.import_module(info.name)
        except Exception as exc:
            failures.append(f"{info.name}: {type(exc).__name__}: {exc}")
assert not failures, "\\n".join(failures)
"""


def _python_files() -> Iterator[Path]:
    """Yield the Python files that are scanned for imports."""
    for directory in SCANNED_DIRS:
        if directory.is_dir():
            yield from directory.rglob("*.py")
    yield from REPO_ROOT.glob("*.py")


def _module_exists(dotted: str) -> bool:
    """Return True if ``dotted`` names a module or package under src/."""
    path = SRC_ROOT.joinpath(*dotted.split("."))
    return path.with_suffix(".py").is_file() or (path / "__init__.py").is_file()


def _resolve_relative(file_path: Path, level: int, module: Optional[str]) -> Optional[str]:
    """Resolve a relative import in a src/ file to a dotted module name."""
    try:
        package_parts = list(file_path.relative_to(SRC_ROOT).with_suffix("").parts[:-1])
    except ValueError:
        return None  # not inside src/
    if level > 1:
        package_parts = package_parts[: len(package_parts) - (level - 1)]
    return ".".join(package_parts + ([module] if module else []))


def _bad_imports(file_path: Path) -> List[str]:
    """Return flet imports and imports of missing bmlibrarian modules."""
    tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))
    problems = []
    for node in ast.walk(tree):
        targets: List[str] = []
        if isinstance(node, ast.Import):
            targets = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = _resolve_relative(file_path, node.level, node.module)
            else:
                base = node.module
            if base is None:
                continue
            # "from pkg import name": name may be a submodule or an attribute
            targets = [base]
        for target in targets:
            if target == "flet" or target.startswith("flet."):
                problems.append(f"{file_path}:{node.lineno} imports {target}")
            elif target.startswith("bmlibrarian.") and not _module_exists(target):
                problems.append(f"{file_path}:{node.lineno} imports missing {target}")
    return problems


def test_no_flet_or_missing_module_imports() -> None:
    """No source file imports flet or a deleted bmlibrarian module."""
    problems = [p for f in _python_files() for p in _bad_imports(f)]
    assert not problems, "\n".join(problems)


def test_gui_and_lab_modules_import_without_flet() -> None:
    """Every bmlibrarian.gui / bmlibrarian.lab module imports with flet blocked."""
    env = {**os.environ, "QT_QPA_PLATFORM": "offscreen"}
    result = subprocess.run(
        [sys.executable, "-c", IMPORT_SWEEP],
        env=env,
        capture_output=True,
        text=True,
        timeout=IMPORT_SWEEP_TIMEOUT_S,
    )
    assert result.returncode == 0, result.stderr[-4000:]


def test_flet_is_not_a_dependency() -> None:
    """pyproject.toml does not depend on flet."""
    project = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    dependencies = project.get("project", {}).get("dependencies", [])
    assert not [d for d in dependencies if d.lower().startswith("flet")]
