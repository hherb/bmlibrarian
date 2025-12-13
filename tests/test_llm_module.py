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
    """Tests for LLMClient (with mocked providers)."""

    def setup_method(self):
        """Reset providers before each test."""
        reset_all_providers()
        reset_global_tracker()

    @patch("bmlibrarian.llm.client.get_provider")
    def test_chat_ollama(self, mock_get_provider):
        """Test chat with Ollama provider."""
        mock_provider = Mock()
        mock_provider.chat.return_value = LLMResponse(
            content="Hello!",
            model="test-model",
            provider=Provider.OLLAMA,
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
        )
        mock_get_provider.return_value = mock_provider

        client = LLMClient(track_usage=False)
        messages = [LLMMessage(role="user", content="Hi")]
        response = client.chat(messages, model="test-model")

        assert response.content == "Hello!"
        mock_provider.chat.assert_called_once()

    @patch("bmlibrarian.llm.client.get_provider")
    def test_chat_anthropic(self, mock_get_provider):
        """Test chat with Anthropic provider."""
        mock_provider = Mock()
        mock_provider.chat.return_value = LLMResponse(
            content="Hello from Claude!",
            model="claude-3-opus",
            provider=Provider.ANTHROPIC,
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
        )
        mock_get_provider.return_value = mock_provider

        client = LLMClient(track_usage=False)
        messages = [LLMMessage(role="user", content="Hi")]
        response = client.chat(messages, model="anthropic:claude-3-opus")

        assert response.content == "Hello from Claude!"
        assert response.provider == Provider.ANTHROPIC

    @patch("bmlibrarian.llm.client.get_provider")
    def test_fallback_on_failure(self, mock_get_provider):
        """Test fallback to Ollama when primary provider fails."""
        # Primary provider (Anthropic) fails
        mock_anthropic = Mock()
        mock_anthropic.chat.side_effect = ConnectionError("API error")

        # Fallback provider (Ollama) succeeds
        mock_ollama = Mock()
        mock_ollama.chat.return_value = LLMResponse(
            content="Fallback response",
            model="fallback-model",
            provider=Provider.OLLAMA,
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
        )

        def get_provider_side_effect(provider_type, **kwargs):
            if provider_type == Provider.ANTHROPIC:
                return mock_anthropic
            return mock_ollama

        mock_get_provider.side_effect = get_provider_side_effect

        client = LLMClient(
            fallback_model="fallback-model",
            track_usage=False,
        )
        messages = [LLMMessage(role="user", content="Hi")]
        response = client.chat(messages, model="anthropic:claude-3-opus")

        assert response.content == "Fallback response"
        assert response.provider == Provider.OLLAMA

    @patch("bmlibrarian.llm.client.get_provider")
    def test_no_fallback_for_ollama(self, mock_get_provider):
        """Test that Ollama failures don't trigger Ollama fallback."""
        mock_provider = Mock()
        mock_provider.chat.side_effect = ConnectionError("Ollama error")
        mock_get_provider.return_value = mock_provider

        client = LLMClient(
            fallback_model="fallback-model",
            track_usage=False,
        )
        messages = [LLMMessage(role="user", content="Hi")]

        with pytest.raises(ConnectionError):
            client.chat(messages, model="test-model")

    @patch("bmlibrarian.llm.client.get_provider")
    def test_usage_tracking(self, mock_get_provider):
        """Test that usage is tracked when enabled."""
        mock_provider = Mock()
        mock_provider.chat.return_value = LLMResponse(
            content="Hello!",
            model="test-model",
            provider=Provider.OLLAMA,
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
        )
        mock_get_provider.return_value = mock_provider

        reset_global_tracker()
        client = LLMClient(track_usage=True)
        messages = [LLMMessage(role="user", content="Hi")]
        client.chat(messages, model="test-model")

        summary = client.get_usage_summary()
        assert summary is not None
        assert summary["total_tokens"] == 150
        assert summary["request_count"] == 1

    @patch("bmlibrarian.llm.client.get_provider")
    def test_generate(self, mock_get_provider):
        """Test generate method."""
        mock_provider = Mock()
        mock_provider.generate.return_value = LLMResponse(
            content="Generated text",
            model="test-model",
            provider=Provider.OLLAMA,
            prompt_tokens=10,
            completion_tokens=20,
            total_tokens=30,
        )
        mock_get_provider.return_value = mock_provider

        client = LLMClient(track_usage=False)
        response = client.generate("Complete this:", model="test-model")

        assert response.content == "Generated text"
        mock_provider.generate.assert_called_once()

    @patch("bmlibrarian.llm.client.get_provider")
    def test_embed(self, mock_get_provider):
        """Test embed method."""
        mock_provider = Mock()
        mock_provider.embed.return_value = EmbeddingResponse(
            embedding=[0.1, 0.2, 0.3],
            model="embed-model",
            provider=Provider.OLLAMA,
            dimensions=3,
        )
        mock_get_provider.return_value = mock_provider

        client = LLMClient(track_usage=False)
        response = client.embed("Test text", model="embed-model")

        assert len(response.embedding) == 3
        assert response.dimensions == 3

    @patch("bmlibrarian.llm.client.get_provider")
    def test_test_provider(self, mock_get_provider):
        """Test provider connectivity check."""
        mock_provider = Mock()
        mock_provider.test_connection.return_value = True
        mock_get_provider.return_value = mock_provider

        client = LLMClient()
        assert client.test_provider(Provider.OLLAMA) is True

    @patch("bmlibrarian.llm.client.get_provider")
    def test_list_models(self, mock_get_provider):
        """Test model listing."""
        mock_provider = Mock()
        mock_provider.list_models.return_value = ["model-a", "model-b"]
        mock_get_provider.return_value = mock_provider

        client = LLMClient()
        models = client.list_models(Provider.OLLAMA)

        assert "ollama" in models
        assert models["ollama"] == ["model-a", "model-b"]


class TestProviderRegistry:
    """Tests for provider registry."""

    def setup_method(self):
        """Reset providers before each test."""
        reset_all_providers()

    def test_reset_all_providers(self):
        """Test that reset clears all providers."""
        from bmlibrarian.llm.providers import get_available_providers

        # Initially empty after reset
        assert len(get_available_providers()) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
