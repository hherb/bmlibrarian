"""
Unit tests for the LLM abstraction module.

Tests cover:
- Model string parsing
- Token tracking and cost calculation
- Provider registry
- Client fallback logic (mocked)
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

from bmlibrarian.llm import (
    # Data types
    Provider,
    ModelSpec,
    LLMMessage,
    LLMResponse,
    EmbeddingResponse,
    GenerationParams,
    # Model resolver
    parse_model_string,
    format_model_string,
    qualify_model_string,
    is_provider_prefix,
    get_supported_providers,
    # Token tracking
    TokenTracker,
    get_token_tracker,
    reset_global_tracker,
    # Client
    LLMClient,
    # Providers
    reset_all_providers,
    is_provider_available,
)
from bmlibrarian.llm.constants import (
    DEFAULT_ANTHROPIC_MAX_TOKENS,
    DEFAULT_EMBEDDING_MODEL,
    OLLAMA_UNLIMITED_MAX_TOKENS,
)


class TestModelResolver:
    """Tests for model string parsing."""

    def test_parse_unprefixed_model(self):
        """Unprefixed models should default to Ollama."""
        spec = parse_model_string("medgemma-27b")
        assert spec.provider == Provider.OLLAMA
        assert spec.model_name == "medgemma-27b"
        assert spec.raw == "medgemma-27b"

    def test_parse_ollama_prefix(self):
        """Explicit ollama: prefix should work."""
        spec = parse_model_string("ollama:medgemma-27b")
        assert spec.provider == Provider.OLLAMA
        assert spec.model_name == "medgemma-27b"

    def test_parse_anthropic_prefix(self):
        """anthropic: prefix should select Anthropic provider."""
        spec = parse_model_string("anthropic:claude-3-opus")
        assert spec.provider == Provider.ANTHROPIC
        assert spec.model_name == "claude-3-opus"

    def test_parse_openai_prefix(self):
        """openai: prefix should select OpenAI provider."""
        spec = parse_model_string("openai:gpt-4")
        assert spec.provider == Provider.OPENAI
        assert spec.model_name == "gpt-4"

    def test_parse_case_insensitive(self):
        """Provider prefixes should be case-insensitive."""
        spec = parse_model_string("ANTHROPIC:claude-3-opus")
        assert spec.provider == Provider.ANTHROPIC
        assert spec.model_name == "claude-3-opus"

    def test_parse_model_with_colon(self):
        """Model names containing colons should work (e.g., gpt-oss:20b)."""
        spec = parse_model_string("gpt-oss:20b")
        assert spec.provider == Provider.OLLAMA
        assert spec.model_name == "gpt-oss:20b"

    def test_parse_model_with_colon_and_prefix(self):
        """Model names with colons and provider prefix should work."""
        spec = parse_model_string("ollama:gpt-oss:20b")
        assert spec.provider == Provider.OLLAMA
        assert spec.model_name == "gpt-oss:20b"

    def test_parse_empty_string_raises(self):
        """Empty string should raise ValueError."""
        with pytest.raises(ValueError, match="cannot be empty"):
            parse_model_string("")

    def test_parse_empty_model_after_prefix_raises(self):
        """Empty model after prefix should raise ValueError."""
        with pytest.raises(ValueError, match="cannot be empty"):
            parse_model_string("anthropic:")

    def test_format_model_string_default_provider(self):
        """Default provider should not include prefix."""
        result = format_model_string(Provider.OLLAMA, "medgemma-27b")
        assert result == "medgemma-27b"

    def test_format_model_string_anthropic(self):
        """Non-default providers should include prefix."""
        result = format_model_string(Provider.ANTHROPIC, "claude-3-opus")
        assert result == "anthropic:claude-3-opus"

    def test_qualify_model_string_adds_prefix_to_colon_bearing_name(self):
        """Ollama tags must not be mistaken for provider prefixes."""
        assert qualify_model_string("gpt-oss:20b") == "ollama:gpt-oss:20b"
        assert (
            qualify_model_string("medgemma4B_it_q8:latest")
            == "ollama:medgemma4B_it_q8:latest"
        )

    def test_qualify_model_string_adds_prefix_to_bare_name(self):
        """Unprefixed names resolve to the default provider, made explicit."""
        assert qualify_model_string("medgemma-27b") == "ollama:medgemma-27b"

    def test_qualify_model_string_is_idempotent(self):
        """Re-qualifying an already-qualified string must not double the prefix."""
        assert qualify_model_string("ollama:gpt-oss:20b") == "ollama:gpt-oss:20b"
        assert (
            qualify_model_string("anthropic:claude-3-opus")
            == "anthropic:claude-3-opus"
        )

    def test_is_provider_prefix(self):
        """Test provider prefix detection."""
        assert is_provider_prefix("ollama")
        assert is_provider_prefix("anthropic")
        assert is_provider_prefix("OPENAI")  # Case insensitive
        assert not is_provider_prefix("gpt-oss")
        assert not is_provider_prefix("medgemma")

    def test_get_supported_providers(self):
        """Test supported providers list."""
        providers = get_supported_providers()
        assert "ollama" in providers
        assert "anthropic" in providers
        assert "openai" in providers


class TestTokenTracker:
    """Tests for token usage tracking."""

    def setup_method(self):
        """Reset tracker before each test."""
        reset_global_tracker()

    def test_record_usage(self):
        """Test basic usage recording."""
        tracker = TokenTracker()
        cost = tracker.record_usage(
            Provider.OLLAMA,
            "medgemma-27b",
            prompt_tokens=100,
            completion_tokens=50,
            operation="chat",
        )
        # Ollama is free
        assert cost == 0.0

        summary = tracker.get_summary()
        assert summary.total_prompt_tokens == 100
        assert summary.total_completion_tokens == 50
        assert summary.total_tokens == 150
        assert summary.request_count == 1

    def test_record_anthropic_usage(self):
        """Test cost calculation for Anthropic."""
        tracker = TokenTracker()
        cost = tracker.record_usage(
            Provider.ANTHROPIC,
            "claude-3-opus",
            prompt_tokens=1000,
            completion_tokens=500,
            operation="chat",
        )
        # Claude 3 Opus: $15/1M input, $75/1M output
        expected_cost = (1000 / 1_000_000) * 15.0 + (500 / 1_000_000) * 75.0
        assert abs(cost - expected_cost) < 0.0001

    def test_record_anthropic_usage_partial_match(self):
        """Test cost calculation with versioned model name."""
        tracker = TokenTracker()
        # Model name includes date suffix
        cost = tracker.record_usage(
            Provider.ANTHROPIC,
            "claude-3-opus-20240229",
            prompt_tokens=1000,
            completion_tokens=500,
            operation="chat",
        )
        # Should still match claude-3-opus pricing
        expected_cost = (1000 / 1_000_000) * 15.0 + (500 / 1_000_000) * 75.0
        assert abs(cost - expected_cost) < 0.0001

    def test_provider_breakdown(self):
        """Test per-provider breakdown."""
        tracker = TokenTracker()
        tracker.record_usage(Provider.OLLAMA, "model-a", 100, 50)
        tracker.record_usage(Provider.OLLAMA, "model-b", 200, 100)
        tracker.record_usage(Provider.ANTHROPIC, "claude-3-haiku", 50, 25)

        summary = tracker.get_summary()
        assert "ollama" in summary.by_provider
        assert summary.by_provider["ollama"]["requests"] == 2
        assert summary.by_provider["ollama"]["tokens"] == 450

        assert "anthropic" in summary.by_provider
        assert summary.by_provider["anthropic"]["requests"] == 1

    def test_model_breakdown(self):
        """Test per-model breakdown."""
        tracker = TokenTracker()
        tracker.record_usage(Provider.OLLAMA, "model-a", 100, 50)
        tracker.record_usage(Provider.OLLAMA, "model-a", 100, 50)
        tracker.record_usage(Provider.OLLAMA, "model-b", 200, 100)

        summary = tracker.get_summary()
        assert "ollama:model-a" in summary.by_model
        assert summary.by_model["ollama:model-a"]["requests"] == 2
        assert summary.by_model["ollama:model-a"]["tokens"] == 300

    def test_format_report(self):
        """Test report formatting."""
        tracker = TokenTracker()
        tracker.record_usage(Provider.OLLAMA, "test-model", 1000, 500)

        report = tracker.format_report()
        assert "LLM Usage Report" in report
        assert "Total tokens: 1,500" in report
        assert "ollama" in report

    def test_reset(self):
        """Test tracker reset."""
        tracker = TokenTracker()
        tracker.record_usage(Provider.OLLAMA, "test", 100, 50)
        assert tracker.get_summary().request_count == 1

        tracker.reset()
        assert tracker.get_summary().request_count == 0

    def test_global_tracker(self):
        """Test global tracker singleton."""
        reset_global_tracker()
        tracker1 = get_token_tracker()
        tracker2 = get_token_tracker()
        assert tracker1 is tracker2


class TestLLMMessage:
    """Tests for LLMMessage dataclass."""

    def test_create_message(self):
        """Test message creation."""
        msg = LLMMessage(role="user", content="Hello!")
        assert msg.role == "user"
        assert msg.content == "Hello!"

    def test_create_system_message(self):
        """Test system message creation."""
        msg = LLMMessage(role="system", content="You are a helpful assistant.")
        assert msg.role == "system"


class TestGenerationParams:
    """Tests for GenerationParams dataclass."""

    def test_default_params(self):
        """Test default parameter values."""
        params = GenerationParams()
        assert params.temperature == 0.7
        assert params.top_p == 0.9
        assert params.max_tokens is None
        assert params.json_mode is False

    def test_custom_params(self):
        """Test custom parameter values."""
        params = GenerationParams(
            temperature=0.5,
            top_p=0.95,
            max_tokens=1000,
            json_mode=True,
            stop_sequences=["END"],
        )
        assert params.temperature == 0.5
        assert params.max_tokens == 1000
        assert params.json_mode is True
        assert params.stop_sequences == ["END"]


class TestLLMResponse:
    """Tests for LLMResponse dataclass."""

    def test_create_response(self):
        """Test response creation."""
        response = LLMResponse(
            content="Hello!",
            model="test-model",
            provider=Provider.OLLAMA,
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
        )
        assert response.content == "Hello!"
        assert response.total_tokens == 15


class TestLLMClient:
    """Tests for LLMClient (with mocked bmlib providers)."""

    def setup_method(self):
        """Reset providers before each test."""
        reset_all_providers()
        reset_global_tracker()

    def _make_bmlib_response(self, content="Hello!", model="test-model",
                             input_tokens=10, output_tokens=5):
        """Create a mock bmlib LLMResponse."""
        from bmlib.llm import LLMResponse as BmlibResponse
        return BmlibResponse(
            content=content,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )

    @patch("bmlib.llm.client.LLMClient.chat")
    def test_chat_ollama(self, mock_bmlib_chat):
        """Test chat with Ollama provider."""
        mock_bmlib_chat.return_value = self._make_bmlib_response()

        client = LLMClient(track_usage=False)
        messages = [LLMMessage(role="user", content="Hi")]
        response = client.chat(messages, model="test-model")

        assert response.content == "Hello!"
        assert response.provider == Provider.OLLAMA
        mock_bmlib_chat.assert_called_once()

    @patch("bmlib.llm.client.LLMClient.chat")
    def test_chat_anthropic(self, mock_bmlib_chat):
        """Test chat with Anthropic provider."""
        mock_bmlib_chat.return_value = self._make_bmlib_response(
            content="Hello from Claude!", model="claude-3-opus",
        )

        client = LLMClient(track_usage=False)
        messages = [LLMMessage(role="user", content="Hi")]
        response = client.chat(messages, model="anthropic:claude-3-opus")

        assert response.content == "Hello from Claude!"
        assert response.provider == Provider.ANTHROPIC

    @patch("bmlib.llm.client.LLMClient.chat")
    def test_fallback_on_failure(self, mock_bmlib_chat):
        """Test fallback to Ollama when primary provider fails."""
        # 1 call fails (anthropic, max_retries=1), then 1 succeeds (ollama fallback)
        responses = [ConnectionError("API error")] + [
            self._make_bmlib_response(
                content="Fallback response", model="fallback-model",
            )
        ]
        mock_bmlib_chat.side_effect = responses

        client = LLMClient(
            fallback_model="fallback-model",
            track_usage=False,
        )
        messages = [LLMMessage(role="user", content="Hi")]
        response = client.chat(
            messages, model="anthropic:claude-3-opus",
            max_retries=1, retry_delay=0.01,
        )

        assert response.content == "Fallback response"
        assert response.provider == Provider.OLLAMA

    @patch("bmlib.llm.client.LLMClient.chat")
    def test_no_fallback_for_ollama(self, mock_bmlib_chat):
        """Test that Ollama failures don't trigger Ollama fallback."""
        mock_bmlib_chat.side_effect = ConnectionError("Ollama error")

        client = LLMClient(
            fallback_model="fallback-model",
            track_usage=False,
        )
        messages = [LLMMessage(role="user", content="Hi")]

        with pytest.raises(ConnectionError):
            client.chat(messages, model="test-model", max_retries=1)

    @patch("bmlib.llm.client.LLMClient.chat")
    def test_usage_tracking(self, mock_bmlib_chat):
        """Test that usage is tracked when enabled."""
        mock_bmlib_chat.return_value = self._make_bmlib_response(
            input_tokens=100, output_tokens=50,
        )

        reset_global_tracker()
        client = LLMClient(track_usage=True)
        messages = [LLMMessage(role="user", content="Hi")]
        client.chat(messages, model="test-model")

        summary = client.get_usage_summary()
        assert summary is not None
        assert summary["total_tokens"] == 150
        assert summary["request_count"] == 1

    @patch("bmlib.llm.client.LLMClient.chat")
    def test_generate(self, mock_bmlib_chat):
        """Test generate method (wraps chat)."""
        mock_bmlib_chat.return_value = self._make_bmlib_response(
            content="Generated text", input_tokens=10, output_tokens=20,
        )

        client = LLMClient(track_usage=False)
        response = client.generate("Complete this:", model="test-model")

        assert response.content == "Generated text"
        mock_bmlib_chat.assert_called_once()

    @patch("bmlib.llm.client.LLMClient.embed")
    def test_embed(self, mock_bmlib_embed):
        """Test embed method."""
        from bmlib.llm import EmbeddingResponse as BmlibEmbedResponse
        mock_bmlib_embed.return_value = BmlibEmbedResponse(
            embedding=[0.1, 0.2, 0.3],
            model="embed-model",
            dimensions=3,
        )

        client = LLMClient(track_usage=False)
        response = client.embed("Test text", model="embed-model")

        assert len(response.embedding) == 3
        assert response.dimensions == 3

    @patch("bmlib.llm.client.LLMClient.test_connection")
    def test_test_provider(self, mock_test):
        """Test provider connectivity check."""
        mock_test.return_value = True

        client = LLMClient()
        assert client.test_provider(Provider.OLLAMA) is True

    @patch("bmlib.llm.client.LLMClient.list_models")
    def test_list_models(self, mock_list):
        """Test model listing."""
        mock_list.return_value = ["model-a", "model-b"]

        client = LLMClient()
        models = client.list_models(Provider.OLLAMA)

        assert "ollama" in models
        assert models["ollama"] == ["model-a", "model-b"]


