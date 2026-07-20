"""
Architectural guard: model communication goes through the LLM layer.

Golden rule #4 requires all model communication to go through the shared
LLM abstraction (``bmlibrarian.llm``, which delegates to bmlib). Modules
that import ``ollama`` directly bypass provider selection, fallback,
retries and token accounting — an ``anthropic:`` model configured by the
user silently does not apply to them.

A number of modules predate the abstraction and still import ollama
directly. Migrating them is tracked separately; these tests exist so the
count can only go down:

- ``test_no_new_direct_ollama_imports`` fails when a module outside the
  allowlist starts importing ollama, so the debt cannot grow.
- ``test_allowlist_contains_no_stale_entries`` fails when an allowlisted
  module stops importing ollama, forcing the entry to be deleted as part
  of the migration rather than left to rot.

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

# Modules that still import ollama directly, pending migration.
# This list may only shrink. Do not add to it — route new code through
# bmlibrarian.llm.LLMClient or the BaseAgent helpers instead.
KNOWN_DIRECT_OLLAMA_MODULES = frozenset({
    "agents/paper_weight/agent.py",
    "agents/query_generation/generator.py",
    "agents/semantic_query_agent.py",
    "agents/systematic_review/executor.py",
    "agents/systematic_review/filters.py",
    "agents/systematic_review/planner.py",
    "agents/systematic_review/synthesizer.py",
    "embeddings/chunk_embedder.py",
    "embeddings/document_embedder.py",
    "gui/flet/config_app.py",
    "gui/flet/settings_tab.py",
    "gui/flet/tabs/agent_tab.py",
    "gui/flet/tabs/document_interrogation_tab.py",
    "gui/flet/tabs/search_tab.py",
    "gui/qt/plugins/document_interrogation/document_interrogation_tab.py",
    "gui/qt/plugins/query_lab/query_lab_tab.py",
    "gui/qt/tabs/agent_tab.py",
    "importers/pdf_matcher.py",
    "lab/paper_checker_lab/tabs/input_tab.py",
    "lab/paper_reviewer_lab/tabs/input_panel.py",
    "lab/pico_lab.py",
    "lab/query_lab.py",
    "lab/transparency_lab.py",
    "paperchecker/components.py",
    "paperchecker/components/counter_statement_generator.py",
    "paperchecker/components/hyde_generator.py",
    "paperchecker/components/statement_extractor.py",
    "paperchecker/components/verdict_analyzer.py",
    "qa/document_qa.py",
})


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
