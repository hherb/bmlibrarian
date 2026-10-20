"""
Fact Checker Agent for auditing biomedical statements against literature evidence.

Takes biomedical statements and evaluates their veracity (yes/no/maybe) by:
- Searching for relevant literature using QueryAgent
- Scoring document relevance using DocumentScoringAgent
- Extracting supporting/contradicting evidence using CitationFinderAgent
- Synthesizing a fact-check evaluation with evidence references

A "maybe" verdict means the literature was examined and found insufficient.
A stage that fails for any other reason (database or LLM outage, a model that
keeps returning unusable output) raises ``FactCheckStageError`` instead;
``check_batch`` reports such a statement, or one whose check raised any other
exception (a bug), as failed without storing a verdict, so incremental mode
retries it on the next run.

Recoverable failures (an unreachable LLM or database, a timeout) are retried
with exponential backoff before they count as failures. A verdict reached
although part of the evidence could not be examined (a failed search
strategy, documents that could not be scored or quoted) is stored with
``degradation_notes`` describing what is missing.
"""

import json
import logging
import os
import tempfile
import uuid
from enum import StrEnum
from typing import Dict, List, Optional, Any, Callable, TypeVar, cast
from dataclasses import dataclass, field
from datetime import datetime, timezone

from bmlibrarian.agents.base import BaseAgent
from bmlibrarian.agents.query_agent import QueryAgent
from bmlibrarian.agents.scoring_agent import DocumentScoringAgent
from bmlibrarian.agents.citation_agent import CitationFinderAgent, Citation
from ...utils.transient_retry import (
    DEFAULT_TRANSIENT_ATTEMPTS,
    DEFAULT_TRANSIENT_BASE_SECONDS,
    call_with_backoff,
)
from ..db.database import (
    FactCheckerDB, Statement, AIEvaluation, Evidence
)

logger = logging.getLogger(__name__)

_SubAgent = TypeVar("_SubAgent", bound=BaseAgent)

# Verdicts the evaluation LLM may return; anything else is an invalid response.
VALID_VERDICTS = ("yes", "no", "maybe")
# Marks a statement whose fact-check failed. Never stored as a verdict.
EVALUATION_ERROR = "error"
# Confidence levels a verdict carries (a failed check has none).
CONFIDENCE_LEVELS = ("high", "medium", "low")
# Stances the evaluation LLM may give each citation.
VALID_STANCES = ("supports", "contradicts", "neutral")
# JSON-parse retries inside one evaluation request (BaseAgent._chat_and_parse_json).
EVALUATION_JSON_RETRIES = 3
# Evaluation requests made in total (the first plus retries) when the LLM
# returns valid JSON with an invalid verdict, stance or missing fields, before
# the statement is reported as failed.
EVALUATION_VALIDATION_ATTEMPTS = 2
# Document IDs listed in a failure message or degradation note.
MAX_LISTED_DOCUMENT_IDS = 10
# Generation tokens added to the evaluation's max_tokens per citation shown.
# A reasoning model (gpt-oss:20b) thinks about each citation and then writes
# its stance; on 49 citations a flat 2,000 tokens all went to reasoning and
# the answer came back empty (#296).
EVALUATION_TOKENS_PER_CITATION = 100


class FactCheckStage(StrEnum):
    """Pipeline stages, named in ``FactCheckStageError`` messages."""

    SEARCH = "literature search"
    SCORING = "relevance scoring"
    CITATIONS = "citation extraction"
    EVALUATION = "statement evaluation"


STAGE_SEARCH = FactCheckStage.SEARCH
STAGE_SCORING = FactCheckStage.SCORING
STAGE_CITATIONS = FactCheckStage.CITATIONS
STAGE_EVALUATION = FactCheckStage.EVALUATION


def evaluation_token_budget(base_tokens: int, citation_count: int) -> int:
    """
    Generation ceiling for an evaluation request over ``citation_count`` citations.

    Args:
        base_tokens: Budget for the verdict and reason (the agent's ``max_tokens``).
        citation_count: Citations in the prompt; each needs a stance.

    Returns:
        ``base_tokens`` plus ``EVALUATION_TOKENS_PER_CITATION`` per citation.
    """
    return base_tokens + EVALUATION_TOKENS_PER_CITATION * max(citation_count, 0)


def _list_ids(document_ids: List[Any]) -> str:
    """
    Format document IDs for a message, shortened past ``MAX_LISTED_DOCUMENT_IDS``.

    Args:
        document_ids: The IDs.

    Returns:
        e.g. ``"101, 102"`` or ``"101, 102, ... (+5 more)"``.
    """
    shown = ", ".join(str(doc_id) for doc_id in document_ids[:MAX_LISTED_DOCUMENT_IDS])
    hidden = len(document_ids) - MAX_LISTED_DOCUMENT_IDS
    return f"{shown}, ... (+{hidden} more)" if hidden > 0 else shown


def _count_reasons(rejections: List[Dict[str, Any]]) -> str:
    """
    Summarise citation rejections by reason.

    Args:
        rejections: ``failed_citations`` entries of the citation agent.

    Returns:
        e.g. ``"passage is not one or more complete sentences ×2"``.
    """
    counts: Dict[str, int] = {}
    for entry in rejections:
        reason = str(entry.get('reason', 'unknown reason'))
        counts[reason] = counts.get(reason, 0) + 1
    return ", ".join(f"{reason} ×{count}" for reason, count in counts.items())


def _require_sub_agent(agent: Optional[_SubAgent], name: str) -> _SubAgent:
    """
    Return a sub-agent, failing loudly if it was never initialised.

    Args:
        agent: The sub-agent attribute (``None`` until ``_initialize_agents``).
        name: Its class name, for the error message.

    Returns:
        The sub-agent.

    Raises:
        RuntimeError: If ``agent`` is ``None``.
    """
    if agent is None:
        raise RuntimeError(f"{name} is not initialised; call _initialize_agents() first")
    return agent


def failed_search_strategies(search_metadata: Any) -> List[str]:
    """
    List the search strategies that failed, from ``search_hybrid`` metadata.

    Args:
        search_metadata: ``QueryAgent.last_search_metadata`` (the strategy
            metadata returned by ``search_hybrid``), or ``None``.

    Returns:
        One ``"<strategy>: <error>"`` entry per failed strategy; empty if none
        failed or the metadata carries no failure information.
    """
    if not isinstance(search_metadata, dict):
        return []
    failures = search_metadata.get('strategies_failed')
    if not isinstance(failures, list):
        return []
    return [
        f"{failure.get('strategy', 'unknown')}: {failure.get('error', 'unknown error')}"
        if isinstance(failure, dict) else str(failure)
        for failure in failures
    ]


class FactCheckStageError(RuntimeError):
    """A fact-check stage failed for a reason other than missing evidence.

    Raised instead of returning a "maybe" verdict, so that an outage or a
    model failure is never recorded as "insufficient evidence".

    Attributes:
        stage: The pipeline stage that failed.
        detail: What went wrong.
    """

    def __init__(self, stage: FactCheckStage, detail: str) -> None:
        """
        Create the error.

        Args:
            stage: The pipeline stage that failed.
            detail: What went wrong.
        """
        self.stage = FactCheckStage(stage)
        self.detail = detail
        # Both arguments go to args so the error can be pickled and rebuilt.
        super().__init__(self.stage, detail)

    def __str__(self) -> str:
        """Describe the failure as "<stage> failed: <detail>"."""
        return f"{self.stage} failed: {self.detail}"


