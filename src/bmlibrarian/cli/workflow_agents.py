"""
Workflow Agent Management Module

Handles agent initialization, setup, and connection testing.
"""

import logging
from typing import Optional
from bmlibrarian.agents import (
    QueryAgent, DocumentScoringAgent, CitationFinderAgent, 
    ReportingAgent, CounterfactualAgent, EditorAgent, AgentOrchestrator
)

logger = logging.getLogger('bmlibrarian.workflow.agents')


class WorkflowAgentManager:
    """Manages agent lifecycle and connection testing."""
    
    def __init__(self, config, ui, query_processor):
        self.config = config
        self.ui = ui
        self.query_processor = query_processor
        
        # Agent components
        self.orchestrator: Optional[AgentOrchestrator] = None
        self.query_agent: Optional[QueryAgent] = None
        self.scoring_agent: Optional[DocumentScoringAgent] = None
        self.citation_agent: Optional[CitationFinderAgent] = None
        self.reporting_agent: Optional[ReportingAgent] = None
        self.counterfactual_agent: Optional[CounterfactualAgent] = None
        self.editor_agent: Optional[EditorAgent] = None
    
    def setup_agents(self) -> bool:
        """Initialize and test all agents."""
        try:
            self.ui.show_progress_message("Setting up BMLibrarian agents...")
            
            # Initialize orchestrator
            self.orchestrator = AgentOrchestrator(
                max_workers=self.config.max_workers, 
                polling_interval=self.config.polling_interval
            )
            
            # Initialize agents
            self.query_agent = QueryAgent(orchestrator=self.orchestrator)
            self.scoring_agent = DocumentScoringAgent(orchestrator=self.orchestrator)
            self.citation_agent = CitationFinderAgent(orchestrator=self.orchestrator)
            self.reporting_agent = ReportingAgent(orchestrator=self.orchestrator)
            self.counterfactual_agent = CounterfactualAgent(orchestrator=self.orchestrator)
            self.editor_agent = EditorAgent(orchestrator=self.orchestrator)
            
            # Register agents
            self.orchestrator.register_agent("query_agent", self.query_agent)
            self.orchestrator.register_agent("document_scoring_agent", self.scoring_agent)
            self.orchestrator.register_agent("citation_finder_agent", self.citation_agent)
            self.orchestrator.register_agent("reporting_agent", self.reporting_agent)
            self.orchestrator.register_agent("counterfactual_agent", self.counterfactual_agent)
            self.orchestrator.register_agent("editor_agent", self.editor_agent)
            
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