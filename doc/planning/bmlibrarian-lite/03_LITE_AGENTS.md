# Phase 3: Lite Agents Implementation

## Overview

Lite agents are simplified versions of the full BMLibrarian agents that work without PostgreSQL. They are designed to be stateless where possible, using LiteStorage for persistence and the existing LLMClient for inference.

## Design Principles

1. **Reuse existing infrastructure**: Use `bmlibrarian.llm.LLMClient` and `bmlibrarian.pubmed_search`
2. **Stateless operations**: Agents don't maintain internal state between calls
3. **ChromaDB storage**: Use LiteStorage for all persistence
4. **Minimal dependencies**: Only require lite module dependencies

## Components

### 3.1 Base Agent (`src/bmlibrarian/lite/agents/base.py`)

```python
"""Base class for Lite agents."""

import logging
from typing import Optional

from bmlibrarian.llm import LLMClient, LLMMessage
from ..config import LiteConfig

logger = logging.getLogger(__name__)


class LiteBaseAgent:
    """
    Base class for all Lite agents.

    Provides common functionality for LLM communication and configuration.
    """

    def __init__(
        self,
        config: Optional[LiteConfig] = None,
        llm_client: Optional[LLMClient] = None,
    ) -> None:
        """
        Initialize the agent.

        Args:
            config: Lite configuration
            llm_client: Optional pre-configured LLM client
        """
        self.config = config or LiteConfig()
        self._llm_client = llm_client

    @property
    def llm_client(self) -> LLMClient:
        """Get or create LLM client."""
        if self._llm_client is None:
            self._llm_client = LLMClient()
        return self._llm_client

    def _get_model(self) -> str:
        """Get the configured model string."""
        provider = self.config.llm.provider
        model = self.config.llm.model
        return f"{provider}:{model}"

    def _chat(
        self,
        messages: list[LLMMessage],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> str:
        """
        Send a chat request to the LLM.

        Args:
            messages: List of messages
            temperature: Optional temperature override
            max_tokens: Optional max tokens override

        Returns:
            Response text
        """
        response = self.llm_client.chat(
            messages=messages,
            model=self._get_model(),
            temperature=temperature or self.config.llm.temperature,
            max_tokens=max_tokens or self.config.llm.max_tokens,
        )
        return response.content

    def _create_system_message(self, content: str) -> LLMMessage:
        """Create a system message."""
        return LLMMessage(role="system", content=content)

    def _create_user_message(self, content: str) -> LLMMessage:
        """Create a user message."""
        return LLMMessage(role="user", content=content)
```

### 3.2 Search Agent (`src/bmlibrarian/lite/agents/search_agent.py`)

