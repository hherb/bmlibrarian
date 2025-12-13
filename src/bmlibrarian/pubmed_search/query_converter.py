"""
Natural language to PubMed query converter.

This module uses LLM to convert natural language research questions into
optimized PubMed queries with MeSH terms, field tags, and boolean operators.

Example usage:
    from bmlibrarian.pubmed_search import QueryConverter

    converter = QueryConverter()

    # Convert a research question
    result = converter.convert(
        "What are the cardiovascular benefits of exercise in elderly patients?"
    )

    print(result.primary_query.query_string)
    # Output: (("Exercise"[MeSH] OR "Physical Activity"[MeSH]) AND
    #          ("Cardiovascular Diseases"[MeSH] OR cardiovascular[tiab]) AND
    #          ("Aged"[MeSH] OR elderly[tiab]))
"""

import json
import logging
import re
from typing import Optional, List, Dict, Any, Callable

from bmlibrarian.llm import LLMClient, LLMMessage, get_llm_client

from .constants import (
    DEFAULT_QUERY_MODEL,
    DEFAULT_TEMPERATURE,
    DEFAULT_TOP_P,
    DEFAULT_MAX_TOKENS,
    PUBLICATION_TYPE_FILTERS,
    SUBSET_FILTERS,
)
from .data_types import (
    PubMedQuery,
    QueryConcept,
    QueryConversionResult,
    PublicationType,
    DateRange,
)
from .mesh_lookup import MeSHLookup

logger = logging.getLogger(__name__)


# Prompt template for query conversion
QUERY_CONVERSION_PROMPT = """You are a biomedical information specialist expert at PubMed searching.
Convert the following research question into an optimized PubMed query.

Research Question: {question}

Instructions:
1. Identify the key biomedical concepts (use PICO framework if applicable: Population, Intervention, Comparison, Outcome)
2. For each concept, provide:
   - Primary MeSH term(s) - use exact official MeSH vocabulary
   - Alternative/narrower MeSH terms for better coverage
   - Free-text keywords for title/abstract search [tiab]
   - Synonyms and alternative spellings
3. Structure the query with:
   - OR between synonyms and alternatives within a concept
   - AND between different concepts
   - Proper parentheses for grouping
4. Consider adding appropriate filters if the question suggests them:
   - Publication types: Clinical Trial, Meta-Analysis, Systematic Review, RCT
   - Date ranges if topic is time-sensitive
   - Humans filter for clinical questions
   - Language filters if relevant

IMPORTANT: Output ONLY valid JSON, no other text. Use this exact format:
{{
  "concepts": [
    {{
      "name": "concept name describing what this represents",
      "mesh_terms": ["Primary MeSH Term", "Alternative MeSH Term"],
      "keywords": ["keyword1", "keyword2", "multi-word phrase"],
      "synonyms": ["alternative spelling", "abbreviation"],
      "pico_role": "population|intervention|comparison|outcome|null"
    }}
  ],
  "suggested_filters": {{
    "publication_types": ["Clinical Trial", "Meta-Analysis"],
    "date_range": {{"start_year": 2020, "end_year": null}},
    "humans_only": true,
    "has_abstract": true,
    "language": "english"
  }},
  "confidence": 0.85,
  "notes": "Brief explanation of query strategy"
}}

Guidelines for MeSH terms:
- Use official MeSH descriptor names (e.g., "Cardiovascular Diseases" not "Heart Disease")
- Include both broad and specific terms for comprehensive coverage
- Common MeSH terms include: "Humans", "Aged", "Diabetes Mellitus", "Hypertension", "Neoplasms"

Generate the JSON response for converting the research question to a PubMed query:"""


