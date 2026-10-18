"""
Citation Finder Agent for extracting relevant passages from scored documents.

Processes documents above a threshold score to extract specific passages
that answer user questions, building a queue of verifiable citations.
"""

import json
import logging
import math
from typing import Dict, List, Optional, Any, Iterator, Tuple, Callable
from dataclasses import dataclass
from datetime import datetime, timezone
import psycopg

from .base import BaseAgent
from .queue_manager import TaskPriority, TaskStatus
from ..utils.passage_match import PassageMatch, find_passage
from ..utils.sentence_bounds import complete_sentence_span
from ..utils.transient_retry import (
    DEFAULT_TRANSIENT_ATTEMPTS,
    DEFAULT_TRANSIENT_BASE_SECONDS,
    call_with_backoff,
)

logger = logging.getLogger(__name__)

# Minimum similarity between the LLM's "verbatim" passage and the abstract
# span it is matched to; below this the passage is treated as a paraphrase.
CITATION_MIN_SIMILARITY = 0.95

# Why an LLM citation response was rejected (logged, and recorded in
# ``failed_citations`` when the final attempt fails). All are retried.
REJECT_NOT_JSON_OBJECT = "response is not a JSON object"
REJECT_BAD_RELEVANCE = "relevance_score is not a number"
REJECT_PASSAGE_NOT_TEXT = "passage is missing or not text"
REJECT_PASSAGE_EMPTY = "passage is empty"
REJECT_PASSAGE_NOT_FOUND = "passage not found in abstract"
REJECT_BELOW_THRESHOLD = "passage similarity below threshold"
REJECT_MISSING_SUMMARY = "summary is missing or not text"
# The matched span is a fragment (a term, a clause, or it starts/ends
# mid-sentence); citations must be one or more complete sentences (#289).
REJECT_INCOMPLETE_SENTENCE = "passage is not one or more complete sentences"

# Rejections whose log line includes the passage similarity (for the other
# reasons the similarity says nothing, or reads like a pass).
SIMILARITY_REJECTIONS = frozenset({REJECT_BELOW_THRESHOLD})

# Rejections whose llm_passage is a repr of a non-text value, not a passage.
NON_TEXT_REJECTIONS = frozenset({REJECT_NOT_JSON_OBJECT, REJECT_PASSAGE_NOT_TEXT})

# Characters of a rejected LLM passage kept in failed_citations / in logs.
FAILED_PASSAGE_STORED_CHARS = 200
FAILED_PASSAGE_LOGGED_CHARS = 100
# Characters of an error message kept in errored_documents.
ERROR_MESSAGE_STORED_CHARS = 300


def _as_relevance(value: Any) -> Optional[float]:
    """Parse an LLM relevance score.

    Args:
        value: Raw ``relevance_score`` from the LLM response.

    Returns:
        The score as a finite float, or None if it is not a number.
    """
    if isinstance(value, bool):
        return None
    try:
        score = float(value)
    except (TypeError, ValueError):
        return None
    return score if math.isfinite(score) else None


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


