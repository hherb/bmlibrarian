"""Agent Factory for unified agent initialization.

This module provides a centralized factory for creating and configuring
BMLibrarian agents with proper parameter filtering and configuration management.

Eliminates duplicate agent initialization code across GUI and CLI workflows.
"""

import logging
from typing import Dict, Any, Optional, Callable

from .query_agent import QueryAgent
from .scoring_agent import DocumentScoringAgent
from .citation_agent import CitationFinderAgent
from .reporting_agent import ReportingAgent
from .counterfactual_agent import CounterfactualAgent
from .editor_agent import EditorAgent
from .orchestrator import AgentOrchestrator

logger = logging.getLogger(__name__)


class AgentFactory:
    """Factory for creating BMLibrarian agents with proper configuration.

    Provides centralized agent initialization with:
    - Automatic parameter filtering for each agent type
    - Configuration management from BMLibrarian config system
    - Orchestrator integration
    - Consistent error handling

    Examples:
        >>> # Create all agents at once
        >>> agents = AgentFactory.create_all_agents()
        >>> query_agent = agents['query_agent']

        >>> # Create single agent with custom config
        >>> scoring_agent = AgentFactory.create_agent(
        ...     'scoring',
        ...     model='gpt-oss:20b',
        ...     temperature=0.3
        ... )

        >>> # Create agents with shared orchestrator
        >>> orchestrator = AgentOrchestrator(max_workers=4)
        >>> agents = AgentFactory.create_all_agents(orchestrator=orchestrator)
    """

    # Supported parameters for each agent type
    # Only these parameters will be passed to agent constructors
    SUPPORTED_PARAMS = {
        'query': {'model', 'host', 'temperature', 'top_p', 'callback', 'show_model_info', 'orchestrator'},
        'scoring': {'model', 'host', 'temperature', 'top_p', 'callback', 'show_model_info', 'orchestrator'},
        'citation': {'model', 'host', 'temperature', 'top_p', 'callback', 'show_model_info', 'orchestrator'},
        'reporting': {'model', 'host', 'temperature', 'top_p', 'callback', 'show_model_info', 'orchestrator'},
        'counterfactual': {'model', 'host', 'temperature', 'top_p', 'callback', 'show_model_info', 'orchestrator'},
        'editor': {'model', 'host', 'temperature', 'top_p', 'callback', 'show_model_info', 'orchestrator'}
    }

    # Agent class mapping
    AGENT_CLASSES = {
        'query': QueryAgent,
        'scoring': DocumentScoringAgent,
        'citation': CitationFinderAgent,
        'reporting': ReportingAgent,
        'counterfactual': CounterfactualAgent,
        'editor': EditorAgent
    }

    # Default orchestrator names for agent registration
    AGENT_REGISTRY_NAMES = {
        'query': 'query_agent',
        'scoring': 'document_scoring_agent',
        'citation': 'citation_finder_agent',
        'reporting': 'reporting_agent',
        'counterfactual': 'counterfactual_agent',
        'editor': 'editor_agent'
    }

    @staticmethod
    def filter_agent_config(agent_config: Dict[str, Any], agent_type: str) -> Dict[str, Any]:
        """Filter agent configuration to only include supported parameters.

        Args:
            agent_config: Raw configuration dictionary
            agent_type: Agent type ('query', 'scoring', 'citation', etc.)

        Returns:
            Filtered configuration with only supported parameters

        Examples:
            >>> config = {'temperature': 0.3, 'top_p': 0.9, 'unsupported': 'value'}
            >>> filtered = AgentFactory.filter_agent_config(config, 'query')
            >>> 'temperature' in filtered
            True
            >>> 'unsupported' in filtered
            False
        """
        allowed_params = AgentFactory.SUPPORTED_PARAMS.get(agent_type, set())
        return {k: v for k, v in agent_config.items() if k in allowed_params}

    @staticmethod
    def create_agent(agent_type: str, orchestrator: Optional[AgentOrchestrator] = None,
                    **kwargs) -> Any:
        """Create a single agent with filtered configuration.

        Args:
            agent_type: Type of agent ('query', 'scoring', 'citation', etc.)
            orchestrator: Optional orchestrator for agent registration
            **kwargs: Agent configuration parameters (will be filtered)

        Returns:
            Initialized agent instance

        Raises:
            ValueError: If agent_type is not recognized

        Examples:
            >>> agent = AgentFactory.create_agent('query', model='gpt-oss:20b')
            >>> agent.model
            'gpt-oss:20b'
        """
        if agent_type not in AgentFactory.AGENT_CLASSES:
            raise ValueError(f"Unknown agent type: {agent_type}. "
                           f"Valid types: {list(AgentFactory.AGENT_CLASSES.keys())}")

        # Add orchestrator to kwargs if provided
        if orchestrator:
            kwargs['orchestrator'] = orchestrator

        # Filter configuration to supported parameters
        filtered_config = AgentFactory.filter_agent_config(kwargs, agent_type)

        # Create agent instance
        agent_class = AgentFactory.AGENT_CLASSES[agent_type]
        agent = agent_class(**filtered_config)

        logger.debug(f"Created {agent_type} agent with config: {filtered_config}")
        return agent

    @staticmethod
    def create_all_agents(orchestrator: Optional[AgentOrchestrator] = None,
                         config: Optional[Dict[str, Any]] = None,
                         callback: Optional[Callable] = None,
                         auto_register: bool = True) -> Dict[str, Any]:
        """Create all BMLibrarian agents with unified configuration.

        Args:
            orchestrator: Optional shared orchestrator (creates new if not provided)
            config: Optional configuration dictionary (uses BMLibrarian config if not provided)
            callback: Optional callback function for all agents
            auto_register: Automatically register agents with orchestrator (default: True)

        Returns:
            Dictionary with agent instances and orchestrator:
            {
                'query_agent': QueryAgent,
                'scoring_agent': DocumentScoringAgent,
                'citation_agent': CitationFinderAgent,
                'reporting_agent': ReportingAgent,
                'counterfactual_agent': CounterfactualAgent,
                'editor_agent': EditorAgent,
                'orchestrator': AgentOrchestrator
            }

        Examples:
            >>> # Use with BMLibrarian config system
            >>> agents = AgentFactory.create_all_agents()

            >>> # Use with custom config
            >>> custom_config = {
            ...     'ollama': {'host': 'http://localhost:11434'},
            ...     'models': {'query_agent': 'gpt-oss:20b'},
            ...     'agents': {'query': {'temperature': 0.3}}
            ... }
            >>> agents = AgentFactory.create_all_agents(config=custom_config)
        """
        # Create orchestrator if not provided
        if orchestrator is None:
            orchestrator = AgentOrchestrator(max_workers=2)
            logger.info("Created new orchestrator with max_workers=2")

        # Load configuration if not provided
        if config is None:
            try:
                from ..config import get_config, get_model, get_agent_config
                config_obj = get_config()
                ollama_config = config_obj.get_ollama_config()

                # Build config dictionary from BMLibrarian config system
                config = {
                    'ollama': ollama_config,
                    'models': {
                        'query_agent': get_model('query_agent'),
                        'scoring_agent': get_model('scoring_agent'),
                        'citation_agent': get_model('citation_agent'),
                        'reporting_agent': get_model('reporting_agent'),
                        'counterfactual_agent': get_model('counterfactual_agent'),
                        'editor_agent': get_model('editor_agent')
                    },
                    'agents': {
                        'query': get_agent_config('query'),
                        'scoring': get_agent_config('scoring'),
                        'citation': get_agent_config('citation'),
                        'reporting': get_agent_config('reporting'),
                        'counterfactual': get_agent_config('counterfactual'),
                        'editor': get_agent_config('editor')
                    }
                }
                logger.info("Loaded configuration from BMLibrarian config system")
            except ImportError as e:
                logger.warning(f"Could not import config module: {e}. Using defaults.")
                config = {}

        # Extract configuration components
        ollama_config = config.get('ollama', {})
        host = ollama_config.get('host', 'http://localhost:11434')
        models = config.get('models', {})
        agent_configs = config.get('agents', {})

        # Helper to build agent kwargs
        def build_agent_kwargs(agent_type: str, model_key: str) -> Dict[str, Any]:
            """Build kwargs for specific agent type."""
            kwargs = {
                'orchestrator': orchestrator,
                'host': host
            }

            # Add model if specified
            if model_key in models:
                kwargs['model'] = models[model_key]

            # Add agent-specific config
            if agent_type in agent_configs:
                kwargs.update(agent_configs[agent_type])

            # Add callback if provided
            if callback:
                kwargs['callback'] = callback

            return kwargs

        # Create all agents
        agents = {}

        try:
            agents['query_agent'] = AgentFactory.create_agent(
                'query', **build_agent_kwargs('query', 'query_agent')
            )
            agents['scoring_agent'] = AgentFactory.create_agent(
                'scoring', **build_agent_kwargs('scoring', 'scoring_agent')
            )
            agents['citation_agent'] = AgentFactory.create_agent(
                'citation', **build_agent_kwargs('citation', 'citation_agent')
            )
            agents['reporting_agent'] = AgentFactory.create_agent(
                'reporting', **build_agent_kwargs('reporting', 'reporting_agent')
            )
            agents['counterfactual_agent'] = AgentFactory.create_agent(
                'counterfactual', **build_agent_kwargs('counterfactual', 'counterfactual_agent')
            )
            agents['editor_agent'] = AgentFactory.create_agent(
                'editor', **build_agent_kwargs('editor', 'editor_agent')
            )

            # Add orchestrator to result
            agents['orchestrator'] = orchestrator

            # Register agents with orchestrator if requested
            if auto_register:
                for agent_type, agent_name in AgentFactory.AGENT_REGISTRY_NAMES.items():
                    agent_key = f"{agent_type}_agent"
                    if agent_key in agents:
                        orchestrator.register_agent(agent_name, agents[agent_key])
                        logger.debug(f"Registered {agent_key} as {agent_name}")

            logger.info(f"Created {len(agents) - 1} agents successfully")

            # Log model information
            for agent_name, agent in agents.items():
                if hasattr(agent, 'model') and agent_name != 'orchestrator':
                    logger.info(f"{agent_name} using model: {agent.model}")

            return agents

        except Exception as e:
            logger.error(f"Failed to create agents: {e}")
            raise

    @staticmethod
    def test_all_connections(agents: Dict[str, Any]) -> Dict[str, bool]:
        """Test connections for all agents.

        Args:
            agents: Dictionary of agent instances from create_all_agents()

        Returns:
            Dictionary mapping agent names to connection status (True/False)

        Examples:
            >>> agents = AgentFactory.create_all_agents()
            >>> results = AgentFactory.test_all_connections(agents)
            >>> results['query_agent']
            True
        """
        results = {}

        for agent_name, agent in agents.items():
            if agent_name == 'orchestrator':
                continue

            try:
                if hasattr(agent, 'test_connection'):
                    results[agent_name] = agent.test_connection()
                else:
                    results[agent_name] = False
                    logger.warning(f"{agent_name} does not support connection testing")
            except Exception as e:
                logger.error(f"Connection test failed for {agent_name}: {e}")
                results[agent_name] = False

        return results

    @staticmethod
    def print_connection_status(results: Dict[str, bool]) -> None:
        """Print formatted connection status for all agents.

        Args:
            results: Connection test results from test_all_connections()

        Examples:
            >>> agents = AgentFactory.create_all_agents()
            >>> results = AgentFactory.test_all_connections(agents)
            >>> AgentFactory.print_connection_status(results)
            ✅ query_agent: Connected
            ✅ scoring_agent: Connected
            ...
        """
        print("\nAgent Connection Status:")
        print("-" * 40)

        for agent_name, connected in sorted(results.items()):
            status = "✅ Connected" if connected else "❌ Failed"
            # Format agent name nicely
            display_name = agent_name.replace('_', ' ').title()
            print(f"   {display_name}: {status}")

        # Summary
        total = len(results)
        connected = sum(1 for status in results.values() if status)
        print("-" * 40)
        print(f"Total: {connected}/{total} agents connected")

        if connected < total:
            print("\n⚠️  Some agents failed to connect. Please check:")
            print("   - Ollama is running: ollama serve")
            print("   - Required models are installed")
