"""
Helpers for testing code that talks to a model.

Model communication is patched at the provider boundary —
``bmlib.llm.client.LLMClient.chat`` — which sits one layer below
bmlibrarian's own LLM abstraction. Everything bmlibrarian adds on top
(model-string qualification, retry, fallback, usage tracking, response
adaptation) therefore stays live inside the test.

Do not substitute a component's ``client`` attribute with a ``MagicMock``
instead. That stubs out exactly the layer under test. PR #247 shipped a
component calling a removed ollama API with all of its tests green,
because the fixture replaced the client wholesale and fed it responses in
the old ollama dict shape; the tests asserted against an API that no
longer existed.
"""

from contextlib import contextmanager
from typing import Any, Iterator
from unittest.mock import patch

import bmlib.llm.client as _bmlib_llm_client
from bmlib.llm import LLMResponse as BmlibLLMResponse
from unittest.mock import MagicMock

DEFAULT_TEST_MODEL = "gpt-oss:20b"


def llm_response(
    content: str,
    model: str = DEFAULT_TEST_MODEL,
) -> BmlibLLMResponse:
    """
    Build a provider response carrying the given completion text.

    Args:
        content: Completion text the model should appear to return
        model: Model name recorded on the response

    Returns:
        A bmlib LLMResponse, the shape bmlibrarian's LLM layer adapts from
    """
    return BmlibLLMResponse(content=content, model=model)


@contextmanager
def patch_llm(content: str | None = None, **kwargs: Any) -> Iterator[MagicMock]:
    """
    Patch model communication at the provider boundary.

    Args:
        content: Completion text to return, when a single fixed reply is
            wanted. Mutually exclusive with return_value/side_effect.
        **kwargs: Forwarded to patch.object — e.g. ``side_effect`` for a
            failure, or a sequence of responses across successive calls

    Yields:
        The patched chat mock, for call assertions

    Raises:
        ValueError: If content is combined with return_value
    """
    if content is not None:
        if "return_value" in kwargs:
            raise ValueError("Pass either content or return_value, not both")
        kwargs["return_value"] = llm_response(content)

    with patch.object(_bmlib_llm_client.LLMClient, "chat", **kwargs) as mock_chat:
        yield mock_chat
