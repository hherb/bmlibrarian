"""
Workflow Steps Handler for BMLibrarian Research GUI

Handles the execution logic for individual workflow steps including document
processing, scoring, citation extraction, and agent coordination.
"""

from typing import Dict, Any, Callable, List, Tuple, Optional, Generator
from ..cli.workflow_steps import WorkflowStep


class WorkflowStepsHandler:
    """Handles execution of individual workflow steps with agent coordination."""

    def __init__(self, agents: Dict[str, Any], config_overrides: Optional[Dict[str, Any]] = None, tab_manager: Optional[Any] = None):
        self.agents = agents
        self.config_overrides = config_overrides if config_overrides is not None else {}
        self.multi_query_generation_result = None  # Store for linking with search results
        self.multi_query_stats = None  # Store query execution statistics
        self.performance_tracker = None  # Query performance tracker
        self.tab_manager = tab_manager  # Reference to TabManager for GUI updates

        # Audit tracking session context (set by WorkflowExecutor)
        self.research_question_id = None
        self.session_id = None
        self.query_ids = []  # Track generated query IDs for document linking
        self.scoring_ids = {}  # Track scoring_ids: doc_id -> scoring_id

    def _log_generated_queries_to_audit(self, multi_result) -> List[int]:
        """
        Log generated queries to the audit.generated_queries table.

        Args:
            multi_result: MultiModelQueryResult with all generated queries

        Returns:
            List of query_ids that were logged
        """
        if not self.research_question_id or not self.session_id:
            return []

        if '_audit_conn' not in self.agents or not self.agents['_audit_conn']:
            return []

        query_ids = []
        conn = self.agents['_audit_conn']

        try:
            with conn.cursor() as cur:
                for query_result in multi_result.all_queries:
                    if query_result.error:
                        continue  # Skip failed queries

                    # Sanitize the query
                    from ..agents.utils.query_syntax import fix_tsquery_syntax
                    sanitized = fix_tsquery_syntax(query_result.query)

                    cur.execute("""
                        INSERT INTO audit.generated_queries (
                            research_question_id, session_id, model_name,
                            temperature, top_p, attempt_number,
                            query_text, query_text_sanitized,
                            generation_time_ms
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        RETURNING query_id
                    """, (
                        self.research_question_id,
                        self.session_id,
                        query_result.model,
                        query_result.temperature,
                        1.0,  # top_p - not available in QueryGenerationResult, use default
                        query_result.attempt_number,
                        query_result.query,
                        sanitized,
                        query_result.generation_time * 1000  # Convert seconds to milliseconds
                    ))
                    query_id = cur.fetchone()[0]
                    query_ids.append(query_id)

                conn.commit()
                print(f"📊 Logged {len(query_ids)} queries to audit.generated_queries")

        except Exception as e:
            print(f"⚠️ Error logging queries to audit: {e}")
            conn.rollback()

        return query_ids

    def _log_single_query_to_audit(self, query_text: str, model_name: str) -> Optional[int]:
        """
        Log a single query to the audit.generated_queries table.

        Args:
            query_text: The generated query text
            model_name: The model used to generate the query

        Returns:
            query_id if logged, None otherwise
        """
        if not self.research_question_id or not self.session_id:
            return None

        if '_audit_conn' not in self.agents or not self.agents['_audit_conn']:
            return None

        conn = self.agents['_audit_conn']

        try:
            # Sanitize the query
            from ..agents.utils.query_syntax import fix_tsquery_syntax
            sanitized = fix_tsquery_syntax(query_text)

            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO audit.generated_queries (
                        research_question_id, session_id, model_name,
                        temperature, top_p, attempt_number,
                        query_text, query_text_sanitized,
                        generation_time_ms
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING query_id
                """, (
                    self.research_question_id,
                    self.session_id,
                    model_name,
                    0.0,  # Temperature not available for single query
                    0.0,  # Top_p not available for single query
                    1,    # Single query is always attempt 1
                    query_text,
                    sanitized,
                    None  # Generation time not tracked for single query
                ))
                query_id = cur.fetchone()[0]

            conn.commit()
            print(f"📊 Logged single query to audit.generated_queries (query_id: {query_id})")
            return query_id

        except Exception as e:
            print(f"⚠️ Error logging single query to audit: {e}")
            conn.rollback()
            return None

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

        # Check if multi-model query generation is enabled
        from ..config import get_query_generation_config
        qg_config = get_query_generation_config()

        if qg_config.get('multi_model_enabled', False):
            # Use multi-model query generation
            num_models = len(qg_config.get('models', []))
            queries_per = qg_config.get('queries_per_model', 1)
            total_queries = num_models * queries_per
            print(f"🔍 Using multi-model query generation with {num_models} models, {queries_per} queries each = {total_queries} total")

            # Set up callback to update GUI progress
            queries_generated = [0]  # Use list to allow modification in nested function

            def progress_callback(event_type: str, data):
                """Update GUI with query generation progress."""
                if event_type == "query_generated":
                    queries_generated[0] += 1
                    if isinstance(data, dict):
                        model_short = data.get('model', '').split(':')[0]
                        attempt = data.get('attempt', '?')
                        query = data.get('query', '')[:60]
                        progress_msg = f"Generated query {queries_generated[0]}/{total_queries}: {model_short} attempt {attempt}"
                        print(f"   ✓ {progress_msg}")
                        if self.tab_manager:
                            self.tab_manager.update_search_progress(progress_msg, show_bar=True)

            # Temporarily set callback
            original_callback = self.agents['query_agent'].callback
            self.agents['query_agent'].callback = progress_callback

            try:
                multi_result = self.agents['query_agent'].convert_question_multi_model(research_question)
            finally:
                self.agents['query_agent'].callback = original_callback
                # Clear progress
                if self.tab_manager:
                    self.tab_manager.update_search_progress("", show_bar=False)

            # Store for later linking with search results
            self.multi_query_generation_result = multi_result

            # Log queries to audit if tracking is enabled
            if self.research_question_id and self.session_id:
                self.query_ids = self._log_generated_queries_to_audit(multi_result)

            # For GUI, we'll use all unique queries (user can't review them in non-interactive mode)
            # In the future, could add interactive query selection UI here
            if multi_result.unique_queries:
                # Sanitize queries for display (same sanitization that will be applied during execution)
                from ..agents.utils.query_syntax import fix_tsquery_syntax
                sanitized_queries = [fix_tsquery_syntax(q) for q in multi_result.unique_queries]

                # For now, use the first sanitized query for display/editing
                # But all queries will be used in the search step
                query_text = sanitized_queries[0]
                print(f"📊 Generated {len(sanitized_queries)} unique queries (sanitized)")

                # Display each query with model and attempt info
                for query_result in multi_result.all_queries:
                    if not query_result.error:
                        sanitized_q = fix_tsquery_syntax(query_result.query)
                        print(f"   model {query_result.model} attempt {query_result.attempt_number}: {sanitized_q}")
            else:
                query_text = ""
        else:
            # Use single-model query generation (original behavior)
            query_text = self.agents['query_agent'].convert_question(research_question)

            # Log single query to audit if tracking is enabled
            if self.research_question_id and self.session_id and query_text:
                model_name = self.agents['query_agent'].model
                query_id = self._log_single_query_to_audit(query_text, model_name)
                if query_id:
                    self.query_ids = [query_id]

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

        from ..config import get_search_config, get_query_generation_config
        search_config = get_search_config()
        qg_config = get_query_generation_config()

        # Debug: Show what max_results value is being used
        config_max_results = search_config.get('max_results', 100)
        override_max_results = self.config_overrides.get('max_results', config_max_results)
        print(f"🔍 Document search debug:")
        print(f"  - Config file max_results: {config_max_results}")
        print(f"  - Config overrides: {self.config_overrides}")
        print(f"  - Final max_rows used: {override_max_results}")

        # Check if multi-model query generation is enabled
        if qg_config.get('multi_model_enabled', False):
            print(f"🔍 Using multi-model document search")

            # Initialize performance tracker for this session
            from ..agents.query_generation import QueryPerformanceTracker
            import hashlib
            # Use separate session ID for performance tracker (MD5 hash)
            tracker_session_id = hashlib.md5(research_question.encode()).hexdigest()
            self.performance_tracker = QueryPerformanceTracker()  # In-memory database
            self.performance_tracker.start_session(tracker_session_id)

            # Create a custom callback to capture query statistics
            original_callback = self.agents['query_agent'].callback

            def stats_callback(event_type: str, data):
                """Capture query statistics from the agent."""
                print(f"🔍 DEBUG: stats_callback called with event_type={event_type}")

                if event_type == "multi_query_stats":
                    # Parse JSON string to dict if needed
                    import json
                    if isinstance(data, str):
                        data = json.loads(data)

                    # Store the statistics for display
                    self.multi_query_stats = data
                    print(f"🔍 DEBUG: Stored multi_query_stats with {len(data.get('query_stats', []))} queries")

                    # Print detailed per-query results
                    if isinstance(data, dict) and 'query_stats' in data:
                        print(f"\n📊 Multi-query execution results:")
                        for stat in data['query_stats']:
                            if stat['success']:
                                # Match with generation info to get model name
                                query_idx = stat['query_index'] - 1  # Convert to 0-based
                                model_info = ""
                                if self.multi_query_generation_result and query_idx < len(self.multi_query_generation_result.all_queries):
                                    gen_result = self.multi_query_generation_result.all_queries[query_idx]
                                    model_info = f"model {gen_result.model} attempt {gen_result.attempt_number}: "

                                print(f"   {model_info}{stat['query_text']}  results: {stat['result_count']}")
                            else:
                                print(f"   Query {stat['query_index']}: FAILED - {stat['error']}")
                        print(f"   Total unique documents: {data['total_unique_ids']}\n")

                # Call original callback if it exists
                if original_callback:
                    original_callback(event_type, data)

            # Temporarily replace callback
            self.agents['query_agent'].callback = stats_callback

            try:
                documents_generator = self.agents['query_agent'].find_abstracts_multi_query(
                    question=research_question,
                    max_rows=override_max_results,
                    human_in_the_loop=False,  # GUI doesn't support interactive query selection yet
                    human_query_modifier=None,
                    performance_tracker=self.performance_tracker,
                    session_id=self.session_id
                )
                # CRITICAL: Consume generator INSIDE try block while callback is active
                documents = list(documents_generator)
            finally:
                # Restore original callback
                self.agents['query_agent'].callback = original_callback
        else:
            # Single-model search (original behavior)
            documents_generator = self.agents['query_agent'].find_abstracts(
                question=research_question,
                max_rows=override_max_results,
                human_in_the_loop=interactive_mode,
                human_query_modifier=query_modifier if interactive_mode else None
            )
            # Convert generator to list
            documents = list(documents_generator)

        # Deduplicate documents by ID (defensive programming - shouldn't be needed with proper ORDER BY)
        seen_ids = set()
        deduplicated_documents = []
        for doc in documents:
            doc_id = doc.get('id')
            if doc_id and doc_id not in seen_ids:
                seen_ids.add(doc_id)
                deduplicated_documents.append(doc)
            elif doc_id:
                print(f"⚠️  Found duplicate document in search results: {doc_id} - {doc.get('title', 'Unknown')[:60]}")

        if len(deduplicated_documents) < len(documents):
            print(f"🔍 Deduplicated {len(documents)} search results to {len(deduplicated_documents)} unique documents")
            documents = deduplicated_documents

        # Store documents in the calling workflow BEFORE completing the step
        # This ensures documents are available when the completion callback fires
        
        update_callback(WorkflowStep.SEARCH_DOCUMENTS, "completed",
                      f"Found {len(documents)} documents")
        
        return documents
    
    def execute_document_scoring(self, research_question: str, documents: List[Dict],
                               update_callback: Callable,
                               score_overrides: Optional[Dict[int, float]] = None,
                               score_approvals: Optional[Dict[int, bool]] = None,
                               progress_callback: Optional[Callable[[int, int, str], None]] = None) -> List[Tuple[Dict, Dict]]:
        """Execute the document scoring step with optional human overrides and approvals.

        Args:
            research_question: The research question for relevance scoring
            documents: List of documents to score
            update_callback: Callback for status updates
            score_overrides: Dictionary mapping document indices to human override scores
            score_approvals: Dictionary mapping document indices to approval status
            progress_callback: Optional callback for progress updates (current, total, item_name)

        Returns:
            List of ALL (document, scoring_result) tuples regardless of threshold
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

        # Use audit-enabled scoring if session context is available
        if self.research_question_id and self.session_id and self.query_ids:
            # Use audit tracking
            # For now, use the first query_id. In multi-model scenarios, documents may have been
            # found by multiple queries, but we'll use the primary query for scoring linkage
            primary_query_id = self.query_ids[0] if self.query_ids else None

            if primary_query_id:
                try:
                    # Note: batch_evaluate_with_audit doesn't support progress callback yet
                    # TODO: Enhance batch_evaluate_with_audit to accept progress_callback parameter
                    # For now, we process without real-time progress updates

                    # Show initial progress
                    if progress_callback:
                        progress_callback(0, len(docs_to_process))

                    # It returns (document, scoring_result, scoring_id) tuples
                    audit_results = self.agents['scoring_agent'].batch_evaluate_with_audit(
                        research_question_id=self.research_question_id,
                        session_id=self.session_id,
                        query_id=primary_query_id,
                        user_question=research_question,
                        documents=docs_to_process,
                        skip_already_scored=True
                    )

                    # Store scoring_ids for citation tracking
                    for doc, result, scoring_id in audit_results:
                        if 'id' in doc:
                            self.scoring_ids[doc['id']] = scoring_id

                    # Show final progress
                    if progress_callback:
                        progress_callback(len(audit_results), len(docs_to_process))

                    # Convert to expected format (document, scoring_result)
                    scored_results = [(doc, result) for doc, result, scoring_id in audit_results]
                    print(f"📊 Scored {len(scored_results)} documents with audit tracking")
                except Exception as e:
                    print(f"⚠️ Audit scoring failed, falling back to non-audit: {e}")
                    # Fall back to non-audit scoring
                    scored_results = list(self.agents['scoring_agent'].process_scoring_queue(
                        user_question=research_question,
                        documents=docs_to_process,
                        progress_callback=agent_progress_callback
                    ))
            else:
                # No query_id, use non-audit scoring
                scored_results = list(self.agents['scoring_agent'].process_scoring_queue(
                    user_question=research_question,
                    documents=docs_to_process,
                    progress_callback=agent_progress_callback
                ))
        else:
            # Use non-audit scoring
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
                    
                    # Apply human override or approval if provided
                    if score_overrides and i in score_overrides:
                        result_dict['score'] = score_overrides[i]
                        result_dict['human_override'] = True
                        result_dict['original_ai_score'] = original_score
                        score = score_overrides[i]
                        print(f"Applied human override for document {i}: {original_score:.1f} → {score_overrides[i]:.1f}")

                        # Log the human override to database
                        try:
                            from bmlibrarian.agents import get_human_edit_logger
                            logger = get_human_edit_logger()
                            logger.log_document_score_edit(
                                user_question=research_question,
                                document=doc,
                                ai_score=int(original_score),
                                ai_reasoning=scoring_result.get('reasoning', ''),
                                human_score=int(score_overrides[i]),
                                explicitly_approved=False
                            )
                        except Exception as e:
                            print(f"Warning: Failed to log human override: {e}")

                    elif score_approvals and i in score_approvals:
                        # User explicitly approved the AI score
                        result_dict['human_approved'] = True
                        print(f"User approved AI score for document {i}: {original_score:.1f}")

                        # Log the human approval to database
                        try:
                            from bmlibrarian.agents import get_human_edit_logger
                            logger = get_human_edit_logger()
                            logger.log_document_score_edit(
                                user_question=research_question,
                                document=doc,
                                ai_score=int(original_score),
                                ai_reasoning=scoring_result.get('reasoning', ''),
                                human_score=None,
                                explicitly_approved=True
                            )
                        except Exception as e:
                            print(f"Warning: Failed to log human approval: {e}")
                    
                    all_scored_documents.append((doc, result_dict))
                    
                    if score >= score_threshold:
                        # Store as (document, scoring_result) tuple as expected by citation agent
                        scored_documents.append((doc, result_dict))
                        if score >= 4.0:
                            high_scoring += 1
            except Exception as e:
                print(f"Error processing scored document: {e}")
                continue
        
        # Update performance tracker with document scores if available
        print(f"🔍 DEBUG: Checking performance tracker: tracker={'available' if self.performance_tracker else 'None'}, session_id={self.session_id if self.session_id else 'None'}")
        if self.performance_tracker and self.session_id:
            document_scores = {}
            for doc, result_dict in all_scored_documents:
                doc_id = doc.get('id')
                if doc_id and 'score' in result_dict:
                    document_scores[doc_id] = result_dict['score']

            print(f"🔍 DEBUG: Collected {len(document_scores)} document scores to update")
            if document_scores:
                print(f"🔍 DEBUG: Updating performance tracker with {len(document_scores)} document scores")
                self.performance_tracker.update_document_scores(self.session_id, document_scores)

                # Get and display performance statistics
                from ..config import get_search_config
                search_config = get_search_config()
                threshold = self.config_overrides.get('score_threshold', search_config.get('score_threshold', 2.5))

                print(f"🔍 DEBUG: Getting query statistics for session {self.session_id} with threshold {threshold}")
                stats = self.performance_tracker.get_query_statistics(
                    session_id=self.session_id,
                    score_threshold=threshold
                )

                print(f"🔍 DEBUG: Got {len(stats) if stats else 0} query statistics")
                if stats:
                    print("\n" + "="*80)
                    print("QUERY PERFORMANCE ANALYSIS")
                    print("="*80)
                    formatted_stats = self.agents['query_agent'].format_query_performance_stats(
                        stats, score_threshold=threshold
                    )
                    print(formatted_stats)

                    # Update GUI if tab_manager is available
                    print(f"🔍 DEBUG: Updating GUI with statistics, tab_manager={'available' if self.tab_manager else 'NOT available'}")
                    if self.tab_manager:
                        self.tab_manager.update_search_performance_stats(stats, score_threshold=threshold)
                        print("🔍 DEBUG: GUI update complete")
                else:
                    print("🔍 DEBUG: No statistics to display")

        # Update status message
        override_msg = ""
        if score_overrides:
            override_msg = f" (with {len(score_overrides)} human overrides)"

        update_callback(WorkflowStep.SCORE_DOCUMENTS, "completed",
                      f"Scored {docs_to_score} documents ({len(scored_documents)} above threshold ≥{score_threshold}), {high_scoring} high relevance (≥4.0){override_msg}")

        # Return ALL scored documents, not just those above threshold
        # This allows users to see all scores and adjust thresholds later
        return all_scored_documents
    
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

        # Use audit-enabled citation extraction if session context and scoring_ids available
        if self.research_question_id and self.session_id and self.scoring_ids:
            try:
                # Convert (doc, result) tuples to (doc, result, scoring_id) tuples
                docs_with_ids = []
                for doc, result in docs_for_citations:
                    doc_id = doc.get('id')
                    if doc_id and doc_id in self.scoring_ids:
                        docs_with_ids.append((doc, result, self.scoring_ids[doc_id]))
                    else:
                        print(f"⚠️ Warning: Document {doc_id} missing scoring_id, skipping for audit citation")

                if docs_with_ids:
                    # Note: extract_citations_with_audit doesn't support progress callback yet
                    # It returns (citation, citation_id) tuples
                    audit_citations = self.agents['citation_agent'].extract_citations_with_audit(
                        research_question_id=self.research_question_id,
                        session_id=self.session_id,
                        user_question=research_question,
                        scored_documents_with_ids=docs_with_ids,
                        score_threshold=score_threshold,
                        min_relevance=0.7  # Could be made configurable
                    )
                    # Convert to expected format (just citations)
                    citations = [citation for citation, citation_id in audit_citations]
                    print(f"📊 Extracted {len(citations)} citations with audit tracking")
                else:
                    print(f"⚠️ No documents with scoring_ids, falling back to non-audit citation extraction")
                    citations = self.agents['citation_agent'].process_scored_documents_for_citations(
                        user_question=research_question,
                        scored_documents=docs_for_citations,
                        score_threshold=score_threshold,
                        progress_callback=progress_callback
                    )
            except Exception as e:
                print(f"⚠️ Audit citation extraction failed, falling back to non-audit: {e}")
                # Fall back to non-audit citation extraction
                citations = self.agents['citation_agent'].process_scored_documents_for_citations(
                    user_question=research_question,
                    scored_documents=docs_for_citations,
                    score_threshold=score_threshold,
                    progress_callback=progress_callback
                )
        else:
            # Use non-audit citation extraction
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

        # Use audit-enabled report generation if session context available
        if self.research_question_id and self.session_id:
            try:
                # generate_report_with_audit returns (formatted_report, report_id)
                report_content, report_id = self.agents['reporting_agent'].generate_report_with_audit(
                    research_question_id=self.research_question_id,
                    session_id=self.session_id,
                    user_question=research_question,
                    citations=citations,
                    report_type='preliminary',
                    format_output=True,
                    is_final=False
                )
                # Wrap the string in an object for compatibility
                class ReportWrapper:
                    def __init__(self, content):
                        self.content = content
                report = ReportWrapper(report_content) if report_content else None
                print(f"📊 Generated report with audit tracking (report_id: {report_id})")
            except Exception as e:
                print(f"⚠️ Audit report generation failed, falling back to non-audit: {e}")
                # Fall back to non-audit report generation
                report = self.agents['reporting_agent'].generate_citation_based_report(
                    user_question=research_question,
                    citations=citations,
                    format_output=True
                )
        else:
            # Use non-audit report generation
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
        """Execute comprehensive counterfactual analysis with progressive GUI updates.

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

        # Use the same max_results as the initial literature search for consistency
        main_max_results = self.config_overrides.get('max_results', search_config.get('max_results', 100))
        counterfactual_max_results = self.config_overrides.get('counterfactual_max_results', main_max_results)

        print(f"🔍 Counterfactual search using max_results: {counterfactual_max_results} (main search used: {main_max_results})")

        # Track intermediate data for progressive updates
        progressive_data = {
            'analysis': None,
            'research_queries': [],
            'contradictory_evidence': []
        }

        # Create a custom progress callback for real-time GUI updates
        def counterfactual_progress_callback(event_type: str, data: Any):
            """Handle counterfactual agent progress events and update GUI progressively."""
            try:
                if event_type == "counterfactual_complete":
                    # Initial analysis complete - update claims and questions
                    if isinstance(data, str):
                        update_callback(WorkflowStep.PERFORM_COUNTERFACTUAL_ANALYSIS, "progress", data)
                elif event_type == "analysis_complete":
                    # Store analysis and update claims/questions sections
                    progressive_data['analysis'] = data
                    if hasattr(data, 'main_claims'):
                        update_callback(WorkflowStep.PERFORM_COUNTERFACTUAL_ANALYSIS, "cf_claims", data.main_claims)
                    if hasattr(data, 'counterfactual_questions'):
                        update_callback(WorkflowStep.PERFORM_COUNTERFACTUAL_ANALYSIS, "cf_questions", data.counterfactual_questions)
                elif event_type == "queries_generated":
                    # Research queries generated - update searches section
                    progressive_data['research_queries'] = data
                    update_callback(WorkflowStep.PERFORM_COUNTERFACTUAL_ANALYSIS, "cf_searches", data)
                elif event_type == "search_results":
                    # Search completed - update results section incrementally
                    update_callback(WorkflowStep.PERFORM_COUNTERFACTUAL_ANALYSIS, "progress", data)
                elif event_type == "scoring_complete":
                    # Scoring complete - update results section with scored documents
                    if isinstance(data, list):
                        progressive_data['contradictory_evidence'].extend(data)
                        update_callback(WorkflowStep.PERFORM_COUNTERFACTUAL_ANALYSIS, "cf_results", progressive_data['contradictory_evidence'])
                elif event_type == "citations_complete":
                    # Citation extraction complete - update citations section
                    if isinstance(data, dict):
                        update_callback(WorkflowStep.PERFORM_COUNTERFACTUAL_ANALYSIS, "cf_citations", data)
                else:
                    # Generic progress message
                    update_callback(WorkflowStep.PERFORM_COUNTERFACTUAL_ANALYSIS, "progress", str(data))
            except Exception as e:
                print(f"⚠️  Error in counterfactual progress callback: {e}")

        # Store original callback and set our custom one
        original_callback = self.agents['counterfactual_agent'].callback
        self.agents['counterfactual_agent'].callback = counterfactual_progress_callback

        try:
            comprehensive_analysis = self.agents['counterfactual_agent'].find_contradictory_literature(
                document_content=report_content,
                document_title="Research Report with Citations",
                max_results_per_query=counterfactual_max_results,
                min_relevance_score=self.config_overrides.get('counterfactual_min_score', search_config.get('counterfactual_min_score', 3)),
                query_agent=self.agents.get('query_agent'),
                scoring_agent=self.agents.get('scoring_agent'),
                citation_agent=self.agents.get('citation_agent')
            )
        finally:
            # Restore original callback
            self.agents['counterfactual_agent'].callback = original_callback

        # Final update with complete data
        if comprehensive_analysis and isinstance(comprehensive_analysis, dict):
            # Update claims section
            analysis_obj = comprehensive_analysis.get('analysis')
            if analysis_obj and hasattr(analysis_obj, 'main_claims'):
                update_callback(WorkflowStep.PERFORM_COUNTERFACTUAL_ANALYSIS, "cf_claims",
                              analysis_obj.main_claims)

            # Update questions section
            if analysis_obj and hasattr(analysis_obj, 'counterfactual_questions'):
                update_callback(WorkflowStep.PERFORM_COUNTERFACTUAL_ANALYSIS, "cf_questions",
                              analysis_obj.counterfactual_questions)

            # Update searches section
            research_queries = comprehensive_analysis.get('research_queries', [])
            if research_queries:
                update_callback(WorkflowStep.PERFORM_COUNTERFACTUAL_ANALYSIS, "cf_searches",
                              research_queries)

            # Update results section
            contradictory_evidence = comprehensive_analysis.get('contradictory_evidence', [])
            if contradictory_evidence:
                update_callback(WorkflowStep.PERFORM_COUNTERFACTUAL_ANALYSIS, "cf_results",
                              contradictory_evidence)

            # Update citations section
            contradictory_citations = comprehensive_analysis.get('contradictory_citations', [])
            rejected_citations = comprehensive_analysis.get('rejected_citations', [])
            no_citation_extracted = comprehensive_analysis.get('no_citation_extracted', [])
            update_callback(WorkflowStep.PERFORM_COUNTERFACTUAL_ANALYSIS, "cf_citations",
                          {
                              'contradictory_citations': contradictory_citations,
                              'rejected_citations': rejected_citations,
                              'no_citation_extracted': no_citation_extracted
                          })

            # Update summary section
            summary = comprehensive_analysis.get('summary', {})
            if summary:
                update_callback(WorkflowStep.PERFORM_COUNTERFACTUAL_ANALYSIS, "cf_summary",
                              summary)

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