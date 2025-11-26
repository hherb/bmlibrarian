"""
Reporting Agent for synthesizing citations into cohesive medical publication-style reports.

Takes extracted citations and generates evidence-based reports with proper
reference formatting in the style of peer-reviewed medical publications.
"""

import json
import logging
from typing import Dict, List, Optional, Any, Tuple, Callable
from dataclasses import dataclass
from datetime import datetime, timezone
import psycopg

from .base import BaseAgent
from .citation_agent import Citation

logger = logging.getLogger(__name__)


@dataclass
class MethodologyMetadata:
    """Metadata about the research methodology and workflow."""
    # Original query information
    human_question: str
    generated_query: str

    # Initial search results
    total_documents_found: int

    # Document scoring information
    scoring_threshold: float
    documents_by_score: Dict[int, int]  # score -> count mapping
    documents_above_threshold: int

    # Citation extraction details
    documents_processed_for_citations: int
    citation_extraction_threshold: float

    # Counterfactual analysis (optional)
    counterfactual_performed: bool = False
    counterfactual_queries_generated: int = 0
    counterfactual_documents_found: int = 0
    counterfactual_citations_extracted: int = 0

    # Processing details
    iterative_processing_used: bool = True
    context_window_management: bool = True

    # Search strategy information (NEW)
    search_strategies_used: Optional[List[str]] = None  # ['semantic', 'bm25', 'fulltext']
    semantic_search_params: Optional[Dict[str, Any]] = None  # {model, threshold, max_results, documents_found}
    bm25_search_params: Optional[Dict[str, Any]] = None  # {k1, b, max_results, query_expression, documents_found}
    fulltext_search_params: Optional[Dict[str, Any]] = None  # {query_expression, max_results, documents_found}

    # AI Model Audit Trail
    query_model: Optional[str] = None
    scoring_model: Optional[str] = None
    citation_model: Optional[str] = None
    reporting_model: Optional[str] = None
    counterfactual_model: Optional[str] = None
    editor_model: Optional[str] = None

    # Model parameters (optional, for transparency)
    model_temperature: Optional[float] = None
    model_top_p: Optional[float] = None


@dataclass
class Reference:
    """Represents a formatted reference for a report."""
    number: int
    authors: List[str]
    title: str
    publication_date: str
    document_id: str
    pmid: Optional[str] = None
    doi: Optional[str] = None
    publication: Optional[str] = None
    
    def format_vancouver_style(self, include_identifiers: bool = True) -> str:
        """Format reference in Vancouver style for medical publications.

        Args:
            include_identifiers: If True, includes PMID and DOI in the formatted string.
                                If False, excludes them (useful when displaying separately).

        Returns:
            Formatted Vancouver-style citation string
        """
        # Format authors (up to 6, then et al.)
        if len(self.authors) <= 6:
            author_str = ", ".join(self.authors)
        else:
            author_str = ", ".join(self.authors[:6]) + ", et al."

        # Format publication year
        # Handle both string and datetime.date objects
        if hasattr(self.publication_date, 'year'):
            # It's a datetime.date object
            year = str(self.publication_date.year)
        elif isinstance(self.publication_date, str):
            # It's a string - extract year
            year = self.publication_date.split('-')[0] if '-' in self.publication_date else self.publication_date
        else:
            # Fallback to string representation
            year = str(self.publication_date)

        # Start with author and title
        formatted = f"{author_str}. {self.title}."

        # Add journal/publication if available
        if self.publication and self.publication.strip() and self.publication.lower() != 'unknown':
            formatted += f" {self.publication}."

        # Add year
        formatted += f" {year}."

        # Add identifiers if requested
        if include_identifiers:
            identifiers = []
            if self.pmid:
                identifiers.append(f"PMID: {self.pmid}")
            if self.doi:
                identifiers.append(f"DOI: {self.doi}")

            if identifiers:
                formatted += f" {'; '.join(identifiers)}."

        return formatted


@dataclass
class Report:
    """Represents a synthesized report with citations and references."""
    user_question: str
    synthesized_answer: str
    references: List[Reference]
    evidence_strength: str  # "Strong", "Moderate", "Limited", "Insufficient"
    methodology_note: str
    created_at: datetime
    citation_count: int
    unique_documents: int
    methodology_metadata: Optional[MethodologyMetadata] = None
    
    def __post_init__(self):
        if not isinstance(self.created_at, datetime):
            self.created_at = datetime.now(timezone.utc)


