# BaseAgent per-call overrides + standalone-agent LLM-layer polish

**Date:** 2026-07-22
**Status:** Approved (design), implementation in progress
**Scope:** `src/bmlibrarian/agents/base.py`, `src/bmlibrarian/importers/pdf_matcher.py`,
`src/bmlibrarian/agents/semantic_query_agent.py`

## Problem

Golden rule #4 requires all model communication to go through the LLM
abstraction. That is already true — the `import ollama` boundary is fully
migrated (`tests/test_llm_layer_boundary.py` allowlist is empty). But ~10
"standalone agent" classes construct their own `LLMClient` directly instead
of inheriting `BaseAgent`, re-implementing agent-level plumbing (token
accounting via `PerformanceMetrics`, `test_connection()`, host/config
resolution, standardized retry/error handling).

Investigation showed most of those sites do **not** cleanly fit `BaseAgent`
today, because its helpers (`_make_llm_request`, `_generate_from_prompt`)
hardcode `model=self.model`, `temperature=self.temperature`,
`top_p=self.top_p`, and silently drop any leftover kwargs (so provider
options like `think=` never reach the client). Consumers that vary these
per call therefore cannot use the helpers:

- `semantic_query_agent` — per-call temperature (rephrase vs. expand) and a
  dedicated `rephrasing_model`.
- `query_generation/generator` — fan-out over 1–3 models with per-attempt
  temperature bumps (multi-model by design).
- `qa/document_qa.answer_question` — a module-level function using `think=`.

## Decision

Extend `BaseAgent`'s helpers **additively** so per-call variation is
expressible, then migrate the two sites this unblocks that are genuine
single-agent shapes. This turns a one-off migration into a reusable
capability and makes `BaseAgent` the true universal entry point — justified
by three concrete consumers, not speculative generality.

### Phase 1 — BaseAgent helper enhancement (zero behavior change for existing agents)

In `_make_llm_request` and `_generate_from_prompt`:

- Add optional params `model: Optional[str] = None`,
  `temperature: Optional[float] = None`, `top_p: Optional[float] = None`.
  Resolve each as `value if value is not None else self.<attr>` before the
  client call. Every existing call omits them → byte-for-byte unchanged.
- Forward a `think: Optional[bool] = None` passthrough to the client (only
  included in the call when not `None`), instead of swallowing it.
- Logging/metrics keep working; when `model` is overridden the structured
  log should report the effective model.

Backward compatibility: all new params default to `None`; the resolved
values equal today's behavior when unset. The `_make_ollama_request` alias
is untouched.

### Phase 2 — migrate the clean fits

**`pdf_matcher.PDFMatcher` → `BaseAgent`:**
- `super().__init__(model=model or DEFAULT_MODEL, host=<resolved ollama host>,
  temperature=METADATA_EXTRACTION_TEMPERATURE, top_p=METADATA_EXTRACTION_TOP_P,
  fallback_model=FALLBACK_MODEL, show_model_info=False)`.
- Implement `get_agent_type()` → `"pdf_matcher"`.
- Replace `self.ollama_client.generate(...)` with
  `self._generate_from_prompt(prompt)` (temperature/top_p already carried by
  the instance). Adjust `response.content` → returned string.
- Net win: **activates the currently-dead `FALLBACK_MODEL`** (defined but
  never wired), adds token accounting + `test_connection()`, unifies host
  handling. Metadata extraction behavior unchanged (same model, temp, top_p).
- Constructor keeps its public signature (`pdf_base_dir`, `ollama_host`,
  `model`) so the 4 call sites in `pdf_import_cli.py` and
  `pdf_upload_workers.py` are unaffected.

**`semantic_query_agent.SemanticQueryAgent` → `BaseAgent`:**
- `super().__init__(model=rephrasing_model or DEFAULT_REPHRASING_MODEL,
  host=<resolved host>, temperature=rephrasing_temperature,
  show_model_info=False)`.
- Implement `get_agent_type()` → `"semantic_query_agent"`.
- Replace the two `self._llm_client.generate(...)` calls with
  `self._generate_from_prompt(prompt, temperature=<per-call>, model=<per-call>,
  num_predict=<max_tokens>)`, using the new per-call overrides for the
  expand call's distinct temperature.
- Keep the public `__init__` signature so callers are unaffected.

### Deferred (documented follow-up, not this slice)

- `query_generation/generator` (multi-model orchestrator): migratable via the
  new per-call `model` override, but it is a fan-out shape deserving its own
  pass. Track in HANDOVER.
- `qa/document_qa.answer_question` (module function): converting to an agent
  is a separate caller-facing API decision. The `think` passthrough lands in
  Phase 1 so it is ready if/when converted.
- Embedders (`document_embedder`, `chunk_embedder`): do embeddings, not chat;
  out of scope. Docstring-only `LLMClient` mentions in `hyde_search.py`: n/a.

## Testing

- New unit tests (mirroring `tests/test_agents.py`: concrete `TestAgent(BaseAgent)`
  + `@patch('bmlib.llm.client.LLMClient.chat'/'.generate')`):
  - override params are honored when passed; `self.*` used when omitted;
  - `think` reaches the client only when set;
  - `PDFMatcher` inherits `BaseAgent`, passes `fallback_model`, and its
    extraction call still returns parsed metadata (client mocked);
  - `SemanticQueryAgent` rephrase/expand use the expected per-call temps.
- Regression gate (no CI, broken baseline): capture failing node-IDs on
  `master`, compare against this branch; **zero new failures** is the gate.
- `ruff check --select F <touched files>` and `mypy` on touched files: no new
  errors.

## Non-goals

- No change to `LLMClient`/`bmlib.llm`.
- No change to any existing agent's behavior or public API.
- No migration of the deferred sites in this slice.
