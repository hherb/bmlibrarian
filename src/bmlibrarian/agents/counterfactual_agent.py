"""
Counterfactual Checking Agent for analyzing documents and generating contradictory research questions.

This agent analyzes documents (such as generated reports) and suggests literature research 
questions designed to find evidence that might contradict the document's claims or conclusions.
This is essential for rigorous academic research and evidence evaluation.
"""

import json
import logging
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass
from datetime import datetime, timezone

from .base import BaseAgent
from ..config import get_config, get_model, get_agent_config

logger = logging.getLogger(__name__)


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
        
        Fixes common issues like unquoted multi-word phrases and invalid syntax.
        
        Args:
            query: Raw query string from QueryAgent
            
        Returns:
            Cleaned query string safe for PostgreSQL to_tsquery
        """
        import re
        
        # Remove any function prefixes that the LLM might have added
        query = query.strip()
        
        # Remove "to_tsquery:", "tsquery:", etc. prefixes
        prefixes_to_remove = ['to_tsquery:', 'tsquery:', 'query:', 'search:']
        for prefix in prefixes_to_remove:
            if query.lower().startswith(prefix.lower()):
                query = query[len(prefix):].strip()
        
        # Remove any outer quotes that might have been added
        if query.startswith('"') and query.endswith('"'):
            query = query[1:-1]
        if query.startswith("'") and query.endswith("'"):
            query = query[1:-1]
        
        # Find unquoted multi-word phrases and quote them
        # Pattern: word spaces word that are not already quoted
        def quote_unquoted_phrases(text):
            # Split by operators but preserve them
            parts = re.split(r'(\s*[&|()]\s*)', text)
            result_parts = []
            
            for part in parts:
                part = part.strip()
                if not part or part in ['&', '|', '(', ')']:
                    result_parts.append(part)
                    continue
                
                # Check if this part contains spaces and isn't already quoted
                if ' ' in part and not (part.startswith("'") and part.endswith("'")):
                    # Quote it and escape internal quotes
                    clean_part = part.replace("'", "''")
                    result_parts.append(f"'{clean_part}'")
                else:
                    result_parts.append(part)
            
            return ' '.join(result_parts)
        
        # Apply the cleaning
        cleaned_query = quote_unquoted_phrases(query)
        
        # Fix any double quotes that might have been created
        cleaned_query = re.sub(r"'''+", "''", cleaned_query)  # Multiple single quotes to double quote
        cleaned_query = re.sub(r'"""*', '"', cleaned_query)   # Multiple double quotes to single
        
        # Remove any double spaces and clean up
        cleaned_query = re.sub(r'\s+', ' ', cleaned_query).strip()
        
        return cleaned_query

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
                
                research_queries.append({
                    'question': question.question,
                    'db_query': db_query,
                    'target_claim': question.target_claim,
                    'search_keywords': question.search_keywords,
                    'priority': question.priority,
                    'reasoning': question.reasoning
                })
                
                logger.debug(f"Generated query for '{question.question[:50]}...': {db_query}")
                
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
        
        for query_info in research_queries:
            self._call_callback("database_search", f"Searching: {query_info['target_claim']}")
            
            try:
                # find_abstracts returns a generator and uses max_rows parameter
                results_generator = find_abstracts(
                    query_info['db_query'], 
                    max_rows=max_results_per_query,
                    plain=False  # Use advanced to_tsquery syntax
                )
                
                # Convert generator to list and check if results exist
                results = list(results_generator)
                
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
                            
            except Exception as e:
                logger.warning(f"Database search failed for query '{query_info['question']}': {e}")
        
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
        
        # Generate summary
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
        
        return result