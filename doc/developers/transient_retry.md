# Retrying recoverable failures (`utils/transient_retry.py`)

A network timeout, a dropped database connection or an LLM server that is
restarting may succeed on a later attempt; a bug or an invalid model
response will not. `bmlibrarian.utils.transient_retry` tells the two apart
and retries only the first kind, with exponential backoff.

## API

```python
from bmlibrarian.utils.transient_retry import call_with_backoff, is_transient_error

rows = call_with_backoff(
    lambda: list(search_with_bm25(query, 100, True, True, True)),
    description="bm25 search",
    max_attempts=3,       # attempts in total; 1 turns retrying off
    base_delay=2.0,       # seconds before the first retry, doubled each retry
    max_delay=30.0,       # cap on the un-jittered wait
)
```

- `is_transient_error(error)`: True for builtin `ConnectionError` and
  `TimeoutError`, `psycopg.OperationalError`, and the transport errors of
  `requests` and `httpx` when installed (`TRANSIENT_ERROR_TYPES`). Explicit
  causes (`raise X from cause`) are followed, up to `MAX_CAUSE_DEPTH`; an
  error merely raised while handling another (`__context__`) is not, so a
  bug in an `except` block is not retried.
- `call_with_backoff(operation, *, description, max_attempts, base_delay,
  max_delay, is_retryable, sleep)`: calls `operation()`; on an error for
  which `is_retryable` is true it waits `rate_limit.backoff_delay(attempt,
  base, cap)` (exponential, up to 25% jitter) and tries again. The final
  attempt's error, or a non-recoverable error, is raised unchanged. Each
  retry is logged at WARNING, a final failure after retries at ERROR.
  Settings are validated (`TypeError`/`ValueError`) because they come from
  config files.
- The operation must be safe to repeat. Collect generator results inside
  it (`lambda: list(gen())`) so a failure midway discards partial rows.

The LLM client (`bmlibrarian.llm.LLMClient`) already retries each request a
few times with a short backoff. `call_with_backoff` sits above it, so a
longer outage (an Ollama restart) is ridden out at the level of a whole
step.

## Where it is used

| Caller | What is retried | Settings |
|---|---|---|
| `database.search_hybrid` | each strategy (semantic, BM25, fulltext) | `search_strategy.retry`: `max_attempts`, `base_delay`, `max_delay` |
| `FactCheckerAgent` | the search, each document's scoring, the evaluation request | `agents.fact_checker`: `transient_retry_attempts`, `transient_retry_base_delay` |
| `CitationFinderAgent` | the LLM connection check and the extraction request | constructor `transient_retry_attempts`, `transient_retry_base_delay` (the fact-checker passes its own) |

Defaults: `DEFAULT_TRANSIENT_ATTEMPTS` (3), `DEFAULT_TRANSIENT_BASE_SECONDS`
(2.0), `DEFAULT_TRANSIENT_CAP_SECONDS` (30.0), also in `DEFAULT_CONFIG`.

## Testing

The wait goes through the module function `_sleep` unless a `sleep` is
passed. `tests/conftest.py` has an autouse fixture, `_no_backoff_waits`,
that replaces `_sleep` with a recorder, so no test waits; a test that wants
to check the waits takes the fixture as an argument and inspects the
recorded delays. `tests/test_transient_retry.py` covers the helper itself
with an injected `sleep`.
