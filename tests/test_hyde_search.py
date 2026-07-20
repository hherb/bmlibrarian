"""
Behavioural tests for the HyDE search utilities.

tests/test_hyde.py only asserts that these functions import and that
QueryAgent exposes a method with the right parameter names. That is why
nobody noticed that ``QueryAgent.find_abstracts_hyde`` had been broken
since the LLM abstraction landed: it passes its ``LLMClient`` into
``generate_hypothetical_documents``, which called ``client.generate(...,
system=..., options=...)`` and ``client.embeddings(...)`` — an ollama API
that ``LLMClient`` does not have.

These tests call the functions, so that class of break fails the build.
"""

from unittest.mock import patch

import pytest
from bmlib.llm import EmbeddingResponse as BmlibEmbeddingResponse

import bmlib.llm.client as _bmlib_llm_client
from llm_test_support import patch_llm

from bmlibrarian.agents.utils.hyde_search import (
    embed_documents,
    generate_hypothetical_documents,
)
from bmlibrarian.llm import LLMClient

GENERATION_MODEL = "gpt-oss:20b"
EMBEDDING_MODEL = "nomic-embed-text:latest"


@pytest.fixture
def client() -> LLMClient:
    """A real LLM client whose transport is patched per-test."""
    return LLMClient(track_usage=False)


class TestGenerateHypotheticalDocuments:
    """Tests for generate_hypothetical_documents."""

    def test_returns_one_document_per_request(self, client: LLMClient) -> None:
        """The requested number of hypothetical abstracts comes back."""
        with patch_llm("A hypothetical abstract about exercise.") as mock_chat:
            docs = generate_hypothetical_documents(
                "Does exercise reduce cardiovascular risk?",
                client,
                GENERATION_MODEL,
                num_docs=3,
            )

        assert len(docs) == 3
        assert mock_chat.call_count == 3

    def test_prompts_vary_between_documents(self, client: LLMClient) -> None:
        """Diversity comes from varying the prompt, so they must differ."""
        with patch_llm("An abstract.") as mock_chat:
            generate_hypothetical_documents(
                "Does exercise help?", client, GENERATION_MODEL, num_docs=3
            )

        prompts = [
            call.kwargs["messages"][-1].content for call in mock_chat.call_args_list
        ]
        assert len(set(prompts)) == 3

    def test_empty_completions_raise(self, client: LLMClient) -> None:
        """No usable abstract is an error, not an empty result."""
        with patch_llm("   "):
            with pytest.raises(ValueError, match="Failed to generate any"):
                generate_hypothetical_documents(
                    "Does exercise help?", client, GENERATION_MODEL, num_docs=2
                )

    def test_partial_failure_keeps_the_successes(self, client: LLMClient) -> None:
        """One failed generation does not discard the others."""
        from bmlib.llm import LLMResponse as BmlibLLMResponse

        with patch_llm(
            side_effect=[
                BmlibLLMResponse(content="First abstract.", model=GENERATION_MODEL),
                RuntimeError("model exploded"),
                BmlibLLMResponse(content="Third abstract.", model=GENERATION_MODEL),
            ]
        ):
            docs = generate_hypothetical_documents(
                "Does exercise help?", client, GENERATION_MODEL, num_docs=3
            )

        assert docs == ["First abstract.", "Third abstract."]


class TestEmbedDocuments:
    """Tests for embed_documents."""

    def test_returns_one_vector_per_document(self, client: LLMClient) -> None:
        """Every document gets an embedding, in order."""
        with patch.object(
            _bmlib_llm_client.LLMClient,
            "embed",
            return_value=BmlibEmbeddingResponse(
                embedding=[0.1, 0.2, 0.3], model=EMBEDDING_MODEL, dimensions=3
            ),
        ) as mock_embed:
            vectors = embed_documents(["doc one", "doc two"], client, EMBEDDING_MODEL)

        assert vectors == [[0.1, 0.2, 0.3], [0.1, 0.2, 0.3]]
        assert mock_embed.call_count == 2

    def test_empty_embedding_raises(self, client: LLMClient) -> None:
        """An empty vector is a failure, not a usable result."""
        with patch.object(
            _bmlib_llm_client.LLMClient,
            "embed",
            return_value=BmlibEmbeddingResponse(embedding=[], model=EMBEDDING_MODEL),
        ):
            with pytest.raises(ConnectionError, match="Failed to generate embedding"):
                embed_documents(["doc one"], client, EMBEDDING_MODEL)

    def test_provider_failure_raises_connection_error(
        self, client: LLMClient
    ) -> None:
        """A transport failure is reported rather than silently skipped."""
        with patch.object(
            _bmlib_llm_client.LLMClient, "embed", side_effect=OSError("no route")
        ):
            with pytest.raises(ConnectionError, match="Failed to generate embedding"):
                embed_documents(["doc one"], client, EMBEDDING_MODEL)