class ReportingAgent(BaseAgent):
    """
    Agent for synthesizing citations into cohesive medical publication-style reports.
    
    Takes output from CitationFinderAgent and creates evidence-based reports
    with proper reference formatting and medical publication style.
    """
    
    def __init__(self,
                 model: str = "gpt-oss:20b",
                 host: str = "http://localhost:11434",
                 temperature: float = 0.3,
                 top_p: float = 0.9,
                 callback: Optional[Callable[[str, str], None]] = None,
                 orchestrator=None,
                 show_model_info: bool = True,
                 audit_conn: Optional[psycopg.Connection] = None):
        """
        Initialize the ReportingAgent.

        Args:
            model: The name of the Ollama model to use (default: gpt-oss:20b)
            host: The Ollama server host URL (default: http://localhost:11434)
            temperature: Model temperature for natural writing (default: 0.3)
            top_p: Model top-p sampling parameter (default: 0.9)
            callback: Optional callback function for progress updates
            orchestrator: Optional orchestrator for queue-based processing
            show_model_info: Whether to display model information on initialization
            audit_conn: Optional PostgreSQL connection for audit tracking
        """
        super().__init__(model=model, host=host, temperature=temperature, top_p=top_p,
                        callback=callback, orchestrator=orchestrator, show_model_info=show_model_info)
        self.agent_type = "reporting_agent"

        # Load map-reduce configuration from config system
        self._load_map_reduce_config()

        # Initialize audit tracking components if connection provided
        self._report_tracker = None

        if audit_conn:
            from bmlibrarian.audit import ReportTracker
            self._report_tracker = ReportTracker(audit_conn)
            logger.info("ReportingAgent initialized with audit tracking")
    
    def get_agent_type(self) -> str:
        """Get the agent type identifier."""
        return "reporting_agent"

    def _load_map_reduce_config(self) -> None:
        """
        Load map-reduce configuration from the config system.

        Sets instance attributes for map-reduce processing thresholds.
        Falls back to class-level defaults if config is unavailable.
        """
        try:
            from ..config import get_agent_config
            config = get_agent_config("reporting")

            # Load map-reduce settings with fallbacks to class defaults
            self.map_reduce_citation_threshold = config.get(
                'map_reduce_citation_threshold',
                self.MAP_REDUCE_CITATION_THRESHOLD
            )
            self.map_batch_size = config.get(
                'map_batch_size',
                self.MAP_BATCH_SIZE
            )
            self.effective_context_limit = config.get(
                'effective_context_limit',
                6000  # Default token limit for citations
            )
            self.map_passage_max_length = config.get(
                'map_passage_max_length',
                self.MAP_PASSAGE_MAX_LENGTH
            )

            logger.debug(
                f"Map-reduce config loaded: threshold={self.map_reduce_citation_threshold}, "
                f"batch_size={self.map_batch_size}, context_limit={self.effective_context_limit}, "
                f"passage_max_length={self.map_passage_max_length}"
            )

        except Exception as e:
            # Fallback to class defaults if config loading fails
            logger.warning(f"Could not load map-reduce config, using defaults: {e}")
            self.map_reduce_citation_threshold = self.MAP_REDUCE_CITATION_THRESHOLD
            self.map_batch_size = self.MAP_BATCH_SIZE
            self.effective_context_limit = 6000
            self.map_passage_max_length = self.MAP_PASSAGE_MAX_LENGTH

    def create_references(self, citations: List[Citation]) -> List[Reference]:
        """
        Create numbered references from citations.
        
        Args:
            citations: List of citations to convert to references
            
        Returns:
            List of formatted references with numbers
        """
        references = []
        seen_docs = set()
        ref_number = 1
        
        for citation in citations:
            # Avoid duplicate references for the same document
            if citation.document_id not in seen_docs:
                reference = Reference(
                    number=ref_number,
                    authors=citation.authors,
                    title=citation.document_title,
                    publication_date=citation.publication_date,
                    document_id=citation.document_id,
                    pmid=citation.pmid,
                    doi=getattr(citation, 'doi', None),
                    publication=getattr(citation, 'publication', None)
                )
                references.append(reference)
                seen_docs.add(citation.document_id)
                ref_number += 1
        
        return references
    
    def map_citations_to_references(self, citations: List[Citation], 
                                  references: List[Reference]) -> Dict[str, int]:
        """
        Create mapping from document IDs to reference numbers.
        
        Args:
            citations: List of citations
            references: List of references with numbers
            
        Returns:
            Dictionary mapping document_id to reference number
        """
        doc_to_ref = {}
        for ref in references:
            doc_to_ref[ref.document_id] = ref.number
        return doc_to_ref
    
    def generate_detailed_methodology(self, metadata: MethodologyMetadata) -> str:
        """
        Generate a detailed methodology section based on workflow metadata.
        
        Args:
            metadata: MethodologyMetadata containing workflow details
            
        Returns:
            Formatted methodology section string
        """
        sections = []
        
        # Query Generation Section
        sections.append("**Query Generation:**")
        sections.append(f"The research question '{metadata.human_question}' was converted into a database query: '{metadata.generated_query}'.")
        sections.append("")

        # Search Strategy Section (NEW)
        if metadata.search_strategies_used:
            sections.append("**Search Methods:**")

            strategies = metadata.search_strategies_used
            search_methods = []

            if 'semantic' in strategies and metadata.semantic_search_params:
                params = metadata.semantic_search_params
                search_methods.append(
                    f"Semantic search using {params['model']} embedding model "
                    f"(threshold: {params['threshold']}, found: {params['documents_found']} documents)"
                )

            if 'bm25' in strategies and metadata.bm25_search_params:
                params = metadata.bm25_search_params
                search_methods.append(
                    f"BM25 ranking search with query '{params['query_expression']}' "
                    f"(k1={params['k1']}, b={params['b']}, found: {params['documents_found']} documents)"
                )

            if 'fulltext' in strategies and metadata.fulltext_search_params:
                params = metadata.fulltext_search_params
                search_methods.append(
                    f"Full-text search with query '{params['query_expression']}' "
                    f"(found: {params['documents_found']} documents)"
                )

            for method in search_methods:
                sections.append(f"- {method}")

            sections.append(f"Combined search across {len(strategies)} methods yielded {metadata.total_documents_found:,} unique documents after deduplication.")
            sections.append("")
        else:
            # Fallback for when no search strategy metadata is available
            sections.append(f"This query identified {metadata.total_documents_found:,} potentially relevant documents from the biomedical literature database.")
            sections.append("")
        
        # Document Scoring Section
        sections.append("**Document Relevance Assessment:**")
        sections.append(f"All {metadata.total_documents_found:,} documents were scored for relevance using AI-powered assessment with a threshold of {metadata.scoring_threshold}. ")
        
        # Score distribution
        if metadata.documents_by_score:
            score_dist = []
            for score in sorted(metadata.documents_by_score.keys(), reverse=True):
                count = metadata.documents_by_score[score]
                score_dist.append(f"score {score}: {count} documents")
            sections.append(f"Score distribution: {'; '.join(score_dist)}. ")
        
        sections.append(f"{metadata.documents_above_threshold} documents exceeded the relevance threshold and were selected for citation extraction.")
        sections.append("")
        
        # Citation Extraction Section
        sections.append("**Citation Extraction:**")
        sections.append(f"{metadata.documents_processed_for_citations} high-scoring documents were processed for citation extraction using a relevance threshold of {metadata.citation_extraction_threshold}. ")
        
        if metadata.iterative_processing_used:
            sections.append("Iterative processing was employed to ensure comprehensive coverage while managing context window limitations. ")
        
        if metadata.context_window_management:
            sections.append("Context window management techniques were used to handle large document sets efficiently.")
        
        sections.append("")
        
        # Counterfactual Analysis Section (if performed)
        if metadata.counterfactual_performed:
            sections.append("**Counterfactual Analysis:**")
            sections.append(f"To assess evidence completeness, {metadata.counterfactual_queries_generated} counterfactual research questions were generated to search for contradictory evidence. ")
            sections.append(f"This identified {metadata.counterfactual_documents_found} additional documents, yielding {metadata.counterfactual_citations_extracted} citations that provided alternative perspectives or contradictory findings.")
            sections.append("")

        # AI Model Audit Trail Section
        model_info = []
        if metadata.query_model:
            model_info.append(f"Query Generation: {metadata.query_model}")
        if metadata.scoring_model:
            model_info.append(f"Document Scoring: {metadata.scoring_model}")
        if metadata.citation_model:
            model_info.append(f"Citation Extraction: {metadata.citation_model}")
        if metadata.reporting_model:
            model_info.append(f"Report Synthesis: {metadata.reporting_model}")
        if metadata.counterfactual_model:
            model_info.append(f"Counterfactual Analysis: {metadata.counterfactual_model}")
        if metadata.editor_model:
            model_info.append(f"Report Editing: {metadata.editor_model}")

        if model_info:
            sections.append("**AI Models Used:**")
            for info in model_info:
                sections.append(f"- {info}")

            # Add model parameters if available
            param_info = []
            if metadata.model_temperature is not None:
                param_info.append(f"Temperature: {metadata.model_temperature}")
            if metadata.model_top_p is not None:
                param_info.append(f"Top-p: {metadata.model_top_p}")

            if param_info:
                sections.append(f"- Model Parameters: {', '.join(param_info)}")

            sections.append("")

        return "\n".join(sections).strip()
    
    def assess_evidence_strength(self, citations: List[Citation]) -> str:
        """
        Assess the strength of evidence based on citation quality and quantity.
        
        Args:
            citations: List of citations to assess
            
        Returns:
            Evidence strength rating
        """
        if not citations:
            return "Insufficient"
        
        avg_relevance = sum(c.relevance_score for c in citations) / len(citations)
        citation_count = len(citations)
        unique_docs = len(set(c.document_id for c in citations))
        
        # Evidence strength criteria
        if citation_count >= 5 and unique_docs >= 3 and avg_relevance >= 0.85:
            return "Strong"
        elif citation_count >= 3 and unique_docs >= 2 and avg_relevance >= 0.75:
            return "Moderate" 
        elif citation_count >= 2 and avg_relevance >= 0.70:
            return "Limited"
        else:
            return "Insufficient"

    # ============================================================================
    # Map-Reduce Pattern for Large Citation Sets
    # ============================================================================
    # When citation count exceeds the model's effective context window, we use a
    # map-reduce approach:
    # 1. MAP: Process citations in batches to extract key findings
    # 2. REDUCE: Synthesize batch summaries into a final coherent report
    # ============================================================================

    # Configuration constants for map-reduce processing
    MAP_REDUCE_CITATION_THRESHOLD = 15  # Use map-reduce when citations exceed this
    MAP_BATCH_SIZE = 8  # Number of citations per batch in map phase
    MAP_PASSAGE_MAX_LENGTH = 500  # Max characters per passage in map phase (full passage used in reduce)

    def _validate_reference_numbers(self, content: str, valid_numbers: set) -> None:
        """
        Validate that reference numbers in generated content match valid references.

        Logs warnings for any reference numbers that don't match the expected set.
        This helps catch cases where the LLM invents reference numbers.

        Args:
            content: Generated report content to validate
            valid_numbers: Set of valid reference numbers
        """
        import re

        # Find all reference patterns like [1], [12], [123]
        ref_pattern = r'\[(\d+)\]'
        found_refs = re.findall(ref_pattern, content)

        if not found_refs:
            logger.warning("No reference numbers found in generated content")
            return

        found_numbers = {int(ref) for ref in found_refs}
        invalid_refs = found_numbers - valid_numbers
        missing_refs = valid_numbers - found_numbers

        if invalid_refs:
            logger.warning(
                f"Generated content contains invalid reference numbers: {sorted(invalid_refs)}. "
                f"Valid numbers are: {sorted(valid_numbers)}"
            )

        if missing_refs and len(missing_refs) < len(valid_numbers):
            # Only log if some refs are used (not all missing)
            logger.debug(
                f"Some valid references not used in content: {sorted(missing_refs)}"
            )

        logger.info(
            f"Reference validation: {len(found_numbers)} unique refs used, "
            f"{len(invalid_refs)} invalid, {len(found_numbers & valid_numbers)} valid"
        )

    def _estimate_citation_tokens(self, citations: List[Citation]) -> int:
        """
        Estimate the token count for a list of citations.

        Uses a simple heuristic: ~4 characters per token (conservative estimate).
        This helps determine whether map-reduce is needed.

        Args:
            citations: List of citations to estimate

        Returns:
            Estimated token count
        """
        total_chars = 0
        for citation in citations:
            # Count characters in key fields
            total_chars += len(citation.document_title or "")
            total_chars += len(citation.summary or "")
            total_chars += len(citation.passage or "")
            # Add overhead for formatting
            total_chars += 100  # Template text per citation

        # Conservative estimate: ~4 chars per token
        return total_chars // 4

    def _should_use_map_reduce(self, citations: List[Citation]) -> bool:
        """
        Determine whether to use map-reduce based on citation count and estimated size.

        Uses instance configuration (loaded from config system) for thresholds.

        Args:
            citations: List of citations to process

        Returns:
            True if map-reduce should be used, False for direct synthesis
        """
        citation_count = len(citations)

        # Use instance threshold (from config) or fall back to class default
        threshold = getattr(
            self, 'map_reduce_citation_threshold', self.MAP_REDUCE_CITATION_THRESHOLD
        )

        # Always use map-reduce above threshold
        if citation_count > threshold:
            logger.info(
                f"Map-reduce triggered: {citation_count} citations "
                f"(threshold: {threshold})"
            )
            return True

        # Also check estimated token count for smaller sets with long passages
        estimated_tokens = self._estimate_citation_tokens(citations)

        # Use instance context limit (from config) or default
        context_limit = getattr(self, 'effective_context_limit', 6000)

        if estimated_tokens > context_limit:
            logger.info(
                f"Map-reduce triggered: estimated {estimated_tokens} tokens "
                f"(limit: {context_limit})"
            )
            return True

        return False

    def _map_phase_summarize_batch(
        self,
        user_question: str,
        batch_citations: List[Citation],
        doc_to_ref: Dict[str, int],
        batch_number: int,
        total_batches: int
    ) -> Optional[Dict[str, Any]]:
        """
        MAP PHASE: Summarize a batch of citations into key findings.

        Processes a subset of citations and extracts:
        - Main themes/findings
        - Key evidence points with reference numbers
        - Relevance to the research question

        Args:
            user_question: Original research question
            batch_citations: Subset of citations to process
            doc_to_ref: Mapping from document IDs to reference numbers
            batch_number: Current batch number (1-indexed)
            total_batches: Total number of batches

        Returns:
            Dictionary with batch summary or None if processing failed
        """
        logger.info(
            f"Map phase: processing batch {batch_number}/{total_batches} "
            f"({len(batch_citations)} citations)"
        )

        # Prepare citation summaries for this batch
        # Use configurable max length for passages to manage context window
        passage_max_length = getattr(self, 'map_passage_max_length', self.MAP_PASSAGE_MAX_LENGTH)

        citation_summaries = []
        for citation in batch_citations:
            ref_number = doc_to_ref.get(citation.document_id, '?')
            # Truncate passage for map phase only (full passage available in original citation)
            passage_text = citation.passage or ""
            if len(passage_text) > passage_max_length:
                passage_display = f"{passage_text[:passage_max_length]}..."
            else:
                passage_display = passage_text

            citation_summaries.append(f"""
[Reference {ref_number}]:
Title: {citation.document_title}
Summary: {citation.summary}
Key Passage: "{passage_display}"
Relevance: {citation.relevance_score:.2f}
""")

        prompt = f"""You are a medical writing expert. Analyze this batch of citations and extract key findings relevant to the research question.

Research Question: "{user_question}"

Citations in this batch (batch {batch_number} of {total_batches}):
{chr(10).join(citation_summaries)}

Your task:
1. Identify 2-4 main themes or findings from these citations
2. For each theme, note the supporting reference numbers
3. Highlight any contradictory or nuanced findings
4. Note the overall relevance to the research question

Response format (JSON):
{{
    "themes": [
        {{
            "theme": "Brief theme description",
            "key_finding": "One sentence summarizing the finding",
            "supporting_refs": [1, 2, 3],
            "evidence_strength": "strong/moderate/limited"
        }}
    ],
    "contradictions": ["Any contradictory findings noted, or empty list"],
    "batch_relevance": "high/medium/low"
}}

Be concise but comprehensive. Focus on extracting the most important evidence."""

        try:
            llm_response = self._generate_from_prompt(
                prompt,
                num_predict=getattr(self, 'max_tokens', 1500)
            )

            batch_data = self._parse_json_response(llm_response)
            batch_data['batch_number'] = batch_number
            batch_data['citation_count'] = len(batch_citations)
            batch_data['reference_numbers'] = [
                doc_to_ref.get(c.document_id, '?') for c in batch_citations
            ]

            logger.info(
                f"Batch {batch_number} extracted {len(batch_data.get('themes', []))} themes"
            )
            return batch_data

        except Exception as e:
            logger.error(f"Map phase batch {batch_number} failed: {e}")
            return None

    def _reduce_phase_synthesize(
        self,
        user_question: str,
        batch_summaries: List[Dict[str, Any]],
        references: List['Reference']
    ) -> Optional[str]:
        """
        REDUCE PHASE: Synthesize batch summaries into final report.

        Combines the extracted themes from all batches into a coherent,
        well-structured medical report.

        Args:
            user_question: Original research question
            batch_summaries: List of batch summary dictionaries from map phase
            references: List of Reference objects for citation

        Returns:
            Synthesized report content or None if synthesis failed
        """
        logger.info(
            f"Reduce phase: synthesizing {len(batch_summaries)} batch summaries"
        )

        # Compile all themes from batches
        all_themes = []
        all_contradictions = []
        total_citations = 0

        for batch in batch_summaries:
            for theme in batch.get('themes', []):
                theme['source_batch'] = batch.get('batch_number', 0)
                all_themes.append(theme)
            all_contradictions.extend(batch.get('contradictions', []))
            total_citations += batch.get('citation_count', 0)

        # Format themes for the synthesis prompt
        themes_text = []
        for i, theme in enumerate(all_themes, 1):
            refs = ', '.join(str(r) for r in theme.get('supporting_refs', []))
            themes_text.append(f"""
Theme {i}: {theme.get('theme', 'Unknown')}
- Finding: {theme.get('key_finding', '')}
- References: [{refs}]
- Strength: {theme.get('evidence_strength', 'unknown')}
""")

        # Build reference list for LLM context (ensures correct citation numbers)
        reference_list_text = []
        seen_refs = set()
        for ref in references:
            if ref.number not in seen_refs:
                seen_refs.add(ref.number)
                # Format: [1] Author et al. Title (Year)
                author_str = ref.authors[0] if ref.authors else "Unknown"
                if len(ref.authors) > 1:
                    author_str += " et al."
                year = str(ref.publication_date)[:4] if ref.publication_date else "n.d."
                reference_list_text.append(
                    f"[{ref.number}] {author_str}. {ref.title[:80]}{'...' if len(ref.title) > 80 else ''} ({year})"
                )

        contradictions_text = ""
        if all_contradictions:
            contradictions_text = f"\nNoted contradictions:\n" + "\n".join(
                f"- {c}" for c in all_contradictions if c
            )

        # Build available references section
        references_section = ""
        if reference_list_text:
            references_section = f"""
Available References (use these exact numbers in your citations):
{chr(10).join(reference_list_text)}
"""

        prompt = f"""You are a medical writing expert. Synthesize these extracted themes into a comprehensive medical research report.

Research Question: "{user_question}"

Extracted Evidence Themes ({len(all_themes)} themes from {len(batch_summaries)} citation batches, {total_citations} total citations):
{chr(10).join(themes_text)}
{contradictions_text}
{references_section}
Your task is to create a structured, readable report:

1. **Introduction (2-3 sentences)**:
   - Start with a clear, direct answer to the research question
   - Provide context for the evidence that follows

2. **Evidence and Discussion (3-4 paragraphs)**:
   - Group related themes into coherent paragraphs
   - Use reference numbers [X] to cite supporting evidence
   - Address any contradictions or nuances in the evidence
   - Synthesize findings rather than listing them

3. **Conclusion (1-2 sentences)**:
   - Summarize key findings and implications

**Writing Guidelines:**
- Use formal, professional medical writing style
- Use specific years (e.g., "In a 2023 study") NOT vague references ("recently")
- Ensure smooth transitions between sections
- Create a cohesive narrative, not a list of findings
- IMPORTANT: Only use reference numbers from the "Available References" list above
- Use the exact reference numbers provided (e.g., [1], [5], [12]) - do not invent new numbers

Response format (JSON):
{{
    "introduction": "2-3 sentences directly answering the research question",
    "evidence_discussion": "3-4 well-structured paragraphs with [X] citations",
    "conclusion": "1-2 sentences summarizing key findings",
    "themes_integrated": ["List of theme topics covered"]
}}

Write a professional medical report that synthesizes all evidence."""

        try:
            llm_response = self._generate_from_prompt(
                prompt,
                num_predict=getattr(self, 'max_tokens', 4000)
            )

            report_data = self._parse_json_response(llm_response)

            # Construct the final report
            introduction = report_data.get('introduction', '')
            evidence_discussion = report_data.get('evidence_discussion', '')
            conclusion = report_data.get('conclusion', '')

            if not introduction or not evidence_discussion:
                logger.warning("Incomplete reduce phase response")
                return None

            structured_content = f"{introduction}\n\n## Evidence and Discussion\n\n{evidence_discussion}"
            if conclusion:
                structured_content += f"\n\n## Conclusion\n\n{conclusion}"

            # Validate reference numbers in generated content
            valid_ref_numbers = {ref.number for ref in references}
            self._validate_reference_numbers(structured_content, valid_ref_numbers)

            logger.info(
                f"Reduce phase complete: integrated {len(report_data.get('themes_integrated', []))} themes"
            )
            return structured_content

        except Exception as e:
            logger.error(f"Reduce phase synthesis failed: {e}")
            return None

    def map_reduce_synthesis(
        self,
        user_question: str,
        citations: List[Citation],
        doc_to_ref: Dict[str, int]
    ) -> Optional[str]:
        """
        Perform map-reduce synthesis for large citation sets.

        This method handles citation sets that would overflow the model's
        context window by:
        1. Splitting citations into manageable batches
        2. Extracting key themes from each batch (MAP)
        3. Synthesizing all themes into a final report (REDUCE)

        Args:
            user_question: Original research question
            citations: List of all citations to synthesize
            doc_to_ref: Mapping from document IDs to reference numbers

        Returns:
            Synthesized report content or None if synthesis failed
        """
        logger.info(
            f"Starting map-reduce synthesis for {len(citations)} citations"
        )

        # Sort citations by relevance (highest first)
        sorted_citations = sorted(
            citations, key=lambda c: c.relevance_score, reverse=True
        )

        # Use instance batch size (from config) or class default
        batch_size = getattr(self, 'map_batch_size', self.MAP_BATCH_SIZE)

        # Split into batches
        batches = []
        for i in range(0, len(sorted_citations), batch_size):
            batch = sorted_citations[i:i + batch_size]
            batches.append(batch)

        logger.info(f"Split into {len(batches)} batches of up to {batch_size} citations")

        # MAP PHASE: Process each batch
        batch_summaries = []
        for batch_num, batch in enumerate(batches, 1):
            self._call_callback(
                "map_phase_progress",
                f"Processing citation batch {batch_num}/{len(batches)}"
            )

            batch_summary = self._map_phase_summarize_batch(
                user_question=user_question,
                batch_citations=batch,
                doc_to_ref=doc_to_ref,
                batch_number=batch_num,
                total_batches=len(batches)
            )

            if batch_summary:
                batch_summaries.append(batch_summary)
            else:
                logger.warning(f"Batch {batch_num} failed, continuing with remaining batches")

        if not batch_summaries:
            logger.error("All batches failed in map phase")
            return None

        logger.info(
            f"Map phase complete: {len(batch_summaries)}/{len(batches)} batches successful"
        )

        # REDUCE PHASE: Synthesize batch summaries
        self._call_callback("reduce_phase_started", "Synthesizing evidence themes")

        # Create references list for the reduce phase
        references = []
        for citation in sorted_citations:
            ref_num = doc_to_ref.get(citation.document_id)
            if ref_num:
                references.append(Reference(
                    number=ref_num,
                    authors=citation.authors,
                    title=citation.document_title,
                    publication_date=citation.publication_date,
                    document_id=citation.document_id,
                    pmid=citation.pmid,
                    doi=getattr(citation, 'doi', None)
                ))

        final_content = self._reduce_phase_synthesize(
            user_question=user_question,
            batch_summaries=batch_summaries,
            references=references
        )

        if final_content:
            logger.info("Map-reduce synthesis completed successfully")
        else:
            logger.error("Reduce phase failed")

        return final_content

    def synthesize_report(self, user_question: str, citations: List[Citation],
                         min_citations: int = 2, methodology_metadata: Optional[MethodologyMetadata] = None) -> Optional[Report]:
        """
        Synthesize citations into a cohesive medical publication-style report using iterative processing.
        
        Args:
            user_question: Original research question
            citations: List of extracted citations
            min_citations: Minimum citations required for report generation
            methodology_metadata: Optional metadata about the research workflow
            
        Returns:
            Synthesized report or None if insufficient evidence
        """
        if len(citations) < min_citations:
            logger.warning(f"Insufficient citations ({len(citations)}) for report generation")
            return None

        if not self.test_connection():
            logger.error("Cannot connect to Ollama - report synthesis unavailable")
            return None

        try:
            # Create references and mapping
            references = self.create_references(citations)
            doc_to_ref = self.map_citations_to_references(citations, references)
            
            # Process citations to build a structured report
            synthesized_content = self.structured_synthesis(user_question, citations, doc_to_ref)
            
            if not synthesized_content:
                logger.error("Failed to synthesize content from citations")
                return None
            
            # Generate methodology note
            if methodology_metadata:
                methodology_note = self.generate_detailed_methodology(methodology_metadata)
            else:
                # Fallback to simple methodology note
                methodology_note = f"Evidence synthesis based on {len(citations)} citations from {len(references)} documents using iterative processing to ensure comprehensive coverage while avoiding context limits."
            
            # Assess evidence strength
            evidence_strength = self.assess_evidence_strength(citations)
            
            # Create report
            report = Report(
                user_question=user_question,
                synthesized_answer=synthesized_content,
                references=references,
                evidence_strength=evidence_strength,
                methodology_note=methodology_note,
                created_at=datetime.now(timezone.utc),
                citation_count=len(citations),
                unique_documents=len(references),
                methodology_metadata=methodology_metadata
            )
            
            logger.info(f"Successfully synthesized report with {len(citations)} citations from {len(references)} documents")
            return report
            
        except Exception as e:
            logger.error(f"Error synthesizing report: {e}")
            return None
    
    def structured_synthesis(self, user_question: str, citations: List[Citation],
                           doc_to_ref: Dict[str, int]) -> Optional[str]:
        """
        Generate a structured, readable report with clear introduction and supporting sections.

        Creates a medical publication-style report that:
        1. Directly answers the research question in the introduction
        2. Organizes evidence into coherent themes/categories
        3. Uses supporting evidence to back up key statements
        4. Maintains professional medical writing style

        For large citation sets that would overflow the model's context window,
        this method automatically delegates to map_reduce_synthesis().

        Args:
            user_question: Original research question
            citations: List of extracted citations
            doc_to_ref: Mapping from document IDs to reference numbers

        Returns:
            Structured report content or None if synthesis failed
        """
        import json

        # Check if we need to use map-reduce for large citation sets
        if self._should_use_map_reduce(citations):
            logger.info(
                f"Using map-reduce synthesis for {len(citations)} citations "
                "(context window protection)"
            )
            self._call_callback(
                "map_reduce_started",
                f"Large citation set ({len(citations)}), using map-reduce synthesis"
            )
            return self.map_reduce_synthesis(user_question, citations, doc_to_ref)

        # Standard synthesis for smaller citation sets
        logger.info(f"Using direct synthesis for {len(citations)} citations")

        # Sort citations by relevance score (highest first)
        sorted_citations = sorted(citations, key=lambda c: c.relevance_score, reverse=True)
        
        # Prepare citation summaries for the LLM
        citation_summaries = []
        for i, citation in enumerate(sorted_citations, 1):
            ref_number = doc_to_ref.get(citation.document_id, '?')
            citation_summaries.append(f"""
Citation {i} [Reference {ref_number}]:
Title: {citation.document_title}
Summary: {citation.summary}
Passage: "{citation.passage}"
Relevance Score: {citation.relevance_score}
""")
        
        # Create comprehensive prompt for structured synthesis
        prompt = f"""You are a medical writing expert tasked with creating a comprehensive, readable research report in the style of a medical publication.

Research Question: "{user_question}"

Available Evidence:
{chr(10).join(citation_summaries)}

Your task is to create a structured, readable report that follows this format:

1. **Introduction (2-3 sentences)**: 
   - Start with a clear, direct answer to the research question
   - Provide a concise overview of what the evidence shows
   - Set the context for the detailed evidence that follows

2. **Evidence and Discussion (3-4 paragraphs)**:
   - Organize the evidence into logical themes or categories
   - Each paragraph should focus on a specific aspect or theme
   - Use the citations to support your statements with proper references
   - Synthesize related findings rather than listing them separately
   - Compare and contrast different studies when relevant

3. **Conclusion (1-2 sentences)**:
   - Summarize the key findings and their implications
   - Reinforce the answer to the research question

**Writing Guidelines:**
- Use formal, professional medical writing style
- Include reference numbers [X] after statements supported by evidence
- Use specific years instead of vague temporal references (e.g., "In a 2023 study" NOT "In a recent study")
- Synthesize information rather than simply listing findings
- Ensure smooth transitions between paragraphs
- Write for a professional medical audience
- Make the report readable and engaging, not just a concatenation of citations

**Important**: Create a cohesive narrative that flows naturally. The reader should be able to understand the answer to the research question immediately, then see how the evidence supports that answer.

Response format (JSON):
{{
    "introduction": "2-3 sentences directly answering the research question with overview",
    "evidence_discussion": "3-4 well-structured paragraphs organizing and synthesizing the evidence",
    "conclusion": "1-2 sentences summarizing key findings and implications",
    "themes_identified": ["List of main themes/categories you organized the evidence around"]
}}

Write a comprehensive, professional medical report."""

        try:
            # Use BaseAgent's generate method with ollama library
            llm_response = self._generate_from_prompt(
                prompt,
                num_predict=getattr(self, 'max_tokens', 4000)  # Longer for comprehensive synthesis
            )
        except (ConnectionError, ValueError) as e:
            logger.error(f"Failed to generate structured report: {e}")
            return None

        try:
            
            # Parse JSON response using inherited robust method from BaseAgent
            try:
                report_data = self._parse_json_response(llm_response)
            except json.JSONDecodeError as e:
                logger.warning(f"Could not parse JSON from structured synthesis response: {e}")
                # Fallback to iterative synthesis
                return self.iterative_synthesis(user_question, sorted_citations, doc_to_ref)
            
            # Construct the structured report
            introduction = report_data.get('introduction', '')
            evidence_discussion = report_data.get('evidence_discussion', '')
            conclusion = report_data.get('conclusion', '')
            
            if not introduction or not evidence_discussion:
                logger.warning("Incomplete structured synthesis response, falling back to iterative method")
                return self.iterative_synthesis(user_question, sorted_citations, doc_to_ref)
            
            # Combine sections into final report with section headers
            structured_content = f"{introduction}\n\n## Evidence and Discussion\n\n{evidence_discussion}"
            if conclusion:
                structured_content += f"\n\n## Conclusion\n\n{conclusion}"
            
            logger.info(f"Successfully generated structured report with themes: {report_data.get('themes_identified', [])}")
            return structured_content
            
        except Exception as e:
            logger.error(f"Error in structured synthesis: {e}")
            # Fallback to iterative synthesis
            logger.info("Falling back to iterative synthesis method")
            return self.iterative_synthesis(user_question, sorted_citations, doc_to_ref)
    
    def iterative_synthesis(self, user_question: str, citations: List[Citation], 
                          doc_to_ref: Dict[str, int]) -> Optional[str]:
        """
        Iteratively process citations to build a cohesive report.

        Process one citation at a time, checking if it adds new information
        or should be combined with existing content.
        """
        # Start with empty content
        current_content = ""
        processed_citations = []
        
        # Sort citations by relevance score (highest first)
        sorted_citations = sorted(citations, key=lambda c: c.relevance_score, reverse=True)
        
        for i, citation in enumerate(sorted_citations):
            ref_number = doc_to_ref.get(citation.document_id, '?')
            
            logger.info(f"Processing citation {i+1}/{len(citations)}: {citation.document_title[:50]}...")
            
            # Create prompt for this specific citation
            if not current_content:
                # First citation - create initial content
                prompt = f"""You are a medical writing expert. Create the opening statement for a medical research report.

Research Question: "{user_question}"

Citation to process:
Passage: "{citation.passage}"
Summary: {citation.summary}
Reference: [{ref_number}]

Your task:
1. Write 1-2 sentences that directly address the research question using this citation
2. Use formal medical writing style
3. Include the reference number [{ref_number}] after relevant statements
4. Start with a clear topic sentence
5. IMPORTANT: Use specific years instead of vague temporal references (e.g., "In a 2023 study" NOT "In a recent study")

Response format (JSON):
{{
    "content": "Your medical writing with reference [{ref_number}]",
    "addresses_question": "Brief note on how this addresses the research question"
}}

Write concisely and professionally."""
            else:
                # Subsequent citations - check if new information
                prompt = f"""You are a medical writing expert. You have existing content for a medical research report and need to decide how to incorporate a new citation.

Research Question: "{user_question}"

Current content:
{current_content}

New citation to process:
Passage: "{citation.passage}"
Summary: {citation.summary}
Reference: [{ref_number}]

Your task:
1. Determine if this citation adds NEW information not already covered
2. If NEW: Write 1-2 additional sentences with reference [{ref_number}]
3. If SUPPORTING existing point: Add reference [{ref_number}] to existing sentence
4. Maintain formal medical writing style
5. IMPORTANT: Use specific years instead of vague temporal references (e.g., "In a 2023 study" NOT "In a recent study")

Response format (JSON):
{{
    "action": "add_new" or "add_reference",
    "content": "New sentence(s) with [{ref_number}] OR updated existing content with added [{ref_number}]",
    "reasoning": "Brief explanation of decision"
}}

Be concise and avoid redundancy."""

            try:
                # Use BaseAgent's generate method with ollama library
                llm_response = self._generate_from_prompt(
                    prompt,
                    num_predict=getattr(self, 'max_tokens', 2000)  # Use config max_tokens or default to 2000
                )
            except (ConnectionError, ValueError) as e:
                logger.warning(f"Failed to process citation {i+1}: {e}")
                continue
                
                # Parse JSON response using inherited robust method from BaseAgent
                try:
                    citation_data = self._parse_json_response(llm_response)
                except json.JSONDecodeError as e:
                    logger.warning(f"Could not parse JSON for citation {i+1}: {e}")
                    continue
                
                # Process the result
                if not current_content:
                    # First citation
                    current_content = citation_data.get('content', '')
                else:
                    # Subsequent citation
                    action = citation_data.get('action', 'add_new')
                    new_content = citation_data.get('content', '')
                    
                    if action == 'add_new' and new_content:
                        # Add new content
                        current_content += " " + new_content
                    elif action == 'add_reference' and new_content:
                        # Replace current content with updated version
                        current_content = new_content
                
                processed_citations.append(citation)
                
            except Exception as e:
                logger.warning(f"Error processing citation {i+1}: {e}")
                continue
        
        if not current_content:
            logger.error("No content generated from citations")
            return None
        
        # Final step: Reformat into cohesive report
        final_content = self.final_formatting(user_question, current_content)
        return final_content or current_content
    
    def final_formatting(self, user_question: str, content: str) -> Optional[str]:
        """Final formatting pass to ensure cohesive medical writing."""
        prompt = f"""You are a medical writing expert. Review and reformat the following content into a cohesive medical publication-style paragraph.

Research Question: "{user_question}"

Current content:
{content}

Your task:
1. Ensure smooth transitions between sentences
2. Maintain formal medical writing style
3. Preserve all reference numbers exactly as they appear
4. Create a logical flow of information
5. Add a concluding statement if appropriate
6. IMPORTANT: Use specific years instead of vague temporal references (e.g., "In a 2023 study" NOT "In a recent study")

Response format (JSON):
{{
    "formatted_content": "Your polished, cohesive medical writing with all references preserved"
}}

Do not add or remove any reference numbers. Only improve readability and flow."""

        try:
            # Use BaseAgent's generate method with ollama library
            llm_response = self._generate_from_prompt(
                prompt,
                num_predict=getattr(self, 'max_tokens', 3000)  # Use config max_tokens or default to 3000
            )
            
            # Parse JSON response using inherited robust method from BaseAgent
            try:
                format_data = self._parse_json_response(llm_response)
                return format_data.get('formatted_content')
            except json.JSONDecodeError as e:
                logger.warning(f"Could not parse final formatting response: {e}")
                return None
        
        except Exception as e:
            logger.warning(f"Error in final formatting: {e}")
            return None
    
    def format_report_output_template(self, report: Report) -> str:
        """
        Format report using template approach - LLM content + programmatic sections.
        
        Args:
            report: Report to format
            
        Returns:
            Formatted report string with programmatic references and methodology
        """
        output = []
        
        # Header
        output.append(f"# {report.user_question}")
        output.append("")
        output.append(f"**Evidence Strength:** {report.evidence_strength}")
        output.append("")
        
        # Main synthesized answer (this comes from LLM)
        output.append("## Key Findings")
        output.append(report.synthesized_answer)
        output.append("")
        
        # Programmatically generated methodology section
        if report.methodology_metadata:
            methodology_section = self.generate_detailed_methodology(report.methodology_metadata)
            output.append("## Methodology")
            output.append(methodology_section)
            output.append("")
        elif report.methodology_note:
            output.append("## Methodology")
            output.append(report.methodology_note)
            output.append("")
        
        # Programmatically generated references section (never touched by LLM)
        output.append("## References")
        for ref in report.references:
            formatted_ref = ref.format_vancouver_style()
            output.append(f"{ref.number}. {formatted_ref}")
        output.append("")
        
        # Report metadata
        output.append("## Report Information")
        output.append(f"- **Generated:** {report.created_at.strftime('%Y-%m-%d %H:%M:%S UTC')}")
        output.append(f"- **Citations analyzed:** {report.citation_count}")
        output.append(f"- **Unique references:** {report.unique_documents}")
        output.append(f"- **Evidence strength:** {report.evidence_strength}")
        
        return "\n".join(output)

    def format_report_output(self, report: Report) -> str:
        """
        Format report for display with proper reference list.
        
        Args:
            report: Report to format
            
        Returns:
            Formatted report string
        """
        output = []
        
        # Header
        output.append(f"Research Question: {report.user_question}")
        output.append("=" * 80)
        output.append("")
        
        # Evidence strength indicator
        output.append(f"Evidence Strength: {report.evidence_strength}")
        output.append("")
        
        # Main synthesized answer
        output.append(report.synthesized_answer)
        output.append("")
        
        # References section
        output.append("REFERENCES")
        output.append("-" * 20)
        output.append("")
        
        for ref in report.references:
            formatted_ref = ref.format_vancouver_style()
            output.append(f"{ref.number}. {formatted_ref}")
        
        output.append("")
        
        # Methodology note
        if report.methodology_note:
            output.append("METHODOLOGY")
            output.append("-" * 20)
            output.append(report.methodology_note)
            output.append("")
        
        # Report metadata
        output.append("REPORT METADATA")
        output.append("-" * 20)
        output.append(f"Generated: {report.created_at.strftime('%Y-%m-%d %H:%M:%S UTC')}")
        output.append(f"Citations analyzed: {report.citation_count}")
        output.append(f"Unique references: {report.unique_documents}")
        output.append(f"Evidence strength: {report.evidence_strength}")
        
        return "\n".join(output)
    
    def generate_citation_based_report(self, user_question: str, citations: List[Citation],
                                     format_output: bool = True, methodology_metadata: Optional[MethodologyMetadata] = None) -> Optional[str]:
        """
        Complete workflow: synthesize citations and format for output.
        
        Args:
            user_question: Research question
            citations: List of citations to synthesize
            format_output: Whether to format for display
            methodology_metadata: Optional metadata about the research workflow
            
        Returns:
            Formatted report string or None if synthesis failed
        """
        report = self.synthesize_report(user_question, citations, methodology_metadata=methodology_metadata)
        
        if not report:
            return None
        
        if format_output:
            return self.format_report_output(report)
        else:
            return report.synthesized_answer
    
    def validate_citations(self, citations: List[Citation]) -> Tuple[List[Citation], List[str]]:
        """
        Validate citations and return valid ones with error messages.

        Args:
            citations: List of citations to validate

        Returns:
            Tuple of (valid_citations, error_messages)
        """
        valid_citations = []
        errors = []

        for i, citation in enumerate(citations):
            # Check required fields
            if not citation.passage or not citation.passage.strip():
                errors.append(f"Citation {i+1}: Empty passage")
                continue

            if not citation.document_id:
                errors.append(f"Citation {i+1}: Missing document ID")
                continue

            if not citation.document_title:
                errors.append(f"Citation {i+1}: Missing document title")
                continue

            if citation.relevance_score < 0 or citation.relevance_score > 1:
                errors.append(f"Citation {i+1}: Invalid relevance score ({citation.relevance_score})")
                continue

            valid_citations.append(citation)

        return valid_citations, errors

    def generate_report_with_audit(
        self,
        research_question_id: int,
        session_id: int,
        user_question: str,
        citations: List[Citation],
        report_type: str = 'preliminary',
        format_output: bool = True,
        methodology_metadata: Optional[MethodologyMetadata] = None,
        is_final: bool = False
    ) -> Tuple[Optional[str], Optional[int]]:
        """
        Generate report WITH AUDIT TRACKING.

        CRITICAL: Records generated report in audit database.

        Args:
            research_question_id: ID of the research question
            session_id: ID of the current session
            user_question: The user's question
            citations: List of citations to synthesize
            report_type: Type of report ('preliminary', 'comprehensive', 'counterfactual')
            format_output: Whether to format for display
            methodology_metadata: Optional metadata about the research workflow
            is_final: Mark this as the final version

        Returns:
            Tuple of (formatted_report, report_id)
            - formatted_report is the report text (or None if failed)
            - report_id is the database ID for the report record (or None if failed)

        Raises:
            RuntimeError: If audit tracking not enabled

        Example:
            >>> import psycopg
            >>> conn = psycopg.connect(dbname="knowledgebase", user="hherb")
            >>> agent = ReportingAgent(audit_conn=conn)
            >>> report_text, report_id = agent.generate_report_with_audit(
            ...     research_question_id=1,
            ...     session_id=1,
            ...     user_question="What are the benefits of exercise?",
            ...     citations=citations,
            ...     report_type='preliminary'
            ... )
            >>> print(f"Report ID: {report_id}")
        """
        if not self._report_tracker:
            raise RuntimeError("Audit tracking not enabled. Pass audit_conn to __init__()")

        if not user_question or not user_question.strip():
            raise ValueError("User question cannot be empty")

        if not citations or not isinstance(citations, list):
            raise ValueError("Citations must be a non-empty list")

        valid_types = ['preliminary', 'comprehensive', 'counterfactual']
        if report_type not in valid_types:
            raise ValueError(f"Invalid report_type '{report_type}'. Must be one of: {valid_types}")

        try:
            self._call_callback("report_generation_started", f"Generating {report_type} report")

            # Generate the report
            report_text = self.generate_citation_based_report(
                user_question=user_question,
                citations=citations,
                format_output=format_output,
                methodology_metadata=methodology_metadata
            )

            if not report_text:
                logger.error("Report generation failed")
                return None, None

            # Convert methodology_metadata to dict if provided
            metadata_dict = None
            if methodology_metadata:
                metadata_dict = {
                    'human_question': methodology_metadata.human_question,
                    'generated_query': methodology_metadata.generated_query,
                    'total_documents_found': methodology_metadata.total_documents_found,
                    'scoring_threshold': methodology_metadata.scoring_threshold,
                    'documents_by_score': methodology_metadata.documents_by_score,
                    'documents_above_threshold': methodology_metadata.documents_above_threshold,
                    'documents_processed_for_citations': methodology_metadata.documents_processed_for_citations,
                    'citation_extraction_threshold': methodology_metadata.citation_extraction_threshold,
                    'counterfactual_performed': methodology_metadata.counterfactual_performed,
                    'counterfactual_queries_generated': methodology_metadata.counterfactual_queries_generated,
                    'counterfactual_documents_found': methodology_metadata.counterfactual_documents_found,
                    'counterfactual_citations_extracted': methodology_metadata.counterfactual_citations_extracted,
                    'query_model': methodology_metadata.query_model,
                    'scoring_model': methodology_metadata.scoring_model,
                    'citation_model': methodology_metadata.citation_model,
                    'reporting_model': methodology_metadata.reporting_model,
                    'counterfactual_model': methodology_metadata.counterfactual_model,
                    'editor_model': methodology_metadata.editor_model,
                    'model_temperature': methodology_metadata.model_temperature,
                    'model_top_p': methodology_metadata.model_top_p
                }

            # Record report in audit database
            report_id = self._report_tracker.record_report(
                research_question_id=research_question_id,
                session_id=session_id,
                report_type=report_type,
                model_name=self.model,
                temperature=self.temperature,
                report_text=report_text,
                citation_count=len(citations),
                methodology_metadata=metadata_dict,
                report_format='markdown',
                is_final=is_final
            )

            self._call_callback(
                "report_generation_completed",
                f"Generated {report_type} report with {len(citations)} citations"
            )

            logger.info(f"Generated {report_type} report {report_id} with {len(citations)} citations")

            return report_text, report_id

        except Exception as e:
            logger.error(f"Failed to generate report: {e}")
            return None, None

    def get_existing_reports(
        self,
        research_question_id: int,
        report_type: Optional[str] = None,
        final_only: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Get existing reports from audit database.

        CRITICAL FOR RESUMPTION: Returns reports already generated for this question.

        Args:
            research_question_id: ID of the research question
            report_type: Optional filter by report type ('preliminary', 'comprehensive', 'counterfactual')
            final_only: If True, only return the final report

        Returns:
            List of dictionaries with report data (or single report if final_only=True)

        Raises:
            RuntimeError: If audit tracking not enabled

        Example:
            >>> final_report = agent.get_existing_reports(question_id, final_only=True)
            >>> print(f"Final report: {final_report['report_text'][:100]}...")
        """
        if not self._report_tracker:
            raise RuntimeError("Audit tracking not enabled. Pass audit_conn to __init__()")

        if final_only:
            final_report = self._report_tracker.get_final_report(research_question_id)
            return [final_report] if final_report else []
        elif report_type:
            latest = self._report_tracker.get_latest_report(research_question_id, report_type)
            return [latest] if latest else []
        else:
            return self._report_tracker.get_all_reports(research_question_id)

    def mark_as_final(
        self,
        report_id: int
    ) -> None:
        """
        Mark a report as the final version.

        Unmarks any other reports for the same research question.

        Args:
            report_id: ID of the report

        Raises:
            RuntimeError: If audit tracking not enabled

        Example:
            >>> agent.mark_as_final(report_id=42)
        """
        if not self._report_tracker:
            raise RuntimeError("Audit tracking not enabled. Pass audit_conn to __init__()")

        self._report_tracker.mark_report_as_final(report_id)
        logger.info(f"Marked report {report_id} as final")

    def record_counterfactual_analysis_with_audit(
        self,
        research_question_id: int,
        session_id: int,
        source_report_id: Optional[int] = None,
        num_questions_generated: Optional[int] = None,
        num_queries_executed: Optional[int] = None,
        num_documents_found: Optional[int] = None,
        num_citations_extracted: Optional[int] = None
    ) -> int:
        """
        Record a counterfactual analysis session in audit database.

        Args:
            research_question_id: ID of the research question
            session_id: ID of the current session
            source_report_id: ID of report analyzed (optional)
            num_questions_generated: Number of counterfactual questions generated
            num_queries_executed: Number of queries executed
            num_documents_found: Number of documents found
            num_citations_extracted: Number of citations extracted

        Returns:
            analysis_id (int) - Database ID for the analysis record

        Raises:
            RuntimeError: If audit tracking not enabled

        Example:
            >>> analysis_id = agent.record_counterfactual_analysis_with_audit(
            ...     research_question_id=1,
            ...     session_id=1,
            ...     num_questions_generated=3,
            ...     num_documents_found=15,
            ...     num_citations_extracted=5
            ... )
        """
        if not self._report_tracker:
            raise RuntimeError("Audit tracking not enabled. Pass audit_conn to __init__()")

        analysis_id = self._report_tracker.record_counterfactual_analysis(
            research_question_id=research_question_id,
            session_id=session_id,
            model_name=self.model,
            temperature=self.temperature,
            source_report_id=source_report_id,
            num_questions_generated=num_questions_generated,
            num_queries_executed=num_queries_executed,
            num_documents_found=num_documents_found,
            num_citations_extracted=num_citations_extracted
        )

        logger.info(f"Recorded counterfactual analysis {analysis_id}")
        return analysis_id