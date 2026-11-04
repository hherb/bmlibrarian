"""
Architectural guard: model communication goes through the LLM layer.

Golden rule #4 requires all model communication to go through the shared
LLM abstraction (``bmlibrarian.llm``, which delegates to bmlib). Modules
that import ``ollama`` directly bypass provider selection, fallback,
retries and token accounting — an ``anthropic:`` model configured by the
user silently does not apply to them.

The migration of the modules that predated the abstraction is complete:
the import allowlist (``KNOWN_DIRECT_OLLAMA_MODULES``) is empty, and nothing
under ``src/bmlibrarian/`` outside the LLM layer imports ollama. These tests
keep it that way:

- ``test_no_new_direct_ollama_imports`` fails when any module starts
  importing ollama, so the debt cannot come back.
- ``test_allowlist_contains_no_stale_entries`` is now vacuous, and stays
  only so that a temporary entry, should one ever be justified, must be
  removed again once its module is migrated rather than left to rot.
- ``test_no_new_raw_ollama_http`` and
  ``test_raw_http_allowlist_contains_no_stale_entries`` do the same for raw
  HTTP calls (``KNOWN_RAW_OLLAMA_HTTP_MODULES``); see below.
- ``test_endpoint_detection_ignores_docstrings`` tests that detector itself.

Scope note: this covers the package only. Standalone tooling under
``scripts/`` is not part of the shipped library and is not scanned.

Imports are detected by parsing the AST, not by grepping, so ``import
ollama`` appearing inside a docstring example is correctly ignored.

Raw HTTP to the Ollama REST API (``/api/tags``, ``/api/chat``, …) bypasses
the layer just as surely without importing anything (#250), so
``test_no_new_raw_ollama_http`` also flags string literals naming those
endpoints. Docstrings and comments do not count. URLs assembled from parts
without the literal ``/api/<endpoint>`` (``urljoin(host, "api/tags")``,
``f"{host}/api/{name}"``) are not detected.
"""

import ast
import re
from collections.abc import Callable
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


# Ollama REST endpoints; a string literal naming one is a raw HTTP call.
OLLAMA_ENDPOINT_PATTERN = re.compile(
    r"/api/(tags|generate|chat|embed|embeddings|pull|push|show|ps|version)\b"
)

# Modules allowed to call the Ollama REST API directly. Same rules as
# KNOWN_DIRECT_OLLAMA_MODULES: do not add to it without a reason that the
# LLM layer cannot serve.
KNOWN_RAW_OLLAMA_HTTP_MODULES: frozenset[str] = frozenset({
    # Batch embedding server for bulk chunk embedding (/api/embed takes a
    # list of inputs); the LLM layer embeds one text per request. Its
    # /api/tags model check could already use list_ollama_models: remaining
    # debt, kept here because the module is allowlisted as a whole.
    "embeddings/embedding_server.py",
})


def _docstring_nodes(tree: ast.AST) -> set[int]:
    """
    Collect the ids of every docstring and bare string-expression node.

    Args:
        tree: Parsed module

    Returns:
        ``id()`` of each string Constant that is a statement on its own
    """
    return {
        id(node.value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
    }


def _names_ollama_endpoint(source: str) -> bool:
    """
    Report whether a module's code contains a string naming an Ollama endpoint.

    Args:
        source: Python source text

    Returns:
        True if any string literal (f-string parts included) outside a
        docstring names an Ollama REST endpoint.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return False

    docstrings = _docstring_nodes(tree)
    return any(
        isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docstrings
        and OLLAMA_ENDPOINT_PATTERN.search(node.value)
        for node in ast.walk(tree)
    )


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
    return _scan_package(_imports_ollama)


def _scan_package(check: Callable[[str], bool]) -> set[str]:
    """
    Find every package module, outside the LLM layer, whose source fails a check.

    Args:
        check: Callable taking module source text, True when it offends

    Returns:
        Package-relative POSIX paths
    """
    found: set[str] = set()
    for path in PACKAGE_ROOT.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        relative = path.relative_to(PACKAGE_ROOT)
        if relative.parts and relative.parts[0] == LLM_LAYER:
            continue
        if check(path.read_text(encoding="utf-8")):
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


@pytest.fixture(scope="module")
def raw_http_callers() -> set[str]:
    """Scan the package once for modules naming Ollama REST endpoints."""
    return _scan_package(_names_ollama_endpoint)


def test_endpoint_detection_ignores_docstrings() -> None:
    """A docstring mention is fine; a URL built in code is not."""
    documented = '"""Uses the /api/embed endpoint."""\n'
    assert not _names_ollama_endpoint(documented)
    assert _names_ollama_endpoint(documented + 'url = f"{host}/api/tags"\n')
    assert _names_ollama_endpoint('requests.post(host + "/api/generate")\n')
    assert not _names_ollama_endpoint('path = "/api/tagsoup"\n')


def test_no_new_raw_ollama_http(raw_http_callers: set[str]) -> None:
    """New code must not reach the Ollama REST API around the LLM layer."""
    unexpected = raw_http_callers - KNOWN_RAW_OLLAMA_HTTP_MODULES

    assert not unexpected, (
        "These modules call the Ollama REST API directly, bypassing provider "
        "selection, fallback, retries and token accounting:\n  "
        + "\n  ".join(sorted(unexpected))
        + "\n\nUse bmlibrarian.llm.LLMClient, or bmlibrarian.llm."
          "list_ollama_models for a model picker."
    )


def test_raw_http_allowlist_contains_no_stale_entries(
    raw_http_callers: set[str],
) -> None:
    """A migrated module must be removed from the raw-HTTP allowlist."""
    stale = KNOWN_RAW_OLLAMA_HTTP_MODULES - raw_http_callers

    assert not stale, (
        "These modules no longer call the Ollama REST API and must be dropped "
        "from KNOWN_RAW_OLLAMA_HTTP_MODULES:\n  " + "\n  ".join(sorted(stale))
    )