class TestModelStringRouting:
    """
    Model strings forwarded to bmlib must carry an explicit provider prefix.

    bmlib's LLMClient._parse_model_string splits on the first colon with no
    known-prefix check, so an unqualified "gpt-oss:20b" resolves to provider
    "gpt-oss" and raises ValueError. Every model name this project ships with
    contains a colon, so qualifying the string is mandatory, not cosmetic.
    """

    def setup_method(self):
        """Reset providers before each test."""
        reset_all_providers()
        reset_global_tracker()

    @staticmethod
    def _resolve_as_bmlib_would(model_str):
        """
        Resolve a model string exactly the way bmlib will resolve it.

        Asserting through bmlib's own parser pins the real contract rather
        than a particular string format, so the test survives a change in
        how bmlibrarian spells the prefix.
        """
        from bmlib.llm.client import LLMClient as BmlibLLMClient

        return BmlibLLMClient(default_provider="ollama")._parse_model_string(model_str)

    @staticmethod
    def _make_bmlib_response(model="test-model"):
        """Create a mock bmlib LLMResponse."""
        from bmlib.llm import LLMResponse as BmlibResponse

        return BmlibResponse(
            content="Hello!", model=model, input_tokens=10, output_tokens=5,
        )

    @pytest.mark.parametrize(
        "model,expected_name",
        [
            ("gpt-oss:20b", "gpt-oss:20b"),
            ("medgemma4B_it_q8:latest", "medgemma4B_it_q8:latest"),
            ("plain-model", "plain-model"),
            ("ollama:gpt-oss:20b", "gpt-oss:20b"),
        ],
    )
    @patch("bmlib.llm.client.LLMClient.chat")
    def test_chat_forwards_ollama_qualified_model(
        self, mock_bmlib_chat, model, expected_name,
    ):
        """Colon-bearing Ollama model names must reach bmlib provider-qualified."""
        mock_bmlib_chat.return_value = self._make_bmlib_response()

        client = LLMClient(track_usage=False)
        client.chat([LLMMessage(role="user", content="Hi")], model=model)

        forwarded = mock_bmlib_chat.call_args.kwargs["model"]
        assert self._resolve_as_bmlib_would(forwarded) == ("ollama", expected_name)

    @patch("bmlib.llm.client.LLMClient.chat")
    def test_chat_forwards_anthropic_qualified_model(self, mock_bmlib_chat):
        """Non-Ollama providers keep their own prefix rather than being coerced."""
        mock_bmlib_chat.return_value = self._make_bmlib_response(model="claude-3-opus")

        client = LLMClient(track_usage=False)
        client.chat(
            [LLMMessage(role="user", content="Hi")], model="anthropic:claude-3-opus",
        )

        forwarded = mock_bmlib_chat.call_args.kwargs["model"]
        assert self._resolve_as_bmlib_would(forwarded) == ("anthropic", "claude-3-opus")

    @patch("bmlib.llm.client.LLMClient.embed")
    def test_embed_forwards_ollama_qualified_default_model(self, mock_bmlib_embed):
        """
        The configured default embedding model contains a colon.

        Unqualified, bmlib resolves it to provider "snowflake-arctic-embed2"
        and every embedding call — and so all semantic search — fails.
        """
        from bmlib.llm import EmbeddingResponse as BmlibEmbedResponse

        mock_bmlib_embed.return_value = BmlibEmbedResponse(
            embedding=[0.1, 0.2, 0.3], model=DEFAULT_EMBEDDING_MODEL, dimensions=3,
        )

        client = LLMClient(track_usage=False)
        client.embed("Test text")

        forwarded = mock_bmlib_embed.call_args.kwargs["model"]
        assert self._resolve_as_bmlib_would(forwarded) == (
            "ollama", DEFAULT_EMBEDDING_MODEL,
        )


