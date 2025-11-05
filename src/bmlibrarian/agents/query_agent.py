"""
Query Agent for Natural Language to PostgreSQL Query Conversion

Specialized agent that converts human language questions into PostgreSQL
to_tsquery format optimized for biomedical literature searches.
"""

import re
import logging
from typing import Generator, Dict, Optional, Callable, TYPE_CHECKING, Any, List
from datetime import date

from .base import BaseAgent
from ..database import find_abstracts
from .utils.query_syntax import fix_tsquery_syntax

if TYPE_CHECKING:
    from .orchestrator import AgentOrchestrator
    from .query_generation.data_types import MultiModelQueryResult


logger = logging.getLogger(__name__)


class QueryAgent(BaseAgent):
    """
    Agent for converting natural language questions to PostgreSQL to_tsquery format.
    
    Uses Ollama to connect to a local LLM for intelligent keyword extraction
    and query composition tailored for biomedical literature searches.
    """
    
    def __init__(
        self,
        model: str = "medgemma4B_it_q8:latest",
        host: str = "http://localhost:11434",
        temperature: float = 0.1,
        top_p: float = 0.9,
        callback: Optional[Callable[[str, str], None]] = None,
        orchestrator: Optional["AgentOrchestrator"] = None,
        show_model_info: bool = True
    ):
        """
        Initialize the QueryAgent.
        
        Args:
            model: The name of the Ollama model to use (default: medgemma4B_it_q8:latest)
            host: The Ollama server host URL (default: http://localhost:11434)
            temperature: Model temperature for response consistency (default: 0.1)
            top_p: Model top-p sampling parameter (default: 0.9)
            callback: Optional callback function for progress updates
            orchestrator: Optional orchestrator for queue-based processing
            show_model_info: Whether to display model information on initialization
        """
        super().__init__(model, host, temperature, top_p, callback, orchestrator, show_model_info)
        
        # System prompt for biomedical query conversion
        self.system_prompt = """You are a biomedical literature search expert. Your task is to convert natural language questions into PostgreSQL to_tsquery format for searching biomedical publication abstracts.

Rules:
1. Extract the most relevant biomedical keywords from the user's question
2. Use '&' for AND operations (terms that should all appear)
3. Use '|' for OR operations (alternative terms)
4. Use '!' for NOT operations (to exclude terms) - prefix the term to negate
5. Use parentheses to group related terms
6. Use multi-word phrases naturally (e.g., myocardial infarction, early diagnosis)
7. Focus on medical terminology, drug names, disease names, biological processes
8. Include both specific terms and broader category terms when relevant
9. Avoid common words like 'the', 'and', 'or', 'what', 'how'
10. Return ONLY the to_tsquery string, no explanation

Examples:
Question: "What are the effects of aspirin on cardiovascular disease?"
to_tsquery: "aspirin & (cardiovascular | cardiac | heart) & (disease | disorder | condition)"

Question: "How does diabetes affect kidney function?"
to_tsquery: "diabetes & (kidney | renal | nephro) & (function | dysfunction | disease)"

Question: "Studies on COVID-19 vaccine effectiveness"
to_tsquery: "(covid | coronavirus | sars-cov-2) & vaccine & (effectiveness | efficacy)"

Question: "Research on myocardial infarction and heart attacks"
to_tsquery: "(myocardial infarction | AMI | heart attack) & research"

Question: "Biomarkers for early Alzheimer's diagnosis"
to_tsquery: "(Alzheimer's disease | AD | early diagnosis | early detection) & (biomarker | marker | blood test | cerebrospinal fluid)"

Question: "Statins for cholesterol but not in children"
to_tsquery: "statin & cholesterol & !(children | pediatric | paediatric)"
"""
    
    def get_agent_type(self) -> str:
        """Get the agent type identifier."""
        return "query_agent"
    
    def convert_question(self, question: str) -> str:
        """
        Convert a natural language question to PostgreSQL to_tsquery format.
        
        Args:
            question: The natural language question to convert
            
        Returns:
            A string formatted for PostgreSQL to_tsquery()
            
        Raises:
            ConnectionError: If unable to connect to Ollama
            ValueError: If the question is empty or invalid
        """
        if not question or not question.strip():
            raise ValueError("Question cannot be empty")
        
        self._call_callback("conversion_started", question)
        
        try:
            messages = [{'role': 'user', 'content': question}]
            
            query = self._make_ollama_request(
                messages,
                system_prompt=self.system_prompt,
                num_predict=100
            )
            
            # Clean up quotation marks, remove duplicates, and validate
            logger.debug(f"Raw LLM response: {repr(query)}")
            query = self._clean_quotes(query)
            logger.debug(f"After cleaning quotes: {repr(query)}")
            query = self._remove_duplicates(query)
            logger.debug(f"After removing duplicates: {repr(query)}")
            query = self._fix_malformed_syntax(query)
            logger.debug(f"After syntax fixes: {repr(query)}")
            
            if not self._validate_tsquery(query):
                logger.warning(f"Generated query may be invalid: {query}")
            
            self._call_callback("query_generated", query)
            return query
            
        except Exception as e:
            self._call_callback("conversion_failed", str(e))
            raise
    
    def _clean_quotes(self, query: str) -> str:
        """
        Clean up and properly quote phrases in the query string.

        Removes surrounding quotes, escapes single quotes in phrases,
        and wraps multi-word phrases in single quotes for PostgreSQL to_tsquery compatibility.

        Args:
            query: The query string to clean

        Returns:
            The cleaned query string with properly quoted phrases
        """
        # Remove any surrounding quotes that the LLM might have added
        # Handle multiple layers of quotes if present
        query = query.strip()
        
        # Remove common prefixes that the LLM might include
        prefixes_to_remove = ['to_tsquery:', 'tsquery:', 'query:', 'search:']
        for prefix in prefixes_to_remove:
            if query.lower().startswith(prefix.lower()):
                query = query[len(prefix):].strip()
        
        while ((query.startswith('"') and query.endswith('"')) or 
               (query.startswith("'") and query.endswith("'"))):
            query = query[1:-1].strip()
            
        # Also handle cases where quotes might be imbalanced or mixed
        if query.startswith('"') and not query.endswith('"'):
            query = query[1:]
        elif query.startswith("'") and not query.endswith("'"):
            query = query[1:]
        elif query.endswith('"') and not query.startswith('"'):
            query = query[:-1]
        elif query.endswith("'") and not query.startswith("'"):
            query = query[:-1]

        # Remove existing quotation marks around phrases, but preserve apostrophes
        # This is tricky because we need to distinguish between quotes and apostrophes
        # Strategy: replace quoted phrases first, then handle remaining quotes
        import re as re_module
        
        # Convert double quotes to single quotes for PostgreSQL compatibility
        query = re_module.sub(r'"([^"]*)"', r"'\1'", query)
        
        # Remove quotes that are clearly used for phrase delimiting (not apostrophes)
        # Pattern: quotes that are preceded/followed by spaces or operators
        query = re_module.sub(r'(?<=[&|()\s])[\'"]+', '', query)  # Leading quotes
        query = re_module.sub(r'[\'"]+(?=[&|)()\s]|$)', '', query)  # Trailing quotes

        # Now find multi-word phrases and quote them properly
        def quote_phrase(match):
            phrase = match.group(0)
            # Escape single quotes within the phrase by doubling them
            phrase = phrase.replace("'", "''")
            return f"'{phrase}'"

        # Pattern to match multi-word phrases:
        # - Two or more words separated by spaces
        # - Not preceded/followed by operators or parentheses
        # - Words can contain letters, numbers, apostrophes, hyphens
        pattern = r'\b[a-zA-Z0-9\'\-]+(?:\s+[a-zA-Z0-9\'\-]+)+\b'

        query = re_module.sub(pattern, quote_phrase, query)

        return query
    
    def _remove_duplicates(self, query: str) -> str:
        """
        Remove duplicate terms from OR groups in the query.
        
        Args:
            query: The query string to deduplicate
            
        Returns:
            Query with duplicate terms removed
        """
        import re as re_module
        
        def deduplicate_or_group(match):
            """Process a parenthesized OR group and remove duplicates."""
            group_content = match.group(1)  # Content inside parentheses
            
            # Split on | to get individual terms
            terms = [term.strip() for term in group_content.split('|')]
            
            # Remove duplicates while preserving order
            seen = set()
            unique_terms = []
            for term in terms:
                # Normalize for comparison (handle quotes and case)
                normalized = term.lower().strip('\'"')
                if normalized not in seen and term.strip():
                    seen.add(normalized)
                    unique_terms.append(term)
            
            # Rejoin with |
            if len(unique_terms) > 1:
                return f"({' | '.join(unique_terms)})"
            elif len(unique_terms) == 1:
                return unique_terms[0]
            else:
                return ""
        
        # Find and deduplicate OR groups: (term1 | term2 | term1 | term3)
        pattern = r'\(([^()]+)\)'
        query = re_module.sub(pattern, deduplicate_or_group, query)
        
        # Clean up any double spaces or operators
        query = re_module.sub(r'\s+', ' ', query)
        query = re_module.sub(r'\s*\|\s*', ' | ', query)
        query = re_module.sub(r'\s*&\s*', ' & ', query)
        
        return query.strip()
    
    def _fix_malformed_syntax(self, query: str) -> str:
        """
        Fix common syntax issues in generated queries using comprehensive fix.

        Args:
            query: The query string to fix

        Returns:
            Query with syntax issues fixed
        """
        # Use the comprehensive fix_tsquery_syntax function
        return fix_tsquery_syntax(query)
    
    def _validate_tsquery(self, query: str) -> bool:
        """
        Basic validation of to_tsquery format.

        Args:
            query: The query string to validate

        Returns:
            True if the query appears to be valid to_tsquery format
        """
        if not query:
            return False

        # Check for balanced parentheses
        if query.count('(') != query.count(')'):
            return False

        # Check for valid operators
        invalid_patterns = ['&&', '||', '&|', '|&']
        for pattern in invalid_patterns:
            if pattern in query:
                return False

        return True
    
    def find_abstracts(
        self,
        question: str,
        max_rows: int = 100,
        use_pubmed: bool = True,
        use_medrxiv: bool = True,
        use_others: bool = True,
        from_date: Optional[date] = None,
        to_date: Optional[date] = None,
        batch_size: int = 50,
        use_ranking: bool = False,
        human_in_the_loop: bool = False,
        human_query_modifier: Optional[Callable[[str], str]] = None,
        offset: int = 0
    ) -> Generator[Dict, None, None]:
        """
        Find biomedical abstracts using natural language questions.

        Converts a human language question to a PostgreSQL to_tsquery format,
        then searches the database for matching abstracts.

        Args:
            question: Natural language question (e.g., "What are the effects of aspirin on heart disease?")
            max_rows: Maximum number of rows to return (0 = no limit)
            use_pubmed: Include PubMed sources
            use_medrxiv: Include medRxiv sources
            use_others: Include other sources
            from_date: Only include documents published on or after this date (inclusive)
            to_date: Only include documents published on or before this date (inclusive)
            batch_size: Number of rows to fetch in each database round trip
            use_ranking: If True, calculate and order by relevance ranking
            human_in_the_loop: If True, allow human to modify the generated query
            human_query_modifier: Optional function to modify query when human_in_the_loop=True
            offset: Number of rows to skip before returning results (default: 0)

        Yields:
            Dict containing document information (same format as database.find_abstracts)

        Raises:
            ValueError: If question is empty
            ConnectionError: If unable to connect to Ollama or database
        """
        if not question or not question.strip():
            raise ValueError("Question cannot be empty")

        # Step 1: Convert natural language question to ts_query
        try:
            ts_query_str = self.convert_question(question)
            logger.info(f"Generated ts_query: {ts_query_str}")

        except Exception as e:
            self._call_callback("conversion_failed", str(e))
            raise

        # Step 2: Human-in-the-loop query modification
        if human_in_the_loop and human_query_modifier:
            try:
                self._call_callback("human_review_started", ts_query_str)

                modified_query = human_query_modifier(ts_query_str)

                if modified_query and modified_query.strip() != ts_query_str:
                    ts_query_str = modified_query.strip()
                    logger.info(f"Human modified query to: {ts_query_str}")
                    self._call_callback("query_modified", ts_query_str)
                else:
                    self._call_callback("query_unchanged", ts_query_str)

            except Exception as e:
                logger.warning(f"Human query modification failed: {e}")
                self._call_callback("human_review_failed", str(e))
                # Continue with original query

        # Step 2.5: Fix any malformed quotes in the query (from LLM or human edits)
        ts_query_str_before = ts_query_str
        ts_query_str = fix_tsquery_syntax(ts_query_str)
        if ts_query_str != ts_query_str_before:
            logger.info(f"Query syntax fixed: '{ts_query_str_before}' -> '{ts_query_str}'")

        # Step 3: Search database with the final query
        try:
            self._call_callback("search_started", ts_query_str)

            # Call the database find_abstracts function with plain=False since we generated to_tsquery format
            yield from find_abstracts(
                ts_query_str=ts_query_str,
                max_rows=max_rows,
                use_pubmed=use_pubmed,
                use_medrxiv=use_medrxiv,
                use_others=use_others,
                plain=False,  # We generated to_tsquery format, not plain text
                from_date=from_date,
                to_date=to_date,
                batch_size=batch_size,
                use_ranking=use_ranking,
                offset=offset
            )

            self._call_callback("search_completed", ts_query_str)

        except Exception as e:
            self._call_callback("search_failed", str(e))
            logger.error(f"Database search failed: {e}")
            raise

    def convert_question_multi_model(
        self,
        question: str
    ) -> 'MultiModelQueryResult':
        """
        Convert question using multiple models for improved query diversity.

        When multi_model_enabled is False, falls back to single-model behavior
        identical to convert_question() for backward compatibility.

        Args:
            question: The natural language question to convert

        Returns:
            MultiModelQueryResult containing all generated queries and metadata

        Raises:
            ValueError: If question is empty
            ConnectionError: If unable to connect to Ollama
        """
        if not question or not question.strip():
            raise ValueError("Question cannot be empty")

        from bmlibrarian.config import get_query_generation_config
        from .query_generation import MultiModelQueryGenerator
        from .query_generation.data_types import QueryGenerationResult, MultiModelQueryResult

        # Get configuration
        qg_config = get_query_generation_config()

        # Check if multi-model is enabled
        if not qg_config.get('multi_model_enabled', False):
            # Fallback: single model, single query (backward compatible)
            logger.info("Multi-model disabled, using single-model fallback")

            single_query = self.convert_question(question)

            single_result = QueryGenerationResult(
                model=self.model,
                query=single_query,
                generation_time=0.0,
                temperature=self.temperature,
                attempt_number=1,
                error=None
            )

            return MultiModelQueryResult(
                all_queries=[single_result],
                unique_queries=[single_query],
                model_count=1,
                total_queries=1,
                total_generation_time=0.0,
                question=question
            )

        # Multi-model generation (SERIAL execution)
        logger.info(f"Multi-model enabled: {len(qg_config['models'])} models, {qg_config['queries_per_model']} queries/model")

        self._call_callback("multi_model_generation_started", question)

        generator = MultiModelQueryGenerator(self.host, self.callback)

        result = generator.generate_queries(
            question=question,
            system_prompt=self.system_prompt,
            models=qg_config['models'],
            queries_per_model=qg_config['queries_per_model'],
            temperature=self.temperature,
            top_p=self.top_p
        )

        self._call_callback("multi_model_generation_completed",
            f"Generated {result.total_queries} queries, {len(result.unique_queries)} unique")

        return result

    def find_abstracts_multi_query(
        self,
        question: str,
        max_rows: int = 100,
        use_pubmed: bool = True,
        use_medrxiv: bool = True,
        use_others: bool = True,
        from_date: Optional[date] = None,
        to_date: Optional[date] = None,
        human_in_the_loop: bool = False,
        human_query_modifier: Optional[Callable[[list[str]], list[str]]] = None,
        performance_tracker: Optional[Any] = None,
        session_id: Optional[str] = None
    ) -> Generator[Dict, None, None]:
        """
        Find abstracts using multi-model query generation.

        Process (SERIAL execution):
        1. Generate multiple queries using different models
        2. If human_in_the_loop, show queries and allow selection/editing
        3. Execute each query SERIALLY to get document IDs
        4. De-duplicate IDs across all queries
        5. Fetch full documents for unique IDs
        6. Yield documents

        Args:
            question: Natural language question
            max_rows: Max results per query (total may be less after dedup)
            use_pubmed: Include PubMed sources
            use_medrxiv: Include medRxiv sources
            use_others: Include other sources
            from_date: Only include documents published on or after this date
            to_date: Only include documents published on or before this date
            human_in_the_loop: Allow user to review/select queries
            human_query_modifier: Callback for query selection
            performance_tracker: Optional QueryPerformanceTracker for tracking stats
            session_id: Optional session ID for performance tracking

        Yields:
            Document dictionaries (same format as find_abstracts)

        Example:
            >>> agent = QueryAgent()
            >>> for doc in agent.find_abstracts_multi_query("aspirin benefits"):
            ...     print(doc['title'])
        """
        from bmlibrarian.config import get_query_generation_config
        from bmlibrarian.database import find_abstract_ids, fetch_documents_by_ids

        # Get configuration
        qg_config = get_query_generation_config()

        # Check if multi-model enabled
        if not qg_config.get('multi_model_enabled', False):
            # Fallback to original single-query behavior
            logger.info("Multi-model disabled, using single-query fallback")
            yield from self.find_abstracts(
                question=question,
                max_rows=max_rows,
                use_pubmed=use_pubmed,
                use_medrxiv=use_medrxiv,
                use_others=use_others,
                from_date=from_date,
                to_date=to_date
            )
            return

        # Step 1: Generate queries with multiple models
        logger.info("Starting multi-model query generation")
        self._call_callback("multi_query_generation_started", question)

        query_results = self.convert_question_multi_model(question)

        # Step 2: Human-in-the-loop query selection
        queries_to_execute = query_results.unique_queries

        if human_in_the_loop and human_query_modifier:
            try:
                self._call_callback("human_query_review_started", "Showing queries for review")
                modified_queries = human_query_modifier(queries_to_execute)
                if modified_queries:
                    queries_to_execute = modified_queries
                    logger.info(f"User selected {len(queries_to_execute)} queries to execute")
                self._call_callback("queries_selected", f"{len(queries_to_execute)} queries selected")
            except Exception as e:
                logger.warning(f"Human query modification failed: {e}")
                # Continue with original queries

        # Step 3: Execute queries SERIALLY and collect IDs
        logger.info(f"Executing {len(queries_to_execute)} queries serially")
        self._call_callback("multi_query_execution_started", f"Executing {len(queries_to_execute)} queries")

        all_document_ids = set()
        # Use max_rows per query (not divided) - merged list may contain more documents
        rows_per_query = max_rows

        # Track per-query statistics for detailed reporting
        query_stats = []

        # Get mapping from SANITIZED query text to QueryGenerationResult for model info
        query_to_result = {}
        for qr in query_results.all_queries:
            sanitized_qr_query = fix_tsquery_syntax(qr.query)
            query_to_result[sanitized_qr_query] = qr

        for i, query in enumerate(queries_to_execute, 1):
            import time
            query_start_time = time.time()

            try:
                # Fix query syntax before execution
                sanitized_query = fix_tsquery_syntax(query)

                logger.info(f"Executing query {i}/{len(queries_to_execute)}: {sanitized_query[:50]}...")
                self._call_callback("query_executing", f"Query {i}/{len(queries_to_execute)}")

                # Execute query to get IDs only (fast)
                ids = find_abstract_ids(
                    ts_query_str=sanitized_query,
                    max_rows=rows_per_query,
                    use_pubmed=use_pubmed,
                    use_medrxiv=use_medrxiv,
                    use_others=use_others,
                    plain=False,  # Use to_tsquery format
                    from_date=from_date,
                    to_date=to_date
                )

                query_execution_time = time.time() - query_start_time

                all_document_ids.update(ids)

                # Store per-query statistics
                query_stat = {
                    'query_index': i,
                    'query_text': sanitized_query,
                    'result_count': len(ids),
                    'success': True,
                    'error': None
                }
                query_stats.append(query_stat)

                # Track in performance tracker if provided
                if performance_tracker and session_id:
                    # Get model info from QueryGenerationResult using sanitized query
                    gen_result = query_to_result.get(sanitized_query)
                    if gen_result:
                        import uuid
                        query_id = str(uuid.uuid4())
                        performance_tracker.track_query(
                            query_id=query_id,
                            session_id=session_id,
                            model=gen_result.model,
                            query_text=sanitized_query,
                            temperature=gen_result.temperature,
                            top_p=self.top_p,
                            attempt_number=gen_result.attempt_number,
                            execution_time=query_execution_time,
                            document_ids=list(ids)
                        )
                        logger.debug(f"Tracked query {i} for model {gen_result.model}, {len(ids)} docs")
                    else:
                        logger.warning(f"Could not find model info for sanitized query: {sanitized_query[:60]}...")

                logger.info(f"Query {i} found {len(ids)} IDs, total unique: {len(all_document_ids)}")
                self._call_callback("query_executed", f"Found {len(ids)} IDs")

            except Exception as e:
                # Store error information
                query_stat = {
                    'query_index': i,
                    'query_text': query,
                    'result_count': 0,
                    'success': False,
                    'error': str(e)
                }
                query_stats.append(query_stat)

                logger.error(f"Query execution failed: {query} - {e}")
                self._call_callback("query_failed", f"Query {i} failed: {str(e)}")
                # Continue with other queries

        # Send detailed query statistics via callback
        import json
        self._call_callback("multi_query_stats", json.dumps({
            'query_stats': query_stats,
            'total_unique_ids': len(all_document_ids)
        }))

        # Step 4: Fetch full documents for unique IDs
        logger.info(f"Fetching {len(all_document_ids)} unique documents")
        self._call_callback("fetching_documents", f"Fetching {len(all_document_ids)} documents")

        if not all_document_ids:
            logger.warning("No documents found across all queries")
            self._call_callback("no_documents_found", "No documents found")
            return

        documents = fetch_documents_by_ids(all_document_ids)

        logger.info(f"Multi-query search complete: {len(queries_to_execute)} queries → {len(documents)} documents")
        self._call_callback("multi_query_search_completed",
            f"{len(queries_to_execute)} queries → {len(documents)} documents")

        # Step 5: Yield documents
        for doc in documents:
            yield doc

    @staticmethod
    def format_query_performance_stats(
        stats: List[Any],
        score_threshold: float = 3.0
    ) -> str:
        """Format query performance statistics for display.

        Args:
            stats: List of QueryPerformanceStats from performance_tracker
            score_threshold: Threshold used for high-scoring documents

        Returns:
            Formatted string with statistics table
        """
        from .query_generation import QueryPerformanceStats

        if not stats:
            return "No performance statistics available"

        lines = []
        lines.append(f"\n{'='*80}")
        lines.append("QUERY PERFORMANCE STATISTICS")
        lines.append(f"{'='*80}")
        lines.append(f"Score threshold: {score_threshold}")
        lines.append("")

        for i, stat in enumerate(stats, 1):
            lines.append(f"Query #{i} ({stat.model}, T={stat.temperature:.2f}):")
            lines.append(f"  Total documents: {stat.total_documents}")
            lines.append(f"  High-scoring (>={score_threshold}): {stat.high_scoring_documents}")
            lines.append(f"  Unique to this query: {stat.unique_documents}")
            lines.append(f"  Unique high-scoring: {stat.unique_high_scoring}")
            lines.append(f"  Execution time: {stat.execution_time:.2f}s")
            lines.append(f"  Query: {stat.query[:60]}..." if len(stat.query) > 60 else f"  Query: {stat.query}")
            lines.append("")

        # Summary statistics
        total_docs = sum(s.total_documents for s in stats)
        total_high_scoring = sum(s.high_scoring_documents for s in stats)
        total_unique = sum(s.unique_documents for s in stats)
        total_unique_high = sum(s.unique_high_scoring for s in stats)
        avg_exec_time = sum(s.execution_time for s in stats) / len(stats) if stats else 0

        lines.append(f"{'='*80}")
        lines.append("SUMMARY")
        lines.append(f"{'='*80}")
        lines.append(f"Total queries executed: {len(stats)}")
        lines.append(f"Total documents found (with duplicates): {total_docs}")
        lines.append(f"Total high-scoring (with duplicates): {total_high_scoring}")
        lines.append(f"Total unique documents found: {total_unique}")
        lines.append(f"Total unique high-scoring: {total_unique_high}")
        lines.append(f"Average execution time: {avg_exec_time:.2f}s")
        lines.append(f"{'='*80}")

        return "\n".join(lines)