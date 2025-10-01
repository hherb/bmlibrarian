"""
Counterfactual Checking Agent for analyzing documents and generating contradictory research questions.

This agent analyzes documents (such as generated reports) and suggests literature research 
questions designed to find evidence that might contradict the document's claims or conclusions.
This is essential for rigorous academic research and evidence evaluation.
"""

import json
import logging
import re
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass
from datetime import datetime, timezone

from .base import BaseAgent
from ..config import get_config, get_model, get_agent_config

logger = logging.getLogger(__name__)


def fix_tsquery_syntax(query: str) -> str:
    """
    Fix PostgreSQL tsquery syntax errors without oversimplifying queries.
    
    Focuses on quote escaping and malformed syntax patterns that cause 
    "syntax error in tsquery" without reducing query complexity.
    
    Args:
        query: The original tsquery string
        
    Returns:
        Fixed tsquery string with corrected syntax but preserved complexity
    """
    # Basic cleanup - remove function prefixes
    query = query.strip()
    if query.startswith(('to_tsquery:', 'tsquery:')):
        query = re.sub(r'^[a-z_]+:\s*', '', query, flags=re.IGNORECASE)
    
    # Remove outer quotes that wrap the entire query
    if (query.startswith('"') and query.endswith('"')) or (query.startswith("'") and query.endswith("'")):
        query = query[1:-1]
    
    # CRITICAL FIX: Handle the specific malformed quote patterns causing errors
    # Fix patterns like: '(''phrase''' -> 'phrase'
    query = re.sub(r"'\(\s*''([^']+)''\s*'", r"'\1'", query)
    query = re.sub(r"'\(\s*''([^']+)'''\s*'", r"'\1'", query)
    
    # Fix patterns like: '''phrase''' -> 'phrase'  
    query = re.sub(r"'''([^']+)'''", r"'\1'", query)
    query = re.sub(r"''([^']+)''", r"'\1'", query)
    
    # Fix quotes around operators: '&' -> &, '|' -> |
    query = re.sub(r"'(\s*[&|]\s*)'", r'\1', query)
    
    # Fix quotes around parentheses: '(' -> (, ')' -> )
    query = re.sub(r"'\s*\(\s*'", '(', query)
    query = re.sub(r"'\s*\)\s*'", ')', query)
    
    # Convert double quotes to single quotes consistently
    query = re.sub(r'"([^"]*)"', r"'\1'", query)
    
    # Handle operator syntax
    query = re.sub(r'\sOR\s', ' | ', query, flags=re.IGNORECASE)
    query = re.sub(r'\sAND\s', ' & ', query, flags=re.IGNORECASE)
    
    # Clean up spacing around operators (preserve structure)
    query = re.sub(r'\s*\|\s*', ' | ', query)
    query = re.sub(r'\s*&\s*', ' & ', query)
    query = re.sub(r'\s*\(\s*', '(', query)
    query = re.sub(r'\s*\)\s*', ')', query)
    
    # Fix phrase quoting: add quotes to multi-word phrases, remove from single words
    def fix_phrase_quoting(text):
        # Split on operators and parentheses while preserving them
        parts = re.split(r'(\s*[&|()]\s*)', text)
        fixed_parts = []
        
        for part in parts:
            part = part.strip()
            # Skip operators and parentheses
            if not part or part in ['&', '|', '(', ')'] or re.match(r'^\s*[&|()]+\s*$', part):
                fixed_parts.append(part)
                continue
            
            # Clean existing quotes
            clean_part = part.strip("'\"")
            
            # Quote multi-word phrases (including hyphenated terms), leave single words unquoted
            if ' ' in clean_part or '-' in clean_part:
                # Escape internal quotes and wrap in quotes
                escaped = clean_part.replace("'", "''")
                fixed_parts.append(f"'{escaped}'")
            else:
                fixed_parts.append(clean_part)
        
        return ''.join(fixed_parts)
    
    query = fix_phrase_quoting(query)
    
    # Fix empty quoted strings
    query = re.sub(r"'\s*'", '', query)
    
    # Clean up extra spaces
    query = re.sub(r'\s+', ' ', query).strip()
    
    return query