```python
"""Lite search agent for PubMed queries."""

import logging
from typing import List, Optional

from bmlibrarian.pubmed_search import PubMedSearchClient, QueryConverter
from ..storage import LiteStorage
from ..data_models import LiteDocument, DocumentSource, SearchSession
from ..chroma_embeddings import create_embedding_function
from .base import LiteBaseAgent

logger = logging.getLogger(__name__)


class LiteSearchAgent(LiteBaseAgent):
    """
    Search agent for PubMed queries with ChromaDB caching.

    Converts natural language queries to PubMed searches and caches
    results in ChromaDB for semantic search.
    """

    def __init__(
        self,
        storage: Optional[LiteStorage] = None,
        **kwargs,
    ) -> None:
        """
        Initialize the search agent.

        Args:
            storage: LiteStorage instance
            **kwargs: Additional arguments for base agent
        """
        super().__init__(**kwargs)
        self.storage = storage or LiteStorage(self.config)

        # Initialize PubMed clients
        self._search_client = PubMedSearchClient(
            email=self.config.pubmed.email,
            api_key=self.config.pubmed.api_key,
        )
        self._query_converter = QueryConverter()

        # Create embedding function
        self._embed_fn = create_embedding_function(
            model_name=self.config.embeddings.model
        )

    def search(
        self,
        query: str,
        max_results: int = 100,
    ) -> tuple[SearchSession, List[LiteDocument]]:
        """
        Search PubMed and cache results.

        Args:
            query: Natural language research question
            max_results: Maximum results to fetch

        Returns:
            Tuple of (search session, list of documents)
        """
        logger.info(f"Searching PubMed for: {query}")

        # Convert to PubMed query
        pubmed_query = self._query_converter.convert(query)
        logger.debug(f"PubMed query: {pubmed_query}")

        # Execute search
        pmids = self._search_client.search(pubmed_query, max_results=max_results)
        logger.info(f"Found {len(pmids)} results")

        if not pmids:
            session = self.storage.create_search_session(
                query=pubmed_query,
                natural_language_query=query,
                document_count=0,
            )
            return session, []

        # Fetch article details
        articles = self._search_client.fetch_details(pmids)

        # Convert to LiteDocuments
        documents = []
        for article in articles:
            doc = LiteDocument(
                id=f"pmid-{article.pmid}",
                title=article.title,
                abstract=article.abstract or "",
                authors=article.authors,
                year=article.pub_year,
                journal=article.journal,
                doi=article.doi,
                pmid=article.pmid,
                source=DocumentSource.PUBMED,
            )
            documents.append(doc)

        # Store in ChromaDB with embeddings
        self.storage.add_documents(documents, embedding_function=self._embed_fn)

        # Create search session
        session = self.storage.create_search_session(
            query=pubmed_query,
            natural_language_query=query,
            document_count=len(documents),
        )

        logger.info(f"Cached {len(documents)} documents")
        return session, documents

    def semantic_search(
        self,
        query: str,
        n_results: int = 20,
    ) -> List[LiteDocument]:
        """
        Search cached documents by semantic similarity.

        Args:
            query: Search query
            n_results: Maximum results to return

        Returns:
            List of matching documents
        """
        return self.storage.search_documents(
            query=query,
            n_results=n_results,
            embedding_function=self._embed_fn,
        )
```

### 3.3 Scoring Agent (`src/bmlibrarian/lite/agents/scoring_agent.py`)