@dataclass
class EvidenceReference:
    """Represents a literature reference supporting the fact-check evaluation."""
    citation_text: str
    pmid: Optional[str] = None
    doi: Optional[str] = None
    document_id: Optional[str] = None
    relevance_score: Optional[float] = None
    supports_statement: Optional[bool] = None  # True=supports, False=contradicts, None=neutral

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result = {
            "citation": self.citation_text
        }
        if self.pmid:
            result["pmid"] = f"PMID:{self.pmid}"
        if self.doi:
            result["doi"] = f"DOI:{self.doi}"
        if self.document_id:
            result["document_id"] = self.document_id
        if self.relevance_score is not None:
            result["relevance_score"] = self.relevance_score
        if self.supports_statement is not None:
            result["stance"] = "supports" if self.supports_statement else "contradicts"
        return result


@dataclass
class FactCheckResult:
    """Result of a fact-check: a verdict, or a failed check (``is_error``).

    A verdict has ``evaluation`` in ``VALID_VERDICTS`` and a confidence in
    ``CONFIDENCE_LEVELS``; ``degradation_notes`` lists evidence that could not
    be examined (empty for a complete check). A failed check has
    ``evaluation == EVALUATION_ERROR``, no confidence, evidence, citation
    counts, expected-answer match or notes, and ``error_stage`` names the
    failing stage when known. Use ``FactCheckResult.failed`` to build one.
    """
    statement: str
    evaluation: str  # "yes", "no", "maybe", or EVALUATION_ERROR (check failed)
    reason: str
    evidence_list: List[EvidenceReference]
    confidence: Optional[str] = "medium"  # "high", "medium", "low"; None for a failed check
    documents_reviewed: int = 0
    supporting_citations: int = 0
    contradicting_citations: int = 0
    neutral_citations: int = 0
    expected_answer: Optional[str] = None
    matches_expected: Optional[bool] = None
    input_statement_id: Optional[str] = None  # Original ID from input file (e.g., PMID)
    timestamp: Optional[str] = None
    # Evidence that could not be examined although a verdict was reached.
    degradation_notes: List[str] = field(default_factory=list)
    # Stage that failed, for a failed check (None if unknown or a bug).
    error_stage: Optional[FactCheckStage] = None

    def __post_init__(self) -> None:
        """Validate the verdict/error invariants and set the timestamp.

        Raises:
            ValueError: If ``evaluation`` is not a verdict or the error
                marker, a verdict lacks a valid confidence or names an error
                stage, or a failed check carries a verdict's payload.
        """
        if self.evaluation == EVALUATION_ERROR:
            payload = {
                'confidence': self.confidence,
                'evidence_list': self.evidence_list,
                'matches_expected': self.matches_expected,
                'citation counts': (
                    self.supporting_citations or self.contradicting_citations
                    or self.neutral_citations or None
                ),
                'degradation_notes': self.degradation_notes,
            }
            present = [name for name, value in payload.items() if value not in (None, [])]
            if present:
                raise ValueError(f"A failed fact-check cannot carry {', '.join(present)}")
        elif self.evaluation in VALID_VERDICTS:
            if self.confidence not in CONFIDENCE_LEVELS:
                raise ValueError(
                    f"A verdict needs a confidence in {CONFIDENCE_LEVELS}, got {self.confidence!r}"
                )
            if self.error_stage is not None:
                raise ValueError("A verdict cannot name a failed stage")
        else:
            raise ValueError(
                f"Invalid evaluation {self.evaluation!r} "
                f"(expected one of {VALID_VERDICTS} or {EVALUATION_ERROR!r})"
            )
        if self.timestamp is None:
            self.timestamp = datetime.now(timezone.utc).isoformat()

    @classmethod
    def failed(
        cls,
        statement: str,
        error: BaseException,
        expected_answer: Optional[str] = None,
        input_statement_id: Optional[str] = None,
    ) -> "FactCheckResult":
        """
        Build the result of a fact-check that failed.

        Args:
            statement: The statement that could not be checked.
            error: Why (a ``FactCheckStageError`` names the stage).
            expected_answer: The expected answer from the input, if any.
            input_statement_id: The statement's ID in the input file, if any.

        Returns:
            A result with ``is_error`` True.
        """
        return cls(
            statement=statement,
            evaluation=EVALUATION_ERROR,
            reason=f"Error during fact-checking: {error}",
            evidence_list=[],
            confidence=None,
            expected_answer=expected_answer,
            input_statement_id=input_statement_id,
            error_stage=error.stage if isinstance(error, FactCheckStageError) else None,
        )

    @property
    def is_error(self) -> bool:
        """True if the fact-check failed and ``evaluation`` is not a verdict."""
        return self.evaluation == EVALUATION_ERROR

    @property
    def is_degraded(self) -> bool:
        """True for a verdict reached although some evidence was not examined."""
        return bool(self.degradation_notes)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result = {
            "statement": self.statement,
            "evaluation": self.evaluation,
            "reason": self.reason,
            "evidence_list": [ref.to_dict() for ref in self.evidence_list],
            "confidence": self.confidence,
            "metadata": {
                "documents_reviewed": self.documents_reviewed,
                "supporting_citations": self.supporting_citations,
                "contradicting_citations": self.contradicting_citations,
                "neutral_citations": self.neutral_citations,
                "timestamp": self.timestamp
            }
        }

        if self.input_statement_id is not None:
            result["input_statement_id"] = self.input_statement_id

        if self.degradation_notes:
            result["degradation_notes"] = list(self.degradation_notes)

        if self.error_stage is not None:
            result["error_stage"] = str(self.error_stage)

        if self.expected_answer is not None:
            result["expected_answer"] = self.expected_answer
            result["matches_expected"] = self.matches_expected

        return result


