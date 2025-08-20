"""
Base Agent Class for BMLibrarian AI Agents

Provides common functionality for all AI agents including:
- Ollama connection management
- Model configuration
- Callback system for progress updates
- Error handling patterns
- Connection testing utilities
- Queue integration for large-scale processing
"""

import logging
import ollama
from typing import Optional, Callable, Dict, Any, TYPE_CHECKING
from abc import ABC, abstractmethod

if TYPE_CHECKING:
    from .orchestrator import AgentOrchestrator


logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    """
    Base class for all BMLibrarian AI agents.
    
    Provides common functionality including Ollama integration,
    callback management, and standardized error handling.
    """
    
    def __init__(
        self,
        model: str,
        host: str = "http://localhost:11434",
        temperature: float = 0.1,
        top_p: float = 0.9,
        callback: Optional[Callable[[str, str], None]] = None,
        orchestrator: Optional["AgentOrchestrator"] = None,
        show_model_info: bool = True
    ):
        """
        Initialize the base agent.
        
        Args:
            model: The name of the Ollama model to use
            host: The Ollama server host URL (default: http://localhost:11434)
            temperature: Model temperature for response randomness (0.0-1.0)
            top_p: Model top-p sampling parameter (0.0-1.0)
            callback: Optional callback function called with (step, data) for progress updates
            orchestrator: Optional orchestrator for queue-based processing
            show_model_info: Whether to display model information on initialization
        """
        self.model = model
        self.host = host
        self.temperature = temperature
        self.top_p = top_p
        self.callback = callback
        self.client = ollama.Client(host=host)
        self.orchestrator = orchestrator
        
        # Display model information if requested
        if show_model_info:
            self._display_model_info()
    
    def _display_model_info(self) -> None:
        """Display model information to terminal."""
        agent_type = self.get_agent_type() if hasattr(self, 'get_agent_type') else "Agent"
        print(f"🤖 {agent_type} initialized with model: {self.model}")
    
    def _call_callback(self, step: str, data: str) -> None:
        """
        Call the callback function if provided.
        
        Args:
            step: The current processing step
            data: Data associated with the step
        """
        if self.callback:
            try:
                self.callback(step, data)
            except Exception as e:
                logger.warning(f"Callback function failed for step '{step}': {e}")
    
    def _get_ollama_options(self, **overrides) -> Dict[str, Any]:
        """
        Get Ollama options with defaults and overrides.
        
        Args:
            **overrides: Option overrides to apply
            
        Returns:
            Dictionary of Ollama options
        """
        options = {
            'temperature': self.temperature,
            'top_p': self.top_p,
            'num_predict': 100  # Default response length limit
        }
        options.update(overrides)
        return options
    
    def _make_ollama_request(
        self,
        messages: list,
        system_prompt: Optional[str] = None,
        **ollama_options
    ) -> str:
        """
        Make a request to Ollama with standardized error handling.
        
        Args:
            messages: List of message dictionaries for the conversation
            system_prompt: Optional system prompt to prepend
            **ollama_options: Additional Ollama options
            
        Returns:
            The model's response content
            
        Raises:
            ConnectionError: If unable to connect to Ollama
            ValueError: If the response is invalid
        """
        try:
            # Prepend system message if provided
            if system_prompt:
                messages = [{'role': 'system', 'content': system_prompt}] + messages
            
            # Get options with any overrides
            options = self._get_ollama_options(**ollama_options)
            
            response = self.client.chat(
                model=self.model,
                messages=messages,
                options=options
            )
            
            content = response['message']['content']
            if not content or not content.strip():
                raise ValueError("Empty response from model")
                
            return content.strip()
            
        except ollama.ResponseError as e:
            logger.error(f"Ollama response error: {e}")
            raise ConnectionError(f"Failed to get response from Ollama: {e}")
        except Exception as e:
            logger.error(f"Unexpected error in Ollama request: {e}")
            raise
    
    def test_connection(self) -> bool:
        """
        Test the connection to Ollama server and verify model availability.
        
        Returns:
            True if connection is successful and model is available
        """
        try:
            models = self.client.list()
            available_models = [model.model for model in models.models]
            
            if self.model not in available_models:
                logger.warning(f"Model {self.model} not found. Available models: {available_models}")
                return False
                
            logger.info(f"Successfully connected to Ollama. Model {self.model} is available.")
            return True
            
        except Exception as e:
            logger.error(f"Failed to connect to Ollama: {e}")
            return False
    
    def get_available_models(self) -> list[str]:
        """
        Get list of available models from Ollama.
        
        Returns:
            List of available model names
            
        Raises:
            ConnectionError: If unable to connect to Ollama
        """
        try:
            models = self.client.list()
            return [model.model for model in models.models]
        except Exception as e:
            logger.error(f"Failed to get available models: {e}")
            raise ConnectionError(f"Failed to connect to Ollama: {e}")
    
    def set_callback(self, callback: Optional[Callable[[str, str], None]]) -> None:
        """
        Set or update the callback function.
        
        Args:
            callback: New callback function or None to disable callbacks
        """
        self.callback = callback
    
    def set_orchestrator(self, orchestrator: Optional["AgentOrchestrator"]) -> None:
        """
        Set or update the orchestrator for queue-based processing.
        
        Args:
            orchestrator: Orchestrator instance or None to disable queue processing
        """
        self.orchestrator = orchestrator
    
    def submit_task(self,
                   method_name: str,
                   data: Dict[str, Any],
                   target_agent: Optional[str] = None,
                   priority: Optional[Any] = None) -> Optional[str]:
        """
        Submit a task to the orchestrator queue.
        
        Args:
            method_name: Method to call on the target agent
            data: Task data/parameters
            target_agent: Target agent type (defaults to self)
            priority: Task priority (uses orchestrator default if None)
            
        Returns:
            Task ID if orchestrator is available, None otherwise
        """
        if not self.orchestrator:
            return None
        
        from .queue_manager import TaskPriority
        
        return self.orchestrator.submit_task(
            target_agent=target_agent or self.get_agent_type(),
            method_name=method_name,
            data=data,
            source_agent=self.get_agent_type(),
            priority=priority or TaskPriority.NORMAL
        )
    
    def submit_batch_tasks(self,
                          method_name: str,
                          data_list: list[Dict[str, Any]],
                          target_agent: Optional[str] = None,
                          priority: Optional[Any] = None) -> Optional[list[str]]:
        """
        Submit multiple tasks to the orchestrator queue.
        
        Args:
            method_name: Method to call on the target agent
            data_list: List of task data dictionaries
            target_agent: Target agent type (defaults to self)
            priority: Task priority (uses orchestrator default if None)
            
        Returns:
            List of task IDs if orchestrator is available, None otherwise
        """
        if not self.orchestrator:
            return None
        
        from .queue_manager import TaskPriority
        
        return self.orchestrator.submit_batch_tasks(
            target_agent=target_agent or self.get_agent_type(),
            method_name=method_name,
            data_list=data_list,
            source_agent=self.get_agent_type(),
            priority=priority or TaskPriority.NORMAL
        )
    
    @abstractmethod
    def get_agent_type(self) -> str:
        """
        Get the type/name of this agent.
        
        Returns:
            String identifier for the agent type
        """
        pass