```python
"""Lite document scoring agent."""

import json
import logging
import re
from typing import List, Optional

from bmlibrarian.llm import LLMMessage
from ..data_models import LiteDocument, ScoredDocument
from .base import LiteBaseAgent

logger = logging.getLogger(__name__)

SCORING_SYSTEM_PROMPT = """You are a medical research relevance assessor. Your task is to evaluate how relevant a document is to answering a specific research question.

Score each document on a scale of 1-5:
- 5: Directly answers the question with strong evidence
- 4: Highly relevant, provides substantial supporting information
- 3: Moderately relevant, contains useful related information
- 2: Marginally relevant, tangentially related
- 1: Not relevant to the research question

Respond in JSON format:
{
    "score": <1-5>,
    "explanation": "<brief explanation of relevance>"
}"""


class LiteScoringAgent(LiteBaseAgent):
    """
    Stateless document scoring agent.

    Evaluates document relevance to a research question using LLM inference.
    """

    def score_document(
        self,
        question: str,
        document: LiteDocument,
    ) -> ScoredDocument:
        """
        Score a single document's relevance.

        Args:
            question: Research question
            document: Document to score

        Returns:
            ScoredDocument with score and explanation
        """
        user_prompt = f"""Research Question: {question}

Document Title: {document.title}
Authors: {document.formatted_authors}
Year: {document.year or 'Unknown'}

Abstract:
{document.abstract}

Evaluate the relevance of this document to the research question."""

        messages = [
            self._create_system_message(SCORING_SYSTEM_PROMPT),
            self._create_user_message(user_prompt),
        ]

        try:
            response = self._chat(messages, temperature=0.1)
            result = self._parse_score_response(response)

            return ScoredDocument(
                document=document,
                score=result["score"],
                explanation=result["explanation"],
            )
        except Exception as e:
            logger.error(f"Failed to score document {document.id}: {e}")
            return ScoredDocument(
                document=document,
                score=1,
                explanation=f"Scoring failed: {str(e)}",
            )

    def score_documents(
        self,
        question: str,
        documents: List[LiteDocument],
        min_score: int = 1,
        progress_callback: Optional[callable] = None,
    ) -> List[ScoredDocument]:
        """
        Score multiple documents.

        Args:
            question: Research question
            documents: Documents to score
            min_score: Minimum score to include in results
            progress_callback: Optional callback(current, total) for progress

        Returns:
            List of scored documents (filtered by min_score)
        """
        scored = []
        total = len(documents)

        for i, doc in enumerate(documents):
            if progress_callback:
                progress_callback(i + 1, total)

            scored_doc = self.score_document(question, doc)

            if scored_doc.score >= min_score:
                scored.append(scored_doc)

            logger.debug(
                f"Document {doc.id}: score={scored_doc.score} "
                f"({i+1}/{total})"
            )

        # Sort by score descending
        scored.sort(key=lambda x: x.score, reverse=True)

        logger.info(
            f"Scored {total} documents, {len(scored)} with score >= {min_score}"
        )
        return scored

    def _parse_score_response(self, response: str) -> dict:
        """
        Parse LLM response to extract score and explanation.

        Args:
            response: LLM response text

        Returns:
            Dictionary with 'score' and 'explanation'
        """
        # Try to parse as JSON
        try:
            # Extract JSON from response
            json_match = re.search(r'\{[^}]+\}', response, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
                score = int(data.get("score", 1))
                score = max(1, min(5, score))  # Clamp to 1-5
                return {
                    "score": score,
                    "explanation": data.get("explanation", ""),
                }
        except (json.JSONDecodeError, ValueError):
            pass

        # Fallback: try to extract score from text
        score_match = re.search(r'score[:\s]+(\d)', response, re.IGNORECASE)
        if score_match:
            score = int(score_match.group(1))
            score = max(1, min(5, score))
            return {"score": score, "explanation": response}

        # Default
        logger.warning(f"Could not parse score from: {response[:100]}")
        return {"score": 1, "explanation": "Could not parse response"}
```

### 3.4 Citation Agent (`src/bmlibrarian/lite/agents/citation_agent.py`)