class TestMaxTokensDefaulting:
    """
    An unset max_tokens must not silently cap generation.

    bmlib always forwards max_tokens to the provider (Ollama receives it as
    num_predict), whereas bmlibrarian's previous Ollama provider omitted the
    option unless a limit was explicitly requested. Long-form output from the
    reporting and editor agents relies on there being no default ceiling.
    """

    def setup_method(self):
        """Reset providers before each test."""
        reset_all_providers()
        reset_global_tracker()

    @staticmethod
    def _make_bmlib_response():
        """Create a mock bmlib LLMResponse."""
        from bmlib.llm import LLMResponse as BmlibResponse

        return BmlibResponse(
            content="Hello!", model="test-model", input_tokens=10, output_tokens=5,
        )

    @patch("bmlib.llm.client.LLMClient.chat")
    def test_unset_max_tokens_does_not_cap_ollama(self, mock_bmlib_chat):
        """Ollama must be told to generate without a ceiling."""
        mock_bmlib_chat.return_value = self._make_bmlib_response()

        client = LLMClient(track_usage=False)
        client.chat([LLMMessage(role="user", content="Hi")], model="gpt-oss:20b")

        assert (
            mock_bmlib_chat.call_args.kwargs["max_tokens"]
            == OLLAMA_UNLIMITED_MAX_TOKENS
        )

    @patch("bmlib.llm.client.LLMClient.chat")
    def test_unset_max_tokens_uses_documented_default_for_anthropic(
        self, mock_bmlib_chat,
    ):
        """Anthropic requires a positive max_tokens, so a default applies there."""
        mock_bmlib_chat.return_value = self._make_bmlib_response()

        client = LLMClient(track_usage=False)
        client.chat(
            [LLMMessage(role="user", content="Hi")], model="anthropic:claude-3-opus",
        )

        assert (
            mock_bmlib_chat.call_args.kwargs["max_tokens"]
            == DEFAULT_ANTHROPIC_MAX_TOKENS
        )

    @patch("bmlib.llm.client.LLMClient.chat")
    def test_explicit_max_tokens_is_honoured(self, mock_bmlib_chat):
        """An explicit limit must be passed through unchanged."""
        mock_bmlib_chat.return_value = self._make_bmlib_response()

        client = LLMClient(track_usage=False)
        client.chat(
            [LLMMessage(role="user", content="Hi")], model="gpt-oss:20b", max_tokens=256,
        )

        assert mock_bmlib_chat.call_args.kwargs["max_tokens"] == 256


