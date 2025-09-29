"""
Interactive User Interface Handler for BMLibrarian Research GUI

Handles all user interaction logic including inline editing, approval workflows,
and step-by-step user review processes.
"""

import time
from typing import Optional, Callable, Dict, Any, List
from ..cli.workflow_steps import WorkflowStep


class InteractiveHandler:
    """Handles all interactive user interface operations for the research workflow."""
    
    def __init__(self, step_cards: Optional[Dict] = None):
        self.step_cards = step_cards
        self.waiting_for_user = False
        self.user_response = None
    
    def get_user_approval_for_query(self, query_text: str, research_question: str, 
                                  update_callback: Callable, query_cleaner: Callable) -> Optional[str]:
        """Get user approval and editing for the generated query in interactive mode."""
        # Show step as waiting and enable inline editing
        update_callback(WorkflowStep.GENERATE_AND_EDIT_QUERY, "waiting", 
                      f"Generated query: {query_text}\n\nClick below to edit the query if needed, then click Accept to continue.")
        
        # Enable inline editing on the step card
        return self._show_inline_query_editing(query_text, update_callback, query_cleaner)
    
    def _show_inline_query_editing(self, query_text: str, update_callback: Callable, 
                                 query_cleaner: Callable) -> Optional[str]:
        """Show inline query editing in the step card."""
        self.waiting_for_user = True
        self.user_response = None
        edited_query = None
        
        def handle_edit_result(approved: bool, new_query: str = ""):
            """Handle the result from inline editing."""
            nonlocal edited_query
            if approved:
                # Clean the query by removing markdown formatting
                cleaned_query = query_cleaner(new_query if new_query.strip() else query_text)
                edited_query = cleaned_query
                # Update the step to show the accepted query
                update_callback(WorkflowStep.GENERATE_AND_EDIT_QUERY, "completed",
                              f"Final query: {edited_query}")
            else:
                edited_query = None  # User cancelled
            self.waiting_for_user = False
        
        # Get the step card for query generation and enable inline editing
        print(f"Available step cards: {list(self.step_cards.keys()) if self.step_cards else 'None'}")
        step_card = self._get_step_card(WorkflowStep.GENERATE_AND_EDIT_QUERY)
        print(f"Retrieved step card for query editing: {step_card is not None}")
        
        if step_card:
            try:
                step_card.enable_inline_editing(query_text, handle_edit_result)
                # Trigger a page update to show the editing interface
                self._trigger_page_update(update_callback, WorkflowStep.GENERATE_AND_EDIT_QUERY)
                print("Inline query editing enabled successfully")
            except Exception as e:
                print(f"Error enabling inline editing: {e} - auto-approving query")
                return query_text
        else:
            print("Step card not found - auto-approving query")
            print("This means inline editing is not available, falling back to showing full query")
            return query_text
        
        # Wait for user response
        print("Workflow paused: Waiting for inline query editing...")
        timeout = 300  # 5 minute timeout
        elapsed = 0
        
        while self.waiting_for_user and elapsed < timeout:
            time.sleep(0.1)  # Check every 100ms
            elapsed += 0.1
        
        if elapsed >= timeout:
            print("Query editing timeout - using original query")
            return query_text
        
        # Disable inline editing
        if step_card:
            step_card.disable_inline_editing()
        
        print(f"Inline query editing completed. Result: {edited_query is not None}")
        return edited_query
    
    def get_user_approval_for_search_results(self, documents: List[Dict[str, Any]], 
                                           update_callback: Callable) -> bool:
        """Get user approval for search results in interactive mode."""
        # Show detailed search results with expandable abstracts
        content = f"""Found {len(documents)} documents for your research question.

Interactive mode: Review the detailed search results below. Click on any document to expand and view the full abstract."""
        
        update_callback(WorkflowStep.REVIEW_SEARCH_RESULTS, "waiting", content)
        
        # Show interactive document search results interface
        return self._show_interactive_search_results(documents, update_callback)
    
    def get_user_approval_for_scores(self, documents: List, scored_documents: List, threshold: float, 
                                   update_callback: Callable) -> dict:
        """Get user approval and potential score overrides for document scores in interactive mode.
        
        Returns:
            Dictionary with score overrides where key is document index and value is human score
        """
        high_scoring = sum(1 for _, result in scored_documents if result.get('score', 0) >= 4.0)
        
        # Create score distribution summary
        score_ranges = {"5.0": 0, "4.0-4.9": 0, "3.0-3.9": 0, "2.5-2.9": 0}
        for _, result in scored_documents:
            score = result.get('score', 0)
            if score >= 5.0:
                score_ranges["5.0"] += 1
            elif score >= 4.0:
                score_ranges["4.0-4.9"] += 1
            elif score >= 3.0:
                score_ranges["3.0-3.9"] += 1
            else:
                score_ranges["2.5-2.9"] += 1
        
        score_summary = "\n".join([f"Score {range_}: {count} documents" 
                                 for range_, count in score_ranges.items() if count > 0])
        
        content = f"""Document scoring completed!

Found {len(scored_documents)} documents above threshold ≥{threshold}
High relevance documents (≥4.0): {high_scoring}

Score distribution:
{score_summary}

Interactive mode: Review and edit document scores below. Click buttons to continue."""
        
        update_callback(WorkflowStep.SCORE_DOCUMENTS, "waiting", content)
        
        # Show interactive document scoring interface
        return self._show_interactive_scoring(documents, scored_documents, update_callback)
    
    def _show_interactive_scoring(self, documents: List, scored_documents: List, 
                                update_callback: Callable) -> dict:
        """Show interactive scoring interface with document details and human override options."""
        self.waiting_for_user = True
        self.user_response = None
        score_overrides = {}
        
        def handle_scoring_result(overrides: dict):
            """Handle the result from interactive scoring."""
            nonlocal score_overrides
            score_overrides = overrides
            
            # Update step content based on whether overrides were applied
            if overrides:
                override_count = len(overrides)
                update_callback(WorkflowStep.SCORE_DOCUMENTS, "completed",
                              f"Applied {override_count} human score overrides")
            else:
                update_callback(WorkflowStep.SCORE_DOCUMENTS, "completed",
                              "Proceeding with AI scores")
            
            self.waiting_for_user = False
        
        # Get the step card for document scoring and enable scoring interface
        print(f"Available step cards: {list(self.step_cards.keys()) if self.step_cards else 'None'}")
        step_card = self._get_step_card(WorkflowStep.SCORE_DOCUMENTS)
        print(f"Retrieved step card for document scoring: {step_card is not None}")
        
        if step_card:
            try:
                step_card.enable_document_scoring(documents, scored_documents, handle_scoring_result)
                # Trigger a page update to show the scoring interface
                self._trigger_page_update(update_callback)
                print("Interactive document scoring enabled successfully")
            except Exception as e:
                print(f"Error enabling document scoring: {e} - proceeding with AI scores")
                return {}
        else:
            print("Step card not found - proceeding with AI scores")
            return {}
        
        # Wait for user response
        print("Workflow paused: Waiting for interactive document scoring...")
        timeout = 600  # 10 minute timeout for scoring review
        elapsed = 0
        
        while self.waiting_for_user and elapsed < timeout:
            time.sleep(0.1)  # Check every 100ms
            elapsed += 0.1
        
        if elapsed >= timeout:
            print("Document scoring timeout - using AI scores")
            return {}
        
        # Disable scoring interface
        if step_card:
            step_card.disable_document_scoring()
        
        print(f"Interactive document scoring completed. Overrides: {len(score_overrides)}")
        return score_overrides
    
    def get_user_approval_for_citations(self, citations: List, update_callback: Callable) -> bool:
        """Get user approval for extracted citations in interactive mode."""
        # Show preview of first few citations
        citation_preview = ""
        for i, citation in enumerate(citations[:3], 1):
            if hasattr(citation, 'text'):
                text = citation.text[:100] + "..." if len(citation.text) > 100 else citation.text
            elif isinstance(citation, dict):
                text = citation.get('text', str(citation))[:100] + "..."
            else:
                text = str(citation)[:100] + "..."
            citation_preview += f"{i}. {text}\n\n"
        
        content = f"""Citation extraction completed!

Extracted {len(citations)} relevant citations from high-scoring documents.

First few citations:
{citation_preview}Interactive mode: Review the citations above. Proceeding automatically in 3 seconds..."""
        
        update_callback(WorkflowStep.EXTRACT_CITATIONS, "waiting", content)
        
        # Brief pause to let user see the citations
        time.sleep(3)
        
        return True  # Auto-approve after showing citations
    
    def _show_interactive_search_results(self, documents: List[Dict[str, Any]], 
                                       update_callback: Callable) -> bool:
        """Show interactive search results interface with expandable document listings."""
        print(f"Showing interactive search results for {len(documents)} documents")
        
        # Get the step card for search results review and enable search results display
        step_card = self._get_step_card(WorkflowStep.REVIEW_SEARCH_RESULTS)
        print(f"Retrieved step card for search results review: {step_card is not None}")
        
        if step_card:
            try:
                print(f"Enabling document search results display...")
                step_card.enable_document_search_results(documents)
                print("Search results display enabled on step card")
                
                # Check if the search results container was created
                if hasattr(step_card, 'search_results_container') and step_card.search_results_container:
                    print("✅ Search results container was created successfully")
                else:
                    print("❌ Search results container was NOT created")
                
                # Update the step to force a UI refresh
                update_callback(WorkflowStep.REVIEW_SEARCH_RESULTS, "waiting",
                              f"📋 Interactive review: {len(documents)} documents found. Click to expand any document and view full abstract.")
                print("Step status updated via callback")
                
            except Exception as e:
                print(f"Error enabling search results display: {e}")
                return True
        else:
            print("Step card not found - auto-approving search results")
            return True
        
        # Give user time to review the results (auto-approve after timeout)
        print("Workflow paused: Showing interactive search results for 10 seconds...")
        timeout = 10  # 10 second timeout for search results review
        time.sleep(timeout)
        
        # Auto-complete the review and clean up
        update_callback(WorkflowStep.REVIEW_SEARCH_RESULTS, "completed",
                      f"Reviewed {len(documents)} search results")
        
        # Disable search results interface
        if step_card:
            try:
                step_card.disable_document_search_results()
                print("Search results display disabled")
            except Exception as e:
                print(f"Error disabling search results display: {e}")
        
        print("Interactive search results review completed.")
        return True
    
    def _get_step_card(self, step: WorkflowStep):
        """Get the step card for a specific workflow step."""
        if self.step_cards and step in self.step_cards:
            return self.step_cards[step]
        return None
    
    def _trigger_page_update(self, update_callback: Callable, step: WorkflowStep = None):
        """Trigger a page update to refresh the UI."""
        try:
            # Call the update callback to trigger a page refresh for the appropriate step
            target_step = step or WorkflowStep.REVIEW_SEARCH_RESULTS
            update_callback(target_step, "waiting", "")
        except Exception as e:
            print(f"Error triggering page update: {e}")