```python
"""Lite citation extraction agent."""

import json
import logging
import re
from typing import List, Optional

from ..data_models import Citation, ScoredDocument
from .base import LiteBaseAgent

logger = logging.getLogger(__name__)

CITATION_SYSTEM_PROMPT = """You are a medical research citation extractor. Your task is to identify the most relevant passages from a document that help answer a research question.

Extract 1-3 key passages that:
1. Directly address the research question
2. Contain specific findings, data, or conclusions
3. Are self-contained and understandable

Respond in JSON format:
{
    "passages": [
        {
            "text": "<exact quote from the abstract>",
            "relevance": "<why this passage is relevant>"
        }
    ]
}"""


class LiteCitationAgent(LiteBaseAgent):
    """
    Stateless citation extraction agent.

    Extracts relevant passages from documents that answer a research question.
    """

    def extract_citations(
        self,
        question: str,
        scored_doc: ScoredDocument,
    ) -> List[Citation]:
        """
        Extract citations from a scored document.

        Args:
            question: Research question
            scored_doc: Document with relevance score

        Returns:
            List of extracted citations
        """
        doc = scored_doc.document

        user_prompt = f"""Research Question: {question}

Document Title: {doc.title}
Authors: {doc.formatted_authors}
Year: {doc.year or 'Unknown'}
Relevance Score: {scored_doc.score}/5

Abstract:
{doc.abstract}

Extract the most relevant passages that help answer the research question."""

        messages = [
            self._create_system_message(CITATION_SYSTEM_PROMPT),
            self._create_user_message(user_prompt),
        ]

        try:
            response = self._chat(messages, temperature=0.1)
            passages = self._parse_citation_response(response)

            citations = []
            for passage in passages:
                citation = Citation(
                    document=doc,
                    passage=passage["text"],
                    relevance_score=scored_doc.score,
                    context=passage.get("relevance", ""),
                )
                citations.append(citation)

            return citations

        except Exception as e:
            logger.error(f"Failed to extract citations from {doc.id}: {e}")
            # Return a basic citation using the abstract
            return [Citation(
                document=doc,
                passage=doc.abstract[:500] if len(doc.abstract) > 500 else doc.abstract,
                relevance_score=scored_doc.score,
                context="Full abstract (extraction failed)",
            )]

    def extract_all_citations(
        self,
        question: str,
        scored_documents: List[ScoredDocument],
        min_score: int = 3,
        progress_callback: Optional[callable] = None,
    ) -> List[Citation]:
        """
        Extract citations from all scored documents.

        Args:
            question: Research question
            scored_documents: Documents to extract from
            min_score: Minimum score to process
            progress_callback: Optional callback(current, total)

        Returns:
            List of all extracted citations
        """
        all_citations = []
        eligible = [d for d in scored_documents if d.score >= min_score]
        total = len(eligible)

        for i, scored_doc in enumerate(eligible):
            if progress_callback:
                progress_callback(i + 1, total)

            citations = self.extract_citations(question, scored_doc)
            all_citations.extend(citations)

            logger.debug(
                f"Extracted {len(citations)} citations from {scored_doc.document.id}"
            )

        logger.info(
            f"Extracted {len(all_citations)} citations from {total} documents"
        )
        return all_citations

    def _parse_citation_response(self, response: str) -> List[dict]:
        """
        Parse LLM response to extract passages.

        Args:
            response: LLM response text

        Returns:
            List of passage dictionaries
        """
        try:
            # Extract JSON from response
            json_match = re.search(r'\{[^{}]*"passages"[^{}]*\[.*?\]\s*\}', response, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
                return data.get("passages", [])
        except (json.JSONDecodeError, ValueError):
            pass

        # Fallback: return empty list
        logger.warning(f"Could not parse citations from: {response[:100]}")
        return []
```

### 3.5 Reporting Agent (`src/bmlibrarian/lite/agents/reporting_agent.py`)

