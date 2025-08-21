"""
Workflow Orchestration Module

Handles the main research workflow coordination, agent setup, and state management.
This module now provides backwards compatibility while using the refactored modular components.
"""

import time
import logging
from typing import List, Dict, Any, Tuple, Optional
from bmlibrarian.agents import (
    QueryAgent, DocumentScoringAgent, CitationFinderAgent, 
    ReportingAgent, CounterfactualAgent, EditorAgent, AgentOrchestrator, 
    Citation, Report, CounterfactualAnalysis, EditedReport
)
from .workflow_steps import (
    WorkflowStep, StepResult, WorkflowDefinition, WorkflowExecutor,
    create_default_research_workflow
)
from .workflow_refactored import RefactoredWorkflowOrchestrator

# Get logger for workflow operations
logger = logging.getLogger('bmlibrarian.workflow')


class WorkflowOrchestrator:
    """Orchestrates the complete research workflow with agent coordination.
    
    This class now delegates to the refactored modular implementation for better maintainability
    while preserving the original interface for backwards compatibility.
    """
    
    def __init__(self, config, ui, query_processor, formatter):
        # Initialize the refactored orchestrator
        self._refactored_orchestrator = RefactoredWorkflowOrchestrator(
            config, ui, query_processor, formatter
        )
        
        # Expose compatibility properties
        self.config = config
        self.ui = ui
        self.query_processor = query_processor
        self.formatter = formatter
    
    def setup_agents(self) -> bool:
        """Initialize and test all agents."""
        return self._refactored_orchestrator.setup_agents()
    
    def run_complete_workflow(self, auto_question: str = None) -> bool:
        """Execute the complete research workflow."""
        return self._refactored_orchestrator.run_complete_workflow(auto_question)
    
    def get_workflow_state(self) -> Dict[str, Any]:
        """Get current workflow state for potential resumption."""
        return self._refactored_orchestrator.get_workflow_state()
    
    def clear_workflow_state(self) -> None:
        """Clear current workflow state for a fresh start."""
        self._refactored_orchestrator.clear_workflow_state()
    
    # Legacy properties for backwards compatibility
    @property
    def current_question(self) -> Optional[str]:
        return self._refactored_orchestrator.state_manager.current_question
    
    @property
    def search_results(self) -> List[Dict[str, Any]]:
        return self._refactored_orchestrator.state_manager.search_results
    
    @property
    def scored_documents(self) -> List[Tuple[Dict[str, Any], Dict[str, Any]]]:
        return self._refactored_orchestrator.state_manager.scored_documents
    
    @property
    def extracted_citations(self) -> List[Citation]:
        return self._refactored_orchestrator.state_manager.extracted_citations
    
    @property
    def final_report(self) -> Optional[Report]:
        return self._refactored_orchestrator.state_manager.final_report
    
    @property
    def counterfactual_analysis(self) -> Optional[CounterfactualAnalysis]:
        return self._refactored_orchestrator.state_manager.counterfactual_analysis
    
    @property
    def contradictory_evidence(self) -> Optional[Dict[str, Any]]:
        return self._refactored_orchestrator.state_manager.contradictory_evidence
    
    @property
    def comprehensive_report(self) -> Optional[EditedReport]:
        return self._refactored_orchestrator.state_manager.comprehensive_report
    
    # Agent properties for backwards compatibility
    @property
    def orchestrator(self) -> Optional[AgentOrchestrator]:
        return self._refactored_orchestrator.agent_manager.orchestrator
    
    @property
    def query_agent(self) -> Optional[QueryAgent]:
        return self._refactored_orchestrator.agent_manager.query_agent
    
    @property
    def scoring_agent(self) -> Optional[DocumentScoringAgent]:
        return self._refactored_orchestrator.agent_manager.scoring_agent
    
    @property
    def citation_agent(self) -> Optional[CitationFinderAgent]:
        return self._refactored_orchestrator.agent_manager.citation_agent
    
    @property
    def reporting_agent(self) -> Optional[ReportingAgent]:
        return self._refactored_orchestrator.agent_manager.reporting_agent
    
    @property
    def counterfactual_agent(self) -> Optional[CounterfactualAgent]:
        return self._refactored_orchestrator.agent_manager.counterfactual_agent
    
    @property
    def editor_agent(self) -> Optional[EditorAgent]:
        return self._refactored_orchestrator.agent_manager.editor_agent


# All legacy method implementations have been moved to the modular components:
# - workflow_agents.py: Agent management and connection testing
# - workflow_state.py: State management and data persistence  
# - workflow_execution.py: Core document processing operations
# - workflow_handlers.py: Individual workflow step execution logic
# - workflow_refactored.py: Main orchestrator using modular components
#
# The refactored architecture provides better separation of concerns and maintainability