def simplify_query_for_retry(query: str, attempt: int) -> str:
    """
    Fix tsquery syntax errors with progressive approaches while preserving query complexity.
    
    Args:
        query: The query to fix
        attempt: The retry attempt number (1, 2, 3, etc.)
        
    Returns:
        Query string with syntax fixes applied
    """
    if attempt == 1:
        # First retry: Apply comprehensive syntax fixes but preserve structure
        query = fix_tsquery_syntax(query)
        
        # Additional fix for specific problematic patterns seen in errors
        # Fix patterns like: & '('"phrase"')' -> & 'phrase'
        query = re.sub(r"&\s*'\(\s*['\"]([^'\"]+)['\"]?\s*\)\s*'", r"& '\1'", query)
        query = re.sub(r"\|\s*'\(\s*['\"]([^'\"]+)['\"]?\s*\)\s*'", r"| '\1'", query)
        
        # Fix standalone quotes around complex expressions
        query = re.sub(r"'\s*\(([^)]+)\)\s*'", r'(\1)', query)
        
    elif attempt == 2:
        # Second retry: More aggressive quote fixing while preserving logic
        query = fix_tsquery_syntax(query)
        
        # Handle nested quote issues more aggressively  
        # Fix pattern: (phrase1 | phrase2) & '('"phrase3"')' 
        query = re.sub(r"'\(\s*['\"]([^'\"]+)['\"]?\s*\)'", r"'\1'", query)
        
        # Ensure proper phrase quoting - multi-word phrases get quotes, single words don't
        def fix_phrase_quoting(text):
            # Split on operators and parentheses while preserving them
            parts = re.split(r'(\s*[&|()]\s*)', text)
            fixed_parts = []
            
            for part in parts:
                part = part.strip()
                # Skip operators and parentheses
                if not part or part in ['&', '|', '(', ')'] or re.match(r'^\s*[&|()]+\s*$', part):
                    fixed_parts.append(part)
                    continue
                
                # Clean existing quotes
                clean_part = part.strip("'\"")
                
                # Quote multi-word phrases, leave single words unquoted
                if ' ' in clean_part:
                    # Escape internal quotes and wrap in quotes
                    escaped = clean_part.replace("'", "''")
                    fixed_parts.append(f"'{escaped}'")
                else:
                    fixed_parts.append(clean_part)
            
            return ''.join(fixed_parts)
        
        query = fix_phrase_quoting(query)
        
    elif attempt >= 3:
        # Final retry: Preserve original query but ensure basic syntax correctness
        query = fix_tsquery_syntax(query)
        
        # Last resort fixes for any remaining syntax issues
        # Remove any malformed quote combinations
        query = re.sub(r"['\"]+'", "'", query)  # Multiple quotes become single quote
        query = re.sub(r"'+['\"]", "'", query)  # Mixed quotes become single quote
        
        # Ensure no empty quoted expressions
        query = re.sub(r"'\s*'", "", query)
        
        # Final operator cleanup
        query = re.sub(r'\s*&\s*', ' & ', query)
        query = re.sub(r'\s*\|\s*', ' | ', query)
        
    return query.strip()


