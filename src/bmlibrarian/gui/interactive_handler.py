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

    def __init__(self, step_cards: Optional[Dict] = None, tab_manager=None):
        self.step_cards = step_cards
        self.tab_manager = tab_manager
        self.waiting_for_user = False
        self.user_response = None
    
    def get_user_approval_for_query(self, query_text: str, research_question: str,
                                  update_callback: Callable, query_cleaner: Callable) -> Optional[str]:
        """Get user approval and editing for the generated query in interactive mode."""
        # Show step as waiting and enable inline editing
        update_callback(WorkflowStep.GENERATE_AND_EDIT_QUERY, "waiting",
                      f"Generated query: {query_text}\n\nClick below to edit the query if needed, then click Accept to continue.")

        # Enable inline editing on the step card
        return self._show_inline_query_editing(query_text, research_question, update_callback, query_cleaner)
    
    def _show_inline_query_editing(self, query_text: str, research_question: str,
                                 update_callback: Callable, query_cleaner: Callable) -> Optional[str]:
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

                # Log query edit to database if it was changed
                if edited_query != query_text:
                    try:
                        from bmlibrarian.agents import get_human_edit_logger
                        logger = get_human_edit_logger()
                        # Note: We'd need access to system_prompt here. For now, we'll use a simplified context
                        logger.log_query_edit(
                            user_question=research_question,
                            system_prompt="Query generation system prompt (see QueryAgent.system_prompt)",
                            ai_query=query_text,
                            human_query=edited_query
                        )
                    except Exception as e:
                        print(f"Warning: Failed to log query edit: {e}")

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
        """Show interactive scoring interface with document details and human override and approval options."""
        self.waiting_for_user = True
        self.user_response = None
        score_data = {}

        def handle_scoring_result(result: dict):
            """Handle the result from interactive scoring."""
            nonlocal score_data
            score_data = result

            # Extract overrides and approvals
            overrides = result.get('overrides', {}) if isinstance(result, dict) else result
            approvals = result.get('approvals', {}) if isinstance(result, dict) else {}

            # Update step content based on what was provided
            messages = []
            if overrides:
                messages.append(f"{len(overrides)} override(s)")
            if approvals:
                messages.append(f"{len(approvals)} approval(s)")

            if messages:
                update_callback(WorkflowStep.SCORE_DOCUMENTS, "completed",
                              f"Applied {', '.join(messages)}")
            else:
                update_callback(WorkflowStep.SCORE_DOCUMENTS, "completed",
                              "Proceeding with AI scores")

            self.waiting_for_user = False
        
        # Use the scoring tab interface instead of step card
        if self.tab_manager and self.tab_manager.scoring_interface:
            try:
                # Switch to the Scoring tab (index 2)
                if self.tab_manager.tabs_container:
                    self.tab_manager.tabs_container.selected_index = 2  # Scoring tab
                    if self.tab_manager.page:
                        self.tab_manager.page.update()

                # Start the scoring interface
                self.tab_manager.scoring_interface.start_scoring(
                    documents, scored_documents, handle_scoring_result
                )
                print("Interactive document scoring enabled in Scoring tab")
            except Exception as e:
                print(f"Error enabling scoring interface: {e} - proceeding with AI scores")
                import traceback
                traceback.print_exc()
                return {}
        else:
            print("Scoring interface not found - proceeding with AI scores")
            return {}

        # Wait for user response
        print("Workflow paused: Waiting for interactive document scoring in Scoring tab...")
        timeout = 600  # 10 minute timeout for scoring review
        elapsed = 0

        while self.waiting_for_user and elapsed < timeout:
            time.sleep(0.1)  # Check every 100ms
            elapsed += 0.1

        if elapsed >= timeout:
            print("Document scoring timeout - using AI scores")
            return {}

        # Disable scoring interface
        if self.tab_manager and self.tab_manager.scoring_interface:
            self.tab_manager.scoring_interface.disable_scoring()

        print(f"Interactive document scoring completed. Result: {score_data}")
        return score_data
    
    def get_user_approval_for_citations(self, citations: List, update_callback: Callable) -> Dict[int, str]:
        """Get user review for extracted citations in interactive mode.

        Returns:
            Dictionary mapping citation indices to review status ('accepted', 'refused', or None)
        """
        content = f"""Citation extraction completed!

Extracted {len(citations)} relevant citations from high-scoring documents.

Interactive mode: Review each citation below. Toggle status: Refuse ❌ → Unrated ⚪ → Accept ✅"""

        update_callback(WorkflowStep.EXTRACT_CITATIONS, "waiting", content)

        # Show interactive citation review interface
        return self._show_interactive_citation_review(citations, update_callback)

    def _show_interactive_citation_review(self, citations: List, update_callback: Callable) -> Dict[int, str]:
        """Show interactive citation review interface with accept/refuse/unrated toggles."""
        self.waiting_for_user = True
        self.user_response = None
        citation_reviews = {}

        def handle_citation_reviews(reviews: dict):
            """Handle the result from citation review."""
            nonlocal citation_reviews
            citation_reviews = reviews

            # Count review statuses
            accepted = sum(1 for status in reviews.values() if status == 'accepted')
            refused = sum(1 for status in reviews.values() if status == 'refused')
            unrated = len(citations) - accepted - refused

            # Update step content based on reviews
            if reviews:
                update_callback(WorkflowStep.EXTRACT_CITATIONS, "completed",
                              f"Citation review: {accepted} accepted, {refused} refused, {unrated} unrated")
            else:
                update_callback(WorkflowStep.EXTRACT_CITATIONS, "completed",
                              f"Proceeding with all {len(citations)} citations")

            self.waiting_for_user = False

        # Get the step card for citation extraction and enable review interface
        print(f"Available step cards: {list(self.step_cards.keys()) if self.step_cards else 'None'}")
        step_card = self._get_step_card(WorkflowStep.EXTRACT_CITATIONS)
        print(f"Retrieved step card for citation review: {step_card is not None}")

        if step_card:
            try:
                step_card.enable_citation_review(citations, handle_citation_reviews)
                # Trigger a page update to show the review interface
                self._trigger_page_update(update_callback)
                print("Interactive citation review enabled successfully")
            except Exception as e:
                print(f"Error enabling citation review: {e} - proceeding with all citations")
                return {}
        else:
            print("Step card not found - proceeding with all citations")
            return {}

        # Wait for user response
        print("Workflow paused: Waiting for interactive citation review...")
        timeout = 600  # 10 minute timeout for citation review
        elapsed = 0

        while self.waiting_for_user and elapsed < timeout:
            time.sleep(0.1)  # Check every 100ms
            elapsed += 0.1

        if elapsed >= timeout:
            print("Citation review timeout - using all citations")
            return {}

        # Disable review interface
        if step_card:
            step_card.disable_citation_review()

        print(f"Interactive citation review completed. Reviews: {citation_reviews}")
        return citation_reviews
    
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
        
        # Auto-complete the review (no delay needed - documents are in Literature tab)
        update_callback(WorkflowStep.REVIEW_SEARCH_RESULTS, "completed",
                      f"Reviewed {len(documents)} search results (available in Literature tab)")
        
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