KEYWORD_EXPANSION_PROMPT = """You are a biomedical terminology expert.
Given the following concept and its current terms, suggest additional synonyms,
abbreviations, and alternative phrasings that would help find more relevant articles.

Concept: {concept_name}
Current MeSH terms: {mesh_terms}
Current keywords: {keywords}

Provide additional terms that researchers might use when writing about this topic.
Consider:
- Common abbreviations (e.g., CVD for cardiovascular disease)
- British vs American spellings
- Lay terms vs technical terms
- Historical terminology changes

Output JSON only:
{{
  "additional_keywords": ["term1", "term2"],
  "additional_synonyms": ["synonym1", "synonym2"],
  "notes": "brief explanation"
}}"""


class QueryConverter:
    """
    Converts natural language research questions to PubMed queries.

    Uses LLM to extract biomedical concepts, map to MeSH terms, and
    construct optimized PubMed search queries with proper boolean
    operators and field tags.
    """

    def __init__(
        self,
        model: Optional[str] = None,
        llm_client: Optional[LLMClient] = None,
        mesh_lookup: Optional[MeSHLookup] = None,
        temperature: float = DEFAULT_TEMPERATURE,
        top_p: float = DEFAULT_TOP_P,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        validate_mesh: bool = True,
        expand_keywords: bool = True,
    ) -> None:
        """
        Initialize the query converter.

        Args:
            model: LLM model to use for conversion
            llm_client: Optional pre-configured LLM client
            mesh_lookup: Optional pre-configured MeSH lookup service
            temperature: LLM temperature for generation
            top_p: LLM top-p for generation
            max_tokens: Maximum tokens for LLM response
            validate_mesh: Whether to validate MeSH terms against official vocabulary
            expand_keywords: Whether to expand keywords with additional synonyms
        """
        self.model = model or self._get_default_model()
        self.llm_client = llm_client or get_llm_client()
        self.mesh_lookup = mesh_lookup or MeSHLookup()
        self.temperature = temperature
        self.top_p = top_p
        self.max_tokens = max_tokens
        self.validate_mesh = validate_mesh
        self.expand_keywords = expand_keywords

        logger.info(f"QueryConverter initialized with model: {self.model}")

    def _get_default_model(self) -> str:
        """Get the default model from configuration."""
        try:
            from bmlibrarian.config import get_model
            return get_model("pubmed_search", DEFAULT_QUERY_MODEL)
        except ImportError:
            return DEFAULT_QUERY_MODEL

    def convert(
        self,
        question: str,
        publication_types: Optional[List[PublicationType]] = None,
        date_range: Optional[DateRange] = None,
        humans_only: bool = False,
        has_abstract: bool = False,
        free_full_text: bool = False,
        language: Optional[str] = None,
        progress_callback: Optional[Callable[[str, str], None]] = None,
    ) -> QueryConversionResult:
        """
        Convert a natural language question to a PubMed query.

        Args:
            question: Natural language research question
            publication_types: Filter by publication type(s)
            date_range: Filter by date range
            humans_only: Filter to human studies only
            has_abstract: Filter to articles with abstracts
            free_full_text: Filter to free full text only
            language: Filter by language
            progress_callback: Optional callback(step, message) for progress updates

        Returns:
            QueryConversionResult with primary query and alternatives
        """
        if not question or not question.strip():
            raise ValueError("Question cannot be empty")

        def report_progress(step: str, message: str) -> None:
            logger.info(f"[{step}] {message}")
            if progress_callback:
                progress_callback(step, message)

        report_progress("init", f"Converting question to PubMed query")

        # Step 1: Extract concepts using LLM
        report_progress("extract", "Extracting biomedical concepts...")
        llm_result = self._extract_concepts_llm(question)

        if llm_result is None:
            logger.error("LLM failed to extract concepts")
            # Fallback: create simple query
            return self._create_fallback_result(question, publication_types, date_range)

        # Step 2: Parse LLM response
        report_progress("parse", "Parsing concept extraction...")
        concepts, suggested_filters, confidence, notes, raw_response = llm_result

        # Step 3: Validate MeSH terms
        mesh_terms_found = []
        mesh_terms_validated = []
        mesh_terms_invalid = []

        if self.validate_mesh:
            report_progress("validate", "Validating MeSH terms...")
            for concept in concepts:
                for term in concept.mesh_terms:
                    mesh_terms_found.append(term)
                    validation = self.mesh_lookup.validate_term(term)
                    if validation.is_valid:
                        mesh_terms_validated.append(term)
                    else:
                        mesh_terms_invalid.append(term)
                        logger.warning(f"Invalid MeSH term: {term}")

        # Step 4: Expand keywords if enabled
        if self.expand_keywords:
            report_progress("expand", "Expanding keywords...")
            concepts = self._expand_concept_keywords(concepts)

        # Step 5: Build the query string
        report_progress("build", "Building PubMed query string...")

        # Apply user-specified filters or use LLM suggestions
        effective_pub_types = publication_types
        effective_date_range = date_range
        effective_humans = humans_only
        effective_abstract = has_abstract
        effective_language = language

        if suggested_filters:
            if effective_pub_types is None and suggested_filters.get("publication_types"):
                effective_pub_types = self._parse_publication_types(
                    suggested_filters["publication_types"]
                )
            if effective_date_range is None and suggested_filters.get("date_range"):
                effective_date_range = self._parse_date_range(
                    suggested_filters["date_range"]
                )
            if not effective_humans and suggested_filters.get("humans_only"):
                effective_humans = True
            if not effective_abstract and suggested_filters.get("has_abstract"):
                effective_abstract = True
            if not effective_language and suggested_filters.get("language"):
                effective_language = suggested_filters["language"]

        query_string = self._build_query_string(
            concepts=concepts,
            publication_types=effective_pub_types,
            humans_only=effective_humans,
            has_abstract=effective_abstract,
            free_full_text=free_full_text,
            language=effective_language,
        )

        # Create primary query
        primary_query = PubMedQuery(
            original_question=question,
            query_string=query_string,
            concepts=concepts,
            publication_types=effective_pub_types or [],
            date_range=effective_date_range,
            humans_only=effective_humans,
            has_abstract=effective_abstract,
            free_full_text=free_full_text,
            language=effective_language,
            generation_model=self.model,
            confidence_score=confidence,
        )

        # Generate warnings
        warnings = []
        if mesh_terms_invalid:
            warnings.append(
                f"Some MeSH terms could not be validated: {', '.join(mesh_terms_invalid)}"
            )
        if confidence and confidence < 0.7:
            warnings.append(
                f"Low confidence in query conversion ({confidence:.0%}). "
                "Consider reviewing the generated query."
            )

        report_progress("complete", "Query conversion complete")

        return QueryConversionResult(
            primary_query=primary_query,
            alternative_queries=[],  # Could generate alternatives in future
            mesh_terms_found=mesh_terms_found,
            mesh_terms_validated=mesh_terms_validated,
            mesh_terms_invalid=mesh_terms_invalid,
            concepts_extracted=concepts,
            warnings=warnings,
            llm_response_raw=raw_response,
        )

    def _extract_concepts_llm(
        self,
        question: str,
    ) -> Optional[tuple[List[QueryConcept], Dict[str, Any], float, str, str]]:
        """
        Extract biomedical concepts from question using LLM.

        Args:
            question: Research question

        Returns:
            Tuple of (concepts, suggested_filters, confidence, notes, raw_response)
            or None if extraction failed
        """
        prompt = QUERY_CONVERSION_PROMPT.format(question=question)

        try:
            response = self.llm_client.chat(
                messages=[LLMMessage(role="user", content=prompt)],
                model=self.model,
                temperature=self.temperature,
                top_p=self.top_p,
                max_tokens=self.max_tokens,
                json_mode=True,
            )

            raw_response = response.content
            logger.debug(f"LLM response: {raw_response[:500]}...")

            # Parse JSON response
            data = self._parse_llm_json(raw_response)
            if data is None:
                return None

            # Extract concepts
            concepts = []
            for concept_data in data.get("concepts", []):
                concept = QueryConcept(
                    name=concept_data.get("name", ""),
                    mesh_terms=concept_data.get("mesh_terms", []),
                    keywords=concept_data.get("keywords", []),
                    synonyms=concept_data.get("synonyms", []),
                    pico_role=concept_data.get("pico_role"),
                    is_pico_component=concept_data.get("pico_role") is not None,
                )
                concepts.append(concept)

            suggested_filters = data.get("suggested_filters", {})
            confidence = data.get("confidence", 0.5)
            notes = data.get("notes", "")

            return concepts, suggested_filters, confidence, notes, raw_response

        except Exception as e:
            logger.error(f"LLM concept extraction failed: {e}")
            return None

    def _parse_llm_json(self, response: str) -> Optional[Dict[str, Any]]:
        """
        Parse JSON from LLM response, handling common issues.

        Args:
            response: Raw LLM response

        Returns:
            Parsed JSON dictionary or None
        """
        # Try direct parsing
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            pass

        # Try to extract JSON from markdown code blocks
        json_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", response, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass

        # Try to find JSON object in response
        brace_match = re.search(r"\{.*\}", response, re.DOTALL)
        if brace_match:
            try:
                return json.loads(brace_match.group(0))
            except json.JSONDecodeError:
                pass

        logger.error(f"Could not parse JSON from LLM response: {response[:200]}...")
        return None

    def _expand_concept_keywords(
        self,
        concepts: List[QueryConcept],
    ) -> List[QueryConcept]:
        """
        Expand keywords for each concept using LLM.

        Args:
            concepts: List of query concepts

        Returns:
            Concepts with expanded keywords
        """
        expanded_concepts = []

        for concept in concepts:
            try:
                prompt = KEYWORD_EXPANSION_PROMPT.format(
                    concept_name=concept.name,
                    mesh_terms=", ".join(concept.mesh_terms),
                    keywords=", ".join(concept.keywords),
                )

                response = self.llm_client.chat(
                    messages=[LLMMessage(role="user", content=prompt)],
                    model=self.model,
                    temperature=self.temperature,
                    top_p=self.top_p,
                    max_tokens=500,
                    json_mode=True,
                )

                data = self._parse_llm_json(response.content)
                if data:
                    additional_keywords = data.get("additional_keywords", [])
                    additional_synonyms = data.get("additional_synonyms", [])

                    # Create new concept with expanded terms
                    expanded = QueryConcept(
                        name=concept.name,
                        mesh_terms=concept.mesh_terms,
                        keywords=list(set(concept.keywords + additional_keywords)),
                        synonyms=list(set(concept.synonyms + additional_synonyms)),
                        pico_role=concept.pico_role,
                        is_pico_component=concept.is_pico_component,
                    )
                    expanded_concepts.append(expanded)
                else:
                    expanded_concepts.append(concept)

            except Exception as e:
                logger.warning(f"Keyword expansion failed for {concept.name}: {e}")
                expanded_concepts.append(concept)

        return expanded_concepts

    def _build_query_string(
        self,
        concepts: List[QueryConcept],
        publication_types: Optional[List[PublicationType]] = None,
        humans_only: bool = False,
        has_abstract: bool = False,
        free_full_text: bool = False,
        language: Optional[str] = None,
    ) -> str:
        """
        Build the final PubMed query string from concepts and filters.

        Args:
            concepts: List of query concepts
            publication_types: Publication type filters
            humans_only: Include humans filter
            has_abstract: Include has abstract filter
            free_full_text: Include free full text filter
            language: Language filter

        Returns:
            Formatted PubMed query string
        """
        # Build concept clauses
        concept_clauses = []
        for concept in concepts:
            clause = concept.to_pubmed_clause(mesh_explosion=True)
            if clause:
                concept_clauses.append(clause)

        if not concept_clauses:
            return ""

        # Combine concepts with AND
        query_parts = ["(" + " AND ".join(concept_clauses) + ")"]

        # Add filters
        filter_parts = []

        if publication_types:
            type_clauses = [pt.to_pubmed_filter() for pt in publication_types]
            if type_clauses:
                filter_parts.append("(" + " OR ".join(type_clauses) + ")")

        if humans_only:
            filter_parts.append(SUBSET_FILTERS["humans"])

        if has_abstract:
            filter_parts.append(SUBSET_FILTERS["has_abstract"])

        if free_full_text:
            filter_parts.append(SUBSET_FILTERS["free_full_text"])

        if language:
            filter_parts.append(f"{language}[la]")

        # Combine main query with filters using AND
        if filter_parts:
            query_parts.extend(filter_parts)

        return " AND ".join(query_parts)

    def _parse_publication_types(
        self,
        type_strings: List[str],
    ) -> List[PublicationType]:
        """Parse publication type strings to enum values."""
        result = []
        for type_str in type_strings:
            normalized = type_str.lower().replace(" ", "_").replace("-", "_")
            for pt in PublicationType:
                if normalized in pt.name.lower() or normalized in pt.value.lower():
                    result.append(pt)
                    break
        return result

    def _parse_date_range(
        self,
        date_data: Dict[str, Any],
    ) -> Optional[DateRange]:
        """Parse date range from LLM suggested filters."""
        from datetime import date

        start_year = date_data.get("start_year")
        end_year = date_data.get("end_year")

        start_date = None
        end_date = None

        if start_year:
            try:
                start_date = date(int(start_year), 1, 1)
            except (ValueError, TypeError):
                pass

        if end_year:
            try:
                end_date = date(int(end_year), 12, 31)
            except (ValueError, TypeError):
                pass

        if start_date or end_date:
            return DateRange(start_date=start_date, end_date=end_date)

        return None

    def _create_fallback_result(
        self,
        question: str,
        publication_types: Optional[List[PublicationType]] = None,
        date_range: Optional[DateRange] = None,
    ) -> QueryConversionResult:
        """
        Create a simple fallback query when LLM extraction fails.

        Uses basic keyword extraction from the question.

        Args:
            question: Original research question
            publication_types: Optional publication type filters
            date_range: Optional date range filter

        Returns:
            QueryConversionResult with simple keyword-based query
        """
        # Extract simple keywords (remove common stop words)
        stop_words = {
            "the", "a", "an", "is", "are", "was", "were", "be", "been",
            "being", "have", "has", "had", "do", "does", "did", "will",
            "would", "could", "should", "may", "might", "must", "shall",
            "can", "need", "dare", "ought", "used", "to", "of", "in",
            "for", "on", "with", "at", "by", "from", "as", "into", "through",
            "during", "before", "after", "above", "below", "between", "under",
            "again", "further", "then", "once", "here", "there", "when",
            "where", "why", "how", "all", "each", "few", "more", "most",
            "other", "some", "such", "no", "nor", "not", "only", "own",
            "same", "so", "than", "too", "very", "what", "which", "who",
        }

        words = re.findall(r'\b[a-zA-Z]{3,}\b', question.lower())
        keywords = [w for w in words if w not in stop_words][:10]

        # Build simple query
        keyword_clauses = [f"{kw}[tiab]" for kw in keywords]
        query_string = " AND ".join(keyword_clauses) if keyword_clauses else question

        # Create concept
        concept = QueryConcept(
            name="Keywords from question",
            keywords=keywords,
        )

        primary_query = PubMedQuery(
            original_question=question,
            query_string=query_string,
            concepts=[concept],
            publication_types=publication_types or [],
            date_range=date_range,
            generation_model="fallback",
            confidence_score=0.3,
        )

        return QueryConversionResult(
            primary_query=primary_query,
            warnings=["LLM extraction failed. Using basic keyword matching as fallback."],
        )

    def get_query_preview(self, question: str) -> str:
        """
        Get a preview of the query that would be generated.

        Quick method that shows the query without full processing.

        Args:
            question: Research question

        Returns:
            Preview of the PubMed query string
        """
        result = self.convert(question)
        return result.primary_query.query_string
