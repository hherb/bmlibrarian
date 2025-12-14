"""
Base class for BMLibrarian Lite agents.

Provides common functionality for LLM communication and configuration.
All Lite agents inherit from this base class to share the unified LLM client
interface and configuration management.
"""

import logging
from typing import Optional

from bmlibrarian.llm import LLMClient, LLMMessage
from ..config import LiteConfig

logger = logging.getLogger(__name__)


class LiteBaseAgent:
    """
    Base class for all Lite agents.

    Provides common functionality for LLM communication and configuration.
    Agents inheriting from this class gain access to:
    - Configured LLM client with provider selection
    - Helper methods for creating chat messages
    - Configuration management

    Attributes:
        config: Lite configuration instance
    """

    def __init__(
        self,
        config: Optional[LiteConfig] = None,
        llm_client: Optional[LLMClient] = None,
    ) -> None:
        """
        Initialize the base agent.

        Args:
            config: Lite configuration (uses defaults if not provided)
            llm_client: Optional pre-configured LLM client
        """
        self.config = config or LiteConfig()
        self._llm_client = llm_client

    @property
    def llm_client(self) -> LLMClient:
        """
        Get or create LLM client.

        The client is lazily created on first access.

        Returns:
            Configured LLMClient instance
        """
        if self._llm_client is None:
            self._llm_client = LLMClient()
        return self._llm_client

    def _get_model(self) -> str:
        """
        Get the configured model string.

        Combines provider and model name into the format expected
        by LLMClient (e.g., "anthropic:claude-3-haiku-20240307").

        Returns:
            Model string with provider prefix
        """
        provider = self.config.llm.provider
        model = self.config.llm.model
        return f"{provider}:{model}"

    def _chat(
        self,
        messages: list[LLMMessage],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        json_mode: bool = False,
    ) -> str:
        """
        Send a chat request to the LLM.

        Args:
            messages: List of conversation messages
            temperature: Optional temperature override
            max_tokens: Optional max tokens override
            json_mode: Request JSON-formatted output

        Returns:
            Response text from the LLM
        """
        response = self.llm_client.chat(
            messages=messages,
            model=self._get_model(),
            temperature=temperature or self.config.llm.temperature,
            max_tokens=max_tokens or self.config.llm.max_tokens,
            json_mode=json_mode,
        )
        return response.content

    def _create_system_message(self, content: str) -> LLMMessage:
        """
        Create a system message for the LLM.

        Args:
            content: System prompt content

        Returns:
            LLMMessage with role="system"
        """
        return LLMMessage(role="system", content=content)

    def _create_user_message(self, content: str) -> LLMMessage:
        """
        Create a user message for the LLM.

        Args:
            content: User message content

        Returns:
            LLMMessage with role="user"
        """
        return LLMMessage(role="user", content=content)

    def _create_assistant_message(self, content: str) -> LLMMessage:
        """
        Create an assistant message for conversation history.

        Args:
            content: Assistant message content

        Returns:
            LLMMessage with role="assistant"
        """
        return LLMMessage(role="assistant", content=content)

    def test_connection(self) -> bool:
        """
        Test if the LLM provider is available.

        Returns:
            True if connection is successful
        """
        try:
            # Simple test message
            messages = [self._create_user_message("Hello")]
            self._chat(messages, max_tokens=10)
            return True
        except Exception as e:
            logger.warning(f"LLM connection test failed: {e}")
            return False