def extract_keywords_from_question(question: str) -> str:
    """
    Extract main keywords from a research question as fallback query.
    
    Args:
        question: Research question text
        
    Returns:
        Simple keyword-based tsquery
    """
    # Remove common question words
    stop_words = {'are', 'is', 'was', 'were', 'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'there', 'studies', 'showing', 'compared'}
    
    # Extract meaningful words (3+ characters, not stop words)
    words = re.findall(r'\b[a-zA-Z]{3,}\b', question.lower())
    keywords = [word for word in words if word not in stop_words]
    
    # Take first 4-5 most relevant keywords
    return ' & '.join(keywords[:5]) if keywords else 'medical'


@dataclass
class CounterfactualQuestion:
    """Represents a research question designed to find contradictory evidence."""
    question: str
    reasoning: str
    target_claim: str  # The specific claim this question targets
    search_keywords: List[str]  # Suggested keywords for literature search
    priority: str  # HIGH, MEDIUM, LOW based on importance of the claim
    created_at: Optional[datetime] = None
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now(timezone.utc)


@dataclass
class CounterfactualAnalysis:
    """Complete analysis of a document with suggested counterfactual questions."""
    document_title: str
    main_claims: List[str]
    counterfactual_questions: List[CounterfactualQuestion]
    overall_assessment: str
    confidence_level: str  # HIGH, MEDIUM, LOW - how confident we are in the document's claims
    created_at: Optional[datetime] = None
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now(timezone.utc)


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
2. For each factual statement, generate DIRECT counterfactual questions that would contradict it
3. Create search-ready questions that can be converted to database queries

Guidelines for counterfactual question generation:
- Extract specific claims like "Drug X is first-line treatment for Disease Y" → "What are alternative first-line treatments for Disease Y?"
- Convert dosage claims like "10mg daily is optimal" → "What are the reported adverse effects of 10mg daily dosing?"
- Challenge effectiveness claims like "Treatment reduces risk by 30%" → "Studies showing Treatment ineffectiveness or increased risk"
- Question population claims like "Effective in elderly" → "Treatment effectiveness in different age groups"

IMPORTANT: Generate DIRECT, SPECIFIC questions that can be searched:
✓ GOOD: "What are the first-line antibiotics for melioidosis treatment?"
✓ GOOD: "Ceftazidime treatment failure in melioidosis cases"  
✓ GOOD: "Alternative treatments when ceftazidime fails in melioidosis"
✗ BAD: "Are there methodological limitations in the studies?"
✗ BAD: "Could there be confounding factors affecting the results?"

For search_keywords, provide concrete medical terms:
- Use specific drug names, diseases, treatments
- Include failure/adverse/alternative terms when appropriate
- Examples: "ceftazidime", "melioidosis", "treatment failure", "first-line", "antibiotic resistance"

Response Format:
Return ONLY a valid JSON object with this exact structure:

{
    "main_claims": [
        "Specific factual claim from the document (e.g., 'Ceftazidime is first-line treatment for melioidosis')"
    ],
    "counterfactual_questions": [
        {
            "question": "Direct searchable question to find contradictory evidence (e.g., 'What are alternative first-line treatments for melioidosis?')",
            "reasoning": "What this would prove if contradictory evidence is found",
            "target_claim": "The exact claim this question challenges",
            "search_keywords": ["specific", "medical", "terms"],
            "priority": "HIGH|MEDIUM|LOW"
        }
    ],
    "overall_assessment": "Brief assessment of how testable these claims are",
    "confidence_level": "HIGH|MEDIUM|LOW - how much contradictory evidence might exist"
}

Focus on concrete, searchable questions that would directly contradict specific claims."""

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
                    # First, try to extract JSON from the response if it contains extra text
                    response_cleaned = response.strip()
                    
                    # Look for JSON object in the response
                    json_start = response_cleaned.find('{')
                    json_end = response_cleaned.rfind('}')
                    
                    if json_start != -1 and json_end != -1 and json_end > json_start:
                        json_part = response_cleaned[json_start:json_end + 1]
                        result_data = json.loads(json_part)
                    else:
                        # Try parsing the whole response as JSON
                        result_data = json.loads(response_cleaned)
                    
                    # Validate required fields
                    required_fields = ['main_claims', 'counterfactual_questions', 'overall_assessment', 'confidence_level']
                    for field in required_fields:
                        if field not in result_data:
                            raise ValueError(f"Missing required field: {field}")
                    
                    # Create CounterfactualQuestion objects
                    counterfactual_questions = []
                    for q_data in result_data['counterfactual_questions']:
                        # Validate question structure
                        required_q_fields = ['question', 'reasoning', 'target_claim', 'search_keywords', 'priority']
                        for field in required_q_fields:
                            if field not in q_data:
                                raise ValueError(f"Missing required question field: {field}")
                        
                        question = CounterfactualQuestion(
                            question=q_data['question'],
                            reasoning=q_data['reasoning'],
                            target_claim=q_data['target_claim'],
                            search_keywords=q_data['search_keywords'],
                            priority=q_data['priority'].upper()
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
        # Use the improved fix_tsquery_syntax function
        return fix_tsquery_syntax(query)

    def generate_research_queries_with_agent(self, questions: List[CounterfactualQuestion], query_agent=None) -> List[Dict[str, str]]:
        """
        Generate database-ready research queries by directly using the QueryAgent on counterfactual questions.
        
        Args:
            questions: List of CounterfactualQuestion objects
            query_agent: QueryAgent instance for proper query formatting
            
        Returns:
            List of dictionaries with 'question', 'query', and 'metadata'
        """
        if query_agent is None:
            # Import here to avoid circular imports
            from .query_agent import QueryAgent
            query_agent = QueryAgent(model=get_model("query_agent"))
        
        research_queries = []
        
        for question in questions:
            try:
                # Use the counterfactual question directly with the QueryAgent
                # The questions are now designed to be search-ready
                db_query = query_agent.convert_question(question.question)
                
                # Clean the query to ensure PostgreSQL compatibility (fix double quotes)
                cleaned_query = self._clean_tsquery(db_query)
                
                research_queries.append({
                    'question': question.question,
                    'db_query': cleaned_query,
                    'target_claim': question.target_claim,
                    'search_keywords': question.search_keywords,
                    'priority': question.priority,
                    'reasoning': question.reasoning
                })
                
                logger.debug(f"Generated query for '{question.question[:50]}...': {cleaned_query}")
                
            except Exception as e:
                logger.warning(f"QueryAgent failed for question '{question.question}': {e}")
                logger.info(f"Skipping question that couldn't be converted to database query")
                # Skip questions that can't be converted rather than using poor fallbacks
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
        protocol = f"""# Counterfactual Research Protocol
Document: {analysis.document_title}
Generated: {analysis.created_at.strftime('%Y-%m-%d %H:%M:%S') if analysis.created_at else 'Unknown'}
Confidence in Original Claims: {analysis.confidence_level}

## Main Claims to Verify
"""
        for i, claim in enumerate(analysis.main_claims, 1):
            protocol += f"{i}. {claim}\n"
        
        protocol += f"\n## Overall Assessment\n{analysis.overall_assessment}\n\n"
        
        # Group questions by priority
        high_priority = [q for q in analysis.counterfactual_questions if q.priority == "HIGH"]
        medium_priority = [q for q in analysis.counterfactual_questions if q.priority == "MEDIUM"] 
        low_priority = [q for q in analysis.counterfactual_questions if q.priority == "LOW"]
        
        for priority_group, priority_name in [(high_priority, "HIGH PRIORITY"), 
                                            (medium_priority, "MEDIUM PRIORITY"),
                                            (low_priority, "LOW PRIORITY")]:
            if priority_group:
                protocol += f"## {priority_name} Research Questions\n\n"
                for i, question in enumerate(priority_group, 1):
                    protocol += f"### Question {i}\n"
                    protocol += f"**Research Question:** {question.question}\n\n"
                    protocol += f"**Target Claim:** {question.target_claim}\n\n"
                    protocol += f"**Reasoning:** {question.reasoning}\n\n"
                    protocol += f"**Search Keywords:** {', '.join(question.search_keywords)}\n\n"
                    protocol += "---\n\n"
        
        return protocol
    
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
            self._call_callback("database_search", f"Searching: {query_info['target_claim']}")
            
            # Try database search with retry mechanism
            results = self._search_with_retry(
                query_info, 
                max_results_per_query, 
                max_retries,
                auto_fix_syntax
            )
            
            if results:
                # Score documents for relevance
                for result in results:
                    score_result = scoring_agent.evaluate_document(
                        query_info['question'], result
                    )
                    
                    if score_result and score_result['score'] >= min_relevance_score:
                        all_contradictory_evidence.append({
                            'document': result,
                            'score': score_result['score'],
                            'reasoning': score_result['reasoning'],
                            'query_info': query_info
                        })
        
        result['contradictory_evidence'] = all_contradictory_evidence
        
        # Step 4: Extract citations from contradictory evidence
        if all_contradictory_evidence:
            if citation_agent is None:
                from .citation_agent import CitationFinderAgent
                citation_agent = CitationFinderAgent(model=get_model("citation_agent"))
            
            self._call_callback("citations_extracting", f"Extracting citations from {len(all_contradictory_evidence)} documents")
            
            contradictory_citations = []
            
            # Process top contradictory evidence (sorted by score)
            sorted_evidence = sorted(all_contradictory_evidence, key=lambda x: x['score'], reverse=True)
            
            for evidence in sorted_evidence[:10]:  # Limit to top 10 for performance
                doc = evidence['document']
                query_info = evidence['query_info']
                
                citation = citation_agent.extract_citation_from_document(
                    query_info['question'], doc, min_relevance=0.4
                )
                
                if citation:
                    contradictory_citations.append({
                        'citation': citation,
                        'original_claim': query_info['target_claim'],
                        'counterfactual_question': query_info['question'],
                        'document_score': evidence['score'],
                        'score_reasoning': evidence['reasoning']
                    })
            
            result['contradictory_citations'] = contradictory_citations
            self._call_callback("workflow_complete", f"Found {len(contradictory_citations)} contradictory citations")
        
        # Generate formatted counterfactual report
        formatted_result = self._format_counterfactual_report(
            analysis, 
            research_queries,
            result.get('contradictory_citations', []),
            all_contradictory_evidence
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
    
    def _format_counterfactual_report(
        self,
        analysis: 'CounterfactualAnalysis',
        research_queries: List[Dict[str, str]],
        contradictory_citations: List[Dict[str, Any]],
        contradictory_evidence: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Format counterfactual analysis results into the structured claim/statement/evidence format.

        Args:
            analysis: CounterfactualAnalysis object with original claims
            research_queries: List of query information with target claims
            contradictory_citations: List of contradictory citations found
            contradictory_evidence: List of contradictory documents found

        Returns:
            Structured format with claims, counterfactual statements, evidence, critical assessment, and summary
        """
        formatted_items = []

        # Create a mapping from claims to their counterfactual questions
        claim_to_question = {}
        for query_info in research_queries:
            target_claim = query_info.get('target_claim', '')
            counterfactual_question = query_info.get('question', '')
            if target_claim and counterfactual_question:
                claim_to_question[target_claim] = counterfactual_question

        # Group citations by their original claims
        claims_with_evidence = {}
        for citation_item in contradictory_citations:
            original_claim = citation_item.get('original_claim', 'Unknown claim')
            if original_claim not in claims_with_evidence:
                claims_with_evidence[original_claim] = {
                    'claim': original_claim,
                    'counterfactual_statement': citation_item.get('counterfactual_question', ''),
                    'citations': []
                }

            citation = citation_item.get('citation')
            if citation:
                claims_with_evidence[original_claim]['citations'].append({
                    'title': getattr(citation, 'document_title', 'Unknown title'),
                    'content': getattr(citation, 'summary', 'No content available'),
                    'passage': getattr(citation, 'passage', ''),
                    'relevance_score': getattr(citation, 'relevance_score', 0),
                    'document_score': citation_item.get('document_score', 0),
                    'score_reasoning': citation_item.get('score_reasoning', '')
                })

        # Process ALL claims from the original analysis (not just those with evidence)
        for main_claim in analysis.main_claims:
            # Check if we found evidence for this claim
            if main_claim in claims_with_evidence:
                # We have contradictory evidence
                claim_data = claims_with_evidence[main_claim]
                citations = claim_data['citations']

                # Critical assessment based on evidence strength
                assessment = self._assess_counter_evidence_strength(
                    main_claim,
                    claim_data['counterfactual_statement'],
                    citations
                )

                formatted_item = {
                    'claim': main_claim,
                    'counterfactual_statement': claim_data['counterfactual_statement'],
                    'counterfactual_evidence': citations,
                    'evidence_found': True,
                    'critical_assessment': assessment
                }
            else:
                # No contradictory evidence found for this claim
                counterfactual_statement = claim_to_question.get(main_claim, 'No counterfactual question generated')

                formatted_item = {
                    'claim': main_claim,
                    'counterfactual_statement': counterfactual_statement,
                    'counterfactual_evidence': [],
                    'evidence_found': False,
                    'critical_assessment': 'No contradictory evidence found in the database. This claim appears well-supported or lacks available counter-evidence in the current literature database.'
                }

            formatted_items.append(formatted_item)

        # Generate overall summary
        total_claims = len(analysis.main_claims)
        claims_with_evidence_count = len([item for item in formatted_items if item['evidence_found']])
        total_citations = sum(len(item['counterfactual_evidence']) for item in formatted_items)

        confidence_assessment = analysis.confidence_level
        if total_citations > 0:
            if total_citations >= 3:
                confidence_assessment = "LOW - Multiple contradictory studies found"
            elif total_citations >= 1:
                confidence_assessment = "MEDIUM-LOW - Some contradictory evidence found"

        summary_statement = f"""
Counterfactual Analysis Summary:
- Original report confidence: {analysis.confidence_level}
- Claims analyzed: {total_claims}
- Claims with contradictory evidence: {claims_with_evidence_count}
- Claims without contradictory evidence: {total_claims - claims_with_evidence_count}
- Total contradictory citations found: {total_citations}
- Revised confidence assessment: {confidence_assessment}

{f"WARNING: Found {total_citations} citations that contradict {claims_with_evidence_count} of {total_claims} key claims in the original report. " if total_citations > 0 else "No contradictory evidence found for any claims. "}
{"The original conclusions should be interpreted with caution given the contradictory evidence." if total_citations >= 2 else ""}
        """.strip()

        return {
            'items': formatted_items,
            'summary_statement': summary_statement,
            'statistics': {
                'total_claims_analyzed': total_claims,
                'claims_with_contradictory_evidence': claims_with_evidence_count,
                'claims_without_contradictory_evidence': total_claims - claims_with_evidence_count,
                'total_contradictory_citations': total_citations,
                'original_confidence': analysis.confidence_level,
                'revised_confidence': confidence_assessment
            }
        }

    def _assess_counter_evidence_strength(
        self,
        original_claim: str,
        counterfactual_statement: str,
        citations: List[Dict[str, Any]]
    ) -> str:
        """
        Assess whether the counter-evidence is sufficient to challenge or reject the original claim.

        Args:
            original_claim: The original claim being challenged
            counterfactual_statement: The counterfactual research question
            citations: List of contradictory citations found

        Returns:
            Critical assessment string explaining the strength of counter-evidence
        """
        if not citations:
            return "No contradictory evidence found."

        num_citations = len(citations)
        avg_document_score = sum(c.get('document_score', 0) for c in citations) / num_citations
        avg_relevance_score = sum(c.get('relevance_score', 0) for c in citations) / num_citations
        high_quality_citations = sum(1 for c in citations if c.get('document_score', 0) >= 4)

        # Build assessment based on quantity and quality
        assessment_parts = []

        # Quantity assessment
        if num_citations >= 3:
            assessment_parts.append(f"**Multiple sources ({num_citations} citations)** provide contradictory evidence.")
        elif num_citations == 2:
            assessment_parts.append(f"**Two independent sources** provide contradictory evidence.")
        else:
            assessment_parts.append(f"**Single source** provides contradictory evidence.")

        # Quality assessment
        if avg_document_score >= 4.0:
            assessment_parts.append(f"The counter-evidence is **highly relevant** (avg. relevance: {avg_document_score:.1f}/5).")
        elif avg_document_score >= 3.0:
            assessment_parts.append(f"The counter-evidence is **moderately relevant** (avg. relevance: {avg_document_score:.1f}/5).")
        else:
            assessment_parts.append(f"The counter-evidence is **weakly relevant** (avg. relevance: {avg_document_score:.1f}/5).")

        # Strength conclusion
        if num_citations >= 3 and avg_document_score >= 4.0:
            conclusion = "**STRONG CHALLENGE**: The contradictory evidence is substantial and highly relevant, significantly undermining confidence in the original claim."
        elif num_citations >= 2 and avg_document_score >= 3.5:
            conclusion = "**MODERATE CHALLENGE**: The contradictory evidence raises important questions about the original claim's validity and warrants careful consideration."
        elif num_citations >= 1 and avg_document_score >= 3.0:
            conclusion = "**WEAK CHALLENGE**: The contradictory evidence suggests alternative interpretations exist, but is insufficient to reject the original claim."
        else:
            conclusion = "**MINIMAL CHALLENGE**: The contradictory evidence is limited in quantity or relevance, providing only marginal challenges to the original claim."

        assessment_parts.append(conclusion)

        return " ".join(assessment_parts)
    
    def _search_with_retry(self, query_info: Dict[str, str], max_results: int, max_retries: int, auto_fix_syntax: bool) -> List[Dict]:
        """
        Search database with automatic retry and query reformulation on syntax errors.
        
        Args:
            query_info: Dictionary containing 'db_query', 'question', and 'target_claim'
            max_results: Maximum number of results to return
            max_retries: Maximum number of retry attempts
            auto_fix_syntax: Whether to automatically fix syntax errors
            
        Returns:
            List of document dictionaries, or empty list if all attempts fail
        """
        try:
            from ..database import find_abstracts
        except ImportError:
            logger.error("Database module not available")
            return []
        
        original_query = query_info['db_query']
        question = query_info['question']
        target_claim = query_info['target_claim']
        
        for attempt in range(max_retries + 1):  # +1 for the original attempt
            try:
                if attempt == 0:
                    # First attempt: use original query
                    current_query = original_query
                    self._call_callback("database_search", f"Attempting search: {target_claim[:50]}...")
                else:
                    # Retry attempts: reformulate query
                    if auto_fix_syntax:
                        current_query = simplify_query_for_retry(original_query, attempt)
                    else:
                        # Fallback to keywords if no auto-fix
                        current_query = extract_keywords_from_question(question)
                    
                    self._call_callback(
                        "database_search", 
                        f"Retry {attempt}/{max_retries}: Reformulated query for '{target_claim[:40]}...'"
                    )
                    logger.info(f"Query retry {attempt}: '{original_query}' -> '{current_query}'")
                
                # Attempt database search
                results_generator = find_abstracts(
                    current_query,
                    max_rows=max_results,
                    plain=False  # Use advanced to_tsquery syntax
                )
                
                # Convert generator to list
                results = list(results_generator)
                
                if results:
                    # Success! Log and return results
                    if attempt > 0:
                        logger.info(f"Query retry {attempt} succeeded with {len(results)} results")
                        self._call_callback("database_search", f"Retry {attempt} succeeded: {len(results)} results found")
                    else:
                        logger.debug(f"Query succeeded on first attempt: {len(results)} results")
                    
                    return results
                else:
                    # No results, but no error - this is not a syntax error
                    if attempt == 0:
                        logger.info(f"Query returned no results: '{current_query}'")
                    continue
                    
            except Exception as e:
                error_msg = str(e).lower()
                
                # Check if this is a tsquery syntax error
                if 'syntax error in tsquery' in error_msg or 'tsquery' in error_msg:
                    if attempt < max_retries:
                        logger.warning(f"tsquery syntax error on attempt {attempt + 1}: {e}")
                        self._call_callback(
                            "database_search", 
                            f"Query syntax error, attempting reformulation (attempt {attempt + 1}/{max_retries})..."
                        )
                        continue  # Try next reformulation
                    else:
                        # Final attempt failed with syntax error
                        logger.error(f"Query failed after {max_retries} retries with syntax error: {e}")
                        self._call_callback(
                            "database_search", 
                            f"Query failed after {max_retries} retries: {str(e)[:100]}..."
                        )
                        break
                else:
                    # Non-syntax error (database connection, etc.)
                    logger.error(f"Database search failed with non-syntax error: {e}")
                    self._call_callback("database_search", f"Database error: {str(e)[:100]}...")
                    break
        
        # All attempts failed
        logger.warning(f"All {max_retries + 1} search attempts failed for question: '{question[:100]}...'")
        return []