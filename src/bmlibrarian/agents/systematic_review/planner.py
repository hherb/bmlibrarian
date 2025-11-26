"""
Planner Component for SystematicReviewAgent

Provides LLM-based search strategy planning for systematic literature reviews.
Generates diverse search queries to ensure comprehensive coverage of the
research question.

Features:
- Multi-strategy query generation (semantic, keyword, hybrid, HyDE)
- PICO-based query decomposition for clinical questions
- Query variation generation using LLM
- Iteration support for expanding searches
- MeSH term extraction support
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple, TYPE_CHECKING

import ollama

from .data_models import (
    SearchCriteria,
    PlannedQuery,
    SearchPlan,
    QueryType,
    StudyTypeFilter,
)
from .config import (
    SystematicReviewConfig,
    get_systematic_review_config,
    DEFAULT_MAX_SEARCH_RESULTS,
)

if TYPE_CHECKING:
    from ...database import DatabaseManager

logger = logging.getLogger(__name__)


# =============================================================================
# Constants
# =============================================================================

# Query generation settings
DEFAULT_QUERY_VARIATIONS = 3
MIN_QUERIES_PER_PLAN = 2
MAX_QUERIES_PER_PLAN = 10
DEFAULT_ESTIMATED_YIELD_PER_QUERY = 100

# LLM prompts
QUERY_GENERATION_SYSTEM_PROMPT = """You are an expert biomedical literature search strategist.
Your task is to generate effective search queries for systematic literature reviews.

You understand:
- Medical terminology and MeSH terms
- Boolean query syntax (AND, OR, NOT)
- PostgreSQL to_tsquery format
- PICO framework (Population, Intervention, Comparison, Outcome)
- How to balance precision and recall in literature searches

Generate queries that are:
1. Specific enough to find relevant papers
2. Broad enough to not miss important papers
3. Use synonyms and related terms where appropriate
4. Consider both common and technical terminology
"""

PICO_EXTRACTION_PROMPT = """Analyze this research question and extract PICO components if applicable.

Research Question: {question}

If this is a clinical question, extract:
- Population: The patient group or condition being studied
- Intervention: The treatment, exposure, or action being evaluated
- Comparison: What the intervention is compared against (if any)
- Outcome: The health outcomes or endpoints measured

If not a clinical question, return "N/A" for all components.

Respond in JSON format:
{{
    "is_clinical": true/false,
    "population": "...",
    "intervention": "...",
    "comparison": "...",
    "outcome": "..."
}}"""

QUERY_VARIATION_PROMPT = """Generate {num_variations} search query variations for a systematic review.

Research Question: {question}
Purpose: {purpose}
Inclusion Criteria: {inclusion_criteria}
Exclusion Criteria: {exclusion_criteria}

Generate diverse queries that:
1. Use different phrasings of key concepts
2. Include relevant synonyms and related terms
3. Vary between specific and broader terms
4. Consider different perspectives on the research question

Return a JSON array of query objects:
[
    {{
        "query_text": "the search query",
        "query_type": "semantic|keyword|hybrid",
        "purpose": "what this query aims to find",
        "expected_coverage": "what aspect of the research question it addresses"
    }}
]

