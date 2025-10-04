"""
Citation Finder Agent for extracting relevant passages from scored documents.

Processes documents above a threshold score to extract specific passages
that answer user questions, building a queue of verifiable citations.
"""

import json
import logging
from typing import Dict, List, Optional, Any, Iterator, Tuple, Callable
from dataclasses import dataclass
from datetime import datetime, timezone

from .base import BaseAgent
from .queue_manager import QueueManager, TaskPriority, TaskStatus

logger = logging.getLogger(__name__)


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
                 show_model_info: bool = True):
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
        """
        super().__init__(model=model, host=host, temperature=temperature, top_p=top_p, 
                        callback=callback, orchestrator=orchestrator, show_model_info=show_model_info)
        self.agent_type = "citation_finder_agent"
    
    def get_agent_type(self) -> str:
        """Get the agent type identifier."""
        return "citation_finder_agent"

    def extract_citation_from_document(self, user_question: str, document: Dict[str, Any], 
                                     min_relevance: float = 0.7) -> Optional[Citation]:
        """
        Extract relevant citation from a single document.
        
        Args:
            user_question: The original user question
            document: Document with abstract/content and metadata
            min_relevance: Minimum relevance score to accept citation
            
        Returns:
            Citation object if relevant passage found, None otherwise
        """
        if not self.test_connection():
            logger.error("Cannot connect to Ollama - citation extraction unavailable")
            return None
        
        try:
            # Build prompt for citation extraction
            abstract = document.get('abstract', '')
            title = document.get('title', 'Untitled')
            
            if not abstract:
                logger.warning(f"No abstract found for document {document.get('id', 'unknown')}")
                return None
            
            prompt = f"""You are a research assistant tasked with extracting relevant citations from scientific papers.

Given the user question and document abstract below, extract the most relevant passage that directly answers or significantly contributes to answering the question.

User Question: "{user_question}"

Document Title: {title}
Abstract: {abstract}

Your task:
1. Identify the most relevant passage from the abstract that answers the question
2. Create a brief 1-2 sentence summary of how this passage relates to the question
3. Rate the relevance on a scale of 0.0 to 1.0 (where 1.0 is perfectly relevant)
4. Only extract passages with relevance >= 0.7

Response format (JSON):
{{
    "relevant_passage": "exact text from the abstract that is most relevant",
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

            # Make request to Ollama using BaseAgent method
            try:
                llm_response = self._generate_from_prompt(prompt)
            except (ConnectionError, ValueError) as e:
                logger.error(f"Ollama request failed for document {document.get('id', 'unknown')}: {e}")
                return None
            
            # Parse JSON response using inherited robust method from BaseAgent
            try:
                citation_data = self._parse_json_response(llm_response)
            except json.JSONDecodeError as e:
                logger.error(f"Could not parse JSON from LLM response: {e}")
                return None
            
            # Check if relevant content was found
            if not citation_data.get('has_relevant_content', False):
                return None
            
            relevance_score = float(citation_data.get('relevance_score', 0.0))
            if relevance_score < min_relevance:
                logger.debug(f"Relevance score {relevance_score} below threshold {min_relevance}")
                return None
            
            # Create citation with verified document ID and abstract for review
            citation = Citation(
                passage=citation_data['relevant_passage'],
                summary=citation_data['summary'],
                relevance_score=relevance_score,
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
            logger.error(f"Error extracting citation from document {document.get('id')}: {e}")
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
        citations = []
        qualifying_docs = [
            (doc, score) for doc, score in scored_documents
            if score.get('score', 0) > score_threshold
        ]

        if not qualifying_docs:
            logger.info(f"No documents above score threshold {score_threshold}")
            return citations

        logger.info(f"Processing {len(qualifying_docs)} documents above threshold {score_threshold}")

        for i, (document, score_result) in enumerate(qualifying_docs):
            if progress_callback:
                progress_callback(i + 1, len(qualifying_docs))

            citation = self.extract_citation_from_document(
                user_question=user_question,
                document=document,
                min_relevance=min_relevance
            )

            if citation:
                citations.append(citation)
                logger.debug(f"Extracted citation from document {document['id']}: {citation.summary}")

        logger.info(f"Extracted {len(citations)} citations from {len(qualifying_docs)} documents")
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
        
        # Filter documents above threshold
        qualifying_docs = [
            (doc, score) for doc, score in scored_documents 
            if score.get('score', 0) > score_threshold
        ]
        
        if not qualifying_docs:
            logger.info(f"No documents above score threshold {score_threshold}")
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
            if score.get('score', 0) > score_threshold
        ]
        
        if not qualifying_docs:
            logger.info(f"No documents above threshold {score_threshold}")
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
                            created_at=datetime.fromisoformat(result_data['created_at'])
                        )
                
                processed += 1
                if progress_callback:
                    progress_callback(processed, total_docs)
                
                yield doc, citation
    
    def verify_document_exists(self, document_id: str) -> bool:
        """
        Verify that a document ID exists in the database.
        
        Args:
            document_id: Document ID to verify
            
        Returns:
            True if document exists, False otherwise
        """
        # This would connect to the actual database to verify
        # For now, we assume all document IDs in our queue are valid
        # since they come from database queries
        return True
    
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