@dataclass(frozen=True)
class _ResponseCheck:
    """Outcome of checking one LLM citation response against the abstract.

    Exactly one of three cases: ``irrelevant`` (the LLM found nothing relevant
    enough; stop without retrying), ``failure`` set (reject and retry), or
    accepted: ``passage`` holds the abstract's own text for the complete
    sentences around the matched span, with the response's ``summary`` and
    ``relevance_score``. ``match`` keeps the raw match, whose offsets do not
    include closing punctuation the sentence check took from the abstract.
    """

    irrelevant: bool = False
    failure: Optional[str] = None
    match: PassageMatch = PassageMatch(similarity=0.0)
    llm_passage: str = ""
    passage: str = ""
    relevance_score: float = 0.0
    summary: str = ""


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
                 max_retries: int = 3,
                 transient_retry_attempts: int = DEFAULT_TRANSIENT_ATTEMPTS,
                 transient_retry_base_delay: float = DEFAULT_TRANSIENT_BASE_SECONDS):
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
            transient_retry_attempts: Attempts in total when the LLM server
                is unreachable or times out (exponential backoff between them).
            transient_retry_base_delay: Seconds before the first such retry.
        """
        super().__init__(model=model, host=host, temperature=temperature, top_p=top_p,
                        callback=callback, orchestrator=orchestrator, show_model_info=show_model_info)
        self.agent_type = "citation_finder_agent"
        self.max_retries = max_retries
        self.transient_retry_attempts = transient_retry_attempts
        self.transient_retry_base_delay = transient_retry_base_delay

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
        self._validation_stats: Dict[str, Any] = {
            'total_extractions': 0,
            'validations_passed': 0,
            'validations_failed': 0,
            'exact_matches': 0,
            'fuzzy_matches': 0,
            'errors': 0,
            'failed_citations': [],
            # One entry per document counted in 'errors':
            # {'document_id': ..., 'error': message}.
            'errored_documents': []
        }

    def get_agent_type(self) -> str:
        """Get the agent type identifier."""
        return "citation_finder_agent"

    def _validate_and_extract_exact_match(
        self,
        llm_passage: str,
        abstract: str,
        min_similarity: float = CITATION_MIN_SIMILARITY
    ) -> PassageMatch:
        """
        Verify citation passage exists in abstract and extract exact matching text.

        If the LLM changed whitespace, case or a few characters, this locates
        the matching span of the original abstract and returns that text, so
        citations always carry EXACT source text, never LLM-generated copies.
        See ``bmlibrarian.utils.passage_match.find_passage``.

        Args:
            llm_passage: Text extracted by LLM (may be modified/paraphrased)
            abstract: Source abstract to search
            min_similarity: Acceptance threshold in (0, 1]; default
                ``CITATION_MIN_SIMILARITY``.

        Returns:
            The :class:`PassageMatch`. ``matched`` tells whether the passage was
            accepted, ``text`` holds the abstract's own wording of the matched
            span, and ``exact`` is True when only case, whitespace, accents,
            typography or compatibility forms differed (see ``fold_char``).
        """
        match = find_passage(llm_passage, abstract, min_similarity)
        if match.text is not None:
            logger.debug(
                f"Found {'exact' if match.exact else 'fuzzy'} match in abstract "
                f"(similarity={match.similarity:.3f}, {len(match.text)} chars)"
            )
        else:
            logger.debug(f"No valid match found (best similarity={match.similarity:.3f})")
        return match

    def _check_response(
        self,
        citation_data: Any,
        abstract: str,
        min_relevance: float,
        min_similarity: float,
    ) -> _ResponseCheck:
        """
        Check an LLM citation response and verify its passage against the abstract.

        Args:
            citation_data: Parsed JSON response from the LLM.
            abstract: Source abstract the passage must come from.
            min_relevance: Minimum relevance score to accept a citation.
            min_similarity: Passage acceptance threshold in (0, 1].

        Returns:
            A :class:`_ResponseCheck`: irrelevant, rejected with a reason
            (``REJECT_*``), or accepted with the matched abstract span.
        """
        if not isinstance(citation_data, dict):
            return _ResponseCheck(
                failure=REJECT_NOT_JSON_OBJECT, llm_passage=repr(citation_data)
            )
        if not citation_data.get('has_relevant_content', False):
            return _ResponseCheck(irrelevant=True)

        raw_passage = citation_data.get('relevant_passage')
        llm_passage = raw_passage if isinstance(raw_passage, str) else repr(raw_passage)
        relevance_score = _as_relevance(citation_data.get('relevance_score', 0.0))
        if relevance_score is None:
            return _ResponseCheck(failure=REJECT_BAD_RELEVANCE, llm_passage=llm_passage)
        if relevance_score < min_relevance:
            logger.debug(f"Relevance score {relevance_score} below threshold {min_relevance}")
            return _ResponseCheck(irrelevant=True)

        if not isinstance(raw_passage, str):
            return _ResponseCheck(failure=REJECT_PASSAGE_NOT_TEXT, llm_passage=llm_passage)
        if not raw_passage.strip():
            return _ResponseCheck(failure=REJECT_PASSAGE_EMPTY, llm_passage=llm_passage)

        match = self._validate_and_extract_exact_match(raw_passage, abstract, min_similarity)
        # PassageMatch sets text, start and end together; checking all three
        # also narrows the offsets for the sentence check below.
        if match.text is None or match.start is None or match.end is None:
            # 0.0 means no candidate span at all, not a near miss.
            reason = REJECT_PASSAGE_NOT_FOUND if match.similarity == 0.0 else REJECT_BELOW_THRESHOLD
            return _ResponseCheck(failure=reason, match=match, llm_passage=llm_passage)

        sentences = complete_sentence_span(abstract, match.start, match.end)
        if sentences is None:
            return _ResponseCheck(
                failure=REJECT_INCOMPLETE_SENTENCE, match=match, llm_passage=llm_passage
            )

        summary = citation_data.get('summary')
        if not isinstance(summary, str):
            return _ResponseCheck(
                failure=REJECT_MISSING_SUMMARY, match=match, llm_passage=llm_passage
            )
        return _ResponseCheck(
            match=match,
            llm_passage=llm_passage,
            passage=abstract[sentences[0]:sentences[1]],
            relevance_score=relevance_score,
            summary=summary,
        )

    def _extraction_summary(
        self, extracted: int, documents: int, rejections_before: int, errors_before: int
    ) -> str:
        """
        Describe a batch extraction, including rejected passages and errors.

        Args:
            extracted: Citations extracted in this batch.
            documents: Documents processed in this batch.
            rejections_before: Length of ``failed_citations`` before the batch.
            errors_before: ``errors`` before the batch started.

        Returns:
            A one-line summary for logs and progress callbacks, with the
            rejections broken down by reason (``REJECT_*``).
        """
        summary = f"Extracted {extracted} citations from {documents} documents"
        rejections = self._validation_stats['failed_citations'][rejections_before:]
        errors = self._validation_stats['errors'] - errors_before
        notes = []
        if rejections:
            counts: Dict[str, int] = {}
            for entry in rejections:
                counts[entry['reason']] = counts.get(entry['reason'], 0) + 1
            breakdown = ", ".join(f"{reason} ×{count}" for reason, count in counts.items())
            notes.append(f"{len(rejections)} rejected: {breakdown}")
        if errors:
            notes.append(f"{errors} failed with an error, see log")
        return f"{summary} ({'; '.join(notes)})" if notes else summary

    def _record_error(self, document_id: Any, error: str) -> None:
        """
        Count a document whose extraction failed (not a judgement about it).

        Args:
            document_id: The document's ID.
            error: What went wrong.
        """
        self._validation_stats['errors'] += 1
        self._validation_stats['errored_documents'].append({
            'document_id': document_id,
            'error': error[:ERROR_MESSAGE_STORED_CHARS],
        })

    def _ensure_connection(self, document_id: Any) -> None:
        """
        Check the LLM server is reachable, retrying with backoff.

        Args:
            document_id: The document about to be processed, for log messages.

        Raises:
            ConnectionError: If the server stayed unreachable.
        """
        def check() -> None:
            """Raise ConnectionError if the server does not answer."""
            if not self.test_connection():
                raise ConnectionError("cannot connect to the LLM server")

        call_with_backoff(
            check,
            description=f"LLM connection check (citation extraction, doc {document_id})",
            max_attempts=self.transient_retry_attempts,
            base_delay=self.transient_retry_base_delay,
        )

    @staticmethod
    def _retry_note(previous_failure: Optional[str], previous_passage: str = "") -> str:
        """
        Tell the model why its previous answer was rejected (#290).

        Args:
            previous_failure: The ``REJECT_*`` reason of the previous attempt
                (with its similarity, for a similarity rejection), or None on
                the first attempt.
            previous_passage: The passage the previous attempt returned,
                quoted (shortened, marked with "…") so the model can see what
                to correct; "" when it returned no text passage.

        Returns:
            A prompt line naming the rejection, or "" on the first attempt.
        """
        if previous_failure is None:
            return ""
        quoted = previous_passage.strip()
        if len(quoted) > FAILED_PASSAGE_STORED_CHARS:
            quoted = quoted[:FAILED_PASSAGE_STORED_CHARS] + "…"
        rejected = f' Your previous passage was: "{quoted}".' if quoted else ""
        return (
            f"- Your previous answer was REJECTED because: {previous_failure}.{rejected} "
            f"Correct this and follow every requirement above exactly"
        )

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
            Citation object if relevant passage found, None otherwise. When
            ``None`` is due to a failure (no LLM connection, unusable LLM
            output, an unexpected exception) rather than a judgement about the
            document, the ``errors`` validation statistic is incremented and
            the document is listed in ``errored_documents``. An unreachable or
            timed-out LLM server is retried with exponential backoff first.
        """
        # Get document metadata for logging
        doc_id = document.get('id', 'unknown')
        abstract = document.get('abstract', '')
        title = document.get('title', 'Untitled')

        if not isinstance(abstract, str) or not abstract.strip():
            logger.warning(f"No abstract text found for document {doc_id}")
            return None

        try:
            self._ensure_connection(doc_id)
        except ConnectionError as e:
            self._record_error(doc_id, str(e))
            logger.error(f"Cannot connect to the LLM server - citation extraction "
                         f"unavailable for document {doc_id}: {e}")
            return None

        min_similarity = CITATION_MIN_SIMILARITY
        # Reason the previous attempt's passage was rejected, told to the
        # model on the retry so it is not sent the identical prompt.
        previous_failure: Optional[str] = None
        previous_passage = ""

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
1. Identify the most relevant passage (one or more complete sentences) from the abstract that answers the question
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
- The passage MUST be one or more COMPLETE sentences: start at the first word of a sentence and end at its closing punctuation. Never extract a single word, a phrase or part of a sentence; such passages are rejected
{self._retry_note(previous_failure, previous_passage)}

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

                # Request and parse JSON (retrying parse failures with a new
                # generation, and an unreachable server with backoff)
                try:
                    citation_data = call_with_backoff(
                        lambda: self._generate_and_parse_json(
                            prompt,
                            max_retries=self.max_retries,
                            retry_context=f"citation extraction (doc {doc_id})"
                        ),
                        description=f"citation extraction LLM request (doc {doc_id})",
                        max_attempts=self.transient_retry_attempts,
                        base_delay=self.transient_retry_base_delay,
                    )
                except json.JSONDecodeError as e:
                    self._record_error(doc_id, f"unparseable LLM output: {e}")
                    logger.error(f"Could not parse JSON from LLM after {self.max_retries + 1} attempts for document {doc_id}: {e}")
                    return None
                except (ConnectionError, ValueError) as e:
                    self._record_error(doc_id, str(e))
                    logger.error(f"Ollama request failed for document {doc_id}: {e}")
                    return None

                check = self._check_response(
                    citation_data, abstract, min_relevance, min_similarity
                )
                if check.irrelevant:
                    return None

                if check.failure is not None:
                    # Validation failed - check if we should retry
                    is_final_attempt = (attempt == self.max_retries)
                    detail = check.failure
                    if check.failure in SIMILARITY_REJECTIONS:
                        detail += (
                            f" (similarity={check.match.similarity:.3f}, "
                            f"threshold={min_similarity})"
                        )
                    previous_failure = detail
                    # Not-text rejections carry a repr; don't quote it as a passage.
                    previous_passage = (
                        "" if check.failure in NON_TEXT_REJECTIONS else check.llm_passage
                    )

                    if is_final_attempt:
                        # Final attempt failed - track statistics and reject
                        self._validation_stats['total_extractions'] += 1
                        self._validation_stats['validations_failed'] += 1
                        self._validation_stats['failed_citations'].append({
                            'document_id': doc_id,
                            'reason': check.failure,
                            'similarity': check.match.similarity,
                            'llm_passage': check.llm_passage[:FAILED_PASSAGE_STORED_CHARS],
                            'question': user_question,
                            'attempts': attempt + 1
                        })

                        logger.warning(
                            f"🚫 CITATION VALIDATION FAILED (document {doc_id}): {detail}. "
                            f"All {self.max_retries + 1} attempts exhausted. REJECTING. "
                            f"LLM output: {check.llm_passage[:FAILED_PASSAGE_LOGGED_CHARS]}..."
                        )
                        return None
                    else:
                        # Not final attempt - log and retry
                        logger.warning(
                            f"⚠️  CITATION VALIDATION FAILED (document {doc_id}, attempt {attempt + 1}): "
                            f"{detail}. Will retry ({self.max_retries - attempt} attempts remaining)..."
                        )
                        continue  # Retry

                # Validation succeeded! Track statistics and return citation
                match = check.match
                self._validation_stats['total_extractions'] += 1
                self._validation_stats['validations_passed'] += 1

                if match.exact:
                    self._validation_stats['exact_matches'] += 1
                else:
                    self._validation_stats['fuzzy_matches'] += 1
                if check.passage != check.llm_passage:
                    logger.info(
                        f"✓ Citation {'exact' if match.exact else 'fuzzy'}-matched "
                        f"(similarity={match.similarity:.3f}). "
                        f"Stored the abstract's own text for the complete "
                        f"sentence(s) instead of the LLM text (doc {doc_id})"
                    )

                # Log successful retry if this wasn't the first attempt
                if attempt > 0:
                    logger.info(
                        f"✅ RETRY SUCCESS (document {doc_id}): "
                        f"Validation passed on attempt {attempt + 1}/{self.max_retries + 1}"
                    )

                # Create citation with EXACT text from abstract (not LLM-generated)
                citation = Citation(
                    passage=check.passage,  # ← Use extracted exact text, not LLM's version!
                    summary=check.summary,
                    relevance_score=check.relevance_score,
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
                self._record_error(doc_id, f"unexpected error: {e}")
                logger.exception(
                    f"Unexpected error extracting citation from document {doc_id} "
                    f"(attempt {attempt + 1})"
                )
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
        citations: List[Citation] = []
        qualifying_docs = [
            (doc, score) for doc, score in scored_documents
            if score.get('score', 0) >= score_threshold
        ]

        if not qualifying_docs:
            logger.info(f"No documents meeting score threshold {score_threshold}")
            return citations

        logger.info(f"Processing {len(qualifying_docs)} documents at or above threshold {score_threshold}")
        rejections_before = len(self._validation_stats['failed_citations'])
        errors_before = self._validation_stats['errors']

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

        summary = self._extraction_summary(
            len(citations), len(qualifying_docs), rejections_before, errors_before
        )
        logger.info(summary)
        self._call_callback("citation_extraction_completed", summary)
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
        failed_before = self._validation_stats['validations_failed']
        errors_before = self._validation_stats['errors']
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

            except Exception:
                self._validation_stats['errors'] += 1
                logger.exception(f"Failed to extract citation from document {i+1}")
                # Continue with other documents
                continue

        total_extracted = len(results)
        self._call_callback(
            "citation_extraction_completed",
            self._extraction_summary(
                total_extracted, len(qualifying_docs), failed_before, errors_before
            )
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