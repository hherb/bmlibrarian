"""
Workflow State Management Module

Handles workflow state, context, and data persistence.
"""

from typing import List, Dict, Any, Tuple, Optional
from bmlibrarian.agents import Citation, Report, CounterfactualAnalysis, EditedReport


class WorkflowStateManager:
    """Manages workflow state and context data."""
    
    def __init__(self):
        # Workflow state
        self.current_question: Optional[str] = None
        self.current_query: Optional[str] = None
        self.search_results: List[Dict[str, Any]] = []
        self.scored_documents: List[Tuple[Dict[str, Any], Dict[str, Any]]] = []
        self.extracted_citations: List[Citation] = []
        self.final_report: Optional[Report] = None
        self.counterfactual_analysis: Optional[CounterfactualAnalysis] = None
        self.contradictory_evidence: Optional[Dict[str, Any]] = None
        self.comprehensive_report: Optional[EditedReport] = None
    
    def get_workflow_state(self) -> Dict[str, Any]:
        """Get current workflow state for potential resumption."""
        return {
            'current_question': self.current_question,
            'current_query': self.current_query,
            'search_results_count': len(self.search_results),
            'scored_documents_count': len(self.scored_documents),
            'extracted_citations_count': len(self.extracted_citations),
            'has_final_report': self.final_report is not None,
            'has_counterfactual_analysis': self.counterfactual_analysis is not None,
            'has_contradictory_evidence': self.contradictory_evidence is not None,
            'has_comprehensive_report': self.comprehensive_report is not None
        }
    
    def clear_workflow_state(self) -> None:
        """Clear current workflow state for a fresh start."""
        self.current_question = None
        self.current_query = None
        self.search_results = []
        self.scored_documents = []
        self.extracted_citations = []
        self.final_report = None
        self.counterfactual_analysis = None
        self.contradictory_evidence = None
        self.comprehensive_report = None
    
    def update_question(self, question: str):
        """Update the current research question."""
        self.current_question = question
    
    def update_search_results(self, documents: List[Dict[str, Any]]):
        """Update search results."""
        self.search_results = documents
    
    def update_scored_documents(self, scored_docs: List[Tuple[Dict[str, Any], Dict[str, Any]]]):
        """Update scored documents."""
        self.scored_documents = scored_docs
    
    def update_citations(self, citations: List[Citation]):
        """Update extracted citations."""
        self.extracted_citations = citations
    
    def update_final_report(self, report: Report):
        """Update the final report."""
        self.final_report = report
    
    def update_counterfactual_analysis(self, analysis: CounterfactualAnalysis):
        """Update counterfactual analysis."""
        self.counterfactual_analysis = analysis
    
    def update_contradictory_evidence(self, evidence: Dict[str, Any]):
        """Update contradictory evidence."""
        self.contradictory_evidence = evidence
    
    def update_comprehensive_report(self, report: EditedReport):
        """Update comprehensive report."""
        self.comprehensive_report = report