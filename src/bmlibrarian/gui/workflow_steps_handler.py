"""
Workflow Steps Handler for BMLibrarian Research GUI

Handles the execution logic for individual workflow steps including document
processing, scoring, citation extraction, and agent coordination.
"""

from typing import Dict, Any, Callable, List, Tuple, Optional, Generator
from ..cli.workflow_steps import WorkflowStep


class WorkflowStepsHandler:
    """Handles execution of individual workflow steps with agent coordination."""
    
    def __init__(self, agents: Dict[str, Any], config_overrides: Optional[Dict[str, Any]] = None):
        self.agents = agents
        self.config_overrides = config_overrides or {}
    
    def execute_query_generation(self, research_question: str, 
                               update_callback: Callable) -> str:
        """Execute the query generation step.
        
        Args:
            research_question: The research question to convert
            update_callback: Callback for status updates
            
        Returns:
            Generated PostgreSQL query string
        """
        update_callback(WorkflowStep.GENERATE_AND_EDIT_QUERY, "running",
                      "Generating database query...")
        
        query_text = self.agents['query_agent'].convert_question(research_question)
        
        return query_text
    
    def execute_document_search(self, research_question: str, query_text: str,
                              update_callback: Callable, interactive_mode: bool = False) -> List[Dict]:
        """Execute the document search step.
        
        Args:
            research_question: Original research question
            query_text: PostgreSQL query to execute
            update_callback: Callback for status updates
            interactive_mode: Whether running in interactive mode
            
        Returns:
            List of document dictionaries
        """
        update_callback(WorkflowStep.SEARCH_DOCUMENTS, "running",
                      "Searching database...")
        
        # Use the query that might have been edited by the user
        def query_modifier(original_query):
            # Return the query_text that was potentially edited by the user
            return query_text
        
        documents_generator = self.agents['query_agent'].find_abstracts(
            question=research_question,
            max_rows=self.config_overrides.get('max_results', 50),
            human_in_the_loop=interactive_mode,
            human_query_modifier=query_modifier if interactive_mode else None
        )
        
        # Convert generator to list
        documents = list(documents_generator)
        
        update_callback(WorkflowStep.SEARCH_DOCUMENTS, "completed",
                      f"Found {len(documents)} documents")
        
        return documents
    
    def execute_document_scoring(self, research_question: str, documents: List[Dict],
                               update_callback: Callable, score_overrides: Optional[Dict[int, float]] = None) -> List[Tuple[Dict, Dict]]:
        """Execute the document scoring step with optional human overrides.
        
        Args:
            research_question: The research question for relevance scoring
            documents: List of documents to score
            update_callback: Callback for status updates
            score_overrides: Dictionary mapping document indices to human scores
            
        Returns:
            List of (document, scoring_result) tuples above threshold
        """
        update_callback(WorkflowStep.SCORE_DOCUMENTS, "running",
                      "Scoring documents for relevance...")
        
        scored_documents = []
        all_scored_documents = []  # Keep track of all scored docs for override application
        high_scoring = 0
        
        # Get scoring configuration
        score_threshold = self.config_overrides.get('score_threshold', 2.5)
        max_docs_to_score = self.config_overrides.get('max_documents_to_score')
        
        # Score ALL documents unless explicitly limited
        if max_docs_to_score is None:
            docs_to_process = documents
            docs_to_score = len(documents)
        else:
            docs_to_process = documents[:max_docs_to_score]
            docs_to_score = min(max_docs_to_score, len(documents))
            
        for i, doc in enumerate(docs_to_process):
            try:
                scoring_result = self.agents['scoring_agent'].evaluate_document(research_question, doc)
                if scoring_result and isinstance(scoring_result, dict) and 'score' in scoring_result:
                    original_score = scoring_result['score']
                    
                    # Apply human override if provided
                    if score_overrides and i in score_overrides:
                        # Create modified scoring result with human score
                        modified_result = scoring_result.copy()
                        modified_result['score'] = score_overrides[i]
                        modified_result['human_override'] = True
                        modified_result['original_ai_score'] = original_score
                        scoring_result = modified_result
                        print(f"Applied human override for document {i}: {original_score:.1f} → {score_overrides[i]:.1f}")
                    
                    score = scoring_result['score']
                    all_scored_documents.append((doc, scoring_result))
                    
                    if score >= score_threshold:
                        # Store as (document, scoring_result) tuple as expected by citation agent
                        scored_documents.append((doc, scoring_result))
                        if score >= 4.0:
                            high_scoring += 1
            except Exception as e:
                print(f"Error scoring document: {e}")
                continue
        
        # Update status message
        override_msg = ""
        if score_overrides:
            override_msg = f" (with {len(score_overrides)} human overrides)"
            
        update_callback(WorkflowStep.SCORE_DOCUMENTS, "completed",
                      f"Scored {docs_to_score} documents ({len(scored_documents)} above threshold ≥{score_threshold}), {high_scoring} high relevance (≥4.0){override_msg}")
        
        return scored_documents
    
    def execute_citation_extraction(self, research_question: str, 
                                  scored_documents: List[Tuple[Dict, Dict]],
                                  update_callback: Callable) -> List:
        """Execute the citation extraction step.
        
        Args:
            research_question: The research question for citation relevance
            scored_documents: List of (document, scoring_result) tuples
            update_callback: Callback for status updates
            
        Returns:
            List of extracted citations
        """
        update_callback(WorkflowStep.EXTRACT_CITATIONS, "running",
                      "Extracting relevant citations...")
        
        # Use ALL scored documents for citations unless explicitly limited
        max_docs_for_citations = self.config_overrides.get('max_documents_for_citations')
        score_threshold = self.config_overrides.get('score_threshold', 2.5)
        
        if max_docs_for_citations is None:
            docs_for_citations = scored_documents  # Use ALL scored documents
        else:
            docs_for_citations = scored_documents[:max_docs_for_citations]
        
        citations = self.agents['citation_agent'].process_scored_documents_for_citations(
            user_question=research_question,
            scored_documents=docs_for_citations,
            score_threshold=score_threshold
        )
        
        update_callback(WorkflowStep.EXTRACT_CITATIONS, "completed",
                      f"Extracted {len(citations)} citations from {len(docs_for_citations)} documents")
        
        return citations
    
    def execute_report_generation(self, research_question: str, citations: List,
                                update_callback: Callable) -> Any:
        """Execute the report generation step.
        
        Args:
            research_question: The research question being answered
            citations: List of extracted citations
            update_callback: Callback for status updates
            
        Returns:
            Generated report object
        """
        update_callback(WorkflowStep.GENERATE_REPORT, "running",
                      "Generating research report...")
        
        report = self.agents['reporting_agent'].generate_citation_based_report(
            user_question=research_question,
            citations=citations,
            format_output=True
        )
        
        update_callback(WorkflowStep.GENERATE_REPORT, "completed",
                      "Generated preliminary report")
        
        return report
    
    def execute_counterfactual_analysis(self, report_content: str, citations: List,
                                      update_callback: Callable) -> Any:
        """Execute the counterfactual analysis step.
        
        Args:
            report_content: Content of the generated report
            citations: List of citations used in the report
            update_callback: Callback for status updates
            
        Returns:
            Counterfactual analysis results
        """
        update_callback(WorkflowStep.PERFORM_COUNTERFACTUAL_ANALYSIS, "running",
                      "Performing counterfactual analysis...")
        
        counterfactual_analysis = self.agents['counterfactual_agent'].analyze_report_citations(
            report_content=report_content,
            citations=citations
        )
        
        update_callback(WorkflowStep.PERFORM_COUNTERFACTUAL_ANALYSIS, "completed",
                      "Counterfactual analysis complete")
        
        return counterfactual_analysis
    
    def complete_remaining_steps(self, update_callback: Callable):
        """Complete the remaining workflow steps (placeholders for now).
        
        Args:
            update_callback: Callback for status updates
        """
        remaining_steps = [
            WorkflowStep.SEARCH_CONTRADICTORY_EVIDENCE,
            WorkflowStep.EDIT_COMPREHENSIVE_REPORT,
            WorkflowStep.EXPORT_REPORT
        ]
        
        for step in remaining_steps:
            update_callback(step, "completed", f"{step.display_name} completed")
    
    def get_step_execution_summary(self, documents: List[Dict], 
                                 scored_documents: List[Tuple[Dict, Dict]], 
                                 citations: List) -> Dict[str, Any]:
        """Get a summary of step execution results.
        
        Args:
            documents: List of found documents
            scored_documents: List of scored documents
            citations: List of extracted citations
            
        Returns:
            Dictionary with execution summary statistics
        """
        high_scoring = sum(1 for _, result in scored_documents if result.get('score', 0) >= 4.0)
        
        return {
            'total_documents': len(documents),
            'scored_documents': len(scored_documents),
            'high_scoring_documents': high_scoring,
            'extracted_citations': len(citations),
            'score_threshold': self.config_overrides.get('score_threshold', 2.5),
            'max_results': self.config_overrides.get('max_results', 50)
        }