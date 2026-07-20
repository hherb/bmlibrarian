"""
Tests for batch embedding on bmlibrarian's LLM client.

Batching exists for throughput: measured against a local Ollama server,
32 chunks cost 0.59s batched versus 4.48s looped. A wrapper that
silently degraded to a loop would keep every test green while undoing
the only reason the method exists, so these tests assert the request
count, not just the returned vectors.

Patched at ``bmlib.llm.client.LLMClient.embed_batch`` — the provider
boundary — so bmlibrarian's own model qualification, provider forcing
and usage tracking stay live inside the test.
"""

from unittest.mock import patch

import pytest
import bmlib.llm.client as _bmlib_llm_client
from bmlib.llm import BatchEmbeddingResponse as BmlibBatchEmbeddingResponse

from bmlibrarian.llm import LLMClient, Provider

MODEL = "snowflake-arctic-embed2:latest"


@pytest.fixture
def client() -> LLMClient:
    """An LLM client whose provider transport is patched per-test."""
    return LLMClient(track_usage=False)


def _batch(vectors: list[list[float]]) -> BmlibBatchEmbeddingResponse:
    """Build a provider batch response carrying the given vectors."""
    return BmlibBatchEmbeddingResponse(
        embeddings=vectors,
        model=MODEL,
        dimensions=len(vectors[0]) if vectors else 0,
        input_tokens=len(vectors),
    )


class TestEmbedBatch:
    """Tests for LLMClient.embed_batch."""

    def test_returns_one_vector_per_text_in_order(self, client: LLMClient) -> None:
        """Vectors come back aligned with the input texts."""
        vectors = [[0.1, 0.2], [0.3, 0.4], [0.5, 0.6]]
        with patch.object(
            _bmlib_llm_client.LLMClient, "embed_batch", return_value=_batch(vectors)
        ):
            response = client.embed_batch(["a", "b", "c"], model=MODEL)

        assert response.embeddings == vectors
        assert response.dimensions == 2

    def test_batches_in_one_provider_call(self, client: LLMClient) -> None:
        """
        The whole batch is one round-trip.

        This is the assertion that would catch a wrapper quietly looping
        embed() per text, which is the failure mode batching exists to
        avoid.
        """
        texts = [f"chunk {i}" for i in range(32)]
        with patch.object(
            _bmlib_llm_client.LLMClient,
            "embed_batch",
            return_value=_batch([[0.1, 0.2]] * 32),
        ) as mock_batch:
            client.embed_batch(texts, model=MODEL)

        assert mock_batch.call_count == 1

    def test_empty_input_makes_no_provider_call(self, client: LLMClient) -> None:
        """An empty batch short-circuits rather than contacting a provider."""
        with patch.object(
            _bmlib_llm_client.LLMClient, "embed_batch"
        ) as mock_batch:
            response = client.embed_batch([], model=MODEL)

        assert response.embeddings == []
        assert mock_batch.call_count == 0

    def test_forces_ollama_regardless_of_prefix(self, client: LLMClient) -> None:
        """
        Embeddings stay local, as they do for embed().

        pgvector dimensions are fixed by the stored corpus, so an
        anthropic: prefix must not reroute an embedding request.
        """
        with patch.object(
            _bmlib_llm_client.LLMClient,
            "embed_batch",
            return_value=_batch([[0.1, 0.2]]),
        ) as mock_batch:
            response = client.embed_batch(["a"], model="anthropic:some-model")

        assert response.provider == Provider.OLLAMA
        assert mock_batch.call_args.kwargs["model"].startswith("ollama:")

    def test_qualifies_a_tagged_model_name(self, client: LLMClient) -> None:
        """
        A tag is not mistaken for a provider prefix.

        bmlib splits on the first colon, so "snowflake-arctic-embed2:latest"
        would otherwise read as provider "snowflake-arctic-embed2".
        """
        with patch.object(
            _bmlib_llm_client.LLMClient,
            "embed_batch",
            return_value=_batch([[0.1, 0.2]]),
        ) as mock_batch:
            client.embed_batch(["a"], model=MODEL)

        assert mock_batch.call_args.kwargs["model"] == f"ollama:{MODEL}"

    def test_records_usage_once_for_the_batch(self) -> None:
        """Token usage is attributed to the embed operation."""
        tracked = LLMClient(track_usage=True)
        with patch.object(
            _bmlib_llm_client.LLMClient,
            "embed_batch",
            return_value=_batch([[0.1, 0.2]] * 4),
        ):
            tracked.embed_batch(["a", "b", "c", "d"], model=MODEL)

        summary = tracked.get_usage_summary()
        assert summary is not None
        assert summary["total_prompt_tokens"] >= 4
