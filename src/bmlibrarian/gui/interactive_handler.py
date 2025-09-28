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
                self._trigger_page_update(update_callback)
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
        # Show informational content and auto-approve after brief pause
        doc_details = ""
        for i, doc in enumerate(documents[:5], 1):  # Show first 5 documents
            title = doc.get('title', 'Untitled')[:60]
            doc_details += f"{i}. {title}\n"
        
        if len(documents) > 5:
            doc_details += f"... and {len(documents) - 5} more documents\n"
        
        content = f"""Found {len(documents)} documents for your research question.

First few results:
{doc_details}
Interactive mode: Review the search results above. Proceeding automatically in 3 seconds..."""
        
        update_callback(WorkflowStep.REVIEW_SEARCH_RESULTS, "waiting", content)
        
        # Brief pause to let user see the results
        time.sleep(3)
        
        return True  # Auto-approve after showing results
    
    def get_user_approval_for_scores(self, scored_documents: List, threshold: float, 
                                   update_callback: Callable) -> bool:
        """Get user approval for document scores in interactive mode."""
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

Interactive mode: Review the document scores above. Proceeding automatically in 3 seconds..."""
        
        update_callback(WorkflowStep.SCORE_DOCUMENTS, "waiting", content)
        
        # Brief pause to let user see the scores
        time.sleep(3)
        
        return True  # Auto-approve after showing scores
    
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
    
    def _get_step_card(self, step: WorkflowStep):
        """Get the step card for a specific workflow step."""
        if self.step_cards and step in self.step_cards:
            return self.step_cards[step]
        return None
    
    def _trigger_page_update(self, update_callback: Callable):
        """Trigger a page update to refresh the UI."""
        try:
            # Call the update callback to trigger a page refresh
            update_callback(WorkflowStep.GENERATE_AND_EDIT_QUERY, "waiting", "")
        except Exception as e:
            print(f"Error triggering page update: {e}")