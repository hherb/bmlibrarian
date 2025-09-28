"""
Document Scoring Agent for Relevance Assessment

Specialized agent that evaluates how well documents match user questions,
providing numerical scores and reasoning for document relevance assessment.
"""

import json
import logging
from typing import Dict, Optional, Callable, TypedDict, List, Tuple, Iterator

from .base import BaseAgent
from .queue_manager import TaskPriority


logger = logging.getLogger(__name__)


class ScoringResult(TypedDict):
    """Result structure for document scoring."""
    score: int  # 0-5 relevance score
    reasoning: str  # Explanation for the score


class DocumentScoringAgent(BaseAgent):
    """
    Agent for scoring document relevance to user questions.
    
    Evaluates biomedical documents against user questions using an LLM
    to provide structured relevance scores and reasoning.
    """
    
    def __init__(
        self,
        model: str = "gpt-oss:20b",
        host: str = "http://localhost:11434",
        temperature: float = 0.1,
        top_p: float = 0.9,
        callback: Optional[Callable[[str, str], None]] = None,
        orchestrator: Optional["AgentOrchestrator"] = None,
        show_model_info: bool = True
    ):
        """
        Initialize the DocumentScoringAgent.
        
        Args:
            model: The name of the Ollama model to use (default: gpt-oss:20b)
            host: The Ollama server host URL (default: http://localhost:11434)
            temperature: Model temperature for consistent scoring (default: 0.1)
            top_p: Model top-p sampling parameter (default: 0.9)
            callback: Optional callback function for progress updates
            orchestrator: Optional orchestrator for queue-based processing
            show_model_info: Whether to display model information on initialization
        """
        super().__init__(model, host, temperature, top_p, callback, orchestrator, show_model_info)
        
        # System prompt for document relevance scoring
        self.system_prompt = """You are a biomedical literature expert evaluating document relevance. Your task is to score how well a document answers or relates to a user's question.

Scoring Scale:
- 0: Document is not related to the user question at all
- 1: Document is tangentially related but doesn't address the question
- 2: Document is somewhat related and provides minimal relevant information
- 3: Document contributes significantly to answering the question
- 4: Document addresses the question well with substantial relevant content
- 5: Document completely answers the user question with comprehensive information

Instructions:
1. Analyze the user question to understand what information they seek
2. Examine the document title, abstract, and available metadata
3. Determine how well the document addresses the specific question
4. Provide a score (0-5) and clear reasoning for your assessment
5. Focus on content relevance, not just topic similarity

Response Format:
Return ONLY a valid JSON object with this exact structure. Do not include any text before or after the JSON:
{
    "score": <integer 0-5>,
    "reasoning": "<clear explanation for the score>"
}

IMPORTANT: 
- Return RAW JSON only - no markdown code blocks (```json) or backticks
- Ensure the JSON is complete and properly closed
- Keep reasoning under 200 characters to avoid truncation
- Use only double quotes for JSON strings
- Do not include trailing commas
- Do not wrap the JSON in any formatting

Example Response:
{
    "score": 4,
    "reasoning": "Document addresses COVID vaccine effectiveness with clinical data and efficacy rates, covering main question aspects with substantial detail."
}"""
    
    def get_agent_type(self) -> str:
        """Get the agent type identifier."""
        return "document_scoring_agent"
    
    def evaluate_document(
        self,
        user_question: str,
        document: Dict
    ) -> ScoringResult:
        """
        Evaluate how well a document answers a user question.
        
        Args:
            user_question: The user's question or information need
            document: Document dictionary from database (must contain 'title' and 'abstract')
            
        Returns:
            ScoringResult with score (0-5) and reasoning
            
        Raises:
            ValueError: If inputs are invalid or missing required fields
            ConnectionError: If unable to connect to Ollama
            
        Examples:
            >>> agent = DocumentScoringAgent()
            >>> doc = {
            ...     'title': 'COVID-19 Vaccine Efficacy in Clinical Trials',
            ...     'abstract': 'This study evaluates the effectiveness of...',
            ...     'authors': ['Smith, J.', 'Doe, A.']
            ... }
            >>> result = agent.evaluate_document("How effective are COVID vaccines?", doc)
            >>> print(f"Score: {result['score']}, Reasoning: {result['reasoning']}")
        """
        # Validate inputs
        if not user_question or not user_question.strip():
            raise ValueError("User question cannot be empty")
        
        if not document or not isinstance(document, dict):
            raise ValueError("Document must be a non-empty dictionary")
        
        if 'title' not in document:
            raise ValueError("Document must contain 'title' field")
        
        # Extract relevant document information
        title = document.get('title', '')
        abstract = document.get('abstract', '')
        authors = document.get('authors', [])
        publication = document.get('publication', '')
        publication_date = document.get('publication_date', '')
        keywords = document.get('keywords', [])
        mesh_terms = document.get('mesh_terms', [])
        
        # Build document summary for evaluation
        doc_info = f"""Title: {title}

Abstract: {abstract}"""
        
        # Add additional metadata if available
        if authors:
            author_list = ', '.join(authors[:5])  # Limit to first 5 authors
            if len(authors) > 5:
                author_list += f" (and {len(authors) - 5} others)"
            doc_info += f"\n\nAuthors: {author_list}"
        
        if publication:
            doc_info += f"\nPublication: {publication}"
        
        if publication_date:
            doc_info += f"\nPublication Date: {publication_date}"
        
        if keywords:
            keyword_list = ', '.join(keywords[:10])  # Limit keywords
            doc_info += f"\nKeywords: {keyword_list}"
        
        if mesh_terms:
            mesh_list = ', '.join(mesh_terms[:10])  # Limit MeSH terms
            doc_info += f"\nMeSH Terms: {mesh_list}"
        
        # Create evaluation prompt
        evaluation_prompt = f"""User Question: {user_question}

Document to Evaluate:
{doc_info}

Please evaluate how well this document addresses the user's question and provide your assessment in the specified JSON format."""
        
        self._call_callback("evaluation_started", f"Question: {user_question}")
        
        # Retry logic for failed attempts
        max_retries = 3  # Increased from 2 to handle more edge cases
        response = None
        
        for attempt in range(max_retries + 1):
            try:
                messages = [{'role': 'user', 'content': evaluation_prompt}]
                
                response = self._make_ollama_request(
                    messages,
                    system_prompt=self.system_prompt,
                    num_predict=500 + (attempt * 100),  # Increase length on retries
                    temperature=0.1 + (attempt * 0.05)  # Slightly increase temp on retries
                )
                
                # Check if response looks complete (basic validation)
                if response and len(response.strip()) > 20 and (response.strip().endswith('}') or '"score"' in response):
                    break  # Success, exit retry loop
                else:
                    if attempt < max_retries:
                        logger.warning(f"Response appears incomplete on attempt {attempt + 1}, retrying...")
                        continue
                    else:
                        logger.warning(f"Response still incomplete after {max_retries + 1} attempts")
                        break
                
            except ValueError as e:
                if "Empty response" in str(e) and attempt < max_retries:
                    logger.warning(f"Empty response on attempt {attempt + 1}, retrying...")
                    continue
                raise  # Re-raise if not retryable or max retries exceeded
        
        # Parse JSON response with fallback handling
        try:
            result = self._parse_json_response(response)
            
            # Validate response structure
            if not isinstance(result, dict):
                raise ValueError("Response must be a JSON object")
            
            if 'score' not in result or 'reasoning' not in result:
                raise ValueError("Response must contain 'score' and 'reasoning' fields")
            
            score = result['score']
            reasoning = result['reasoning']
            
            # Validate score
            if not isinstance(score, int) or not (0 <= score <= 5):
                raise ValueError("Score must be an integer between 0 and 5")
            
            # Validate reasoning
            if not isinstance(reasoning, str) or not reasoning.strip():
                raise ValueError("Reasoning must be a non-empty string")
            
            scoring_result: ScoringResult = {
                'score': score,
                'reasoning': reasoning.strip()
            }
            
            self._call_callback("evaluation_completed", f"Score: {score}")
            logger.info(f"Document scored {score}/5 for question: {user_question[:50]}...")
            
            return scoring_result
            
        except (json.JSONDecodeError, ValueError) as e:
            # Check if response was truncated
            response_length = len(response) if response else 0
            if response_length < 50 or (response and not response.strip().endswith('}')):
                logger.warning(f"JSON response appears truncated (length: {response_length}): {response[:100]}...")
            else:
                logger.error(f"Invalid JSON response from model (length: {response_length}): {response[:200]}...")
            
            # Fallback: try to extract score using regex
            fallback_result = self._extract_score_fallback(response)
            if fallback_result:
                self._call_callback("evaluation_completed", f"Score: {fallback_result['score']} (fallback)")
                return fallback_result
            raise ValueError(f"Model returned invalid JSON and fallback failed: {e}")
            
        except Exception as e:
            self._call_callback("evaluation_failed", str(e))
            raise
    
    def _parse_json_response(self, response: str) -> Dict:
        """
        Parse JSON response with robust error handling.
        
        Attempts to fix common JSON formatting issues before parsing.
        
        Args:
            response: Raw response string from model
            
        Returns:
            Parsed JSON dictionary
            
        Raises:
            json.JSONDecodeError: If JSON cannot be parsed
        """
        response = response.strip()
        
        # Remove markdown code block wrapper if present
        if response.startswith('```json') and response.endswith('```'):
            response = response[7:-3].strip()  # Remove ```json and ```
        elif response.startswith('```') and response.endswith('```'):
            response = response[3:-3].strip()   # Remove ``` and ```
        
        # Try parsing as-is first
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            pass
        
        # Try to fix incomplete JSON by adding missing closing braces/quotes
        if response.startswith('{') and not response.endswith('}'):
            # Try to complete the JSON structure
            attempts = [
                response + '"}',  # Missing closing quote and brace
                response + '}',   # Missing closing brace only
                response + '"}'   # Missing quote then brace
            ]
            
            for attempt in attempts:
                try:
                    return json.loads(attempt)
                except json.JSONDecodeError:
                    continue
        
        # If all attempts fail, raise the original error
        raise json.JSONDecodeError("Could not parse JSON response", response, 0)
    
    def _extract_score_fallback(self, response: str) -> Optional[ScoringResult]:
        """
        Extract score using regex when JSON parsing fails.
        
        Args:
            response: Raw response string from model
            
        Returns:
            ScoringResult if score can be extracted, None otherwise
        """
        import re
        
        # Try to extract score using regex patterns
        score_patterns = [
            r'"score":\s*(\d+)',           # "score": 3
            r'score:\s*(\d+)',             # score: 3
            r'Score:\s*(\d+)',             # Score: 3
            r'score.*?(\d+)',              # score is 3, score = 3, etc.
        ]
        
        for pattern in score_patterns:
            match = re.search(pattern, response, re.IGNORECASE)
            if match:
                try:
                    score = int(match.group(1))
                    if 0 <= score <= 5:
                        # Extract reasoning if possible
                        reasoning_patterns = [
                            r'"reasoning":\s*"([^"]*)"',     # "reasoning": "text"
                            r'reasoning:\s*"([^"]*)"',       # reasoning: "text"
                            r'reasoning:\s*([^,}]+)',        # reasoning: text
                        ]
                        
                        reasoning = "Score extracted from malformed response"
                        for reason_pattern in reasoning_patterns:
                            reason_match = re.search(reason_pattern, response, re.IGNORECASE)
                            if reason_match:
                                reasoning = reason_match.group(1).strip()
                                break
                        
                        return ScoringResult(
                            score=score,
                            reasoning=reasoning
                        )
                except ValueError:
                    continue
        
        return None
    
    def batch_evaluate_documents(
        self,
        user_question: str,
        documents: list[Dict]
    ) -> list[tuple[Dict, ScoringResult]]:
        """
        Evaluate multiple documents against a user question.
        
        Args:
            user_question: The user's question or information need
            documents: List of document dictionaries from database
            
        Returns:
            List of tuples containing (document, scoring_result) pairs
            
        Examples:
            >>> agent = DocumentScoringAgent()
            >>> docs = [doc1, doc2, doc3]  # List of document dicts
            >>> results = agent.batch_evaluate_documents("COVID vaccine safety", docs)
            >>> for doc, score_result in results:
            ...     print(f"{doc['title']}: {score_result['score']}/5")
        """
        if not user_question or not user_question.strip():
            raise ValueError("User question cannot be empty")
        
        if not documents or not isinstance(documents, list):
            raise ValueError("Documents must be a non-empty list")
        
        results = []
        
        self._call_callback("batch_evaluation_started", f"Evaluating {len(documents)} documents")
        
        for i, doc in enumerate(documents):
            try:
                self._call_callback("document_evaluation_progress", f"Document {i+1}/{len(documents)}")
                
                scoring_result = self.evaluate_document(user_question, doc)
                results.append((doc, scoring_result))
                
            except Exception as e:
                logger.error(f"Failed to evaluate document {i+1}: {e}")
                # Continue with other documents, append error result
                error_result: ScoringResult = {
                    'score': 0,
                    'reasoning': f"Evaluation failed: {str(e)}"
                }
                results.append((doc, error_result))
        
        self._call_callback("batch_evaluation_completed", f"Evaluated {len(documents)} documents")
        
        return results
    
    def get_top_documents(
        self,
        user_question: str,
        documents: list[Dict],
        top_k: int = 10,
        min_score: int = 2
    ) -> list[tuple[Dict, ScoringResult]]:
        """
        Get the top-k most relevant documents based on scoring.
        
        Args:
            user_question: The user's question or information need
            documents: List of document dictionaries from database
            top_k: Number of top documents to return (default: 10)
            min_score: Minimum score threshold for inclusion (default: 2)
            
        Returns:
            List of (document, scoring_result) tuples sorted by score (highest first)
            
        Examples:
            >>> agent = DocumentScoringAgent()
            >>> top_docs = agent.get_top_documents("heart disease treatment", docs, top_k=5)
            >>> for doc, score_result in top_docs:
            ...     print(f"{score_result['score']}/5: {doc['title']}")
        """
        # Evaluate all documents
        all_results = self.batch_evaluate_documents(user_question, documents)
        
        # Filter by minimum score and sort by score (descending)
        filtered_results = [
            (doc, result) for doc, result in all_results
            if result['score'] >= min_score
        ]
        
        sorted_results = sorted(
            filtered_results,
            key=lambda x: x[1]['score'],
            reverse=True
        )
        
        # Return top-k results
        top_results = sorted_results[:top_k]
        
        self._call_callback(
            "top_documents_selected", 
            f"Selected {len(top_results)} documents with scores >= {min_score}"
        )
        
        return top_results
    
    # Queue-aware methods for large-scale processing
    
    def submit_scoring_tasks(self,
                           user_question: str,
                           documents: List[Dict],
                           priority: TaskPriority = TaskPriority.NORMAL) -> Optional[List[str]]:
        """
        Submit document scoring tasks to the orchestrator queue.
        
        Args:
            user_question: The user's question for relevance evaluation
            documents: List of documents to score
            priority: Task priority level
            
        Returns:
            List of task IDs if orchestrator is available, None otherwise
        """
        if not self.orchestrator:
            logger.warning("No orchestrator configured - cannot submit tasks to queue")
            return None
        
        # Prepare task data for each document
        task_data_list = []
        for doc in documents:
            task_data = {
                "user_question": user_question,
                "document": doc
            }
            task_data_list.append(task_data)
        
        task_ids = self.submit_batch_tasks(
            method_name="evaluate_document_from_queue",
            data_list=task_data_list,
            priority=priority
        )
        
        if task_ids:
            self._call_callback("scoring_tasks_queued", 
                              f"Queued {len(task_ids)} scoring tasks with priority {priority.name}")
        
        return task_ids
    
    def evaluate_document_from_queue(self, user_question: str, document: Dict) -> ScoringResult:
        """
        Queue-compatible wrapper for evaluate_document.
        
        This method is called by the orchestrator when processing queued tasks.
        
        Args:
            user_question: The user's question for relevance evaluation  
            document: Document to evaluate
            
        Returns:
            ScoringResult with score and reasoning
        """
        return self.evaluate_document(user_question, document)
    
    def process_scoring_queue(self,
                            user_question: str,
                            documents: List[Dict],
                            progress_callback: Optional[Callable[[int, int], None]] = None,
                            batch_size: int = 50) -> Iterator[Tuple[Dict, ScoringResult]]:
        """
        Process document scoring using the queue system with memory efficiency.
        
        Args:
            user_question: The user's question for relevance evaluation
            documents: List of documents to score  
            progress_callback: Optional callback for progress updates (completed, total)
            batch_size: Number of documents to process per batch
            
        Yields:
            Tuples of (document, scoring_result) as they are completed
        """
        if not self.orchestrator:
            # Fallback to direct processing if no orchestrator
            logger.info("No orchestrator - falling back to direct processing")
            for i, doc in enumerate(documents):
                result = self.evaluate_document(user_question, doc)
                if progress_callback:
                    progress_callback(i + 1, len(documents))
                yield (doc, result)
            return
        
        total_docs = len(documents)
        processed = 0
        
        # Process in batches to manage memory
        for i in range(0, total_docs, batch_size):
            batch = documents[i:i + batch_size]
            
            # Submit batch to queue
            task_ids = self.submit_scoring_tasks(user_question, batch)
            if not task_ids:
                logger.error("Failed to submit batch to queue")
                continue
            
            # Wait for batch completion and yield results
            completed_tasks = self.orchestrator.wait_for_completion(task_ids)
            
            for task_id, task in completed_tasks.items():
                if task.status.value == "completed" and task.result:
                    # Find corresponding document
                    task_idx = task_ids.index(task_id)
                    doc = batch[task_idx]
                    
                    # Convert result back to ScoringResult
                    scoring_result: ScoringResult = {
                        'score': task.result.get('score', 0),
                        'reasoning': task.result.get('reasoning', 'Unknown result format')
                    }
                    
                    processed += 1
                    if progress_callback:
                        progress_callback(processed, total_docs)
                    
                    yield (doc, scoring_result)
                else:
                    # Handle failed task
                    logger.warning(f"Task {task_id} failed: {task.error_message}")
                    processed += 1
                    if progress_callback:
                        progress_callback(processed, total_docs)
    
    def get_top_documents_queued(self,
                               user_question: str, 
                               documents: List[Dict],
                               top_k: int = 10,
                               min_score: int = 2,
                               progress_callback: Optional[Callable[[int, int], None]] = None) -> List[Tuple[Dict, ScoringResult]]:
        """
        Get top documents using queue processing for memory efficiency.
        
        Args:
            user_question: The user's question for relevance evaluation
            documents: List of documents to evaluate
            top_k: Number of top documents to return
            min_score: Minimum score threshold
            progress_callback: Optional progress callback (completed, total)
            
        Returns:
            List of (document, scoring_result) tuples sorted by score
        """
        # Process all documents through queue
        all_results = []
        for doc, result in self.process_scoring_queue(user_question, documents, progress_callback):
            all_results.append((doc, result))
        
        # Filter and sort results
        filtered_results = [
            (doc, result) for doc, result in all_results
            if result['score'] >= min_score
        ]
        
        sorted_results = sorted(
            filtered_results,
            key=lambda x: x[1]['score'],
            reverse=True
        )
        
        top_results = sorted_results[:top_k]
        
        self._call_callback(
            "queued_top_documents_selected",
            f"Selected {len(top_results)} documents with scores >= {min_score} from {len(documents)} via queue"
        )
        
        return top_results