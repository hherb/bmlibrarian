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
        self.db_manager = None
        self.audit_conn = None
        self.audit_enabled = False

    def _run_pending_migrations(self) -> bool:
        """Run any pending database migrations.

        Returns:
            True if migrations were successful or already applied, False on error
        """
        try:
            from bmlibrarian.migrations import MigrationManager
            from pathlib import Path

            # Create migration manager from environment variables
            migration_manager = MigrationManager.from_env()
            if not migration_manager:
                logger.debug("Could not create MigrationManager (missing credentials)")
                return True  # Not fatal

            # Find migrations directory
            migrations_dir = Path(__file__).parent.parent.parent.parent / "migrations"
            if not migrations_dir.exists():
                logger.debug(f"Migrations directory not found: {migrations_dir}")
                return True  # Not fatal

            # Apply pending migrations (silent mode - use logging)
            applied_count = migration_manager.apply_pending_migrations(migrations_dir, silent=True)

            if applied_count > 0:
                logger.info(f"Applied {applied_count} pending database migration(s)")
            else:
                logger.debug("No pending migrations to apply")

            return True

        except Exception as e:
            logger.warning(f"Error running migrations: {e}")
            logger.debug("Continuing without migration check")
            return True  # Non-fatal

    def _setup_audit_tracking(self) -> bool:
        """Setup audit tracking using DatabaseManager.

        Gets a connection from the pool and keeps it for the session duration.
        This follows the pattern where CLI sessions are short-lived and don't
        need connection recycling.
        """
        try:
            from bmlibrarian.database import get_db_manager

            # Run pending migrations first (ensures audit schema exists)
            self._run_pending_migrations()

            # Get database manager (already handles connection pooling)
            self.db_manager = get_db_manager()

            # Get a connection from the pool for this session
            # Note: We manually manage this connection for the session duration
            # rather than using context manager, as audit trackers expect persistent connections
            self.audit_conn = self.db_manager._pool.getconn()

            # Verify audit schema exists
            with self.audit_conn.cursor() as cur:
                cur.execute("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.schemata
                        WHERE schema_name = 'audit'
                    )
                """)
                audit_exists = cur.fetchone()[0]

                if not audit_exists:
                    logger.warning("Audit schema does not exist in database")
                    logger.info("Migrations may have failed - check logs")
                    # Return connection to pool
                    self.db_manager._pool.putconn(self.audit_conn)
                    self.audit_conn = None
                    self.audit_enabled = False
                    return False

            self.audit_enabled = True
            logger.info("Audit tracking enabled (using DatabaseManager connection pool)")
            return True

        except Exception as e:
            logger.warning(f"Could not enable audit tracking: {e}")
            logger.info("Continuing without audit tracking")
            self.audit_enabled = False
            if self.audit_conn and self.db_manager:
                try:
                    self.db_manager._pool.putconn(self.audit_conn)
                except:
                    pass
            self.audit_conn = None
            self.db_manager = None
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
        if self.audit_conn and self.db_manager:
            try:
                # Return connection to the pool instead of closing
                self.db_manager._pool.putconn(self.audit_conn)
                logger.info("Returned audit connection to pool")
            except Exception as e:
                logger.warning(f"Error returning audit connection to pool: {e}")