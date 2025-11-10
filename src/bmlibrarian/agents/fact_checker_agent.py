"""
Fact Checker Agent for auditing biomedical statements against literature evidence.

Takes biomedical statements and evaluates their veracity (yes/no/maybe) by:
- Searching for relevant literature using QueryAgent
- Scoring document relevance using DocumentScoringAgent
- Extracting supporting/contradicting evidence using CitationFinderAgent
- Synthesizing a fact-check evaluation with evidence references
"""

import json
import logging
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, asdict
from datetime import datetime, timezone

from .base import BaseAgent
from .query_agent import QueryAgent
from .scoring_agent import DocumentScoringAgent, ScoringResult
from .citation_agent import CitationFinderAgent, Citation

logger = logging.getLogger(__name__)


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
        if self.relevance_score is not None:
            result["relevance_score"] = self.relevance_score
        if self.supports_statement is not None:
            result["stance"] = "supports" if self.supports_statement else "contradicts"
        return result


@dataclass
class FactCheckResult:
    """Result of a fact-check evaluation."""
    statement: str
    evaluation: str  # "yes", "no", "maybe"
    reason: str
    evidence_list: List[EvidenceReference]
    confidence: Optional[str] = "medium"  # "high", "medium", "low"
    documents_reviewed: int = 0
    supporting_citations: int = 0
    contradicting_citations: int = 0
    neutral_citations: int = 0
    expected_answer: Optional[str] = None
    matches_expected: Optional[bool] = None
    timestamp: str = None

    def __post_init__(self):
        """Set timestamp if not provided."""
        if self.timestamp is None:
            self.timestamp = datetime.now(timezone.utc).isoformat()

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
        max_citations: int = 10
    ):
        """
        Initialize the FactCheckerAgent.

        Args:
            model: The name of the Ollama model to use for evaluation
            host: The Ollama server host URL
            temperature: Model temperature for response randomness
            top_p: Model top-p sampling parameter
            max_tokens: Maximum tokens for model generation
            callback: Optional callback function for progress updates
            orchestrator: Optional orchestrator for queue-based processing
            show_model_info: Whether to display model information
            score_threshold: Minimum relevance score for documents
            max_search_results: Maximum number of documents to retrieve
            max_citations: Maximum number of citations to extract
        """
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

        # Initialize sub-agents (will be set up during fact-checking)
        self.query_agent = None
        self.scoring_agent = None
        self.citation_agent = None

    def get_agent_type(self) -> str:
        """Get the type identifier for this agent."""
        return "FactCheckerAgent"

    def _initialize_agents(self) -> None:
        """Initialize sub-agents for the fact-checking workflow."""
        if self.query_agent is None:
            self._call_callback("init", "Initializing sub-agents...")

            # Import configuration system
            from ..config import get_model, get_agent_config

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
                **self._filter_agent_params(scoring_config)
            )

            # Initialize CitationFinderAgent
            citation_model = get_model("citation_agent")
            citation_config = get_agent_config("citation")
            self.citation_agent = CitationFinderAgent(
                model=citation_model,
                host=self.host,
                show_model_info=False,
                **self._filter_agent_params(citation_config)
            )

    def _filter_agent_params(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Filter agent configuration to only include supported parameters."""
        supported_params = {'temperature', 'top_p', 'max_tokens', 'callback', 'orchestrator'}
        return {k: v for k, v in config.items() if k in supported_params}

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
            max_documents: Maximum number of documents to search (overrides default)
            score_threshold: Minimum relevance score (overrides default)

        Returns:
            FactCheckResult with evaluation, reason, and evidence
        """
        self._initialize_agents()

        # Use provided values or defaults
        max_docs = max_documents or self.max_search_results
        threshold = score_threshold or self.score_threshold

        self._call_callback("search", f"Searching literature for: {statement}")

        # Step 1: Search for relevant documents
        documents = self._search_documents(statement, max_docs)

        if not documents:
            self._call_callback("warning", "No relevant documents found")
            return FactCheckResult(
                statement=statement,
                evaluation="maybe",
                reason="Insufficient evidence: No relevant documents found in the literature database.",
                evidence_list=[],
                confidence="low",
                documents_reviewed=0,
                expected_answer=expected_answer,
                matches_expected=(expected_answer == "maybe") if expected_answer else None
            )

        self._call_callback("scoring", f"Scoring {len(documents)} documents...")

        # Step 2: Score documents for relevance
        scored_documents = self._score_documents(statement, documents, threshold)

        if not scored_documents:
            self._call_callback("warning", f"No documents above threshold {threshold}")
            return FactCheckResult(
                statement=statement,
                evaluation="maybe",
                reason=f"Insufficient evidence: No documents scored above relevance threshold ({threshold}/5.0).",
                evidence_list=[],
                confidence="low",
                documents_reviewed=len(documents),
                expected_answer=expected_answer,
                matches_expected=(expected_answer == "maybe") if expected_answer else None
            )

        self._call_callback("extraction", f"Extracting evidence from {len(scored_documents)} documents...")

        # Step 3: Extract citations
        citations = self._extract_citations(statement, scored_documents)

        if not citations:
            self._call_callback("warning", "No citations could be extracted")
            return FactCheckResult(
                statement=statement,
                evaluation="maybe",
                reason="Insufficient evidence: Documents found but no relevant citations could be extracted.",
                evidence_list=[],
                confidence="low",
                documents_reviewed=len(scored_documents),
                expected_answer=expected_answer,
                matches_expected=(expected_answer == "maybe") if expected_answer else None
            )

        self._call_callback("evaluation", f"Evaluating statement based on {len(citations)} citations...")

        # Step 4: Evaluate the statement
        result = self._evaluate_statement(
            statement=statement,
            citations=citations,
            scored_documents=scored_documents,
            expected_answer=expected_answer
        )

        self._call_callback("complete", f"Fact-check complete: {result.evaluation}")

        return result

    def _search_documents(self, statement: str, max_results: int) -> List[Dict[str, Any]]:
        """Search for documents relevant to the statement."""
        try:
            # Convert statement to a question format for better query generation
            search_question = self._statement_to_question(statement)
            self._call_callback("query", f"Query: {search_question}")

            # Use QueryAgent to search
            documents = self.query_agent.search_documents(
                user_question=search_question,
                max_results=max_results
            )

            return documents
        except Exception as e:
            logger.error(f"Error searching documents: {e}")
            return []

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
        threshold: float
    ) -> List[tuple[Dict[str, Any], float]]:
        """Score documents for relevance to the statement."""
        scored_docs = []

        for doc in documents:
            try:
                score = self.scoring_agent.evaluate_document(
                    user_question=statement,
                    document=doc
                )

                if score and score >= threshold:
                    scored_docs.append((doc, score))
            except Exception as e:
                logger.warning(f"Error scoring document {doc.get('id', 'unknown')}: {e}")
                continue

        # Sort by score descending
        scored_docs.sort(key=lambda x: x[1], reverse=True)

        return scored_docs

    def _extract_citations(
        self,
        statement: str,
        scored_documents: List[tuple[Dict[str, Any], float]]
    ) -> List[Citation]:
        """Extract relevant citations from scored documents."""
        try:
            # Limit to top documents
            top_docs = scored_documents[:self.max_citations]

            citations = self.citation_agent.process_scored_documents_for_citations(
                user_question=statement,
                scored_documents=top_docs,
                score_threshold=self.score_threshold
            )

            return citations
        except Exception as e:
            logger.error(f"Error extracting citations: {e}")
            return []

    def _evaluate_statement(
        self,
        statement: str,
        citations: List[Citation],
        scored_documents: List[tuple[Dict[str, Any], float]],
        expected_answer: Optional[str] = None
    ) -> FactCheckResult:
        """
        Evaluate the statement based on extracted citations.

        Uses LLM to analyze citations and determine if they support,
        contradict, or are neutral regarding the statement.
        """
        # Prepare evidence summary for LLM
        evidence_summary = self._prepare_evidence_summary(citations)

        # Create evaluation prompt
        prompt = self._create_evaluation_prompt(statement, evidence_summary)

        # Get LLM evaluation
        try:
            response = self._make_ollama_request(
                messages=[{'role': 'user', 'content': prompt}],
                num_predict=self.max_tokens
            )

            # Parse LLM response
            evaluation_data = self._parse_evaluation_response(response)

        except Exception as e:
            logger.error(f"Error getting LLM evaluation: {e}")
            # Fallback to simple heuristic evaluation
            evaluation_data = self._fallback_evaluation(statement, citations)

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

    def _parse_evaluation_response(self, response: str) -> Dict[str, Any]:
        """Parse the LLM's evaluation response."""
        try:
            data = self._parse_json_response(response)

            # Validate required fields
            if 'evaluation' not in data or 'reason' not in data:
                raise ValueError("Missing required fields in evaluation response")

            # Normalize evaluation value
            eval_value = data['evaluation'].lower().strip()
            if eval_value not in ['yes', 'no', 'maybe']:
                logger.warning(f"Invalid evaluation value '{eval_value}', defaulting to 'maybe'")
                eval_value = 'maybe'

            data['evaluation'] = eval_value

            # Ensure citation_stances exists
            if 'citation_stances' not in data:
                data['citation_stances'] = {}

            return data

        except Exception as e:
            logger.error(f"Error parsing evaluation response: {e}")
            raise

    def _fallback_evaluation(self, statement: str, citations: List[Citation]) -> Dict[str, Any]:
        """Provide fallback evaluation when LLM fails."""
        # Simple heuristic: if we have citations, it's "maybe" because we can't determine stance
        return {
            'evaluation': 'maybe',
            'reason': f"Found {len(citations)} relevant citations but unable to automatically determine if they support or contradict the statement. Manual review recommended.",
            'citation_stances': {}
        }

    def _citations_to_evidence_refs(
        self,
        citations: List[Citation],
        scored_documents: List[tuple[Dict[str, Any], float]],
        citation_stances: Dict[str, str]
    ) -> List[EvidenceReference]:
        """Convert Citation objects to EvidenceReference objects."""
        evidence_refs = []

        # Create document ID to score mapping (handle both int and str IDs)
        doc_scores = {}
        for doc, score in scored_documents:
            doc_id = doc['id']
            doc_scores[str(doc_id)] = score
            doc_scores[doc_id] = score

        for i, citation in enumerate(citations, 1):
            # Get stance from LLM evaluation
            stance_str = citation_stances.get(str(i), 'neutral')
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
        output_file: Optional[str] = None
    ) -> List[FactCheckResult]:
        """
        Check multiple statements in batch.

        Args:
            statements: List of dicts with 'statement' and optional 'answer' keys
            output_file: Optional file path to save results as JSON

        Returns:
            List of FactCheckResult objects
        """
        results = []
        total = len(statements)

        self._call_callback("batch_start", f"Processing {total} statements...")

        for i, item in enumerate(statements, 1):
            statement = item.get('statement', '')
            expected = item.get('answer')

            self._call_callback("batch_progress", f"Processing {i}/{total}: {statement[:60]}...")

            try:
                result = self.check_statement(
                    statement=statement,
                    expected_answer=expected
                )
                results.append(result)
            except Exception as e:
                logger.error(f"Error checking statement '{statement}': {e}")
                # Add error result
                results.append(FactCheckResult(
                    statement=statement,
                    evaluation="error",
                    reason=f"Error during fact-checking: {str(e)}",
                    evidence_list=[],
                    confidence="low",
                    expected_answer=expected
                ))

        # Save to file if requested
        if output_file:
            self._save_results(results, output_file)

        self._call_callback("batch_complete", f"Completed {total} statements")

        return results

    def _save_results(self, results: List[FactCheckResult], output_file: str) -> None:
        """Save results to JSON file."""
        try:
            output_data = {
                "results": [result.to_dict() for result in results],
                "summary": self._generate_summary(results)
            }

            with open(output_file, 'w') as f:
                json.dump(output_data, f, indent=2)

            logger.info(f"Results saved to {output_file}")
            self._call_callback("save", f"Results saved to {output_file}")

        except Exception as e:
            logger.error(f"Error saving results: {e}")

    def _generate_summary(self, results: List[FactCheckResult]) -> Dict[str, Any]:
        """Generate summary statistics for batch results."""
        total = len(results)

        evaluations = {'yes': 0, 'no': 0, 'maybe': 0, 'error': 0}
        confidences = {'high': 0, 'medium': 0, 'low': 0}

        matches = 0
        mismatches = 0

        for result in results:
            evaluations[result.evaluation] = evaluations.get(result.evaluation, 0) + 1
            if result.confidence:
                confidences[result.confidence] = confidences.get(result.confidence, 0) + 1

            if result.matches_expected is not None:
                if result.matches_expected:
                    matches += 1
                else:
                    mismatches += 1

        summary = {
            "total_statements": total,
            "evaluations": evaluations,
            "confidences": confidences
        }

        if matches + mismatches > 0:
            summary["validation"] = {
                "matches": matches,
                "mismatches": mismatches,
                "accuracy": round(matches / (matches + mismatches), 3)
            }

        return summary
