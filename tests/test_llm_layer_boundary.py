"""
Architectural guard: model communication goes through the LLM layer.

Golden rule #4 requires all model communication to go through the shared
LLM abstraction (``bmlibrarian.llm``, which delegates to bmlib). Modules
that import ``ollama`` directly bypass provider selection, fallback,
retries and token accounting — an ``anthropic:`` model configured by the
user silently does not apply to them.

The migration of the modules that predated the abstraction is complete:
the allowlist below is empty, and nothing under ``src/bmlibrarian/``
outside the LLM layer imports ollama. These tests keep it that way:

- ``test_no_new_direct_ollama_imports`` fails when any module starts
  importing ollama, so the debt cannot come back.
- ``test_allowlist_contains_no_stale_entries`` is now vacuous, and stays
  only so that a temporary entry, should one ever be justified, must be
  removed again once its module is migrated rather than left to rot.

Scope note: this covers the package only. Standalone tooling under
``scripts/`` is not part of the shipped library and is not scanned.

Imports are detected by parsing the AST, not by grepping, so ``import
ollama`` appearing inside a docstring example is correctly ignored.
"""

import ast
from pathlib import Path

import pytest

# Package root, resolved relative to this file so the test is CWD-independent.
PACKAGE_ROOT = Path(__file__).resolve().parent.parent / "src" / "bmlibrarian"

# The LLM abstraction itself is the one place allowed to talk to ollama.
LLM_LAYER = "llm"

# Deliberately empty: every module has been migrated onto the LLM layer.
#
# Do not add to it. Route model calls through bmlibrarian.llm.LLMClient or
# the BaseAgent helpers (_make_llm_request / _generate_from_prompt /
# _generate_embedding), and list models with bmlibrarian.llm.list_ollama_models.
# Importing ollama directly bypasses provider selection, fallback, retries
# and token accounting — a configured anthropic: model silently would not
# apply, which is the failure this guard exists to prevent.
KNOWN_DIRECT_OLLAMA_MODULES: frozenset[str] = frozenset()


def _imports_ollama(source: str) -> bool:
    """
    Report whether a module's AST contains a real ollama import.

    Args:
        source: Python source text

    Returns:
        True if the module imports ollama at any scope, including inside
        functions. Mentions in docstrings or comments do not count.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        # An unparseable module cannot be importing anything.
        return False

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(alias.name.split(".")[0] == "ollama" for alias in node.names):
                return True
        elif isinstance(node, ast.ImportFrom):
            if (node.module or "").split(".")[0] == "ollama":
                return True
    return False


def _modules_importing_ollama() -> set[str]:
    """
    Find every package module that imports ollama directly.

    Returns:
        Package-relative POSIX paths, excluding the LLM layer itself
    """
    found: set[str] = set()
    for path in PACKAGE_ROOT.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        relative = path.relative_to(PACKAGE_ROOT)
        if relative.parts and relative.parts[0] == LLM_LAYER:
            continue
        if _imports_ollama(path.read_text(encoding="utf-8")):
            found.add(relative.as_posix())
    return found


@pytest.fixture(scope="module")
def direct_importers() -> set[str]:
    """Scan the package once for modules importing ollama directly."""
    return _modules_importing_ollama()


def test_package_root_is_discoverable() -> None:
    """Guard against the scan silently passing because it found no files."""
    assert PACKAGE_ROOT.is_dir(), f"package root not found: {PACKAGE_ROOT}"
    assert any(PACKAGE_ROOT.rglob("*.py")), "no modules found to scan"


def test_no_new_direct_ollama_imports(direct_importers: set[str]) -> None:
    """New code must route model calls through bmlibrarian.llm."""
    unexpected = direct_importers - KNOWN_DIRECT_OLLAMA_MODULES

    assert not unexpected, (
        "These modules import ollama directly, bypassing provider selection, "
        "fallback, retries and token accounting:\n  "
        + "\n  ".join(sorted(unexpected))
        + "\n\nUse bmlibrarian.llm.LLMClient, or the BaseAgent helpers "
          "(_make_llm_request / _generate_from_prompt / _generate_embedding). "
          "To list models for a picker, use bmlibrarian.llm.list_ollama_models."
    )


def test_allowlist_contains_no_stale_entries(direct_importers: set[str]) -> None:
    """A migrated module must be removed from the allowlist."""
    stale = KNOWN_DIRECT_OLLAMA_MODULES - direct_importers

    assert not stale, (
        "These modules no longer import ollama and must be dropped from "
        "KNOWN_DIRECT_OLLAMA_MODULES so the guard keeps tightening:\n  "
        + "\n  ".join(sorted(stale))
    )
