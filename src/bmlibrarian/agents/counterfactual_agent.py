"""
Counterfactual Checking Agent for analyzing documents and generating contradictory research questions.

This agent analyzes documents (such as generated reports) and suggests literature research
questions designed to find evidence that might contradict the document's claims or conclusions.
This is essential for rigorous academic research and evidence evaluation.
"""

import json
import logging
from typing import Dict, List, Optional, Any, Callable

from .base import BaseAgent
from ..config import get_config, get_model, get_agent_config
from .models.counterfactual import CounterfactualQuestion, CounterfactualAnalysis
from .utils.query_syntax import fix_tsquery_syntax
from .utils.citation_validation import (
    validate_citation_supports_counterfactual,
    assess_counter_evidence_strength
)
from .utils.database_search import search_with_retry
from .formatters.counterfactual_formatter import (
    format_counterfactual_report,
    generate_research_protocol
)

logger = logging.getLogger(__name__)


class CounterfactualAgent(BaseAgent):
    """
    Agent for analyzing documents and generating research questions to find contradictory evidence.

    This agent performs counterfactual checking by:
    1. Analyzing a document to identify key claims and conclusions
    2. Generating research questions designed to find contradictory evidence
    3. Providing search keywords and prioritization for each question
    4. Assessing the overall confidence level in the document's claims
    """

    def __init__(
        self,
        model: Optional[str] = None,
        host: Optional[str] = None,
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
        callback: Optional[Callable[[str, str], None]] = None,
        orchestrator: Optional["AgentOrchestrator"] = None,
        show_model_info: bool = True
    ):
        """
        Initialize the CounterfactualAgent.

        Args:
            model: The name of the Ollama model to use (default: from config)
            host: The Ollama server host URL (default: from config)
            temperature: Model temperature for creative question generation (default: from config)
            top_p: Model top-p sampling parameter (default: from config)
            callback: Optional callback function for progress updates
            orchestrator: Optional orchestrator for queue-based processing
            show_model_info: Whether to display model information on initialization
        """
        # Load configuration
        config = get_config()
        agent_config = get_agent_config("counterfactual")
        ollama_config = config.get_ollama_config()

        # Use provided values or fall back to configuration
        model = model or get_model("counterfactual_agent")
        host = host or ollama_config["host"]
        temperature = temperature if temperature is not None else agent_config.get("temperature", 0.2)
        top_p = top_p if top_p is not None else agent_config.get("top_p", 0.9)

        super().__init__(model, host, temperature, top_p, callback, orchestrator, show_model_info)

        # System prompt for counterfactual analysis
        self.system_prompt = """You are a medical research expert specializing in identifying specific factual claims that can be systematically challenged through literature search.

Your task is to:
1. Extract SPECIFIC, CONCRETE factual statements from the document (not general themes)
2. For each factual statement, generate BOTH:
   a) A counterfactual STATEMENT (the opposite claim that would contradict it)
   b) A research QUESTION (for human understanding of what to search for)
3. Create search-ready statements that match how evidence appears in literature

Guidelines for counterfactual generation:
- Original: "Drug X is first-line treatment for Disease Y"
  → Statement: "Drug X is not effective for Disease Y" or "Alternative drugs are superior to Drug X for Disease Y"
  → Question: "What studies show Drug X ineffectiveness or alternative treatments for Disease Y?"

- Original: "Treatment reduces risk by 30%"
  → Statement: "Treatment does not reduce risk" or "Treatment shows no benefit"
  → Question: "What studies show Treatment ineffectiveness or lack of benefit?"

- Original: "Lipophilic statins with clarithromycin cause significant interactions"
  → Statement: "No significant interactions occur between lipophilic statins and clarithromycin" or "Co-prescription of lipophilic statins with clarithromycin is safe"
  → Question: "What studies report safe co-prescription of lipophilic statins with clarithromycin?"

CRITICAL: The counterfactual STATEMENT should express the opposite claim as a declarative statement, not a question. Medical literature contains statements, not questions.

For search_keywords, provide concrete medical terms:
- Use specific drug names, diseases, treatments
- Include safe/no-interaction/ineffective/alternative terms
- Examples: "simvastatin", "clarithromycin", "no interaction", "safe co-prescription"

Response Format:
Return ONLY a valid JSON object with this exact structure:

{
    "main_claims": [
        "Specific factual claim from the document (e.g., 'Lipophilic statins with clarithromycin cause significant drug interactions')"
    ],
    "counterfactual_questions": [
        {
            "counterfactual_statement": "The opposite claim as a declarative statement (e.g., 'No significant interactions occur between lipophilic statins and clarithromycin')",
            "question": "Research question for finding this evidence (e.g., 'What studies report no significant interaction between simvastatin and clarithromycin?')",
            "reasoning": "What this would prove if contradictory evidence is found",
            "target_claim": "The exact claim this question challenges",
            "search_keywords": ["specific", "medical", "terms"],
            "priority": "HIGH|MEDIUM|LOW"
        }
    ],
    "overall_assessment": "Brief assessment of how testable these claims are",
    "confidence_level": "HIGH|MEDIUM|LOW - how much contradictory evidence might exist"
}

Focus on generating counterfactual STATEMENTS that directly contradict specific claims and match how evidence appears in literature."""

    def get_agent_type(self) -> str:
        """Get the agent type identifier."""
        return "counterfactual_agent"

    def analyze_document(self, document_content: str, document_title: str = "Untitled Document") -> Optional[CounterfactualAnalysis]:
        """
        Analyze a document and generate counterfactual research questions.

        Args:
            document_content: The full text content of the document to analyze
            document_title: Optional title of the document

        Returns:
            CounterfactualAnalysis object with suggested research questions, None if analysis fails
        """
        if not document_content or not document_content.strip():
            logger.error("Document content is empty or None")
            return None

        self._call_callback("counterfactual_analysis", f"Analyzing document: {document_title}")

        # Retry mechanism for incomplete responses
        max_retries = 3
        for attempt in range(max_retries):
            try:
                # Prepare the analysis request
                messages = [
                    {
                        'role': 'user',
                        'content': f"""Please analyze the following document and generate counterfactual research questions:

DOCUMENT TITLE: {document_title}

DOCUMENT CONTENT:
{document_content}

Analyze this document to identify its main claims and generate research questions that could help find contradictory evidence. Focus on methodological limitations, alternative explanations, and potential biases."""
                    }
                ]

                # Get response from LLM with increased token limit for comprehensive analysis
                # Increase tokens progressively on retries
                token_limit = 4000 + (attempt * 1000)  # 4000, 5000, 6000
                response = self._make_ollama_request(
                    messages=messages,
                    system_prompt=self.system_prompt,
                    num_predict=token_limit,
                    temperature=self.temperature + (attempt * 0.1)  # Slightly increase randomness on retries
                )

                # Parse the JSON response
                try:
                    # Use inherited robust JSON parsing from BaseAgent
                    result_data = self._parse_json_response(response)

                    # Validate required fields
                    required_fields = ['main_claims', 'counterfactual_questions', 'overall_assessment', 'confidence_level']
                    for field in required_fields:
                        if field not in result_data:
                            raise ValueError(f"Missing required field: {field}")

                    # Create CounterfactualQuestion objects
                    counterfactual_questions = []
                    for q_data in result_data['counterfactual_questions']:
                        # Validate essential fields (allow some to be missing with defaults)
                        if 'target_claim' not in q_data:
                            logger.warning(f"Skipping counterfactual question missing 'target_claim'")
                            continue

                        # Get counterfactual statement (required)
                        counterfactual_statement = q_data.get('counterfactual_statement', '')
                        if not counterfactual_statement:
                            logger.warning(f"No counterfactual_statement for claim '{q_data['target_claim'][:50]}...', skipping")
                            continue

                        # Build question with defaults for optional fields
                        question = CounterfactualQuestion(
                            counterfactual_statement=counterfactual_statement,
                            question=q_data.get('question', counterfactual_statement),  # Default to statement if no question
                            reasoning=q_data.get('reasoning', 'No reasoning provided'),
                            target_claim=q_data['target_claim'],
                            search_keywords=q_data.get('search_keywords', []),
                            priority=q_data.get('priority', 'MEDIUM').upper()
                        )
                        counterfactual_questions.append(question)

                    # Create and return CounterfactualAnalysis object
                    analysis = CounterfactualAnalysis(
                        document_title=document_title,
                        main_claims=result_data['main_claims'],
                        counterfactual_questions=counterfactual_questions,
                        overall_assessment=result_data['overall_assessment'],
                        confidence_level=result_data['confidence_level'].upper()
                    )

                    self._call_callback("counterfactual_complete", f"Generated {len(counterfactual_questions)} research questions")
                    return analysis

                except json.JSONDecodeError as e:
                    # Check if this is an incomplete response that we should retry
                    if len(response) < 100 or not response.strip().endswith('}'):
                        logger.warning(f"Attempt {attempt + 1}: Incomplete JSON response (length: {len(response)}), retrying...")
                        if attempt < max_retries - 1:  # Don't log full error on retries
                            continue

                    logger.error(f"Failed to parse JSON response on attempt {attempt + 1}: {e}")
                    logger.error(f"Raw response (first 500 chars): {response[:500]}")
                    logger.error(f"Raw response length: {len(response)}")

                    if attempt == max_retries - 1:  # Last attempt
                        return None
                    continue

                except ValueError as e:
                    logger.warning(f"Attempt {attempt + 1}: Invalid response structure: {e}")
                    if attempt < max_retries - 1:
                        continue

                    logger.error(f"Invalid response structure after {max_retries} attempts: {e}")
                    logger.error(f"Parsed data keys: {list(result_data.keys()) if 'result_data' in locals() else 'No data parsed'}")
                    return None

            except Exception as e:
                logger.warning(f"Attempt {attempt + 1}: Error during counterfactual analysis: {e}")
                if attempt == max_retries - 1:  # Last attempt
                    logger.error(f"Error during counterfactual analysis after {max_retries} attempts: {e}")
                    return None
                continue

        # Should not reach here, but just in case
        return None

    def analyze_report_citations(self, report_content: str, citations: List[Any]) -> Optional[CounterfactualAnalysis]:
        """
        Analyze a research report along with its citations to generate targeted counterfactual questions.

        Args:
            report_content: The text content of the research report
            citations: List of Citation objects or citation data used in the report

        Returns:
            CounterfactualAnalysis with questions targeting both the report and its evidence base
        """
        if not report_content:
            logger.error("Report content is empty")
            return None

        self._call_callback("citation_analysis", f"Analyzing report with {len(citations)} citations")

        # Format citation information for analysis
        citation_summaries = []
        for i, citation in enumerate(citations, 1):
            if hasattr(citation, 'summary') and hasattr(citation, 'document_title'):
                citation_summaries.append(f"Citation {i}: {citation.document_title} - {citation.summary}")
            elif isinstance(citation, dict):
                title = citation.get('document_title', 'Unknown Title')
                summary = citation.get('summary', 'No summary available')
                citation_summaries.append(f"Citation {i}: {title} - {summary}")

        # Combine report and citations for comprehensive analysis
        combined_content = f"""RESEARCH REPORT:
{report_content}

SUPPORTING CITATIONS:
{chr(10).join(citation_summaries)}"""

        return self.analyze_document(combined_content, "Research Report with Citations")

    def get_high_priority_questions(self, analysis: CounterfactualAnalysis) -> List[CounterfactualQuestion]:
        """
        Filter and return only high-priority counterfactual questions from an analysis.

        Args:
            analysis: CounterfactualAnalysis object

        Returns:
            List of high-priority CounterfactualQuestion objects
        """
        return [q for q in analysis.counterfactual_questions if q.priority == "HIGH"]

    def format_questions_for_search(self, questions: List[CounterfactualQuestion]) -> List[str]:
        """
        Format counterfactual questions into PostgreSQL to_tsquery format for database searches.

        Args:
            questions: List of CounterfactualQuestion objects

        Returns:
            List of PostgreSQL to_tsquery formatted search strings
        """
        search_queries = []
        for question in questions:
            # Convert keywords to PostgreSQL to_tsquery format
            # Quote multi-word phrases and clean single words
            formatted_keywords = []
            for keyword in question.search_keywords:
                if ' ' in keyword.strip():
                    # Multi-word phrase - quote it and escape internal quotes
                    clean_keyword = keyword.strip().replace("'", "''")
                    formatted_keywords.append(f"'{clean_keyword}'")
                else:
                    # Single word - just clean it
                    clean_keyword = keyword.strip().replace("'", "''")
                    formatted_keywords.append(clean_keyword)

            keywords_or = " | ".join(formatted_keywords)

            # Add negation and contradiction terms (single words, so no quoting needed)
            negation_terms = ["ineffective", "contraindication", "adverse", "negative", "fail", "limitation", "confound"]
            negation_or = " | ".join(negation_terms)

            # Combine keywords with negation terms using AND logic
            query = f"({keywords_or}) & ({negation_or})"
            search_queries.append(query)

        return search_queries

    def _clean_tsquery(self, query: str) -> str:
        """
        Clean and validate a PostgreSQL to_tsquery string.

        Fixes syntax errors without oversimplifying the query structure.
        Focuses on quote escaping and malformed patterns.

        Args:
            query: Raw query string from QueryAgent

        Returns:
            Cleaned query string safe for PostgreSQL to_tsquery
        """
        # Use the improved fix_tsquery_syntax function from utils
        return fix_tsquery_syntax(query)

    def generate_research_queries_with_agent(self, questions: List[CounterfactualQuestion], query_agent=None) -> List[Dict[str, str]]:
        """
        Generate database-ready research queries by using the QueryAgent on counterfactual statements.

        Args:
            questions: List of CounterfactualQuestion objects
            query_agent: QueryAgent instance for proper query formatting

        Returns:
            List of dictionaries with 'counterfactual_statement', 'question', 'query', and 'metadata'
        """
        if query_agent is None:
            # Import here to avoid circular imports
            from .query_agent import QueryAgent
            query_agent = QueryAgent(model=get_model("query_agent"))

        research_queries = []

        for question in questions:
            try:
                # IMPORTANT: Use the counterfactual STATEMENT (not question) for database search
                # Medical literature contains statements, not questions
                db_query = query_agent.convert_question(question.counterfactual_statement)

                # Clean the query to ensure PostgreSQL compatibility (fix double quotes)
                cleaned_query = self._clean_tsquery(db_query)

                research_queries.append({
                    'counterfactual_statement': question.counterfactual_statement,
                    'question': question.question,
                    'db_query': cleaned_query,
                    'target_claim': question.target_claim,
                    'search_keywords': question.search_keywords,
                    'priority': question.priority,
                    'reasoning': question.reasoning
                })

                logger.debug(f"Generated query for statement '{question.counterfactual_statement[:50]}...': {cleaned_query}")

            except Exception as e:
                logger.warning(f"QueryAgent failed for statement '{question.counterfactual_statement}': {e}")
                logger.info(f"Skipping counterfactual that couldn't be converted to database query")
                # Skip statements that can't be converted rather than using poor fallbacks
                continue

        logger.info(f"Successfully generated {len(research_queries)} database queries from {len(questions)} counterfactual questions")
        return research_queries

    def generate_research_protocol(self, analysis: CounterfactualAnalysis) -> str:
        """
        Generate a structured research protocol for investigating the counterfactual questions.

        Args:
            analysis: CounterfactualAnalysis object

        Returns:
            Formatted research protocol as a string
        """
        return generate_research_protocol(analysis)

    def find_contradictory_literature(
        self,
        document_content: str,
        document_title: str = "Document",
        max_results_per_query: int = 10,
        min_relevance_score: int = 3,
        query_agent=None,
        scoring_agent=None,
        citation_agent=None
    ) -> Dict[str, Any]:
        """
        Complete workflow to find contradictory literature for a document.

        This method performs the entire counterfactual analysis workflow:
        1. Analyze document for claims and generate questions
        2. Create database queries with QueryAgent
        3. Search database for contradictory evidence
        4. Score and filter results
        5. Extract citations from relevant contradictory studies

        Args:
            document_content: The document text to analyze
            document_title: Title/identifier for the document
            max_results_per_query: Maximum database results per query (default: 10)
            min_relevance_score: Minimum score (1-5) for document relevance (default: 3)
            query_agent: Optional QueryAgent instance
            scoring_agent: Optional DocumentScoringAgent instance
            citation_agent: Optional CitationFinderAgent instance

        Returns:
            Dictionary containing:
            - 'analysis': CounterfactualAnalysis object
            - 'contradictory_evidence': List of contradictory documents with scores
            - 'contradictory_citations': List of extracted citations
            - 'summary': Summary of findings
        """
        result = {
            'analysis': None,
            'contradictory_evidence': [],
            'contradictory_citations': [],
            'summary': {}
        }

        # Step 1: Perform counterfactual analysis
        self._call_callback("workflow_started", f"Analyzing document: {document_title}")

        analysis = self.analyze_document(document_content, document_title)
        if not analysis:
            logger.error("Failed to analyze document for counterfactual questions")
            return result

        result['analysis'] = analysis

        # Step 2: Generate database queries
        if query_agent is None:
            from .query_agent import QueryAgent
            query_agent = QueryAgent(model=get_model("query_agent"))

        high_priority_questions = self.get_high_priority_questions(analysis)
        self._call_callback("queries_generating", f"Creating {len(high_priority_questions)} priority queries")

        research_queries = self.generate_research_queries_with_agent(
            high_priority_questions, query_agent
        )

        # Step 3: Search database for contradictory evidence
        try:
            from ..database import find_abstracts
        except ImportError:
            logger.warning("Database module not available - cannot search for contradictory literature")
            result['summary'] = {
                'claims_analyzed': len(analysis.main_claims),
                'questions_generated': len(analysis.counterfactual_questions),
                'high_priority_questions': len(high_priority_questions),
                'database_available': False
            }
            return result

        all_contradictory_evidence = []

        if scoring_agent is None:
            from .scoring_agent import DocumentScoringAgent
            scoring_agent = DocumentScoringAgent(model=get_model("scoring_agent"))

        # Get retry configuration
        from ..config import get_search_config
        search_config = get_search_config()
        max_retries = search_config.get('query_retry_attempts', 3)
        auto_fix_syntax = search_config.get('auto_fix_tsquery_syntax', True)

        for query_info in research_queries:
            claim_short = query_info['target_claim'][:80] + "..." if len(query_info['target_claim']) > 80 else query_info['target_claim']
            self._call_callback("database_search", f"Searching: {claim_short}")

            # Log the PostgreSQL query for debugging
            db_query = query_info.get('db_query', 'N/A')
            logger.info(f"PostgreSQL query: {db_query}")
            self._call_callback("search_query", f"Query: {db_query}")

            # Try database search with retry mechanism
            results = search_with_retry(
                query_info,
                max_results_per_query,
                max_retries,
                auto_fix_syntax,
                callback=self.callback
            )

            num_found = len(results) if results else 0
            logger.info(f"Documents found: {num_found}")
            self._call_callback("search_results", f"Found {num_found} documents")

            if results:
                # Score documents for relevance using the counterfactual statement
                # (since that's what we searched for)
                num_scored = 0
                for result_doc in results:
                    score_result = scoring_agent.evaluate_document(
                        query_info['counterfactual_statement'], result_doc
                    )

                    if score_result and score_result['score'] >= min_relevance_score:
                        num_scored += 1
                        all_contradictory_evidence.append({
                            'document': result_doc,
                            'score': score_result['score'],
                            'reasoning': score_result['reasoning'],
                            'query_info': query_info
                        })

                logger.info(f"Documents passing score threshold (>={min_relevance_score}): {num_scored}/{num_found}")
                self._call_callback("scoring_complete", f"Passed scoring: {num_scored}/{num_found}")

        result['contradictory_evidence'] = all_contradictory_evidence

        # Step 4: Extract citations from contradictory evidence
        if all_contradictory_evidence:
            if citation_agent is None:
                from .citation_agent import CitationFinderAgent
                citation_agent = CitationFinderAgent(model=get_model("citation_agent"))

            num_docs_to_process = min(10, len(all_contradictory_evidence))
            self._call_callback("citations_extracting", f"Extracting citations from top {num_docs_to_process} documents")
            logger.info(f"Processing top {num_docs_to_process} documents for citation extraction")

            contradictory_citations = []
            num_citations_extracted = 0
            num_citations_validated = 0
            num_citations_rejected = 0

            # Process top contradictory evidence (sorted by score)
            sorted_evidence = sorted(all_contradictory_evidence, key=lambda x: x['score'], reverse=True)

            for idx, evidence in enumerate(sorted_evidence[:10], 1):  # Limit to top 10 for performance
                doc = evidence['document']
                query_info = evidence['query_info']
                doc_title = doc.get('title', 'Unknown')[:60] + "..." if len(doc.get('title', '')) > 60 else doc.get('title', 'Unknown')

                logger.info(f"Processing document {idx}/{num_docs_to_process}: {doc_title}")

                # Use counterfactual statement for citation extraction
                citation = citation_agent.extract_citation_from_document(
                    query_info['counterfactual_statement'], doc, min_relevance=0.4
                )

                if citation:
                    num_citations_extracted += 1
                    logger.info(f"  ✓ Citation extracted from: {citation.document_title}")

                    # CRITICAL VALIDATION: Verify the passage actually SUPPORTS the counterfactual
                    # (not just topically related to it)
                    logger.info(f"  → Validating citation supports counterfactual...")
                    supports_counterfactual = validate_citation_supports_counterfactual(
                        citation.passage,
                        citation.summary,
                        query_info['counterfactual_statement'],
                        query_info['target_claim'],
                        self._make_ollama_request,
                        self._parse_json_response
                    )

                    if supports_counterfactual:
                        num_citations_validated += 1
                        logger.info(f"  ✓ Citation VALIDATED (supports counterfactual)")
                        contradictory_citations.append({
                            'citation': citation,
                            'original_claim': query_info['target_claim'],
                            'counterfactual_statement': query_info['counterfactual_statement'],
                            'counterfactual_question': query_info['question'],
                            'document_score': evidence['score'],
                            'score_reasoning': evidence['reasoning']
                        })
                    else:
                        num_citations_rejected += 1
                        logger.info(f"  ✗ Citation REJECTED (does not support counterfactual): {citation.document_title}")
                else:
                    logger.info(f"  - No citation extracted from: {doc_title}")

            logger.info(f"Citation extraction summary: Extracted={num_citations_extracted}, Validated={num_citations_validated}, Rejected={num_citations_rejected}")
            self._call_callback("validation_complete", f"Citations: {num_citations_extracted} extracted, {num_citations_validated} validated, {num_citations_rejected} rejected")

            result['contradictory_citations'] = contradictory_citations
            self._call_callback("workflow_complete", f"Found {len(contradictory_citations)} valid contradictory citations")

        # Generate formatted counterfactual report
        formatted_result = format_counterfactual_report(
            analysis,
            research_queries,
            result.get('contradictory_citations', []),
            all_contradictory_evidence,
            assess_counter_evidence_strength
        )

        # Keep original result structure for backwards compatibility
        result['summary'] = {
            'document_title': document_title,
            'original_confidence': analysis.confidence_level,
            'claims_analyzed': len(analysis.main_claims),
            'questions_generated': len(analysis.counterfactual_questions),
            'high_priority_questions': len(high_priority_questions),
            'database_searches': len(research_queries),
            'contradictory_documents_found': len(all_contradictory_evidence),
            'contradictory_citations_extracted': len(result.get('contradictory_citations', [])),
            'database_available': True,
            'revised_confidence': 'MEDIUM-LOW' if result.get('contradictory_citations') else analysis.confidence_level
        }

        # Add formatted report to result
        result['formatted_report'] = formatted_result

        return result
