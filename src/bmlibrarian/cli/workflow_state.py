"""
Workflow State Management Module

Handles workflow state, context, and data persistence.
"""

from typing import List, Dict, Any, Tuple, Optional
from bmlibrarian.agents import Citation, Report, CounterfactualAnalysis, EditedReport
from bmlibrarian.agents.reporting_agent import MethodologyMetadata


class WorkflowStateManager:
    """Manages workflow state and context data."""

    def __init__(self):
        # Workflow state
        self.current_question: Optional[str] = None
        self.current_query: Optional[str] = None
        self.search_results: List[Dict[str, Any]] = []
        self.scored_documents: List[Tuple[Dict[str, Any], Dict[str, Any]]] = []
        self.scored_documents_with_ids: List[Tuple[Dict[str, Any], Dict[str, Any], int]] = []  # Includes scoring_id
        self.extracted_citations: List[Citation] = []
        self.final_report: Optional[Report] = None
        self.counterfactual_analysis: Optional[CounterfactualAnalysis] = None
        self.contradictory_evidence: Optional[Dict[str, Any]] = None
        self.comprehensive_report: Optional[EditedReport] = None

        # Methodology tracking
        self.scoring_threshold: float = 2.5
        self.citation_extraction_threshold: float = 0.7
        self.documents_by_score: Dict[int, int] = {}
        self.counterfactual_documents_found: int = 0
        self.counterfactual_citations_extracted: int = 0

        # Search strategy tracking (for audit trail)
        self.search_strategies_metadata: Optional[Dict[str, Any]] = None

        # Audit tracking IDs
        self.research_question_id: Optional[int] = None
        self.session_id: Optional[int] = None
        self.query_id: Optional[int] = None
        self.report_id: Optional[int] = None
    
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
        self.scored_documents_with_ids = []
        self.extracted_citations = []
        self.final_report = None
        self.counterfactual_analysis = None
        self.contradictory_evidence = None
        self.comprehensive_report = None

        # Reset methodology tracking
        self.scoring_threshold = 2.5
        self.citation_extraction_threshold = 0.7
        self.documents_by_score = {}
        self.counterfactual_documents_found = 0
        self.counterfactual_citations_extracted = 0

        # Reset search strategy tracking
        self.search_strategies_metadata = None

        # Reset audit tracking IDs
        self.research_question_id = None
        self.session_id = None
        self.query_id = None
        self.report_id = None
    
    def update_question(self, question: str):
        """Update the current research question."""
        self.current_question = question
    
    def update_query(self, query: str):
        """Update the current database query."""
        self.current_query = query
    
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
    
    def update_scoring_details(self, threshold: float, documents_by_score: Dict[int, int]):
        """Update document scoring details for methodology tracking."""
        self.scoring_threshold = threshold
        self.documents_by_score = documents_by_score
    
    def update_citation_threshold(self, threshold: float):
        """Update citation extraction threshold."""
        self.citation_extraction_threshold = threshold
    
    def update_counterfactual_metrics(self, documents_found: int, citations_extracted: int):
        """Update counterfactual analysis metrics."""
        self.counterfactual_documents_found = documents_found
        self.counterfactual_citations_extracted = citations_extracted

    def update_search_strategies_metadata(self, metadata: Dict[str, Any]):
        """Update search strategies metadata from QueryAgent."""
        self.search_strategies_metadata = metadata
    
    def generate_methodology_metadata(self) -> Optional[MethodologyMetadata]:
        """Generate methodology metadata from current workflow state."""
        if not self.current_question or not self.current_query:
            return None
        
        # Calculate documents above threshold
        documents_above_threshold = sum(
            count for score, count in self.documents_by_score.items() 
            if score > self.scoring_threshold
        )
        
        # Count documents processed for citations (those above threshold)
        documents_processed_for_citations = len([
            doc for doc, score in self.scored_documents 
            if score.get('score', 0) > self.scoring_threshold
        ])
        
        # Count counterfactual queries if analysis was performed
        counterfactual_queries = 0
        if self.counterfactual_analysis and hasattr(self.counterfactual_analysis, 'research_queries'):
            counterfactual_queries = len(self.counterfactual_analysis.research_queries)

        # Extract search strategy metadata
        search_strategies_used = None
        semantic_params = None
        bm25_params = None
        fulltext_params = None

        if self.search_strategies_metadata:
            search_strategies_used = self.search_strategies_metadata.get('strategies_used')
            semantic_params = self.search_strategies_metadata.get('semantic_search_params')
            bm25_params = self.search_strategies_metadata.get('bm25_search_params')
            fulltext_params = self.search_strategies_metadata.get('fulltext_search_params')

        return MethodologyMetadata(
            human_question=self.current_question,
            generated_query=self.current_query,
            total_documents_found=len(self.search_results),
            scoring_threshold=self.scoring_threshold,
            documents_by_score=self.documents_by_score,
            documents_above_threshold=documents_above_threshold,
            documents_processed_for_citations=documents_processed_for_citations,
            citation_extraction_threshold=self.citation_extraction_threshold,
            counterfactual_performed=self.counterfactual_analysis is not None,
            counterfactual_queries_generated=counterfactual_queries,
            counterfactual_documents_found=self.counterfactual_documents_found,
            counterfactual_citations_extracted=self.counterfactual_citations_extracted,
            iterative_processing_used=True,  # Always true for our workflow
            context_window_management=True,   # Always true for our workflow
            # Search strategy information (NEW)
            search_strategies_used=search_strategies_used,
            semantic_search_params=semantic_params,
            bm25_search_params=bm25_params,
            fulltext_search_params=fulltext_params
        )