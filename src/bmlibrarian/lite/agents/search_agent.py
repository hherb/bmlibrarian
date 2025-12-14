"""
Lite search agent for PubMed queries.

This agent handles converting natural language questions to PubMed queries,
executing searches, and caching results in ChromaDB for semantic search.
"""

import logging
from typing import Optional, Callable

from bmlibrarian.pubmed_search import (
    PubMedSearchClient,
    PubMedQuery,
    ArticleMetadata,
)
from ..storage import LiteStorage
from ..config import LiteConfig
from ..data_models import LiteDocument, DocumentSource, SearchSession
from ..chroma_embeddings import create_embedding_function, FastEmbedFunction
from ..query_converter import LiteQueryConverter
from .base import LiteBaseAgent

logger = logging.getLogger(__name__)


class LiteSearchAgent(LiteBaseAgent):
    """
    Search agent for PubMed queries with ChromaDB caching.

    Converts natural language queries to PubMed searches and caches
    results in ChromaDB for semantic search.

    This agent:
    1. Uses LLM to convert research questions to optimized PubMed queries
    2. Executes searches via the PubMed E-utilities API
    3. Caches results in ChromaDB with embeddings for later retrieval
    4. Provides semantic search over cached documents

    Attributes:
        storage: LiteStorage instance for persistence
    """

    def __init__(
        self,
        storage: Optional[LiteStorage] = None,
        config: Optional[LiteConfig] = None,
        **kwargs,
    ) -> None:
        """
        Initialize the search agent.

        Args:
            storage: LiteStorage instance (creates one if not provided)
            config: Lite configuration
            **kwargs: Additional arguments for base agent
        """
        super().__init__(config=config, **kwargs)
        self.storage = storage or LiteStorage(self.config)

        # Initialize PubMed client
        self._search_client = PubMedSearchClient(
            email=self.config.pubmed.email or "",
            api_key=self.config.pubmed.api_key,
        )

        # Initialize lite query converter (simplified, focused queries)
        self._query_converter = LiteQueryConverter(
            llm_client=self.llm_client,
            model=self._get_model(),
        )

        # Create embedding function (lazy initialization)
        self._embed_fn: Optional[FastEmbedFunction] = None

    @property
    def embed_fn(self) -> FastEmbedFunction:
        """Get or create embedding function."""
        if self._embed_fn is None:
            self._embed_fn = create_embedding_function(
                model_name=self.config.embeddings.model
            )
        return self._embed_fn

    def convert_query(self, question: str) -> PubMedQuery:
        """
        Convert a natural language question to a PubMed query.

        Uses LLM to parse the question and generate a focused
        PubMed query with key MeSH terms and keywords.

        Args:
            question: Natural language research question

        Returns:
            PubMedQuery object with query string and metadata
        """
        logger.info(f"Converting question to PubMed query: {question[:100]}...")

        query = self._query_converter.convert(question)

        logger.debug(f"Generated query: {query.query_string}")
        return query

    def search(
        self,
        question: str,
        max_results: Optional[int] = None,
        progress_callback: Optional[Callable[[str], None]] = None,
    ) -> tuple[SearchSession, list[LiteDocument]]:
        """
        Search PubMed and cache results.

        This is the main entry point for searching. It:
        1. Converts the question to a PubMed query
        2. Executes the search
        3. Fetches article metadata
        4. Caches results in ChromaDB

        Args:
            question: Natural language research question
            max_results: Maximum results to fetch (uses config default if None)
            progress_callback: Optional callback for progress updates

        Returns:
            Tuple of (search session, list of documents)
        """
        max_results = max_results or self.config.search.max_results

        if progress_callback:
            progress_callback("Converting question to PubMed query...")

        # Convert to PubMed query
        pubmed_query = self.convert_query(question)
        logger.info(f"PubMed query: {pubmed_query.query_string}")

        if progress_callback:
            progress_callback("Searching PubMed...")

        # Execute search
        search_result = self._search_client.search(pubmed_query, max_results=max_results)
        logger.info(
            f"Found {search_result.total_count} results, "
            f"retrieved {search_result.retrieved_count} PMIDs"
        )

        if not search_result.pmids:
            # No results found
            session = self.storage.create_search_session(
                query=pubmed_query.query_string,
                natural_language_query=question,
                document_count=0,
            )
            return session, []

        if progress_callback:
            progress_callback(f"Fetching details for {len(search_result.pmids)} articles...")

        # Fetch article details
        articles = self._search_client.fetch_details(search_result.pmids)
        logger.info(f"Fetched {len(articles)} article details")

        # Convert to LiteDocuments
        documents = self._articles_to_documents(articles)

        if progress_callback:
            progress_callback(f"Caching {len(documents)} documents...")

        # Store in ChromaDB with embeddings
        if documents:
            self.storage.add_documents(documents, embedding_function=self.embed_fn)

        # Create search session
        session = self.storage.create_search_session(
            query=pubmed_query.query_string,
            natural_language_query=question,
            document_count=len(documents),
        )

        logger.info(f"Cached {len(documents)} documents in session {session.id}")
        return session, documents

    def search_with_query(
        self,
        pubmed_query: str,
        natural_language_query: Optional[str] = None,
        max_results: Optional[int] = None,
        progress_callback: Optional[Callable[[str], None]] = None,
    ) -> tuple[SearchSession, list[LiteDocument]]:
        """
        Search PubMed with a pre-formatted query string.

        Use this when you want to bypass the LLM query conversion
        and use a specific PubMed query directly.

        Args:
            pubmed_query: Pre-formatted PubMed query string
            natural_language_query: Original question (for session tracking)
            max_results: Maximum results to fetch
            progress_callback: Optional callback for progress updates

        Returns:
            Tuple of (search session, list of documents)
        """
        max_results = max_results or self.config.search.max_results

        # Create query object
        query = PubMedQuery(
            original_question=natural_language_query or pubmed_query,
            query_string=pubmed_query,
        )

        if progress_callback:
            progress_callback("Searching PubMed...")

        # Execute search
        search_result = self._search_client.search(query, max_results=max_results)
        logger.info(f"Found {search_result.total_count} results")

        if not search_result.pmids:
            session = self.storage.create_search_session(
                query=pubmed_query,
                natural_language_query=natural_language_query or pubmed_query,
                document_count=0,
            )
            return session, []

        if progress_callback:
            progress_callback(f"Fetching details for {len(search_result.pmids)} articles...")

        # Fetch article details
        articles = self._search_client.fetch_details(search_result.pmids)

        # Convert and store
        documents = self._articles_to_documents(articles)

        if documents:
            if progress_callback:
                progress_callback(f"Caching {len(documents)} documents...")
            self.storage.add_documents(documents, embedding_function=self.embed_fn)

        session = self.storage.create_search_session(
            query=pubmed_query,
            natural_language_query=natural_language_query or pubmed_query,
            document_count=len(documents),
        )

        return session, documents

    def semantic_search(
        self,
        query: str,
        n_results: Optional[int] = None,
    ) -> list[LiteDocument]:
        """
        Search cached documents by semantic similarity.

        Uses embeddings to find documents similar to the query
        from the local ChromaDB cache.

        Args:
            query: Search query (natural language)
            n_results: Maximum results to return

        Returns:
            List of matching documents ordered by similarity
        """
        n_results = n_results or self.config.search.max_results

        return self.storage.search_documents(
            query=query,
            n_results=n_results,
            embedding_function=self.embed_fn,
        )

    def get_document(self, document_id: str) -> Optional[LiteDocument]:
        """
        Get a document by ID from the cache.

        Args:
            document_id: Document ID (e.g., "pmid-12345678")

        Returns:
            LiteDocument if found, None otherwise
        """
        return self.storage.get_document(document_id)

    def get_documents_by_pmids(self, pmids: list[str]) -> list[LiteDocument]:
        """
        Get multiple documents by their PMIDs.

        Args:
            pmids: List of PubMed IDs

        Returns:
            List of found documents (may be fewer than requested)
        """
        documents = []
        for pmid in pmids:
            doc = self.storage.get_document(f"pmid-{pmid}")
            if doc:
                documents.append(doc)
        return documents

    def _articles_to_documents(
        self,
        articles: list[ArticleMetadata],
    ) -> list[LiteDocument]:
        """
        Convert PubMed articles to LiteDocuments.

        Args:
            articles: List of ArticleMetadata from PubMed

        Returns:
            List of LiteDocument objects
        """
        documents = []

        for article in articles:
            # Skip articles without abstracts
            if not article.abstract:
                logger.debug(f"Skipping PMID {article.pmid} - no abstract")
                continue

            # Extract year from publication date
            year = None
            if article.publication_date:
                try:
                    # Try to extract year from date string
                    year = int(article.publication_date[:4])
                except (ValueError, TypeError):
                    pass

            doc = LiteDocument(
                id=f"pmid-{article.pmid}",
                title=article.title,
                abstract=article.abstract,
                authors=article.authors,
                year=year,
                journal=article.publication,
                doi=article.doi,
                pmid=article.pmid,
                pmc_id=article.pmc_id,
                source=DocumentSource.PUBMED,
                url=article.url,
                mesh_terms=article.mesh_terms,
            )
            documents.append(doc)

        return documents
