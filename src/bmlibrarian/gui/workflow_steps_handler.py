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
        
        from ..config import get_search_config
        search_config = get_search_config()
        
        # Debug: Show what max_results value is being used
        config_max_results = search_config.get('max_results', 100)
        override_max_results = self.config_overrides.get('max_results', config_max_results)
        print(f"🔍 Document search debug:")
        print(f"  - Config file max_results: {config_max_results}")
        print(f"  - Config overrides: {self.config_overrides}")
        print(f"  - Final max_rows used: {override_max_results}")
        
        documents_generator = self.agents['query_agent'].find_abstracts(
            question=research_question,
            max_rows=override_max_results,
            human_in_the_loop=interactive_mode,
            human_query_modifier=query_modifier if interactive_mode else None
        )
        
        # Convert generator to list
        documents = list(documents_generator)
        
        # Store documents in the calling workflow BEFORE completing the step
        # This ensures documents are available when the completion callback fires
        
        update_callback(WorkflowStep.SEARCH_DOCUMENTS, "completed",
                      f"Found {len(documents)} documents")
        
        return documents
    
    def execute_document_scoring(self, research_question: str, documents: List[Dict],
                               update_callback: Callable, score_overrides: Optional[Dict[int, float]] = None,
                               progress_callback: Optional[Callable[[int, int, str], None]] = None) -> List[Tuple[Dict, Dict]]:
        """Execute the document scoring step with optional human overrides.
        
        Args:
            research_question: The research question for relevance scoring
            documents: List of documents to score
            update_callback: Callback for status updates
            score_overrides: Dictionary mapping document indices to human scores
            progress_callback: Optional callback for progress updates (current, total, item_name)
            
        Returns:
            List of (document, scoring_result) tuples above threshold
        """
        update_callback(WorkflowStep.SCORE_DOCUMENTS, "running",
                      "Scoring documents for relevance...")
        
        scored_documents = []
        all_scored_documents = []  # Keep track of all scored docs for override application
        high_scoring = 0
        
        # Get scoring configuration from search config
        from ..config import get_search_config
        search_config = get_search_config()
        
        score_threshold = self.config_overrides.get('score_threshold', search_config.get('score_threshold', 2.5))
        max_docs_to_score = self.config_overrides.get('max_documents_to_score', search_config.get('max_documents_to_score'))
        
        # Score ALL documents unless explicitly limited
        if max_docs_to_score is None:
            docs_to_process = documents
            docs_to_score = len(documents)
        else:
            docs_to_process = documents[:max_docs_to_score]
            docs_to_score = min(max_docs_to_score, len(documents))
            
        # Convert progress_callback format for scoring agent (current, total) instead of (current, total, item_name)
        def agent_progress_callback(current: int, total: int):
            if progress_callback:
                # The workflow progress callback expects (current, total) only, not (current, total, item_name)
                progress_callback(current, total)
        
        # Use scoring agent's batch processing method with progress callback
        scored_results = list(self.agents['scoring_agent'].process_scoring_queue(
            user_question=research_question,
            documents=docs_to_process,
            progress_callback=agent_progress_callback
        ))
        
        # Process results and apply overrides
        for i, (doc, scoring_result) in enumerate(scored_results):
            try:
                if scoring_result and 'score' in scoring_result:
                    original_score = scoring_result['score']
                    score = original_score
                    
                    # Convert ScoringResult to dict format
                    result_dict = {
                        'score': score,
                        'reasoning': scoring_result.get('reasoning', 'No reasoning provided'),
                        'confidence': scoring_result.get('confidence', 1.0)
                    }
                    
                    # Apply human override if provided
                    if score_overrides and i in score_overrides:
                        result_dict['score'] = score_overrides[i]
                        result_dict['human_override'] = True
                        result_dict['original_ai_score'] = original_score
                        score = score_overrides[i]
                        print(f"Applied human override for document {i}: {original_score:.1f} → {score_overrides[i]:.1f}")
                    
                    all_scored_documents.append((doc, result_dict))
                    
                    if score >= score_threshold:
                        # Store as (document, scoring_result) tuple as expected by citation agent
                        scored_documents.append((doc, result_dict))
                        if score >= 4.0:
                            high_scoring += 1
            except Exception as e:
                print(f"Error processing scored document: {e}")
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
                                  update_callback: Callable,
                                  progress_callback: Optional[Callable[[int, int, str], None]] = None) -> List:
        """Execute the citation extraction step.
        
        Args:
            research_question: The research question for citation relevance
            scored_documents: List of (document, scoring_result) tuples
            update_callback: Callback for status updates
            progress_callback: Optional callback for progress updates (current, total, item_name)
            
        Returns:
            List of extracted citations
        """
        update_callback(WorkflowStep.EXTRACT_CITATIONS, "running",
                      "Extracting relevant citations...")
        
        # Use ALL scored documents for citations unless explicitly limited
        from ..config import get_search_config
        search_config = get_search_config()
        
        max_docs_for_citations = self.config_overrides.get('max_documents_for_citations', search_config.get('max_documents_for_citations'))
        score_threshold = self.config_overrides.get('score_threshold', search_config.get('score_threshold', 2.5))
        
        if max_docs_for_citations is None:
            docs_for_citations = scored_documents  # Use ALL scored documents
        else:
            docs_for_citations = scored_documents[:max_docs_for_citations]
        
        # Use citation agent method with progress tracking
        citations = self.agents['citation_agent'].process_scored_documents_for_citations(
            user_question=research_question,
            scored_documents=docs_for_citations,
            score_threshold=score_threshold,
            progress_callback=progress_callback
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
        
        # Debug report generation
        if hasattr(report, 'content'):
            report_content = report.content
        elif isinstance(report, str):
            report_content = report
        else:
            report_content = str(report)
        
        print(f"📊 Report generation completed. Length: {len(report_content) if report_content else 0}")
        if report_content:
            print(f"📝 Report ends with: ...{report_content[-200:]}")
        
        update_callback(WorkflowStep.GENERATE_REPORT, "completed",
                      f"Generated preliminary report ({len(report_content) if report_content else 0} chars)")
        
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
    
    def execute_comprehensive_counterfactual_analysis(self, report_content: str, citations: List,
                                                     update_callback: Callable) -> Any:
        """Execute comprehensive counterfactual analysis with literature search.
        
        Args:
            report_content: Content of the generated report
            citations: List of citations used in the report
            update_callback: Callback for status updates
            
        Returns:
            Comprehensive counterfactual analysis results with contradictory evidence
        """
        update_callback(WorkflowStep.PERFORM_COUNTERFACTUAL_ANALYSIS, "running",
                      "Performing comprehensive counterfactual analysis with literature search...")
        
        # Use the comprehensive find_contradictory_literature method
        from ..config import get_search_config
        search_config = get_search_config()
        
        comprehensive_analysis = self.agents['counterfactual_agent'].find_contradictory_literature(
            document_content=report_content,
            document_title="Research Report with Citations",
            max_results_per_query=self.config_overrides.get('counterfactual_max_results', search_config.get('counterfactual_max_results', 10)),
            min_relevance_score=self.config_overrides.get('counterfactual_min_score', search_config.get('counterfactual_min_score', 3)),
            query_agent=self.agents.get('query_agent'),
            scoring_agent=self.agents.get('scoring_agent'),
            citation_agent=self.agents.get('citation_agent')
        )
        
        update_callback(WorkflowStep.PERFORM_COUNTERFACTUAL_ANALYSIS, "completed",
                      "Comprehensive counterfactual analysis complete with literature search")
        
        return comprehensive_analysis
    
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
            'max_results': self.config_overrides.get('max_results', get_search_config().get('max_results', 100))
        }