```python
"""Lite report generation agent."""

import logging
from typing import List, Optional

from ..data_models import Citation
from .base import LiteBaseAgent

logger = logging.getLogger(__name__)

REPORTING_SYSTEM_PROMPT = """You are a medical research report writer. Your task is to synthesize evidence from multiple sources into a coherent, professional research summary.

Guidelines:
1. Write in clear, professional medical prose
2. Cite sources using [Author, Year] format
3. Organize by themes or findings, not by source
4. Include specific data and findings when available
5. Note any conflicting evidence
6. Conclude with a summary of the key findings

Do NOT use generic phrases like "recent studies" - always use specific years."""


class LiteReportingAgent(LiteBaseAgent):
    """
    Stateless report generation agent.

    Synthesizes citations into a coherent research report.
    """

    def generate_report(
        self,
        question: str,
        citations: List[Citation],
    ) -> str:
        """
        Generate a research report from citations.

        Args:
            question: Research question
            citations: List of citations to synthesize

        Returns:
            Formatted research report
        """
        if not citations:
            return self._generate_no_evidence_report(question)

        # Format citations for the prompt
        formatted_citations = self._format_citations_for_prompt(citations)

        user_prompt = f"""Research Question: {question}

Evidence from {len(citations)} sources:

{formatted_citations}

Write a comprehensive research summary that synthesizes this evidence to answer the research question. Include proper citations."""

        messages = [
            self._create_system_message(REPORTING_SYSTEM_PROMPT),
            self._create_user_message(user_prompt),
        ]

        try:
            report = self._chat(messages, temperature=0.3, max_tokens=4096)

            # Add references section
            references = self._format_references(citations)
            full_report = f"{report}\n\n## References\n\n{references}"

            return full_report

        except Exception as e:
            logger.error(f"Failed to generate report: {e}")
            return f"Error generating report: {str(e)}"

    def _generate_no_evidence_report(self, question: str) -> str:
        """Generate a report when no evidence is found."""
        return f"""## Research Summary

**Question:** {question}

No relevant evidence was found in the searched literature. This may indicate:

1. The topic has limited published research
2. The search terms may need refinement
3. The research question may need to be rephrased

### Recommendations

- Try broadening the search terms
- Consider related topics that may provide indirect evidence
- Check if the question can be broken into sub-questions
"""

    def _format_citations_for_prompt(self, citations: List[Citation]) -> str:
        """Format citations for the LLM prompt."""
        formatted = []
        for i, citation in enumerate(citations, 1):
            doc = citation.document
            formatted.append(f"""[{i}] {doc.formatted_authors} ({doc.year or 'n.d.'})
Title: {doc.title}
Journal: {doc.journal or 'Unknown'}
Passage: "{citation.passage}"
""")
        return "\n".join(formatted)

    def _format_references(self, citations: List[Citation]) -> str:
        """Format reference list."""
        # Deduplicate by document ID
        seen = set()
        unique_citations = []
        for citation in citations:
            if citation.document.id not in seen:
                seen.add(citation.document.id)
                unique_citations.append(citation)

        references = []
        for i, citation in enumerate(unique_citations, 1):
            doc = citation.document
            ref = f"{i}. {doc.formatted_authors}"
            if doc.year:
                ref += f" ({doc.year})"
            ref += f". {doc.title}"
            if doc.journal:
                ref += f". *{doc.journal}*"
            if doc.doi:
                ref += f". DOI: {doc.doi}"
            if doc.pmid:
                ref += f". PMID: {doc.pmid}"
            references.append(ref)

        return "\n".join(references)
```

### 3.6 Interrogation Agent (`src/bmlibrarian/lite/agents/interrogation_agent.py`)