Return ONLY valid JSON, no other text."""


# =============================================================================
# Planner Class
# =============================================================================

@dataclass
class PICOComponents:
    """PICO components extracted from a research question."""

    is_clinical: bool = False
    population: str = ""
    intervention: str = ""
    comparison: str = ""
    outcome: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "is_clinical": self.is_clinical,
            "population": self.population,
            "intervention": self.intervention,
            "comparison": self.comparison,
            "outcome": self.outcome,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PICOComponents":
        """Create from dictionary."""
        return cls(
            is_clinical=data.get("is_clinical", False),
            population=data.get("population", ""),
            intervention=data.get("intervention", ""),
            comparison=data.get("comparison", ""),
            outcome=data.get("outcome", ""),
        )

    def generate_query_terms(self) -> List[str]:
        """
        Generate query terms from PICO components.

        Returns:
            List of query term strings derived from PICO components
        """
        terms = []
        if self.population:
            terms.append(self.population)
        if self.intervention:
            terms.append(self.intervention)
        if self.comparison:
            terms.append(self.comparison)
        if self.outcome:
            terms.append(self.outcome)
        return terms


class Planner:
    """
    LLM-based search strategy planning component.

    Generates diverse search queries for comprehensive systematic review coverage.
    Supports multiple query types (semantic, keyword, hybrid) and uses LLM
    to generate query variations.

    Attributes:
        model: Ollama model name for LLM operations
        host: Ollama server URL
        config: Full agent configuration
        temperature: LLM temperature for generation
        top_p: LLM top-p sampling parameter

    Example:
        >>> planner = Planner(model="gpt-oss:20b")
        >>> criteria = SearchCriteria(
        ...     research_question="Effect of statins on CVD prevention",
        ...     purpose="Clinical guideline review",
        ...     inclusion_criteria=["Human studies", "RCTs"],
        ...     exclusion_criteria=["Animal studies"]
        ... )
        >>> plan = planner.generate_search_plan(criteria)
        >>> print(f"Generated {len(plan.queries)} queries")
    """

    def __init__(
        self,
        model: Optional[str] = None,
        host: Optional[str] = None,
        config: Optional[SystematicReviewConfig] = None,
        temperature: float = 0.3,
        top_p: float = 0.9,
        callback: Optional[Callable[[str, str], None]] = None,
    ) -> None:
        """
        Initialize the Planner.

        Args:
            model: Ollama model name. If None, uses config default.
            host: Ollama server URL. If None, uses config default.
            config: Optional full configuration. If None, loads from config system.
            temperature: LLM temperature for generation (default: 0.3)
            top_p: LLM top-p sampling parameter (default: 0.9)
            callback: Optional callback for progress updates
        """
        self.config = config or get_systematic_review_config()
        self.model = model or self.config.model
        self.host = host or self.config.host
        self.temperature = temperature
        self.top_p = top_p
        self.callback = callback

        # Cache for PICO extraction
        self._pico_cache: Dict[str, PICOComponents] = {}

        logger.info(
            f"Planner initialized: model={self.model}, "
            f"temperature={self.temperature}"
        )

    def _call_callback(self, event: str, data: str) -> None:
        """Call progress callback if registered."""
        if self.callback:
            try:
                self.callback(event, data)
            except Exception as e:
                logger.warning(f"Callback error: {e}")

    # =========================================================================
    # Main Planning Methods
    # =========================================================================

    def generate_search_plan(
        self,
        criteria: SearchCriteria,
        num_query_variations: int = DEFAULT_QUERY_VARIATIONS,
        include_hyde: bool = True,
    ) -> SearchPlan:
        """
        Generate a comprehensive search plan.

        Creates diverse queries covering multiple search strategies to ensure
        comprehensive literature coverage.

        Args:
            criteria: Search criteria defining the review parameters
            num_query_variations: Number of query variations to generate per type
            include_hyde: Whether to include HyDE query type

        Returns:
            SearchPlan with all generated queries and rationale

        Raises:
            ValueError: If criteria validation fails
            ConnectionError: If unable to connect to Ollama
        """
        self._call_callback("planning_started", criteria.research_question)
        start_time = time.time()

        queries: List[PlannedQuery] = []

        # Step 1: Extract PICO components if applicable
        pico = self._extract_pico(criteria.research_question)

        # Step 2: Generate base semantic query from research question
        semantic_queries = self._generate_semantic_queries(
            criteria,
            pico,
            num_variations=num_query_variations
        )
        queries.extend(semantic_queries)

        # Step 3: Generate keyword queries
        keyword_queries = self._generate_keyword_queries(
            criteria,
            pico,
            num_variations=max(1, num_query_variations - 1)
        )
        queries.extend(keyword_queries)

        # Step 4: Generate hybrid queries
        hybrid_queries = self._generate_hybrid_queries(criteria, pico)
        queries.extend(hybrid_queries)

        # Step 5: Optionally generate HyDE query
        if include_hyde:
            hyde_query = self._generate_hyde_query(criteria)
            if hyde_query:
                queries.append(hyde_query)

        # Step 6: Generate LLM-based query variations
        try:
            llm_queries = self._generate_query_variations_llm(
                criteria,
                num_variations=num_query_variations
            )
            queries.extend(llm_queries)
        except Exception as e:
            logger.warning(f"LLM query variation failed: {e}")
            # Continue without LLM queries

        # Deduplicate queries by query_text
        queries = self._deduplicate_queries(queries)

        # Limit to max queries
        if len(queries) > MAX_QUERIES_PER_PLAN:
            # Prioritize by type diversity
            queries = self._prioritize_queries(queries, MAX_QUERIES_PER_PLAN)

        # Assign priorities
        for i, query in enumerate(queries):
            query.priority = i + 1

        # Estimate total yield
        total_yield = len(queries) * DEFAULT_ESTIMATED_YIELD_PER_QUERY

        # Generate rationale
        duration = time.time() - start_time
        rationale = self._generate_rationale(criteria, queries, pico, duration)

        # Build coverage analysis
        coverage = self._analyze_coverage(criteria, queries, pico)

        plan = SearchPlan(
            queries=queries,
            total_estimated_yield=total_yield,
            search_rationale=rationale,
            iteration=1,
            coverage_analysis=coverage,
        )

        self._call_callback(
            "planning_completed",
            f"Generated {len(queries)} queries in {duration:.2f}s"
        )

        logger.info(
            f"Search plan generated: {len(queries)} queries, "
            f"estimated yield={total_yield}"
        )

        return plan

    def generate_additional_queries(
        self,
        criteria: SearchCriteria,
        previous_plan: SearchPlan,
        target_additional: int = 3,
    ) -> SearchPlan:
        """
        Generate additional queries for search iteration.

        Used when initial search doesn't find enough results.

        Args:
            criteria: Original search criteria
            previous_plan: Previous search plan to expand upon
            target_additional: Number of additional queries to generate

        Returns:
            New SearchPlan with additional queries
        """
        self._call_callback("iteration_started", f"Iteration {previous_plan.iteration + 1}")

        # Get existing query texts to avoid duplicates
        existing_texts = {q.query_text.lower() for q in previous_plan.queries}

        new_queries: List[PlannedQuery] = []

        # Try broader variations
        try:
            broader_queries = self._generate_broader_queries(
                criteria,
                existing_texts,
                num_variations=target_additional
            )
            new_queries.extend(broader_queries)
        except Exception as e:
            logger.warning(f"Broader query generation failed: {e}")

        # Filter out duplicates
        new_queries = [
            q for q in new_queries
            if q.query_text.lower() not in existing_texts
        ]

        # Combine with previous queries
        all_queries = previous_plan.queries + new_queries

        # Update priorities
        for i, query in enumerate(all_queries):
            query.priority = i + 1

        plan = SearchPlan(
            queries=all_queries,
            total_estimated_yield=len(all_queries) * DEFAULT_ESTIMATED_YIELD_PER_QUERY,
            search_rationale=f"Extended search with {len(new_queries)} additional queries",
            iteration=previous_plan.iteration + 1,
            coverage_analysis=previous_plan.coverage_analysis,
        )

        self._call_callback(
            "iteration_completed",
            f"Added {len(new_queries)} queries"
        )

        return plan

    def should_iterate(
        self,
        current_results: int,
        target_minimum: int,
        iteration: int,
        max_iterations: int = 3,
    ) -> Tuple[bool, str]:
        """
        Decide if more search iterations are needed.

        Args:
            current_results: Number of results found so far
            target_minimum: Minimum results needed
            iteration: Current iteration number
            max_iterations: Maximum allowed iterations

        Returns:
            Tuple of (should_iterate, reason)
        """
        if current_results >= target_minimum:
            return False, f"Found {current_results} results, meeting target of {target_minimum}"

        if iteration >= max_iterations:
            return False, f"Reached maximum iterations ({max_iterations})"

        return True, f"Only {current_results}/{target_minimum} results, more queries needed"

    # =========================================================================
    # PICO Extraction
    # =========================================================================

    def _extract_pico(self, question: str) -> PICOComponents:
        """
        Extract PICO components from research question using LLM.

        Args:
            question: Research question to analyze

        Returns:
            PICOComponents with extracted elements
        """
        # Check cache
        cache_key = question.lower().strip()
        if cache_key in self._pico_cache:
            return self._pico_cache[cache_key]

        try:
            prompt = PICO_EXTRACTION_PROMPT.format(question=question)

            response = ollama.generate(
                model=self.model,
                prompt=prompt,
                options={
                    "temperature": 0.1,  # Low temperature for consistent extraction
                    "num_predict": 300,
                },
            )

            response_text = response.get("response", "").strip()

            # Parse JSON response
            # Find JSON object in response (handle markdown code blocks)
            if "```json" in response_text:
                start = response_text.find("```json") + 7
                end = response_text.find("```", start)
                response_text = response_text[start:end].strip()
            elif "```" in response_text:
                start = response_text.find("```") + 3
                end = response_text.find("```", start)
                response_text = response_text[start:end].strip()

            data = json.loads(response_text)
            pico = PICOComponents.from_dict(data)

            # Cache result
            self._pico_cache[cache_key] = pico

            logger.info(f"PICO extraction: is_clinical={pico.is_clinical}")
            return pico

        except (json.JSONDecodeError, KeyError) as e:
            logger.warning(f"PICO extraction failed to parse: {e}")
            return PICOComponents()
        except Exception as e:
            logger.warning(f"PICO extraction failed: {e}")
            return PICOComponents()

    # =========================================================================
    # Query Generation Methods
    # =========================================================================

    def _generate_semantic_queries(
        self,
        criteria: SearchCriteria,
        pico: PICOComponents,
        num_variations: int = 3,
    ) -> List[PlannedQuery]:
        """Generate semantic search queries."""
        queries = []

        # Primary semantic query from research question
        queries.append(PlannedQuery(
            query_id=f"semantic_{uuid.uuid4().hex[:8]}",
            query_text=criteria.research_question,
            query_type=QueryType.SEMANTIC,
            purpose="Primary semantic search using research question",
            expected_coverage="Broad semantic similarity to research question",
            priority=1,
            estimated_results=DEFAULT_ESTIMATED_YIELD_PER_QUERY,
        ))

        # PICO-based semantic queries
        if pico.is_clinical and pico.population:
            pico_query = " ".join(pico.generate_query_terms())
            if pico_query.strip():
                queries.append(PlannedQuery(
                    query_id=f"semantic_pico_{uuid.uuid4().hex[:8]}",
                    query_text=pico_query,
                    query_type=QueryType.SEMANTIC,
                    purpose="PICO-based semantic search",
                    expected_coverage="Clinical intervention studies matching PICO",
                    priority=2,
                    estimated_results=DEFAULT_ESTIMATED_YIELD_PER_QUERY,
                ))

        # Purpose-focused query
        if criteria.purpose:
            queries.append(PlannedQuery(
                query_id=f"semantic_purpose_{uuid.uuid4().hex[:8]}",
                query_text=f"{criteria.research_question} for {criteria.purpose}",
                query_type=QueryType.SEMANTIC,
                purpose="Purpose-contextualized semantic search",
                expected_coverage="Papers relevant to stated purpose",
                priority=3,
                estimated_results=DEFAULT_ESTIMATED_YIELD_PER_QUERY,
            ))

        return queries[:num_variations]

    def _generate_keyword_queries(
        self,
        criteria: SearchCriteria,
        pico: PICOComponents,
        num_variations: int = 2,
    ) -> List[PlannedQuery]:
        """Generate keyword search queries (PostgreSQL tsquery format)."""
        queries = []

        # Extract key terms from research question
        key_terms = self._extract_key_terms(criteria.research_question)

        if key_terms:
            # Primary keyword query
            keyword_query = " & ".join(key_terms[:5])  # Limit to 5 terms
            queries.append(PlannedQuery(
                query_id=f"keyword_{uuid.uuid4().hex[:8]}",
                query_text=keyword_query,
                query_type=QueryType.KEYWORD,
                purpose="Keyword search with key terms",
                expected_coverage="Documents containing all key terms",
                priority=4,
                estimated_results=DEFAULT_ESTIMATED_YIELD_PER_QUERY,
            ))

        # Custom search terms if provided
        if criteria.custom_search_terms:
            custom_query = " & ".join(criteria.custom_search_terms[:5])
            queries.append(PlannedQuery(
                query_id=f"keyword_custom_{uuid.uuid4().hex[:8]}",
                query_text=custom_query,
                query_type=QueryType.KEYWORD,
                purpose="User-specified custom search terms",
                expected_coverage="Documents matching custom terms",
                priority=5,
                estimated_results=DEFAULT_ESTIMATED_YIELD_PER_QUERY,
            ))

        # MeSH terms if provided
        if criteria.mesh_terms:
            mesh_query = " | ".join(criteria.mesh_terms)
            queries.append(PlannedQuery(
                query_id=f"keyword_mesh_{uuid.uuid4().hex[:8]}",
                query_text=mesh_query,
                query_type=QueryType.KEYWORD,
                purpose="MeSH term search",
                expected_coverage="Documents indexed with specified MeSH terms",
                priority=6,
                estimated_results=DEFAULT_ESTIMATED_YIELD_PER_QUERY,
            ))

        return queries[:num_variations]

    def _generate_hybrid_queries(
        self,
        criteria: SearchCriteria,
        pico: PICOComponents,
    ) -> List[PlannedQuery]:
        """Generate hybrid search queries (semantic + keyword combined)."""
        queries = []

        # Create hybrid query combining semantic and keyword elements
        queries.append(PlannedQuery(
            query_id=f"hybrid_{uuid.uuid4().hex[:8]}",
            query_text=criteria.research_question,
            query_type=QueryType.HYBRID,
            purpose="Hybrid semantic-keyword search",
            expected_coverage="Combined semantic and keyword matching",
            priority=7,
            estimated_results=DEFAULT_ESTIMATED_YIELD_PER_QUERY,
        ))

        return queries

    def _generate_hyde_query(
        self,
        criteria: SearchCriteria,
    ) -> Optional[PlannedQuery]:
        """Generate a HyDE (Hypothetical Document Embeddings) query."""
        return PlannedQuery(
            query_id=f"hyde_{uuid.uuid4().hex[:8]}",
            query_text=criteria.research_question,
            query_type=QueryType.HYDE,
            purpose="HyDE search using hypothetical document generation",
            expected_coverage="Semantically similar papers to hypothetical abstracts",
            priority=8,
            estimated_results=DEFAULT_ESTIMATED_YIELD_PER_QUERY,
        )

    def _generate_query_variations_llm(
        self,
        criteria: SearchCriteria,
        num_variations: int = 3,
    ) -> List[PlannedQuery]:
        """
        Generate query variations using LLM.

        Args:
            criteria: Search criteria
            num_variations: Number of variations to generate

        Returns:
            List of PlannedQuery objects
        """
        prompt = QUERY_VARIATION_PROMPT.format(
            num_variations=num_variations,
            question=criteria.research_question,
            purpose=criteria.purpose,
            inclusion_criteria=", ".join(criteria.inclusion_criteria),
            exclusion_criteria=", ".join(criteria.exclusion_criteria) if criteria.exclusion_criteria else "None",
        )

        try:
            response = ollama.generate(
                model=self.model,
                prompt=prompt,
                system=QUERY_GENERATION_SYSTEM_PROMPT,
                options={
                    "temperature": self.temperature,
                    "top_p": self.top_p,
                    "num_predict": 1000,
                },
            )

            response_text = response.get("response", "").strip()

            # Parse JSON response
            # Handle markdown code blocks
            if "```json" in response_text:
                start = response_text.find("```json") + 7
                end = response_text.find("```", start)
                response_text = response_text[start:end].strip()
            elif "```" in response_text:
                start = response_text.find("```") + 3
                end = response_text.find("```", start)
                response_text = response_text[start:end].strip()

            query_data = json.loads(response_text)

            queries = []
            for i, qd in enumerate(query_data[:num_variations]):
                query_type_str = qd.get("query_type", "semantic").lower()
                if query_type_str == "keyword":
                    query_type = QueryType.KEYWORD
                elif query_type_str == "hybrid":
                    query_type = QueryType.HYBRID
                else:
                    query_type = QueryType.SEMANTIC

                queries.append(PlannedQuery(
                    query_id=f"llm_{uuid.uuid4().hex[:8]}",
                    query_text=qd.get("query_text", ""),
                    query_type=query_type,
                    purpose=qd.get("purpose", "LLM-generated query variation"),
                    expected_coverage=qd.get("expected_coverage", "Varied coverage"),
                    priority=10 + i,
                    estimated_results=DEFAULT_ESTIMATED_YIELD_PER_QUERY,
                ))

            return queries

        except (json.JSONDecodeError, KeyError) as e:
            logger.warning(f"Failed to parse LLM query variations: {e}")
            return []
        except Exception as e:
            logger.error(f"LLM query variation failed: {e}")
            return []

    def _generate_broader_queries(
        self,
        criteria: SearchCriteria,
        existing_texts: set,
        num_variations: int = 3,
    ) -> List[PlannedQuery]:
        """
        Generate broader queries for search iteration.

        Used when initial queries don't find enough results.
        """
        queries = []

        # Try removing specific terms to broaden
        key_terms = self._extract_key_terms(criteria.research_question)

        # Generate queries with fewer terms
        if len(key_terms) >= 3:
            # Use just core terms (first 2-3)
            core_query = " & ".join(key_terms[:2])
            if core_query.lower() not in existing_texts:
                queries.append(PlannedQuery(
                    query_id=f"broad_keyword_{uuid.uuid4().hex[:8]}",
                    query_text=core_query,
                    query_type=QueryType.KEYWORD,
                    purpose="Broader keyword search with core terms only",
                    expected_coverage="Documents with core concepts",
                    priority=15,
                    estimated_results=DEFAULT_ESTIMATED_YIELD_PER_QUERY * 2,
                ))

            # Use OR instead of AND
            or_query = " | ".join(key_terms[:4])
            if or_query.lower() not in existing_texts:
                queries.append(PlannedQuery(
                    query_id=f"broad_or_{uuid.uuid4().hex[:8]}",
                    query_text=or_query,
                    query_type=QueryType.KEYWORD,
                    purpose="Broader search using OR operator",
                    expected_coverage="Documents with any of the key terms",
                    priority=16,
                    estimated_results=DEFAULT_ESTIMATED_YIELD_PER_QUERY * 3,
                ))

        return queries[:num_variations]

    # =========================================================================
    # Helper Methods
    # =========================================================================

    def _extract_key_terms(self, text: str) -> List[str]:
        """
        Extract key biomedical terms from text.

        Simple extraction based on word patterns. Could be enhanced with
        NLP or thesaurus lookup.

        Args:
            text: Text to extract terms from

        Returns:
            List of key terms
        """
        import re

        # Common stop words to filter
        stop_words = {
            'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been',
            'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will',
            'would', 'could', 'should', 'may', 'might', 'must', 'shall',
            'can', 'need', 'what', 'which', 'who', 'whom', 'this', 'that',
            'these', 'those', 'am', 'of', 'in', 'for', 'on', 'with', 'at',
            'by', 'from', 'up', 'about', 'into', 'through', 'during',
            'before', 'after', 'above', 'below', 'to', 'and', 'but', 'or',
            'nor', 'not', 'only', 'own', 'same', 'so', 'than', 'too', 'very',
            'just', 'how', 'when', 'where', 'why', 'effect', 'effects',
            'study', 'studies', 'research', 'evidence',
        }

        # Extract words
        words = re.findall(r'\b[a-zA-Z][a-zA-Z0-9\-]{2,}\b', text.lower())

        # Filter stop words and short words
        terms = [w for w in words if w not in stop_words and len(w) > 2]

        # Deduplicate while preserving order
        seen = set()
        unique_terms = []
        for term in terms:
            if term not in seen:
                seen.add(term)
                unique_terms.append(term)

        return unique_terms

    def _deduplicate_queries(
        self,
        queries: List[PlannedQuery]
    ) -> List[PlannedQuery]:
        """Remove duplicate queries based on normalized query text."""
        seen_texts = set()
        unique_queries = []

        for query in queries:
            normalized = query.query_text.lower().strip()
            if normalized and normalized not in seen_texts:
                seen_texts.add(normalized)
                unique_queries.append(query)

        return unique_queries

    def _prioritize_queries(
        self,
        queries: List[PlannedQuery],
        max_queries: int,
    ) -> List[PlannedQuery]:
        """
        Prioritize queries ensuring type diversity.

        Keeps at least one query of each type if possible.
        """
        # Group by type
        by_type: Dict[QueryType, List[PlannedQuery]] = {}
        for query in queries:
            if query.query_type not in by_type:
                by_type[query.query_type] = []
            by_type[query.query_type].append(query)

        prioritized = []

        # Take one from each type first
        for query_type in [
            QueryType.SEMANTIC,
            QueryType.KEYWORD,
            QueryType.HYBRID,
            QueryType.HYDE,
        ]:
            if query_type in by_type and by_type[query_type]:
                prioritized.append(by_type[query_type].pop(0))

        # Fill remaining slots
        remaining = []
        for type_queries in by_type.values():
            remaining.extend(type_queries)

        for query in remaining:
            if len(prioritized) >= max_queries:
                break
            prioritized.append(query)

        return prioritized

    def _generate_rationale(
        self,
        criteria: SearchCriteria,
        queries: List[PlannedQuery],
        pico: PICOComponents,
        duration: float,
    ) -> str:
        """Generate human-readable rationale for the search plan."""
        query_types = set(q.query_type.value for q in queries)

        rationale_parts = [
            f"Generated {len(queries)} search queries in {duration:.2f} seconds.",
            f"Query types used: {', '.join(sorted(query_types))}.",
        ]

        if pico.is_clinical:
            rationale_parts.append(
                f"Clinical question detected - PICO-based queries included."
            )

        if criteria.custom_search_terms:
            rationale_parts.append(
                f"User-specified search terms incorporated: {', '.join(criteria.custom_search_terms[:3])}..."
            )

        if criteria.mesh_terms:
            rationale_parts.append(
                f"MeSH terms included: {', '.join(criteria.mesh_terms[:3])}..."
            )

        return " ".join(rationale_parts)

    def _analyze_coverage(
        self,
        criteria: SearchCriteria,
        queries: List[PlannedQuery],
        pico: PICOComponents,
    ) -> str:
        """Analyze how well queries cover the research question."""
        coverage_items = []

        # Check query type coverage
        types = set(q.query_type for q in queries)
        if QueryType.SEMANTIC in types:
            coverage_items.append("Semantic similarity matching")
        if QueryType.KEYWORD in types:
            coverage_items.append("Keyword term matching")
        if QueryType.HYBRID in types:
            coverage_items.append("Hybrid search (semantic + keyword)")
        if QueryType.HYDE in types:
            coverage_items.append("HyDE hypothetical document search")

        # Check PICO coverage
        if pico.is_clinical:
            coverage_items.append(f"PICO components: P={pico.population[:20]}...")

        return "; ".join(coverage_items)
