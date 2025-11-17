"""
Citation Finder Agent for extracting relevant passages from scored documents.

Processes documents above a threshold score to extract specific passages
that answer user questions, building a queue of verifiable citations.
"""

import json
import logging
from typing import Dict, List, Optional, Any, Iterator, Tuple, Callable
from dataclasses import dataclass
from datetime import datetime, timezone
import psycopg

from .base import BaseAgent
from .queue_manager import QueueManager, TaskPriority, TaskStatus

logger = logging.getLogger(__name__)


@dataclass
class Citation:
    """Represents an extracted citation from a document."""
    passage: str
    summary: str
    relevance_score: float  # 0-1 confidence in relevance
    document_id: str  # Verified document ID from database
    document_title: str
    authors: List[str]
    publication_date: str
    pmid: Optional[str] = None
    doi: Optional[str] = None
    publication: Optional[str] = None
    created_at: Optional[datetime] = None
    human_review_status: Optional[str] = None  # 'accepted', 'refused', or None (unrated)
    abstract: Optional[str] = None  # Full abstract for display in review

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now(timezone.utc)


class CitationFinderAgent(BaseAgent):
    """
    Agent for finding and extracting relevant citations from scored documents.
    
    Processes documents that exceed a specified score threshold to extract
    passages that directly answer or contribute to answering user questions.
    """
    
    def __init__(self,
                 model: str = "gpt-oss:20b",
                 host: str = "http://localhost:11434",
                 temperature: float = 0.1,
                 top_p: float = 0.9,
                 callback: Optional[Callable[[str, str], None]] = None,
                 orchestrator=None,
                 show_model_info: bool = True,
                 audit_conn: Optional[psycopg.Connection] = None,
                 max_retries: int = 3):
        """
        Initialize the CitationFinderAgent.

        Args:
            model: The name of the Ollama model to use (default: gpt-oss:20b)
            host: The Ollama server host URL (default: http://localhost:11434)
            temperature: Model temperature for citation extraction (default: 0.1)
            top_p: Model top-p sampling parameter (default: 0.9)
            callback: Optional callback function for progress updates
            orchestrator: Optional orchestrator for queue-based processing
            show_model_info: Whether to display model information on initialization
            audit_conn: Optional PostgreSQL connection for audit tracking
            max_retries: Maximum number of retry attempts for failed citation extractions (default: 3)
        """
        super().__init__(model=model, host=host, temperature=temperature, top_p=top_p,
                        callback=callback, orchestrator=orchestrator, show_model_info=show_model_info)
        self.agent_type = "citation_finder_agent"
        self.max_retries = max_retries

        # Initialize audit tracking components if connection provided
        self._citation_tracker = None
        self._evaluator_manager = None
        self._evaluator_id = None

        if audit_conn:
            from bmlibrarian.audit import CitationTracker, EvaluatorManager
            self._citation_tracker = CitationTracker(audit_conn)
            self._evaluator_manager = EvaluatorManager(audit_conn)

            # Auto-create evaluator for this agent configuration
            self._evaluator_id = self._evaluator_manager.get_evaluator_for_agent(
                agent_type='citation',
                model_name=model,
                temperature=temperature,
                top_p=top_p
            )
            logger.info(f"CitationAgent initialized with evaluator_id={self._evaluator_id}")

        # Initialize validation statistics tracking
        self._validation_stats = {
            'total_extractions': 0,
            'validations_passed': 0,
            'validations_failed': 0,
            'exact_matches': 0,
            'fuzzy_matches': 0,
            'failed_citations': []
        }

    def get_agent_type(self) -> str:
        """Get the agent type identifier."""
        return "citation_finder_agent"

    def _validate_and_extract_exact_match(
        self,
        llm_passage: str,
        abstract: str,
        min_similarity: float = 0.95
    ) -> tuple[bool, float, Optional[str]]:
        """
        Verify citation passage exists in abstract and extract exact matching text.

        If LLM paraphrased or slightly modified the text, this finds the closest
        matching substring in the original abstract and returns it. This ensures
        we always use EXACT text from the source, never LLM-generated paraphrases.

        Args:
            llm_passage: Text extracted by LLM (may be modified/paraphrased)
            abstract: Source abstract to search
            min_similarity: Minimum similarity threshold (0.0-1.0, default 0.95)

        Returns:
            (is_valid, similarity_score, exact_text_from_abstract)
            - is_valid: Whether a good match was found
            - similarity_score: Best match similarity (1.0 = perfect)
            - exact_text_from_abstract: The actual text from abstract (None if invalid)
        """
        from difflib import SequenceMatcher

        # Normalize whitespace for comparison
        passage_norm = ' '.join(llm_passage.lower().split())
        abstract_norm = ' '.join(abstract.lower().split())

        # Check for exact substring match first (fastest path)
        if passage_norm in abstract_norm:
            # Find the original text with preserved formatting
            # Search case-insensitively but preserve original case
            abstract_lower = abstract.lower()
            passage_lower = llm_passage.lower()
            start_pos = abstract_lower.find(passage_lower)

            if start_pos != -1:
                exact_text = abstract[start_pos:start_pos + len(llm_passage)]
                logger.debug(f"Found exact match in abstract (similarity=1.0)")
                return True, 1.0, exact_text

        # Fuzzy match with sliding window to find best matching substring
        best_match_score = 0.0
        best_match_start = 0
        best_match_len = len(llm_passage)

        passage_len_chars = len(passage_norm)

        # Try different window sizes (±20% of passage length)
        for window_len in range(
            int(passage_len_chars * 0.8),
            int(passage_len_chars * 1.2) + 1
        ):
            if window_len > len(abstract_norm):
                continue

            # Slide window across abstract
            for i in range(len(abstract_norm) - window_len + 1):
                window = abstract_norm[i:i + window_len]
                similarity = SequenceMatcher(None, passage_norm, window).ratio()

                if similarity > best_match_score:
                    best_match_score = similarity
                    best_match_start = i
                    best_match_len = window_len

        # If we found a good match, extract the original text from abstract
        if best_match_score >= min_similarity:
            # Map normalized position back to original abstract
            # We need to find where character N in normalized text appears in original
            char_count = 0
            orig_start = 0

            for orig_pos, char in enumerate(abstract):
                if char.strip():  # Count non-whitespace characters
                    if char_count == best_match_start:
                        orig_start = orig_pos
                        break
                    char_count += 1

            # Estimate length in original text (account for whitespace)
            # Use a generous buffer to capture full sentences
            extract_len = min(len(llm_passage) + 200, len(abstract) - orig_start)
            candidate = abstract[orig_start:orig_start + extract_len]

            # Find best sentence boundaries
            # Try to extract complete sentences
            sentences = candidate.split('. ')
            if len(sentences) > 1:
                # Take first N sentences that approximately match length
                best_extract = sentences[0]
                for sent in sentences[1:]:
                    if len(best_extract) < len(llm_passage) * 1.3:
                        best_extract += '. ' + sent
                    else:
                        break
                # Clean up and ensure proper ending
                exact_text = best_extract.strip()
                if not exact_text.endswith('.') and len(sentences) > 1:
                    exact_text += '.'
            else:
                exact_text = candidate.strip()

            logger.debug(
                f"Found fuzzy match in abstract (similarity={best_match_score:.3f}). "
                f"Extracted exact text ({len(exact_text)} chars)"
            )
            return True, best_match_score, exact_text

        logger.debug(f"No valid match found (best similarity={best_match_score:.3f})")
        return False, best_match_score, None

    def get_validation_stats(self) -> Dict[str, Any]:
        """Get citation validation statistics."""
        total = self._validation_stats['total_extractions']
        if total == 0:
            return self._validation_stats

        return {
            **self._validation_stats,
            'pass_rate': self._validation_stats['validations_passed'] / total,
            'fail_rate': self._validation_stats['validations_failed'] / total,
            'exact_match_rate': self._validation_stats['exact_matches'] / total,
            'fuzzy_match_rate': self._validation_stats['fuzzy_matches'] / total
        }

    def extract_citation_from_document(self, user_question: str, document: Dict[str, Any],
                                     min_relevance: float = 0.7) -> Optional[Citation]:
        """
        Extract relevant citation from a single document with retry on validation failure.

        Args:
            user_question: The original user question
            document: Document with abstract/content and metadata
            min_relevance: Minimum relevance score to accept citation

        Returns:
            Citation object if relevant passage found, None otherwise
        """
        if not self.test_connection():
            logger.error("Cannot connect to Ollama - citation extraction unavailable")
            return None

        # Get document metadata for logging
        doc_id = document.get('id', 'unknown')
        abstract = document.get('abstract', '')
        title = document.get('title', 'Untitled')

        if not abstract:
            logger.warning(f"No abstract found for document {doc_id}")
            return None

        # Retry loop: initial attempt + retries
        for attempt in range(self.max_retries + 1):
            try:
                # Log retry attempts (skip for first attempt)
                if attempt > 0:
                    logger.info(
                        f"🔄 RETRY {attempt}/{self.max_retries} for document {doc_id} "
                        f"(previous validation failed)"
                    )

                # Build prompt for citation extraction
                prompt = f"""You are a research assistant tasked with extracting relevant citations from scientific papers.

Given the user question and document abstract below, extract the most relevant passage that directly answers or significantly contributes to answering the question.

User Question: "{user_question}"

Document Title: {title}
Abstract: {abstract}

Your task:
1. Identify the most relevant passage from the abstract that answers the question
2. Create a brief 1-2 sentence summary of how this passage relates to the question
3. Rate the relevance on a scale of 0.0 to 1.0 (where 1.0 is perfectly relevant)
4. Only extract passages with relevance >= 0.7

⚠️ CRITICAL REQUIREMENTS:
- Extract ONLY exact text that appears VERBATIM in the abstract above
- Copy the text CHARACTER-FOR-CHARACTER, preserving punctuation and capitalization
- Do NOT paraphrase, summarize, rephrase, or modify the text in ANY way
- Do NOT combine fragments from different parts of the abstract
- Do NOT add interpretations or explanations to the extracted text
- If no single exact passage is sufficiently relevant, respond with has_relevant_content: false
- Extract complete sentences when possible (don't cut off mid-sentence)

Response format (JSON):
{{
    "relevant_passage": "EXACT verbatim text copied character-for-character from the abstract",
    "summary": "brief summary of how this passage answers the question",
    "relevance_score": 0.8,
    "has_relevant_content": true
}}

If no sufficiently relevant content is found, respond with:
{{
    "has_relevant_content": false,
    "relevance_score": 0.0
}}

Respond only with valid JSON."""

                # Make request to Ollama and parse JSON (with automatic retry on parse failures)
                try:
                    citation_data = self._generate_and_parse_json(
                        prompt,
                        max_retries=self.max_retries,
                        retry_context=f"citation extraction (doc {doc_id})"
                    )
                except json.JSONDecodeError as e:
                    logger.error(f"Could not parse JSON from LLM after {self.max_retries + 1} attempts for document {doc_id}: {e}")
                    return None
                except (ConnectionError, ValueError) as e:
                    logger.error(f"Ollama request failed for document {doc_id}: {e}")
                    return None

                # Check if relevant content was found
                if not citation_data.get('has_relevant_content', False):
                    return None

                relevance_score = float(citation_data.get('relevance_score', 0.0))
                if relevance_score < min_relevance:
                    logger.debug(f"Relevance score {relevance_score} below threshold {min_relevance}")
                    return None

                # VALIDATE citation text and extract exact match from abstract
                is_valid, similarity, exact_text = self._validate_and_extract_exact_match(
                    citation_data['relevant_passage'],
                    abstract
                )

                if not is_valid:
                    # Validation failed - check if we should retry
                    is_final_attempt = (attempt == self.max_retries)

                    if is_final_attempt:
                        # Final attempt failed - track statistics and reject
                        self._validation_stats['total_extractions'] += 1
                        self._validation_stats['validations_failed'] += 1
                        self._validation_stats['failed_citations'].append({
                            'document_id': doc_id,
                            'similarity': similarity,
                            'llm_passage': citation_data['relevant_passage'][:200],
                            'question': user_question,
                            'attempts': attempt + 1
                        })

                        logger.warning(
                            f"🚫 CITATION VALIDATION FAILED (document {doc_id}): "
                            f"similarity={similarity:.3f} < threshold=0.95. "
                            f"All {self.max_retries + 1} attempts exhausted. REJECTING. "
                            f"LLM output: {citation_data['relevant_passage'][:100]}..."
                        )
                        return None
                    else:
                        # Not final attempt - log and retry
                        logger.warning(
                            f"⚠️  CITATION VALIDATION FAILED (document {doc_id}, attempt {attempt + 1}): "
                            f"similarity={similarity:.3f} < threshold=0.95. "
                            f"Will retry ({self.max_retries - attempt} attempts remaining)..."
                        )
                        continue  # Retry

                # Validation succeeded! Track statistics and return citation
                self._validation_stats['total_extractions'] += 1
                self._validation_stats['validations_passed'] += 1

                if similarity == 1.0:
                    self._validation_stats['exact_matches'] += 1
                else:
                    self._validation_stats['fuzzy_matches'] += 1
                    logger.info(
                        f"✓ Citation fuzzy-matched (similarity={similarity:.3f}). "
                        f"Replaced LLM text with exact abstract text (doc {doc_id})"
                    )

                # Log successful retry if this wasn't the first attempt
                if attempt > 0:
                    logger.info(
                        f"✅ RETRY SUCCESS (document {doc_id}): "
                        f"Validation passed on attempt {attempt + 1}/{self.max_retries + 1}"
                    )

                # Create citation with EXACT text from abstract (not LLM-generated)
                citation = Citation(
                    passage=exact_text,  # ← Use extracted exact text, not LLM's version!
                    summary=citation_data['summary'],
                    relevance_score=relevance_score,
                    document_id=str(document['id']),  # Ensure string format
                    document_title=title,
                    authors=document.get('authors', []),
                    publication_date=document.get('publication_date', 'Unknown'),
                    pmid=document.get('pmid'),
                    doi=document.get('doi'),
                    publication=document.get('publication'),
                    abstract=abstract  # Include full abstract for citation review
                )

                return citation

            except Exception as e:
                logger.error(f"Error extracting citation from document {doc_id} (attempt {attempt + 1}): {e}")
                # Don't retry on unexpected exceptions
                return None

        # Should never reach here, but just in case
        return None
    
    def process_scored_documents_for_citations(self, user_question: str,
                                             scored_documents: List[Tuple[Dict, Dict]],
                                             score_threshold: float = 2.0,
                                             min_relevance: float = 0.7,
                                             progress_callback: Optional[Callable] = None) -> List[Citation]:
        """
        Process scored documents to extract citations above threshold.

        NOTE: A document can yield multiple citations (different passages),
        but duplicate documents in scored_documents should be handled upstream.

        Args:
            user_question: Original user question
            scored_documents: List of (document, scoring_result) tuples
            score_threshold: Minimum score to process document
            min_relevance: Minimum relevance score for citations
            progress_callback: Optional progress callback

        Returns:
            List of extracted citations
        """
        citations = []
        qualifying_docs = [
            (doc, score) for doc, score in scored_documents
            if score.get('score', 0) >= score_threshold
        ]

        if not qualifying_docs:
            logger.info(f"No documents meeting score threshold {score_threshold}")
            return citations

        logger.info(f"Processing {len(qualifying_docs)} documents at or above threshold {score_threshold}")

        for i, (document, score_result) in enumerate(qualifying_docs):
            # Call progress callback with document title
            if progress_callback:
                doc_title = document.get('title', 'Unknown Document')
                progress_callback(i + 1, len(qualifying_docs), doc_title)

            citation = self.extract_citation_from_document(
                user_question=user_question,
                document=document,
                min_relevance=min_relevance
            )

            if citation:
                citations.append(citation)
                logger.debug(f"Extracted citation from document {document['id']}: {citation.summary}")

        logger.info(f"Extracted {len(citations)} citations from {len(qualifying_docs)} documents")
        return citations
    
    def submit_citation_extraction_tasks(self, user_question: str,
                                       scored_documents: List[Tuple[Dict, Dict]],
                                       score_threshold: float = 2.0,
                                       priority: TaskPriority = TaskPriority.NORMAL) -> Optional[List[str]]:
        """
        Submit citation extraction tasks to the queue.
        
        Args:
            user_question: Original user question
            scored_documents: List of (document, scoring_result) tuples
            score_threshold: Minimum score to process
            priority: Task priority
            
        Returns:
            List of task IDs or None if submission failed
        """
        if not self.orchestrator:
            logger.error("No orchestrator available for task submission")
            return None

        # Filter documents at or above threshold
        qualifying_docs = [
            (doc, score) for doc, score in scored_documents
            if score.get('score', 0) >= score_threshold
        ]

        if not qualifying_docs:
            logger.info(f"No documents meeting score threshold {score_threshold}")
            return []
        
        # Prepare task data for each document
        task_data_list = []
        for doc, score_result in qualifying_docs:
            task_data = {
                'user_question': user_question,
                'document': doc,
                'score_result': score_result,
                'score_threshold': score_threshold,
                'min_relevance': 0.7  # Default minimum relevance
            }
            task_data_list.append(task_data)
        
        # Submit batch of tasks
        task_ids = self.submit_batch_tasks(
            method_name='extract_citation_from_queue',
            data_list=task_data_list,
            priority=priority
        )
        
        if task_ids:
            logger.info(f"Submitted {len(task_ids)} citation extraction tasks to queue")
        
        return task_ids
    
    def extract_citation_from_queue(self, user_question: str, document: Dict[str, Any], 
                                    score_result: Dict[str, Any], score_threshold: float,
                                    min_relevance: float = 0.7) -> Dict[str, Any]:
        """
        Queue-compatible method for extracting citations.
        
        Args:
            user_question: The original user question
            document: Document to extract citation from
            score_result: Scoring results (not used but passed by queue)
            score_threshold: Score threshold (not used but passed by queue)
            min_relevance: Minimum relevance threshold
            
        Returns:
            Citation data or empty dict if no citation found
        """
        
        citation = self.extract_citation_from_document(
            user_question=user_question,
            document=document,
            min_relevance=min_relevance
        )
        
        if citation:
            # Convert to dict for JSON serialization
            return {
                'passage': citation.passage,
                'summary': citation.summary,
                'relevance_score': citation.relevance_score,
                'document_id': citation.document_id,
                'document_title': citation.document_title,
                'authors': citation.authors,
                'publication_date': citation.publication_date,
                'pmid': citation.pmid,
                'doi': citation.doi,
                'publication': citation.publication,
                'abstract': citation.abstract,  # Include abstract for highlighting in GUI
                'created_at': citation.created_at.isoformat(),
                'has_citation': True
            }
        else:
            return {'has_citation': False}
    
    def process_citation_queue(self, user_question: str,
                             scored_documents: List[Tuple[Dict, Dict]],
                             score_threshold: float = 2.0,
                             progress_callback: Optional[Callable] = None,
                             batch_size: int = 25) -> Iterator[Tuple[Dict, Optional[Citation]]]:
        """
        Memory-efficient citation processing using queue system.
        
        Args:
            user_question: Original user question
            scored_documents: Documents with scores
            score_threshold: Minimum score threshold
            progress_callback: Optional progress tracking
            batch_size: Processing batch size
            
        Yields:
            Tuples of (document, citation) where citation may be None
        """
        if not self.orchestrator:
            logger.error("Orchestrator required for queue processing")
            return

        # Filter qualifying documents
        qualifying_docs = [
            (doc, score) for doc, score in scored_documents
            if score.get('score', 0) >= score_threshold
        ]

        if not qualifying_docs:
            logger.info(f"No documents meeting threshold {score_threshold}")
            return
        
        # Submit tasks in batches
        total_docs = len(qualifying_docs)
        processed = 0
        
        for i in range(0, total_docs, batch_size):
            batch_docs = qualifying_docs[i:i + batch_size]
            
            # Submit batch tasks
            task_ids = self.submit_citation_extraction_tasks(
                user_question=user_question,
                scored_documents=batch_docs,
                score_threshold=score_threshold,
                priority=TaskPriority.HIGH
            )
            
            if not task_ids:
                continue
            
            # Wait for batch completion
            results = self.orchestrator.wait_for_completion(task_ids, timeout=60.0)
            
            # Process results
            for j, task_id in enumerate(task_ids):
                doc, score_result = batch_docs[j]
                task = results.get(task_id)
                
                citation = None
                if task and task.status == TaskStatus.COMPLETED and task.result:
                    result_data = task.result
                    if result_data.get('has_citation'):
                        # Reconstruct Citation object
                        citation = Citation(
                            passage=result_data['passage'],
                            summary=result_data['summary'],
                            relevance_score=result_data['relevance_score'],
                            document_id=result_data['document_id'],
                            document_title=result_data['document_title'],
                            authors=result_data['authors'],
                            publication_date=result_data['publication_date'],
                            pmid=result_data.get('pmid'),
                            doi=result_data.get('doi'),
                            publication=result_data.get('publication'),
                            abstract=result_data.get('abstract'),  # Include abstract for highlighting
                            created_at=datetime.fromisoformat(result_data['created_at'])
                        )
                
                processed += 1
                if progress_callback:
                    progress_callback(processed, total_docs)
                
                yield doc, citation
    
    def verify_document_exists(
        self,
        document_id: str,
        expected_title: Optional[str] = None
    ) -> tuple[bool, Optional[str]]:
        """
        Verify that a document ID exists in the database and optionally check title match.

        Args:
            document_id: Document ID to verify
            expected_title: Optional FULL title to verify (not truncated)

        Returns:
            (exists, actual_title): Tuple of existence status and actual title from DB
            - exists: True if document exists and title matches (if provided)
            - actual_title: The full title from database (None if not found)
        """
        from bmlibrarian.database import get_db_manager

        try:
            db_manager = get_db_manager()
            with db_manager.get_connection() as conn:
                with conn.cursor() as cur:
                    # Get FULL title (not truncated) from database
                    cur.execute(
                        "SELECT id, title FROM document WHERE id = %s LIMIT 1",
                        (document_id,)
                    )
                    result = cur.fetchone()

                    if not result:
                        logger.warning(f"Document ID {document_id} not found in database")
                        return False, None

                    db_id, db_title = result

                    # If title verification requested, check it matches
                    if expected_title:
                        # Normalize titles for comparison (case-insensitive, whitespace-normalized)
                        expected_norm = ' '.join(expected_title.lower().split())
                        actual_norm = ' '.join(db_title.lower().split())

                        if expected_norm != actual_norm:
                            logger.warning(
                                f"Document ID {document_id} exists but title mismatch:\n"
                                f"  Expected: {expected_title}\n"
                                f"  Actual:   {db_title}"
                            )
                            return False, db_title

                    return True, db_title

        except Exception as e:
            logger.error(f"Error verifying document {document_id}: {e}")
            return False, None
    
    def get_citation_stats(self, citations: List[Citation]) -> Dict[str, Any]:
        """
        Generate statistics about extracted citations.

        Args:
            citations: List of citations

        Returns:
            Statistics dictionary
        """
        if not citations:
            return {
                'total_citations': 0,
                'average_relevance': 0.0,
                'unique_documents': 0,
                'date_range': None
            }

        relevance_scores = [c.relevance_score for c in citations]
        unique_docs = set(c.document_id for c in citations)
        pub_dates = [c.publication_date for c in citations if c.publication_date != 'Unknown']

        stats = {
            'total_citations': len(citations),
            'average_relevance': sum(relevance_scores) / len(relevance_scores),
            'min_relevance': min(relevance_scores),
            'max_relevance': max(relevance_scores),
            'unique_documents': len(unique_docs),
            'citations_per_document': len(citations) / len(unique_docs) if unique_docs else 0
        }

        if pub_dates:
            stats['date_range'] = {
                'earliest': min(pub_dates),
                'latest': max(pub_dates)
            }

        return stats

    def extract_citations_with_audit(
        self,
        research_question_id: int,
        session_id: int,
        user_question: str,
        scored_documents_with_ids: List[Tuple[Dict, Dict, int]],
        score_threshold: float = 2.0,
        min_relevance: float = 0.7,
        progress_callback: Optional[Callable[[int, int], None]] = None
    ) -> List[Tuple[Citation, int]]:
        """
        Extract citations WITH AUDIT TRACKING.

        CRITICAL: Records each extracted citation with evaluator tracking.

        Args:
            research_question_id: ID of the research question
            session_id: ID of the current session
            user_question: The user's question
            scored_documents_with_ids: List of (document, scoring_result, scoring_id) tuples
            score_threshold: Minimum score to process document
            min_relevance: Minimum relevance for citation extraction
            progress_callback: Optional callback function(current, total) for progress updates

        Returns:
            List of tuples: (citation, citation_id)
            - citation_id is the database ID for the citation record

        Raises:
            RuntimeError: If audit tracking not enabled

        Example:
            >>> import psycopg
            >>> conn = psycopg.connect(dbname="knowledgebase", user="hherb")
            >>> agent = CitationFinderAgent(audit_conn=conn)
            >>> results = agent.extract_citations_with_audit(
            ...     research_question_id=1,
            ...     session_id=1,
            ...     user_question="What are the benefits of exercise?",
            ...     scored_documents_with_ids=scored_docs_with_ids,
            ...     score_threshold=2.0
            ... )
            >>> for citation, citation_id in results:
            ...     print(f"Citation {citation_id}: {citation.summary}")
        """
        if not self._citation_tracker or not self._evaluator_id:
            raise RuntimeError("Audit tracking not enabled. Pass audit_conn to __init__()")

        if not user_question or not user_question.strip():
            raise ValueError("User question cannot be empty")

        if not scored_documents_with_ids or not isinstance(scored_documents_with_ids, list):
            raise ValueError("scored_documents_with_ids must be a non-empty list")

        # Filter to qualifying documents
        qualifying_docs = [
            (doc, score_result, scoring_id)
            for doc, score_result, scoring_id in scored_documents_with_ids
            if score_result.get('score', 0) >= score_threshold
        ]

        if not qualifying_docs:
            logger.info(f"No documents meeting score threshold {score_threshold}")
            return []

        results = []
        self._call_callback("citation_extraction_started", f"Extracting citations from {len(qualifying_docs)} documents")

        for i, (doc, score_result, scoring_id) in enumerate(qualifying_docs):
            try:
                doc_id = doc.get('id')
                if not doc_id:
                    logger.error(f"Document {i+1} missing 'id' field - cannot track in audit")
                    continue

                self._call_callback("citation_extraction_progress", f"Document {i+1}/{len(qualifying_docs)}")

                # Extract citation
                citation = self.extract_citation_from_document(
                    user_question=user_question,
                    document=doc,
                    min_relevance=min_relevance
                )

                if not citation:
                    logger.debug(f"No citation extracted from document {doc_id}")
                    continue

                # Record citation in audit database
                citation_id = self._citation_tracker.record_citation(
                    research_question_id=research_question_id,
                    document_id=doc_id,
                    session_id=session_id,
                    scoring_id=scoring_id,
                    evaluator_id=self._evaluator_id,
                    passage=citation.passage,
                    summary=citation.summary,
                    relevance_confidence=citation.relevance_score
                )

                results.append((citation, citation_id))

                # Report progress for GUI updates
                if progress_callback:
                    progress_callback(i + 1, len(qualifying_docs))

            except Exception as e:
                logger.error(f"Failed to extract citation from document {i+1}: {e}")
                # Continue with other documents
                continue

        total_extracted = len(results)
        self._call_callback(
            "citation_extraction_completed",
            f"Extracted {total_extracted} citations from {len(qualifying_docs)} documents"
        )

        logger.info(f"Extracted {total_extracted} citations with audit tracking")

        return results

    def get_existing_citations(
        self,
        research_question_id: int,
        session_id: Optional[int] = None,
        accepted_only: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Get existing citations from audit database.

        CRITICAL FOR RESUMPTION: Returns citations already extracted for this question.

        Args:
            research_question_id: ID of the research question
            session_id: Optional filter by session
            accepted_only: If True, only return human-accepted citations

        Returns:
            List of dictionaries with citation data

        Raises:
            RuntimeError: If audit tracking not enabled

        Example:
            >>> existing = agent.get_existing_citations(question_id, accepted_only=True)
            >>> print(f"Found {len(existing)} accepted citations")
        """
        if not self._citation_tracker:
            raise RuntimeError("Audit tracking not enabled. Pass audit_conn to __init__()")

        if accepted_only:
            return self._citation_tracker.get_accepted_citations(research_question_id)
        else:
            return self._citation_tracker.get_all_citations(research_question_id, session_id)

    def update_citation_review_status(
        self,
        citation_id: int,
        status: str
    ) -> None:
        """
        Update human review status for a citation.

        Args:
            citation_id: ID of the citation
            status: Review status ('accepted', 'rejected', 'modified')

        Raises:
            RuntimeError: If audit tracking not enabled

        Example:
            >>> agent.update_citation_review_status(citation_id=42, status='accepted')
        """
        if not self._citation_tracker:
            raise RuntimeError("Audit tracking not enabled. Pass audit_conn to __init__()")

        valid_statuses = ['accepted', 'rejected', 'modified']
        if status not in valid_statuses:
            raise ValueError(f"Invalid status '{status}'. Must be one of: {valid_statuses}")

        self._citation_tracker.update_human_review_status(citation_id, status)
        logger.info(f"Updated citation {citation_id} review status: {status}")

    def get_evaluator_id(self) -> Optional[int]:
        """
        Get the evaluator ID for this agent instance.

        Returns:
            Evaluator ID if audit tracking enabled, None otherwise
        """
        return self._evaluator_id