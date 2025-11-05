"""
Workflow Agent Management Module

Handles agent initialization, setup, and connection testing.
"""

import logging
import os
from typing import Optional
from bmlibrarian.agents import AgentFactory, AgentOrchestrator

logger = logging.getLogger('bmlibrarian.workflow.agents')


class WorkflowAgentManager:
    """Manages agent lifecycle and connection testing."""

    def __init__(self, config, ui, query_processor):
        self.config = config
        self.ui = ui
        self.query_processor = query_processor

        # Agent components
        self.orchestrator: Optional[AgentOrchestrator] = None
        self.query_agent = None
        self.scoring_agent = None
        self.citation_agent = None
        self.reporting_agent = None
        self.counterfactual_agent = None
        self.editor_agent = None

        # Audit tracking components
        self.audit_conn = None
        self.audit_enabled = False

    def _setup_audit_tracking(self) -> bool:
        """Setup audit tracking database connection."""
        try:
            import psycopg
            from dotenv import load_dotenv

            # Load environment variables
            load_dotenv()

            # Get database connection parameters from environment
            db_name = os.getenv('POSTGRES_DB', 'knowledgebase')
            db_user = os.getenv('POSTGRES_USER', 'hherb')
            db_password = os.getenv('POSTGRES_PASSWORD', '')
            db_host = os.getenv('POSTGRES_HOST', 'localhost')
            db_port = os.getenv('POSTGRES_PORT', '5432')

            # Create connection
            conn_params = {
                'dbname': db_name,
                'user': db_user,
                'host': db_host,
                'port': db_port
            }
            if db_password:
                conn_params['password'] = db_password

            self.audit_conn = psycopg.connect(**conn_params)
            self.audit_enabled = True

            logger.info(f"Audit tracking enabled (database: {db_name})")
            return True

        except Exception as e:
            logger.warning(f"Could not enable audit tracking: {e}")
            logger.info("Continuing without audit tracking")
            self.audit_enabled = False
            return False

    def setup_agents(self) -> bool:
        """Initialize and test all agents."""
        try:
            self.ui.show_progress_message("Setting up BMLibrarian agents...")

            # Setup audit tracking (optional - non-fatal if fails)
            self._setup_audit_tracking()

            # Create orchestrator
            self.orchestrator = AgentOrchestrator(
                max_workers=self.config.max_workers,
                polling_interval=self.config.polling_interval
            )

            # Use AgentFactory to create all agents with config from model_config
            config_dict = self.config.model_config if self.config.model_config else {}

            agents = AgentFactory.create_all_agents(
                orchestrator=self.orchestrator,
                config=config_dict,
                auto_register=True,
                audit_conn=self.audit_conn  # Pass audit connection
            )

            # Extract individual agents
            self.query_agent = agents.get('query_agent')
            self.scoring_agent = agents.get('scoring_agent')
            self.citation_agent = agents.get('citation_agent')
            self.reporting_agent = agents.get('reporting_agent')
            self.counterfactual_agent = agents.get('counterfactual_agent')
            self.editor_agent = agents.get('editor_agent')

            # Set query agent in processor
            self.query_processor.set_query_agent(self.query_agent)

            self.ui.show_success_message("Agents initialized")

            # Test connections
            return self._test_service_connections()

        except Exception as e:
            self.ui.show_error_message(f"Failed to setup agents: {e}")
            return False
    
    def _test_service_connections(self) -> bool:
        """Test all service connections."""
        self.ui.show_progress_message("Testing service connections...")
        
        # Test database connection
        db_connected = self.query_processor.test_database_connection()
        status_db = "✅ Connected" if db_connected else "❌ Failed"
        print(f"   Database: {status_db}")
        
        # Test Ollama connections
        scoring_connected = self.scoring_agent.test_connection() if self.scoring_agent else False
        status_scoring = "✅ Connected" if scoring_connected else "❌ Failed"
        print(f"   Scoring Agent (Ollama): {status_scoring}")
        
        citation_connected = self.citation_agent.test_connection() if self.citation_agent else False
        status_citation = "✅ Connected" if citation_connected else "❌ Failed"
        print(f"   Citation Agent (Ollama): {status_citation}")
        
        reporting_connected = self.reporting_agent.test_connection() if self.reporting_agent else False
        status_reporting = "✅ Connected" if reporting_connected else "❌ Failed"
        print(f"   Reporting Agent (Ollama): {status_reporting}")
        
        counterfactual_connected = self.counterfactual_agent.test_connection() if self.counterfactual_agent else False
        status_counterfactual = "✅ Connected" if counterfactual_connected else "❌ Failed"
        print(f"   Counterfactual Agent (Ollama): {status_counterfactual}")
        
        editor_connected = self.editor_agent.test_connection() if self.editor_agent else False
        status_editor = "✅ Connected" if editor_connected else "❌ Failed"
        print(f"   Editor Agent (Ollama): {status_editor}")
        
        # Check if all critical services are available
        if not (db_connected and scoring_connected and citation_connected and reporting_connected and counterfactual_connected and editor_connected):
            self.ui.show_warning_message("Some AI services are unavailable. Please ensure:")
            print("   - Ollama is running: ollama serve")
            print("   - Required models are installed:")
            print("     ollama pull gpt-oss:20b")
            print("     ollama pull medgemma4B_it_q8:latest")
            return False
        
        self.ui.show_success_message("All services connected and ready!")
        return True
    
    def start_orchestrator(self):
        """Start the agent orchestrator."""
        if self.orchestrator:
            self.orchestrator.start_processing()
    
    def stop_orchestrator(self):
        """Stop the agent orchestrator."""
        if self.orchestrator:
            self.orchestrator.stop_processing()

    def cleanup(self):
        """Cleanup resources including audit connection."""
        if self.audit_conn:
            try:
                self.audit_conn.close()
                logger.info("Closed audit database connection")
            except Exception as e:
                logger.warning(f"Error closing audit connection: {e}")