class FactCheckerAgent(BaseAgent):
    """
    Agent for fact-checking biomedical statements against literature evidence.

    Orchestrates multiple agents to:
    1. Search for relevant literature (QueryAgent)
    2. Score document relevance (DocumentScoringAgent)
    3. Extract supporting/contradicting evidence (CitationFinderAgent)
    4. Evaluate statement veracity and provide reasoning
    """

    def __init__(
        self,
        model: str,
        host: str = "http://localhost:11434",
        temperature: float = 0.1,
        top_p: float = 0.9,
        max_tokens: int = 2000,
        callback: Optional[Callable[[str, str], None]] = None,
        orchestrator: Optional[Any] = None,
        show_model_info: bool = True,
        score_threshold: float = 2.5,
        max_search_results: int = 50,
        max_citations: Optional[int] = None,
        incremental: bool = False,
        transient_retry_attempts: int = DEFAULT_TRANSIENT_ATTEMPTS,
        transient_retry_base_delay: float = DEFAULT_TRANSIENT_BASE_SECONDS
    ):
        """
        Initialize the FactCheckerAgent.

        Args:
            model: The name of the Ollama model to use for evaluation
            host: The Ollama server host URL
            temperature: Model temperature for response randomness
            top_p: Model top-p sampling parameter
            max_tokens: Generation budget for the verdict and reason; the
                evaluation request adds ``EVALUATION_TOKENS_PER_CITATION``
                per citation (see ``evaluation_token_budget``).
            callback: Optional callback function for progress updates
            orchestrator: Optional orchestrator for queue-based processing
            show_model_info: Whether to display model information
            score_threshold: Minimum relevance score for documents
            max_search_results: Maximum number of documents to retrieve
            max_citations: Maximum number of citations to extract (None = no limit, use all scored documents)
            incremental: If True, skip statements that already have AI evaluations
            transient_retry_attempts: Attempts in total for a call that fails
                with a recoverable error (LLM or database unreachable,
                timeout), with exponential backoff between them.
            transient_retry_base_delay: Seconds before the first such retry.

        Raises:
            TypeError: If ``max_citations`` is neither None nor an int.
            ValueError: If ``max_citations`` is less than 1.
        """
        if max_citations is not None:
            if not isinstance(max_citations, int) or isinstance(max_citations, bool):
                raise TypeError(
                    f"max_citations must be an int or None, got {type(max_citations).__name__}"
                )
            if max_citations < 1:
                raise ValueError(
                    f"max_citations must be >= 1 (None = no limit), got {max_citations}"
                )

        super().__init__(
            model=model,
            host=host,
            temperature=temperature,
            top_p=top_p,
            callback=callback,
            orchestrator=orchestrator,
            show_model_info=show_model_info
        )

        self.max_tokens = max_tokens
        self.score_threshold = score_threshold
        self.max_search_results = max_search_results
        self.max_citations = max_citations
        self.transient_retry_attempts = transient_retry_attempts
        self.transient_retry_base_delay = transient_retry_base_delay
        self.db: Optional[FactCheckerDB] = None
        self.current_session_id: Optional[str] = None
        self.incremental = incremental
        # Count of results that failed to persist to the database; reset per
        # batch in check_batch() and surfaced by the CLI so storage failures
        # are never reported as success.
        self.storage_failures: int = 0
        # Count of statements whose fact-check failed (FactCheckStageError or
        # any other exception); reset per batch. Their results carry
        # EVALUATION_ERROR and are never stored as verdicts.
        self.check_failures: int = 0
        # Verdicts of the current batch that carry degradation_notes.
        self.degraded_results: int = 0
        # Verdicts of the current batch stored in the database.
        self.stored_results: int = 0
        # Set when the batch's JSON export was requested but not written.
        self.export_failed: bool = False
        # Set when the processing-session row could not be written/updated.
        self.session_bookkeeping_failed: bool = False

        # Initialize sub-agents (will be set up during fact-checking)
        self.query_agent: Optional[QueryAgent] = None
        self.scoring_agent: Optional[DocumentScoringAgent] = None
        self.citation_agent: Optional[CitationFinderAgent] = None

    def get_agent_type(self) -> str:
        """Get the type identifier for this agent."""
        return "FactCheckerAgent"

    def _initialize_agents(self) -> None:
        """Initialize sub-agents for the fact-checking workflow."""
        if self.query_agent is None:
            self._call_callback("init", "Initializing sub-agents...")

            # Import configuration system
            from bmlibrarian.config import get_model, get_agent_config

            # Initialize QueryAgent
            query_model = get_model("query_agent")
            query_config = get_agent_config("query")
            self.query_agent = QueryAgent(
                model=query_model,
                host=self.host,
                show_model_info=False,
                **self._filter_agent_params(query_config)
            )

            # Initialize DocumentScoringAgent
            scoring_model = get_model("scoring_agent")
            scoring_config = get_agent_config("scoring")
            self.scoring_agent = DocumentScoringAgent(
                model=scoring_model,
                host=self.host,
                show_model_info=False,
                **self._filter_agent_params(scoring_config, extra={'max_tokens'})
            )

            # Initialize CitationFinderAgent
            citation_model = get_model("citation_agent")
            citation_config = get_agent_config("citation")
            self.citation_agent = CitationFinderAgent(
                model=citation_model,
                host=self.host,
                show_model_info=False,
                transient_retry_attempts=self.transient_retry_attempts,
                transient_retry_base_delay=self.transient_retry_base_delay,
                **self._filter_agent_params(citation_config)
            )

    def _filter_agent_params(
        self, config: Dict[str, Any], extra: frozenset[str] | set[str] = frozenset()
    ) -> Dict[str, Any]:
        """
        Filter agent configuration to only include supported parameters.

        Args:
            config: The sub-agent's config section.
            extra: Keys that sub-agent accepts beyond temperature and top_p
                (DocumentScoringAgent also takes max_tokens).
        """
        supported_params = {'temperature', 'top_p'} | set(extra)
        return {k: v for k, v in config.items() if k in supported_params}

    def _with_backoff(self, operation: Callable[[], Any], description: str) -> Any:
        """
        Run ``operation``, retrying recoverable failures with exponential backoff.

        Args:
            operation: The call to make; it must be safe to repeat.
            description: What it is, for log messages.

        Returns:
            What ``operation`` returned.
        """
        return call_with_backoff(
            operation,
            description=description,
            max_attempts=self.transient_retry_attempts,
            base_delay=self.transient_retry_base_delay,
        )

    def check_statement(
        self,
        statement: str,
        expected_answer: Optional[str] = None,
        max_documents: Optional[int] = None,
        score_threshold: Optional[float] = None
    ) -> FactCheckResult:
        """
        Check a biomedical statement against literature evidence.

        Args:
            statement: The biomedical statement to fact-check
            expected_answer: Optional expected answer (yes/no/maybe) for validation
            max_documents: Maximum number of documents to search. ``None`` uses
                the configured default; ``0`` means no limit (same convention
                as ``QueryAgent.find_abstracts``).
            score_threshold: Minimum relevance score for scoring and citation
                extraction. ``None`` uses the configured default; ``0.0``
                accepts every scored document.

        Returns:
            FactCheckResult with evaluation, reason, and evidence. A "maybe"
            with low confidence and an "Insufficient evidence" reason means no
            stage failed: the stages that ran found too little evidence. If a
            stage failed only in part (a search strategy, some documents),
            ``degradation_notes`` says what was not examined.

        Raises:
            ValueError: If ``max_documents`` is negative.
            FactCheckStageError: If a stage failed for a reason other than
                missing evidence (search error, documents that could not be
                scored or quoted while none succeeded, no usable LLM verdict).
        """
        if max_documents is not None and max_documents < 0:
            raise ValueError(f"max_documents must be >= 0 (0 = no limit), got {max_documents}")

        self._initialize_agents()

        # Use provided values or defaults (`is None`, so an explicit 0 / 0.0
        # is not swallowed by `or`)
        max_docs = self.max_search_results if max_documents is None else max_documents
        threshold = self.score_threshold if score_threshold is None else score_threshold

        self._call_callback("search", f"Searching literature for: {statement}")
        # Evidence that could not be examined, collected by every stage.
        notes: List[str] = []

        # Step 1: Search for relevant documents
        documents = self._search_documents(statement, max_docs, notes)

        if not documents:
            self._call_callback("warning", "No relevant documents found")
            return self._insufficient_evidence(
                statement,
                "No relevant documents found in the literature database.",
                0, expected_answer, notes,
            )

        self._call_callback("scoring", f"Scoring {len(documents)} documents...")

        # Step 2: Score documents for relevance
        scored_documents = self._score_documents(statement, documents, threshold, notes)

        if not scored_documents:
            self._call_callback("warning", f"No documents above threshold {threshold}")
            return self._insufficient_evidence(
                statement,
                f"No documents scored above relevance threshold ({threshold}/5.0).",
                len(documents), expected_answer, notes,
            )

        self._call_callback("extraction", f"Extracting evidence from {len(scored_documents)} documents...")

        # Step 3: Extract citations
        citations = self._extract_citations(statement, scored_documents, threshold, notes)

        if not citations:
            self._call_callback("warning", "No citations could be extracted")
            return self._insufficient_evidence(
                statement,
                "Documents found but no relevant citations could be extracted.",
                len(scored_documents), expected_answer, notes,
            )

        self._call_callback("evaluation", f"Evaluating statement based on {len(citations)} citations...")

        # Step 4: Evaluate the statement
        result = self._evaluate_statement(
            statement=statement,
            citations=citations,
            scored_documents=scored_documents,
            expected_answer=expected_answer
        )
        result.degradation_notes = notes

        if notes:
            self._call_callback(
                "warning", f"Verdict based on partial evidence: {'; '.join(notes)}"
            )
        self._call_callback("complete", f"Fact-check complete: {result.evaluation}")

        return result

    def _insufficient_evidence(
        self,
        statement: str,
        why: str,
        documents_reviewed: int,
        expected_answer: Optional[str],
        notes: List[str],
    ) -> FactCheckResult:
        """
        Build the low-confidence "maybe" for a statement with too little evidence.

        Args:
            statement: The statement checked.
            why: What was missing, appended to "Insufficient evidence: ".
            documents_reviewed: Documents examined.
            expected_answer: The expected answer, if any.
            notes: Evidence that could not be examined (degradation notes).

        Returns:
            The "maybe" result.
        """
        return FactCheckResult(
            statement=statement,
            evaluation="maybe",
            reason=f"Insufficient evidence: {why}",
            evidence_list=[],
            confidence="low",
            documents_reviewed=documents_reviewed,
            expected_answer=expected_answer,
            matches_expected=(expected_answer == "maybe") if expected_answer else None,
            degradation_notes=notes,
        )

    def _search_documents(
        self, statement: str, max_results: int, notes: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """
        Search for documents relevant to the statement.

        A recoverable failure (unreachable LLM or database, timeout) is
        retried with exponential backoff.

        Args:
            statement: The statement to fact-check.
            max_results: Maximum number of documents (0 = no limit).
            notes: Degradation notes; a failed search strategy whose results
                are missing is appended here.

        Returns:
            The documents found; empty only if every search strategy ran and
            matched nothing.

        Raises:
            FactCheckStageError: If query generation or the search raised, or
                nothing was found and at least one search strategy failed
                (``search_hybrid`` logs strategy errors and carries on, so a
                database outage otherwise looks like an empty result).
        """
        query_agent = _require_sub_agent(self.query_agent, "QueryAgent")
        # Convert statement to a question format for better query generation
        search_question = self._statement_to_question(statement)
        self._call_callback("query", f"Query: {search_question}")
        try:
            # find_abstracts returns a generator; list() runs the search.
            documents = self._with_backoff(
                lambda: list(query_agent.find_abstracts(
                    question=search_question,
                    max_rows=max_results
                )),
                "literature search",
            )
        except Exception as e:
            logger.error(f"Error searching documents: {e}", exc_info=True)
            raise FactCheckStageError(STAGE_SEARCH, str(e)) from e

        failed = failed_search_strategies(query_agent.last_search_metadata)
        if failed and not documents:
            raise FactCheckStageError(
                STAGE_SEARCH,
                f"no documents found and search strategies failed: {'; '.join(failed)}",
            )
        if failed:
            logger.warning(
                f"Search strategies failed ({'; '.join(failed)}); continuing with "
                f"{len(documents)} documents from the others"
            )
            if notes is not None:
                notes.extend(
                    f"search strategy failed, its results are missing: {failure}"
                    for failure in failed
                )
        return documents

    def _statement_to_question(self, statement: str) -> str:
        """Convert a statement to a question format for better search results."""
        # Simple heuristic conversion - can be improved with LLM
        statement = statement.strip()

        # If already a question, return as-is
        if statement.endswith('?'):
            return statement

        # Check for yes/no statement patterns
        yes_no_indicators = [
            "all cases", "all patients", "every case", "always",
            "no cases", "never", "none", "is", "are", "does", "do",
            "can", "should", "must", "will"
        ]

        lower_statement = statement.lower()
        if any(indicator in lower_statement for indicator in yes_no_indicators):
            # It's likely a yes/no statement
            if lower_statement.startswith(("all ", "every ", "no ", "never ")):
                return f"Is it true that {statement}?"
            else:
                return f"{statement}?"

        # Default: treat as a topic to research
        return f"What does the literature say about: {statement}?"

    def _score_documents(
        self,
        statement: str,
        documents: List[Dict[str, Any]],
        threshold: float,
        notes: Optional[List[str]] = None,
    ) -> List[tuple[Dict[str, Any], Dict[str, Any]]]:
        """Score documents for relevance to the statement.

        A recoverable failure (unreachable LLM, timeout) is retried with
        exponential backoff. A document that still fails to score is skipped,
        but an empty result is only returned when every document was actually
        scored: if none reached the threshold and some failed, the evidence
        was not fully examined.

        Args:
            statement: The statement to fact-check.
            documents: Documents returned by the search.
            threshold: Minimum relevance score to keep a document.
            notes: Degradation notes; documents that could not be scored are
                appended here when others reached the threshold.

        Returns:
            List of (document, scoring_result) tuples where scoring_result is a dict
            with 'score' and 'reasoning' keys, highest score first.

        Raises:
            FactCheckStageError: If no document reached the threshold and at
                least one document failed to score.
        """
        scoring_agent = _require_sub_agent(self.scoring_agent, "DocumentScoringAgent")
        scored_docs: List[tuple[Dict[str, Any], Dict[str, Any]]] = []
        failed_ids: List[Any] = []
        last_error = ""

        for doc in documents:
            doc_id = doc.get('id', 'unknown')
            try:
                scoring_result = self._with_backoff(
                    lambda: scoring_agent.evaluate_document(user_question=statement, document=doc),
                    f"relevance scoring of document {doc_id}",
                )

                # Extract numeric score for threshold check
                score = scoring_result['score']

                if score >= threshold:
                    # Store the full scoring_result dict, not just the score
                    scored_docs.append((doc, cast(Dict[str, Any], scoring_result)))
            except Exception as e:
                failed_ids.append(doc_id)
                last_error = str(e)
                logger.warning(f"Error scoring document {doc_id}: {e}", exc_info=True)
                continue

        if failed_ids and not scored_docs:
            raise FactCheckStageError(
                STAGE_SCORING,
                f"{len(failed_ids)} of {len(documents)} documents could not be scored "
                f"(IDs {_list_ids(failed_ids)}) and none of the others reached the "
                f"threshold (last error: {last_error})",
            )
        if failed_ids:
            logger.warning(
                f"{len(failed_ids)} of {len(documents)} documents could not be scored; "
                f"continuing with {len(scored_docs)} above the threshold"
            )
            if notes is not None:
                notes.append(
                    f"{len(failed_ids)} of {len(documents)} documents could not be scored "
                    f"(IDs {_list_ids(failed_ids)}; last error: {last_error})"
                )

        # Sort by score descending (access score from dict)
        scored_docs.sort(key=lambda x: x[1]['score'], reverse=True)

        return scored_docs

    def _extract_citations(
        self,
        statement: str,
        scored_documents: List[tuple[Dict[str, Any], Dict[str, Any]]],
        score_threshold: Optional[float] = None,
        notes: Optional[List[str]] = None,
    ) -> List[Citation]:
        """Extract relevant citations from scored documents.

        CRITICAL FIX: Filter by score threshold FIRST, then limit count.
        This prevents the bug where we processed low-scoring documents that
        caused LLM hallucination due to insufficient real citations.

        Args:
            statement: The statement to fact-check
            scored_documents: List of (document, scoring_result) tuples
            score_threshold: Minimum relevance score; ``None`` uses the
                agent default. Must match the threshold used for scoring so a
                per-call override is not undone here.
            notes: Degradation notes; documents that failed or whose passages
                were rejected are appended here when others yielded citations.

        Returns:
            The extracted citations; empty only if every document was examined
            and judged to have no relevant passage.

        Raises:
            FactCheckStageError: If extraction raised, or no citation was
                extracted and at least one document failed with an error or
                had every passage rejected (unusable model output, e.g. a
                fragment instead of complete sentences): that is a model
                failure, not missing evidence.
        """
        threshold = self.score_threshold if score_threshold is None else score_threshold

        # Step 1: Filter by threshold FIRST (most important fix)
        qualifying_docs = [
            (doc, score_result) for doc, score_result in scored_documents
            if score_result.get('score', 0) >= threshold
        ]

        logger.info(
            f"Filtered to {len(qualifying_docs)} documents above threshold "
            f"{threshold} (from {len(scored_documents)} total)"
        )

        # Step 2: Apply max_citations limit AFTER filtering (if set)
        if self.max_citations is None:
            top_docs = qualifying_docs  # Use ALL qualifying documents (recommended)
            logger.info(f"Processing all {len(top_docs)} qualifying documents")
        else:
            top_docs = qualifying_docs[:self.max_citations]
            logger.info(
                f"Limited to top {len(top_docs)} citations "
                f"(max_citations={self.max_citations})"
            )

        if not top_docs:
            logger.warning(
                f"No documents above threshold {threshold} after filtering. "
                f"Consider lowering threshold or improving query."
            )
            return []

        # Step 3: Extract citations (with new validation)
        citation_agent = _require_sub_agent(self.citation_agent, "CitationFinderAgent")
        try:
            # Snapshot sizes, not the lists: the agent's stats are live.
            stats = citation_agent.get_validation_stats()
            errors_before = len(stats.get('errored_documents', []))
            rejections_before = len(stats.get('failed_citations', []))
            citations = citation_agent.process_scored_documents_for_citations(
                user_question=statement,
                scored_documents=top_docs,
                score_threshold=threshold
            )
            stats = citation_agent.get_validation_stats()
            errored = list(stats.get('errored_documents', []))[errors_before:]
            rejected = list(stats.get('failed_citations', []))[rejections_before:]
        except Exception as e:
            logger.error(f"Error extracting citations: {e}", exc_info=True)
            raise FactCheckStageError(STAGE_CITATIONS, str(e)) from e

        problems = []
        if errored:
            problems.append(
                f"{len(errored)} of {len(top_docs)} documents failed with an error "
                f"(IDs {_list_ids([e.get('document_id') for e in errored])}; "
                f"last error: {errored[-1].get('error', 'unknown')})"
            )
        if rejected:
            problems.append(
                f"{len(rejected)} of {len(top_docs)} documents had every passage "
                f"rejected (IDs {_list_ids([r.get('document_id') for r in rejected])}; "
                f"{_count_reasons(rejected)})"
            )

        if problems and not citations:
            raise FactCheckStageError(
                STAGE_CITATIONS, "no citation extracted: " + "; ".join(problems)
            )

        logger.info(
            f"Extracted {len(citations)} validated citations from "
            f"{len(top_docs)} documents"
            + (f" ({'; '.join(problems)})" if problems else "")
        )
        if problems and notes is not None:
            notes.extend(f"citation extraction: {problem}" for problem in problems)

        return citations

    def _evaluate_statement(
        self,
        statement: str,
        citations: List[Citation],
        scored_documents: List[tuple[Dict[str, Any], Dict[str, Any]]],
        expected_answer: Optional[str] = None
    ) -> FactCheckResult:
        """
        Evaluate the statement based on extracted citations.

        Uses LLM to analyze citations and determine if they support,
        contradict, or are neutral regarding the statement.

        Args:
            statement: The statement to fact-check
            citations: Extracted citations
            scored_documents: List of (document, scoring_result) tuples
            expected_answer: Optional expected answer for validation

        Raises:
            FactCheckStageError: If the LLM gave no usable verdict.
        """
        # Prepare evidence summary for LLM
        evidence_summary = self._prepare_evidence_summary(citations)

        # Create evaluation prompt
        prompt = self._create_evaluation_prompt(statement, evidence_summary)

        evaluation_data = self._request_evaluation(prompt, len(citations))

        # Convert citations to evidence references
        evidence_refs = self._citations_to_evidence_refs(
            citations,
            scored_documents,
            evaluation_data.get('citation_stances', {})
        )

        # Count citation types
        supporting = sum(1 for ref in evidence_refs if ref.supports_statement is True)
        contradicting = sum(1 for ref in evidence_refs if ref.supports_statement is False)
        neutral = sum(1 for ref in evidence_refs if ref.supports_statement is None)

        # Determine confidence
        confidence = self._determine_confidence(
            evaluation_data['evaluation'],
            supporting,
            contradicting,
            neutral,
            len(scored_documents)
        )

        # Check if matches expected answer
        matches_expected = None
        if expected_answer:
            matches_expected = (evaluation_data['evaluation'].lower() == expected_answer.lower())

        return FactCheckResult(
            statement=statement,
            evaluation=evaluation_data['evaluation'],
            reason=evaluation_data['reason'],
            evidence_list=evidence_refs,
            confidence=confidence,
            documents_reviewed=len(scored_documents),
            supporting_citations=supporting,
            contradicting_citations=contradicting,
            neutral_citations=neutral,
            expected_answer=expected_answer,
            matches_expected=matches_expected
        )

    def _prepare_evidence_summary(self, citations: List[Citation]) -> str:
        """Prepare a summary of evidence for the LLM."""
        summary_parts = []

        for i, citation in enumerate(citations, 1):
            # Get identifier (PMID or DOI)
            identifier = ""
            if citation.pmid:
                identifier = f" (PMID:{citation.pmid})"
            elif citation.doi:
                identifier = f" (DOI:{citation.doi})"

            summary_parts.append(
                f"[{i}] {citation.passage}{identifier}"
            )

        return "\n\n".join(summary_parts)

    def _create_evaluation_prompt(self, statement: str, evidence_summary: str) -> str:
        """Create the evaluation prompt for the LLM."""
        return f"""You are a biomedical fact-checker. Analyze the following statement against the provided literature evidence.

STATEMENT TO EVALUATE:
{statement}

LITERATURE EVIDENCE:
{evidence_summary}

TASK:
1. Determine if the evidence supports, contradicts, or is insufficient to evaluate the statement
2. Provide your evaluation as: "yes" (statement is supported), "no" (statement is contradicted), or "maybe" (insufficient/mixed evidence)
3. Provide a brief reason (1-3 sentences) for your evaluation
4. For each citation, indicate if it supports, contradicts, or is neutral regarding the statement

RESPONSE FORMAT (JSON):
{{
    "evaluation": "yes|no|maybe",
    "reason": "Brief explanation of your evaluation",
    "citation_stances": {{
        "1": "supports|contradicts|neutral",
        "2": "supports|contradicts|neutral",
        ...
    }}
}}

Respond ONLY with the JSON object, no additional text."""

    def _request_evaluation(self, prompt: str, citation_count: int) -> Dict[str, Any]:
        """
        Ask the LLM for a verdict and validate it.

        An unreachable or timed-out LLM is retried with exponential backoff.
        A response with an invalid verdict, invalid citation stances or
        missing fields is requested again; at most
        ``EVALUATION_VALIDATION_ATTEMPTS`` requests are made in total. An
        invalid response is never coerced into a "maybe" or a "neutral".

        Args:
            prompt: The evaluation prompt.
            citation_count: Number of citations in the prompt; each needs a
                stance.

        Returns:
            The validated evaluation (see ``_validate_evaluation_response``).

        Raises:
            FactCheckStageError: If the LLM request failed, its output could
                not be parsed as JSON, or every response was invalid.
        """
        last_problem = ""
        num_predict = evaluation_token_budget(self.max_tokens, citation_count)
        for attempt in range(1, EVALUATION_VALIDATION_ATTEMPTS + 1):
            try:
                response_data = self._with_backoff(
                    lambda: self._chat_and_parse_json(
                        messages=[{'role': 'user', 'content': prompt}],
                        max_retries=EVALUATION_JSON_RETRIES,
                        retry_context="statement evaluation",
                        num_predict=num_predict
                    ),
                    "statement evaluation LLM request",
                )
            except json.JSONDecodeError as e:
                logger.error(f"Unparseable LLM evaluation: {e}", exc_info=True)
                raise FactCheckStageError(
                    STAGE_EVALUATION, f"LLM output could not be parsed as JSON: {e}"
                ) from e
            except Exception as e:
                logger.error(f"Error getting LLM evaluation: {e}", exc_info=True)
                raise FactCheckStageError(
                    STAGE_EVALUATION, f"LLM request failed ({type(e).__name__}): {e}"
                ) from e

            try:
                return self._validate_evaluation_response(response_data, citation_count)
            except ValueError as e:
                last_problem = str(e)
                logger.warning(
                    f"Invalid evaluation response (attempt {attempt}/"
                    f"{EVALUATION_VALIDATION_ATTEMPTS}): {e}"
                )

        raise FactCheckStageError(
            STAGE_EVALUATION,
            f"invalid LLM response after {EVALUATION_VALIDATION_ATTEMPTS} attempts: "
            f"{last_problem}",
        )

    def _validate_evaluation_response(self, data: Any, citation_count: int) -> Dict[str, Any]:
        """
        Validate and normalize the LLM's evaluation response.

        Args:
            data: The parsed JSON response.
            citation_count: Number of citations the model was shown; each
                (``"1"`` .. ``str(citation_count)``) needs a stance.

        Returns:
            A copy of ``data`` with ``evaluation`` lower-cased and stripped,
            ``reason`` stripped, and ``citation_stances`` mapping each
            citation number to a lower-cased stance in ``VALID_STANCES``.

        Raises:
            ValueError: If the response is not an object, lacks ``evaluation``
                or ``reason``, the verdict is not one of ``VALID_VERDICTS``,
                the reason is empty, or a citation's stance is missing or not
                one of ``VALID_STANCES``.
        """
        if not isinstance(data, dict):
            raise ValueError(
                f"Evaluation response must be a JSON object, got {type(data).__name__}"
            )
        if 'evaluation' not in data or 'reason' not in data:
            raise ValueError("Missing required fields in evaluation response")

        verdict = data['evaluation']
        if not isinstance(verdict, str) or verdict.lower().strip() not in VALID_VERDICTS:
            raise ValueError(
                f"Invalid evaluation value {verdict!r} (expected one of {VALID_VERDICTS})"
            )

        reason = data['reason']
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("Evaluation reason must be a non-empty string")

        return {
            **data,
            'evaluation': verdict.lower().strip(),
            'reason': reason.strip(),
            'citation_stances': self._validate_stances(
                data.get('citation_stances'), citation_count
            ),
        }

    @staticmethod
    def _validate_stances(stances: Any, citation_count: int) -> Dict[str, str]:
        """
        Validate the per-citation stances of an evaluation response.

        Args:
            stances: The response's ``citation_stances``.
            citation_count: Number of citations the model was shown.

        Returns:
            ``{"1": stance, ...}`` with every stance lower-cased and stripped.

        Raises:
            ValueError: If citations were shown and ``stances`` is not an
                object, or a citation's stance is missing or invalid.
        """
        if citation_count == 0:
            return {}
        if not isinstance(stances, dict):
            raise ValueError(
                f"citation_stances must be an object, got {type(stances).__name__}"
            )
        validated: Dict[str, str] = {}
        for number in range(1, citation_count + 1):
            stance = stances.get(str(number))
            normalized = stance.lower().strip() if isinstance(stance, str) else None
            if normalized not in VALID_STANCES:
                raise ValueError(
                    f"Invalid stance {stance!r} for citation {number} "
                    f"(expected one of {VALID_STANCES})"
                )
            validated[str(number)] = normalized
        extra = set(stances) - set(validated)
        if extra:
            logger.warning(f"Ignoring stances for citations that do not exist: {sorted(extra)}")
        return validated

    def _citations_to_evidence_refs(
        self,
        citations: List[Citation],
        scored_documents: List[tuple[Dict[str, Any], Dict[str, Any]]],
        citation_stances: Dict[str, str]
    ) -> List[EvidenceReference]:
        """Convert Citation objects to EvidenceReference objects.

        Args:
            citations: List of Citation objects
            scored_documents: List of (document, scoring_result) tuples
            citation_stances: Validated stances, citation number -> stance
                (see ``_validate_stances``)
        """
        evidence_refs = []

        # Create document ID to score mapping (handle both int and str IDs)
        # Extract numeric score from scoring_result dict
        doc_scores = {}
        for doc, scoring_result in scored_documents:
            doc_id = doc['id']
            score = scoring_result['score']  # Extract numeric score from dict
            doc_scores[str(doc_id)] = score
            doc_scores[doc_id] = score

        for i, citation in enumerate(citations, 1):
            # Get stance from LLM evaluation
            stance_str = citation_stances[str(i)]
            supports = None
            if stance_str == 'supports':
                supports = True
            elif stance_str == 'contradicts':
                supports = False

            # Get relevance score (try both str and int versions of ID)
            relevance_score = doc_scores.get(citation.document_id)
            if relevance_score is None and isinstance(citation.document_id, str):
                try:
                    relevance_score = doc_scores.get(int(citation.document_id))
                except (ValueError, TypeError):
                    pass

            evidence_refs.append(EvidenceReference(
                citation_text=citation.passage,
                pmid=citation.pmid,
                doi=citation.doi,
                document_id=citation.document_id,
                relevance_score=relevance_score,
                supports_statement=supports
            ))

        return evidence_refs

    def _determine_confidence(
        self,
        evaluation: str,
        supporting: int,
        contradicting: int,
        neutral: int,
        total_docs: int
    ) -> str:
        """Determine confidence level based on evidence characteristics."""
        total_citations = supporting + contradicting + neutral

        if total_citations == 0 or total_docs < 3:
            return "low"

        # High confidence: clear majority in one direction with multiple sources
        if evaluation in ['yes', 'no']:
            dominant = supporting if evaluation == 'yes' else contradicting
            if dominant >= 3 and dominant / total_citations >= 0.7 and total_docs >= 5:
                return "high"
            elif dominant >= 2 and dominant / total_citations >= 0.6:
                return "medium"

        # Maybe evaluation: mixed evidence
        if evaluation == 'maybe':
            if total_citations >= 4 and total_docs >= 5:
                return "medium"

        return "low"

    def check_batch(
        self,
        statements: List[Dict[str, str]],
        output_file: Optional[str] = None,
        source_file: Optional[str] = None
    ) -> List[FactCheckResult]:
        """
        Check multiple statements in batch with incremental database storage.

        Results are stored in the database after each statement is processed
        to prevent data loss in case of interruption. A statement whose check
        fails (or an input item that is not a statement object) is returned
        with ``evaluation == EVALUATION_ERROR``, counted in
        ``self.check_failures`` and not stored, so it stays unevaluated and
        incremental mode retries it. Verdicts with degradation notes are
        counted in ``self.degraded_results``; a requested JSON export that was
        not written sets ``self.export_failed``.

        Args:
            statements: List of dicts with either:
                - 'statement' and optional 'answer' keys (legacy format), OR
                - 'id', 'question', and 'answer' keys (extracted format)
            output_file: Optional file path for JSON export
            source_file: Source filename for metadata

        Returns:
            List of FactCheckResult objects
        """
        results = []
        total = len(statements)
        self.storage_failures = 0
        self.check_failures = 0
        self.degraded_results = 0
        self.export_failed = False
        self.session_bookkeeping_failed = False
        self.stored_results = 0

        self._call_callback("batch_start", f"Processing {total} statements...")

        # Initialize database session
        self.current_session_id = str(uuid.uuid4())
        self._initialize_database_session(total, source_file or output_file)

        for i, item in enumerate(statements, 1):
            statement, expected, item_id = "", None, None
            try:
                statement, expected, item_id = self._parse_batch_item(item)
                self._call_callback("batch_progress", f"Processing {i}/{total}: {statement[:60]}...")
                result = self.check_statement(
                    statement=statement,
                    expected_answer=expected
                )

                # Store the original ID if provided
                if item_id:
                    result.input_statement_id = item_id

                results.append(result)
            except Exception as e:
                self.check_failures += 1
                logger.error(f"Error checking statement '{statement}': {e}", exc_info=True)
                self._call_callback(
                    "statement_failed",
                    f"Fact-check failed, not stored: {statement[:60]!r}: {e}"
                )
                results.append(FactCheckResult.failed(
                    statement=statement,
                    error=e,
                    expected_answer=expected,
                    input_statement_id=item_id,
                ))
                # Not stored: an error is not a verdict, and leaving the
                # statement unevaluated lets incremental mode retry it.
                continue

            if result.is_degraded:
                self.degraded_results += 1

            # Store result incrementally in database
            if self.db and self._store_result_in_database(result, source_file):
                self.stored_results += 1

        # Finalize database session
        if self.db:
            self._finalize_database_session(self.stored_results, total)

        # Export to JSON if requested
        if output_file:
            self._call_callback("export", f"Exporting results to {output_file}...")
            if self.export_database_to_json(output_file, export_type="full") is None:
                self.export_failed = True

        # Report citation validation statistics
        if self.citation_agent is not None:
            stats = self.citation_agent.get_validation_stats()
            if stats['total_extractions'] > 0:
                self._call_callback("validation_stats",
                    f"Citation validation: {stats['validations_passed']}/{stats['total_extractions']} passed "
                    f"({stats['pass_rate']:.1%}), "
                    f"{stats['exact_matches']} exact matches, "
                    f"{stats['fuzzy_matches']} fuzzy matches, "
                    f"{stats.get('widened_passages', 0)} widened from fragments, "
                    f"{stats['validations_failed']} rejected"
                )

                if stats['validations_failed'] > 0:
                    logger.warning(
                        f"⚠️  {stats['validations_failed']} citations were REJECTED "
                        f"({_count_reasons(stats.get('failed_citations', []))}). "
                        f"See detailed logs for rejected citation text."
                    )

        self._call_callback("batch_complete", f"Completed {total} statements")

        return results

    @staticmethod
    def _parse_batch_item(item: Any) -> tuple[str, Optional[str], Optional[str]]:
        """
        Read one input item of a batch.

        Supports the legacy format (``statement``/``answer``) and the
        extracted format (``id``/``question``/``answer``).

        Args:
            item: One element of the input list.

        Returns:
            ``(statement, expected_answer, input_statement_id)``.

        Raises:
            ValueError: If the item is not an object or has no statement text.
        """
        if not isinstance(item, dict):
            raise ValueError(f"Input item is not a statement object: {item!r}")
        if 'question' in item:
            statement, item_id = item.get('question'), item.get('id')
        else:
            statement, item_id = item.get('statement'), None
        if not isinstance(statement, str) or not statement.strip():
            raise ValueError(f"Input item has no statement text: {item!r}")
        expected = item.get('answer')
        return statement, expected, None if item_id is None else str(item_id)

    def check_batch_from_file(
        self,
        input_file: str,
        output_file: Optional[str] = None
    ) -> List[FactCheckResult]:
        """
        Check multiple statements from a JSON file.

        Args:
            input_file: Path to JSON file with statements (supports both legacy and extracted formats)
            output_file: Optional file path for JSON export

        Returns:
            List of FactCheckResult objects
        """
        try:
            with open(input_file, 'r', encoding='utf-8') as f:
                statements = json.load(f)

            if not isinstance(statements, list):
                raise ValueError("Input file must contain a JSON array of statement objects")

            self._call_callback("file_loaded", f"Loaded {len(statements)} statements from {input_file}")

            # Initialize database
            if not self.db:
                self.db = FactCheckerDB()
                self._call_callback("database", "Database initialized (PostgreSQL factcheck schema)")

            # In incremental mode, only import NEW statements (not already in database)
            if self.incremental and self.db:
                original_count = len(statements)

                # Extract statement texts (support both formats)
                statement_texts = []
                for item in statements:
                    if 'question' in item:
                        statement_texts.append(item.get('question', ''))
                    else:
                        statement_texts.append(item.get('statement', ''))

                # Get existing statements from database (batch query)
                existing_statements = set(self.db.get_existing_statements(statement_texts))

                # Filter to only NEW statements for import
                new_statements = []
                for item in statements:
                    if 'question' in item:
                        text = item.get('question', '')
                    else:
                        text = item.get('statement', '')

                    if text not in existing_statements:
                        new_statements.append(item)

                new_count = len(new_statements)
                existing_count = original_count - new_count

                if new_count > 0:
                    # Import only NEW statements
                    self._call_callback("import", f"Importing {new_count} new statements into database...")

                    # Create temporary JSON file with only new statements
                    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as tmp:
                        json.dump(new_statements, tmp)
                        tmp_file = tmp.name

                    try:
                        import_stats = self.db.import_json_results(tmp_file, skip_existing=False)
                        self._call_callback("import",
                            f"Import complete: {import_stats['new_statements']} imported, "
                            f"{existing_count} already in database")
                    finally:
                        os.unlink(tmp_file)
                else:
                    self._call_callback("import", f"All {original_count} statements already in database")

                # Now check which statements need evaluation
                texts_needing_eval = set(self.db.get_statements_needing_evaluation(statement_texts))

                # Filter statements list to only those needing evaluation
                filtered_statements = []
                for item in statements:
                    if 'question' in item:
                        text = item.get('question', '')
                    else:
                        text = item.get('statement', '')

                    if text in texts_needing_eval:
                        filtered_statements.append(item)

                skipped_count = original_count - len(filtered_statements)
                statements = filtered_statements

                if skipped_count > 0:
                    self._call_callback("incremental",
                        f"Incremental mode: Skipping {skipped_count} already-evaluated statements, "
                        f"processing {len(statements)} new/unevaluated statements")
                else:
                    self._call_callback("incremental",
                        f"Incremental mode: All {len(statements)} statements need evaluation")
            else:
                # Non-incremental mode: import all statements
                self._call_callback("import", f"Importing {len(statements)} statements into database...")
                import_stats = self.db.import_json_results(input_file, skip_existing=True)
                self._call_callback("import",
                    f"Import complete: {import_stats['new_statements']} new, "
                    f"{import_stats['skipped_existing']} already in database")

            return self.check_batch(statements, output_file, source_file=input_file)

        except Exception as e:
            logger.error(f"Error loading statements from file: {e}")
            raise

    # ========== Database Operations ==========

    def _initialize_database_session(self, total_statements: int, source_file: Optional[str]):
        """Initialize a new processing session in the database."""
        if not self.db:
            return

        session_data = {
            'session_id': self.current_session_id,
            'input_file': source_file or 'unknown',
            'total_statements': total_statements,
            'start_time': datetime.now(timezone.utc).isoformat(),
            'status': 'running',
            'config_snapshot': json.dumps({
                'model': self.model,
                'temperature': self.temperature,
                'top_p': self.top_p,
                'score_threshold': self.score_threshold,
                'max_search_results': self.max_search_results,
                'max_citations': self.max_citations
            })
        }

        try:
            self.db.insert_processing_session(session_data)
            logger.info(f"Started session {self.current_session_id}")
        except Exception as e:
            self.session_bookkeeping_failed = True
            logger.error(f"Error initializing database session: {e}", exc_info=True)

    def _store_result_in_database(self, result: FactCheckResult, source_file: Optional[str]) -> bool:
        """Store a FactCheckResult (a verdict) in the database.

        Args:
            result: The verdict to store.
            source_file: Input file name, recorded with the statement.

        Returns:
            True if the result was persisted, False on any storage error.
            Failures are also counted in ``self.storage_failures`` so batch
            callers (and the CLI) can report them instead of claiming success.

        Raises:
            ValueError: If ``result`` is a failed check: an error is never
                stored as a verdict (it would stop incremental mode from
                retrying the statement).
        """
        if result.is_error:
            raise ValueError(
                f"Refusing to store a failed fact-check as a verdict: {result.statement[:60]!r}"
            )
        if not self.db:
            return False

        try:
            # Insert or get statement
            stmt = Statement(
                statement_text=result.statement,
                input_statement_id=result.input_statement_id,
                expected_answer=result.expected_answer,
                source_file=source_file or 'unknown',
                review_status='pending'
            )
            statement_id = self.db.insert_statement(stmt)

            # Insert AI evaluation
            ai_eval = AIEvaluation(
                statement_id=statement_id,
                evaluation=result.evaluation,
                reason=result.reason,
                confidence=result.confidence,
                documents_reviewed=result.documents_reviewed,
                supporting_citations=result.supporting_citations,
                contradicting_citations=result.contradicting_citations,
                neutral_citations=result.neutral_citations,
                matches_expected=result.matches_expected,
                model_used=self.model,
                session_id=self.current_session_id,
                version=1,
                degradation_notes=list(result.degradation_notes) or None
            )
            eval_id = self.db.insert_ai_evaluation(ai_eval)

            # Insert evidence citations
            for evidence_ref in result.evidence_list:
                evidence = Evidence(
                    evaluation_id=eval_id,
                    citation_text=evidence_ref.citation_text,
                    pmid=evidence_ref.pmid,
                    doi=evidence_ref.doi,
                    document_id=evidence_ref.document_id,
                    relevance_score=evidence_ref.relevance_score,
                    supports_statement="supports" if evidence_ref.supports_statement is True else
                                      "contradicts" if evidence_ref.supports_statement is False else
                                      "neutral"
                )
                self.db.insert_evidence(evidence)

            logger.debug(f"Stored result for statement {statement_id} in database")
            return True

        except Exception as e:
            logger.error(f"Error storing result in database: {e}", exc_info=True)
            self.storage_failures += 1
            return False

    def _finalize_database_session(self, stored_count: int, total: int) -> None:
        """Finalize the processing session in the database.

        The session is ``failed`` if statements were submitted and none got
        a stored verdict, else ``completed``. Failed checks, storage failures
        and verdicts based on partial evidence are described in the session's
        ``error_message``.

        Args:
            stored_count: Verdicts stored in this batch.
            total: Statements submitted in this batch.
        """
        if not self.db or not self.current_session_id:
            return

        problems = []
        if self.check_failures:
            problems.append(
                f"{self.check_failures} statement(s) failed to check and were not "
                f"stored; re-run with --incremental to retry them"
            )
        if self.storage_failures:
            problems.append(f"{self.storage_failures} verdict(s) failed to store")
        if self.degraded_results:
            problems.append(
                f"{self.degraded_results} verdict(s) are based on partial evidence "
                f"(see ai_evaluations.degradation_notes)"
            )
        updates: Dict[str, Any] = {
            'processed_statements': stored_count,
            'end_time': datetime.now(timezone.utc).isoformat(),
            'status': 'failed' if total and not stored_count else 'completed',
        }
        if problems:
            updates['error_message'] = "; ".join(problems)

        try:
            self.db.update_processing_session(self.current_session_id, updates)
            logger.info(f"Finalized session {self.current_session_id}")
        except Exception as e:
            self.session_bookkeeping_failed = True
            logger.error(f"Error finalizing database session: {e}", exc_info=True)

    def export_database_to_json(self, output_file: str, export_type: str = "full",
                                requested_by: str = "system") -> Optional[str]:
        """
        Export database contents to JSON file.

        Args:
            output_file: Path to output JSON file
            export_type: Type of export (full/ai_only/human_annotated/summary)
            requested_by: Username of requester

        Returns:
            Path to exported file, or None if the database is not initialized
            or the export failed (logged; ``check_batch`` reports it through
            ``self.export_failed``).
        """
        if not self.db:
            logger.error("Database not initialized, cannot export")
            return None

        try:
            export_path = self.db.export_to_json(output_file, export_type, requested_by)
            self._call_callback("export", f"Exported to {export_path}")
            return export_path
        except Exception as e:
            logger.error(f"Error exporting database to JSON: {e}", exc_info=True)
            return None