```python
"""Lite document interrogation agent for Q&A."""

import logging
from typing import List, Optional, Tuple

from ..storage import LiteStorage
from ..data_models import DocumentChunk
from ..chunking import chunk_document_for_interrogation
from ..chroma_embeddings import create_embedding_function
from .base import LiteBaseAgent

logger = logging.getLogger(__name__)

INTERROGATION_SYSTEM_PROMPT = """You are a helpful research assistant answering questions about a document.

Guidelines:
1. Answer based ONLY on the provided context
2. If the context doesn't contain the answer, say so clearly
3. Quote relevant passages when appropriate
4. Be concise but thorough
5. If asked about something not in the document, acknowledge this limitation"""


class LiteInterrogationAgent(LiteBaseAgent):
    """
    Document interrogation agent for Q&A sessions.

    Chunks documents, embeds them, and answers questions using
    semantic retrieval + LLM generation.
    """

    def __init__(
        self,
        storage: Optional[LiteStorage] = None,
        **kwargs,
    ) -> None:
        """
        Initialize the interrogation agent.

        Args:
            storage: LiteStorage instance
            **kwargs: Additional arguments for base agent
        """
        super().__init__(**kwargs)
        self.storage = storage or LiteStorage(self.config)
        self._embed_fn = create_embedding_function(
            model_name=self.config.embeddings.model
        )
        self._current_document_id: Optional[str] = None

    def load_document(
        self,
        text: str,
        document_id: Optional[str] = None,
        title: str = "Untitled Document",
    ) -> str:
        """
        Load and chunk a document for interrogation.

        Args:
            text: Document text
            document_id: Optional document ID
            title: Document title for display

        Returns:
            Document ID
        """
        # Chunk the document
        chunks = chunk_document_for_interrogation(
            text=text,
            document_id=document_id,
            chunk_size=self.config.search.chunk_size,
            chunk_overlap=self.config.search.chunk_overlap,
        )

        if not chunks:
            raise ValueError("Document produced no chunks")

        # Store chunks in ChromaDB
        chunk_collection = self.storage.get_chunks_collection(self._embed_fn)

        chunk_collection.upsert(
            ids=[c.id for c in chunks],
            documents=[c.text for c in chunks],
            metadatas=[{
                "document_id": c.document_id,
                "chunk_index": c.chunk_index,
                "title": title,
            } for c in chunks],
        )

        self._current_document_id = chunks[0].document_id
        logger.info(f"Loaded document with {len(chunks)} chunks")

        return self._current_document_id

    def ask(
        self,
        question: str,
        document_id: Optional[str] = None,
        n_context_chunks: int = 5,
    ) -> Tuple[str, List[str]]:
        """
        Ask a question about the loaded document.

        Args:
            question: Question to ask
            document_id: Optional document ID (uses current if not provided)
            n_context_chunks: Number of context chunks to retrieve

        Returns:
            Tuple of (answer, list of source passages)
        """
        doc_id = document_id or self._current_document_id
        if not doc_id:
            raise ValueError("No document loaded. Call load_document() first.")

        # Retrieve relevant chunks
        chunk_collection = self.storage.get_chunks_collection(self._embed_fn)

        results = chunk_collection.query(
            query_texts=[question],
            n_results=n_context_chunks,
            where={"document_id": doc_id},
            include=["documents", "metadatas"],
        )

        if not results["documents"][0]:
            return "No relevant content found in the document.", []

        # Build context
        context_chunks = results["documents"][0]
        context = "\n\n---\n\n".join(context_chunks)

        # Generate answer
        user_prompt = f"""Context from the document:

{context}

---

Question: {question}

Answer the question based on the context above."""

        messages = [
            self._create_system_message(INTERROGATION_SYSTEM_PROMPT),
            self._create_user_message(user_prompt),
        ]

        answer = self._chat(messages, temperature=0.2)

        return answer, context_chunks

    def clear_document(self, document_id: Optional[str] = None) -> None:
        """
        Clear a document's chunks from storage.

        Args:
            document_id: Document ID to clear (uses current if not provided)
        """
        doc_id = document_id or self._current_document_id
        if not doc_id:
            return

        chunk_collection = self.storage.get_chunks_collection(self._embed_fn)

        # Get all chunk IDs for this document
        results = chunk_collection.get(
            where={"document_id": doc_id},
            include=[],
        )

        if results["ids"]:
            chunk_collection.delete(ids=results["ids"])
            logger.info(f"Cleared {len(results['ids'])} chunks for document {doc_id}")

        if doc_id == self._current_document_id:
            self._current_document_id = None
```

### 3.7 Module Init (`src/bmlibrarian/lite/agents/__init__.py`)

```python
"""Lite agents for BMLibrarian Lite."""

from .base import LiteBaseAgent
from .search_agent import LiteSearchAgent
from .scoring_agent import LiteScoringAgent
from .citation_agent import LiteCitationAgent
from .reporting_agent import LiteReportingAgent
from .interrogation_agent import LiteInterrogationAgent

__all__ = [
    "LiteBaseAgent",
    "LiteSearchAgent",
    "LiteScoringAgent",
    "LiteCitationAgent",
    "LiteReportingAgent",
    "LiteInterrogationAgent",
]
```

## Implementation Steps

1. Create agents directory structure
2. Implement base agent
3. Implement search agent
4. Implement scoring agent
5. Implement citation agent
6. Implement reporting agent
7. Implement interrogation agent
8. Add comprehensive tests

## Testing Strategy

Each agent should have tests for:
- Basic functionality
- Error handling
- Edge cases (empty inputs, etc.)
- Integration with LiteStorage

## Golden Rules Checklist

- [x] All LLM communication via LLMClient abstraction
- [x] Type hints on all parameters
- [x] Docstrings on all functions/classes
- [x] Error handling with logging
- [x] No magic numbers in prompts (configurable)
- [x] Stateless operations where possible