class TestUsageAttribution:
    """
    Token usage must be attributed to the operation that incurred it.

    generate() delegates to chat() internally, but cost reporting needs to
    distinguish the two — UsageRecord.operation is documented as one of
    "chat", "generate" or "embed".
    """

    def setup_method(self):
        """Reset providers before each test."""
        reset_all_providers()
        reset_global_tracker()

    @staticmethod
    def _make_bmlib_response():
        """Create a mock bmlib LLMResponse."""
        from bmlib.llm import LLMResponse as BmlibResponse

        return BmlibResponse(
            content="Hello!", model="test-model", input_tokens=10, output_tokens=5,
        )

    @patch("bmlib.llm.client.LLMClient.chat")
    def test_chat_records_chat_operation(self, mock_bmlib_chat):
        """A chat call is attributed to "chat"."""
        mock_bmlib_chat.return_value = self._make_bmlib_response()

        client = LLMClient(track_usage=True)
        client.chat([LLMMessage(role="user", content="Hi")], model="gpt-oss:20b")

        operations = [r.operation for r in get_token_tracker().get_records()]
        assert operations == ["chat"]

    @patch("bmlib.llm.client.LLMClient.chat")
    def test_generate_records_generate_operation(self, mock_bmlib_chat):
        """Delegating to chat() must not relabel the operation."""
        mock_bmlib_chat.return_value = self._make_bmlib_response()

        client = LLMClient(track_usage=True)
        client.generate("Complete this:", model="gpt-oss:20b")

        operations = [r.operation for r in get_token_tracker().get_records()]
        assert operations == ["generate"]


class TestProviderRegistry:
    """Tests for provider registry."""

    def setup_method(self):
        """Reset providers before each test."""
        reset_all_providers()

    @patch("bmlibrarian.llm.providers._bmlib_get_provider")
    def test_is_provider_available_unpacks_provider_tuple(self, mock_get):
        """
        bmlib's BaseProvider.test_connection returns (ok, message).

        This is the provider-level contract, unlike the client-level
        test_connection(name) which returns a plain bool.
        """
        mock_get.return_value = Mock(test_connection=Mock(return_value=(True, "ok")))
        assert is_provider_available(Provider.OLLAMA) is True

    @patch("bmlibrarian.llm.providers._bmlib_get_provider")
    def test_is_provider_available_reports_failure(self, mock_get):
        """A failed connection is reported as unavailable."""
        mock_get.return_value = Mock(
            test_connection=Mock(return_value=(False, "refused")),
        )
        assert is_provider_available(Provider.OLLAMA) is False

    def test_reset_all_providers(self):
        """Test that reset clears all providers."""
        from bmlibrarian.llm.providers import get_available_providers

        # Initially empty after reset
        assert len(get_available_providers()) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
