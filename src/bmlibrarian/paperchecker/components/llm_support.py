"""
Shared LLM plumbing for the PaperChecker components.

Every component (statement extraction, counter-statement generation, HyDE,
verdict analysis) needs the same two things: send a single-turn prompt and
get non-empty text back, and probe whether the configured model's provider
is reachable. Before the migration onto the LLM abstraction each component
carried its own byte-identical copy of that logic, differing only in a log
message.

Retry responsibilities are split deliberately:

- Transport failures are retried by ``LLMClient`` with exponential backoff.
  The helper does not retry them; doing so in both places would multiply
  attempts rather than add resilience.
- An empty completion is not a transport failure, so ``LLMClient`` never
  sees it. The helper retries that case, preserving the behaviour the
  components had before the migration.
"""

import logging
import time
from typing import Final

from ...llm import LLMClient, LLMMessage
from ...llm.model_resolver import parse_model_string

logger = logging.getLogger(__name__)

# Attempts made when the model keeps returning an empty completion.
DEFAULT_MAX_RETRIES: Final[int] = 3

# Initial backoff between empty-response retries; doubles each attempt.
DEFAULT_RETRY_DELAY_SECONDS: Final[float] = 1.0

MILLISECONDS_PER_SECOND: Final[int] = 1000


def call_llm(
    client: LLMClient,
    model: str,
    prompt: str,
    temperature: float,
    description: str,
    max_retries: int = DEFAULT_MAX_RETRIES,
    retry_delay: float = DEFAULT_RETRY_DELAY_SECONDS,
) -> str:
    """
    Send a single-turn prompt and return the model's text.

    Args:
        client: Configured LLM client
        model: Model string, optionally provider-prefixed
        prompt: Prompt sent as a single user message
        temperature: Sampling temperature
        description: Short label for log messages, e.g. "verdict"
        max_retries: Attempts made when the completion comes back empty
        retry_delay: Initial backoff between empty-response retries

    Returns:
        The completion text, stripped of surrounding whitespace

    Raises:
        RuntimeError: If the request fails, or every attempt returns an
            empty completion
    """
    current_delay = retry_delay

    for attempt in range(max_retries):
        start_time = time.time()

        log_msg = f"LLM {description} request to {model}"
        if attempt > 0:
            log_msg += f" (retry {attempt}/{max_retries - 1})"
        logger.info(log_msg)

        try:
            response = client.chat(
                messages=[LLMMessage(role="user", content=prompt)],
                model=model,
                temperature=temperature,
            )
        except Exception as e:
            # LLMClient has already retried transport failures and, where
            # configured, tried the fallback model. Another loop here would
            # only multiply the wait before the caller learns it failed.
            elapsed_ms = (time.time() - start_time) * MILLISECONDS_PER_SECOND
            logger.error(
                f"LLM {description} request failed after {elapsed_ms:.2f}ms: {e}"
            )
            raise RuntimeError(f"LLM call failed: {e}") from e

        content = (response.content or "").strip()
        if content:
            elapsed_ms = (time.time() - start_time) * MILLISECONDS_PER_SECOND
            logger.info(
                f"LLM {description} response received in {elapsed_ms:.2f}ms"
            )
            return content

        if attempt < max_retries - 1:
            logger.warning(
                f"Empty {description} response, retrying in {current_delay:.1f}s"
            )
            time.sleep(current_delay)
            current_delay *= 2

    raise RuntimeError(
        f"Failed to get response from model after {max_retries} attempts: "
        f"empty completion"
    )


def probe_llm_connection(client: LLMClient, model: str) -> bool:
    """
    Report whether the provider backing a model is reachable.

    The provider is taken from the model string, so an ``anthropic:``
    model is probed against Anthropic rather than the local Ollama server.

    Args:
        client: Configured LLM client
        model: Model string, optionally provider-prefixed

    Returns:
        True if the provider responded, False if it did not or the probe
        raised
    """
    try:
        return client.test_provider(parse_model_string(model).provider)
    except Exception as e:
        logger.warning(f"Connection test failed for {model}: {e}")
        return False
