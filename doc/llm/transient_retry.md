# Retrying recoverable failures

Use `bmlibrarian.utils.transient_retry.call_with_backoff` instead of writing
a retry loop. It retries only errors for which `is_transient_error` is true
(connection errors, timeouts, `psycopg.OperationalError`, requests/httpx
transport errors, also when they are the explicit `__cause__`), with
exponential backoff from `rate_limit.backoff_delay`, and re-raises anything
else at once. Never retry a `ValueError`/`KeyError`/JSON error this way:
those are bad data or bugs.

- Take `max_attempts`/`base_delay` from configuration (see the defaults in
  `DEFAULT_CONFIG`: `search_strategy.retry`, `agents.fact_checker`), not
  literals.
- Make the operation idempotent; wrap generators as `lambda: list(gen())`.
- In tests, the autouse fixture `_no_backoff_waits` (tests/conftest.py)
  makes waits instant and records them; request it by name to assert on
  the number of waits.

Details: `doc/developers/transient_retry.md`.
