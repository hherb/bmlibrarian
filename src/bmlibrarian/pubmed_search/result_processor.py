"""
Result processor for storing PubMed API search results.

This module handles storing articles fetched from PubMed into the local
database, with proper duplicate detection, existing record preference,
and search provenance tracking.

Example usage:
    from bmlibrarian.pubmed_search import ResultProcessor

    processor = ResultProcessor()

    # Process search results
    import_result = processor.import_articles(articles, search_session)

    print(f"Imported {import_result.articles_imported} new articles")
    print(f"Skipped {import_result.articles_skipped} existing articles")
"""

import logging
from typing import Optional, List, Dict, Any, Callable, Set
from datetime import datetime

from bmlibrarian.database import get_db_manager

from .data_types import (
    ArticleMetadata,
    ImportResult,
    SearchResult,
    SearchSession,
    SearchStatus,
)

logger = logging.getLogger(__name__)


class ResultProcessor:
    """
    Processes and stores PubMed API search results.

    Handles importing articles into the local database with:
    - Duplicate detection by PMID
    - Preference for existing local records
    - Search provenance tracking
    - Batch processing for efficiency
    """

    def __init__(
        self,
        batch_size: int = 50,
        prefer_existing: bool = True,
    ) -> None:
        """
        Initialize the result processor.

        Args:
            batch_size: Number of articles to process per batch
            prefer_existing: If True, skip articles that already exist locally
        """
        self.db_manager = get_db_manager()
        self.batch_size = batch_size
        self.prefer_existing = prefer_existing

        # Get source_id for PubMed
        self.source_id = self._get_source_id("pubmed")
        if not self.source_id:
            raise ValueError(
                "PubMed source not found in database. "
                "Please ensure 'sources' table contains 'pubmed' entry."
            )

        logger.info(f"ResultProcessor initialized (batch_size={batch_size})")

    def _get_source_id(self, source_name: str) -> Optional[int]:
        """Get the source ID for a given source name."""
        cached_ids = self.db_manager.get_cached_source_ids()
        if cached_ids and source_name.lower() in cached_ids:
            return cached_ids[source_name.lower()]

        # Fallback: query database directly
        with self.db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id FROM sources WHERE LOWER(name) LIKE %s",
                    (f"%{source_name.lower()}%",),
                )
                result = cur.fetchone()
                return result[0] if result else None

    def import_articles(
        self,
        articles: List[ArticleMetadata],
        session: Optional[SearchSession] = None,
        progress_callback: Optional[Callable[[str, str], None]] = None,
        cancel_check: Optional[Callable[[], bool]] = None,
    ) -> ImportResult:
        """
        Import articles into the local database.

        Args:
            articles: List of ArticleMetadata to import
            session: Optional SearchSession for provenance tracking
            progress_callback: Optional callback(step, message) for progress
            cancel_check: Optional function that returns True to cancel

        Returns:
            ImportResult with import statistics
        """
        def report_progress(step: str, message: str) -> None:
            logger.info(f"[{step}] {message}")
            if progress_callback:
                progress_callback(step, message)

        def should_cancel() -> bool:
            return cancel_check() if cancel_check else False

        result = ImportResult(total_found=len(articles))

        if not articles:
            report_progress("complete", "No articles to import")
            return result

        report_progress("init", f"Processing {len(articles)} articles...")

        # Get existing PMIDs to check for duplicates
        report_progress("check", "Checking for existing articles...")
        pmids_to_check = [a.pmid for a in articles if a.pmid]
        existing_pmids = self._get_existing_pmids(pmids_to_check)

        report_progress("found", f"Found {len(existing_pmids)} existing articles in database")

        # Process articles
        for i, article in enumerate(articles):
            if should_cancel():
                report_progress("cancelled", "Import cancelled by user")
                break

            if i > 0 and i % self.batch_size == 0:
                report_progress(
                    "progress",
                    f"Processed {i}/{len(articles)} articles..."
                )

            if not article.pmid:
                result.articles_failed += 1
                result.errors.append("Article missing PMID")
                continue

            # Check if exists
            if article.pmid in existing_pmids:
                if self.prefer_existing:
                    result.articles_skipped += 1
                    result.skipped_pmids.append(article.pmid)
                    continue
                else:
                    # Could update existing record here if needed
                    result.articles_skipped += 1
                    result.skipped_pmids.append(article.pmid)
                    continue

            # Import new article
            try:
                doc_id = self._insert_article(article)
                if doc_id:
                    result.articles_imported += 1
                    result.imported_document_ids.append(doc_id)
                else:
                    result.articles_failed += 1
                    result.failed_pmids.append(article.pmid)
            except Exception as e:
                logger.error(f"Failed to import PMID {article.pmid}: {e}")
                result.articles_failed += 1
                result.failed_pmids.append(article.pmid)
                result.errors.append(f"PMID {article.pmid}: {str(e)}")

        result.articles_fetched = len(articles)

        # Track search provenance if session provided
        if session:
            self._record_search_session(session, result)

        report_progress("complete", result.get_summary())

        return result

    def _get_existing_pmids(self, pmids: List[str]) -> Set[str]:
        """
        Check which PMIDs already exist in the database.

        Args:
            pmids: List of PMIDs to check

        Returns:
            Set of PMIDs that exist in database
        """
        if not pmids:
            return set()

        existing = set()

        # Query in batches to avoid query size limits
        batch_size = 1000
        for i in range(0, len(pmids), batch_size):
            batch = pmids[i:i + batch_size]

            with self.db_manager.get_connection() as conn:
                with conn.cursor() as cur:
                    # Use ANY for efficient IN clause
                    cur.execute(
                        """
                        SELECT external_id FROM document
                        WHERE source_id = %s AND external_id = ANY(%s)
                        """,
                        (self.source_id, batch),
                    )
                    for row in cur.fetchall():
                        existing.add(row[0])

        return existing

    def _insert_article(self, article: ArticleMetadata) -> Optional[int]:
        """
        Insert a single article into the database.

        Args:
            article: ArticleMetadata to insert

        Returns:
            Document ID of inserted article, or None if failed
        """
        with self.db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                try:
                    cur.execute(
                        """
                        INSERT INTO document (
                            source_id, external_id, doi, title, abstract,
                            authors, publication, publication_date,
                            url, mesh_terms, keywords
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        RETURNING id
                        """,
                        (
                            self.source_id,
                            article.pmid,
                            article.doi,
                            article.title,
                            article.abstract,
                            article.authors,
                            article.publication,
                            article.publication_date,
                            article.url,
                            article.mesh_terms,
                            article.keywords,
                        ),
                    )

                    result = cur.fetchone()
                    doc_id = result[0] if result else None

                    logger.debug(f"Inserted article ID {doc_id} (PMID:{article.pmid})")
                    return doc_id

                except Exception as e:
                    logger.error(f"Database error inserting PMID {article.pmid}: {e}")
                    conn.rollback()
                    raise

    def _record_search_session(
        self,
        session: SearchSession,
        result: ImportResult,
    ) -> None:
        """
        Record search session for provenance tracking.

        Args:
            session: SearchSession with query information
            result: ImportResult with import statistics
        """
        try:
            with self.db_manager.get_connection() as conn:
                with conn.cursor() as cur:
                    # Check if table exists (in case migration hasn't run)
                    cur.execute(
                        """
                        SELECT EXISTS (
                            SELECT FROM information_schema.tables
                            WHERE table_name = 'pubmed_api_searches'
                        )
                        """
                    )
                    if not cur.fetchone()[0]:
                        logger.warning(
                            "pubmed_api_searches table not found. "
                            "Run migrations to enable search tracking."
                        )
                        return

                    # Get query info
                    query = session.queries_executed[0] if session.queries_executed else None
                    query_string = query.query_string if query else ""
                    concepts_json = None
                    if query and query.concepts:
                        import json
                        concepts_json = json.dumps([
                            {
                                "name": c.name,
                                "mesh_terms": c.mesh_terms,
                                "keywords": c.keywords,
                            }
                            for c in query.concepts
                        ])

                    cur.execute(
                        """
                        INSERT INTO pubmed_api_searches (
                            session_id, research_question, pubmed_query,
                            query_concepts, total_results, results_retrieved,
                            results_imported, results_duplicate, user_id
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        RETURNING id
                        """,
                        (
                            session.session_id,
                            session.research_question,
                            query_string,
                            concepts_json,
                            result.total_found,
                            result.articles_fetched,
                            result.articles_imported,
                            result.articles_skipped,
                            session.user_id,
                        ),
                    )

                    search_id = cur.fetchone()[0]

                    # Link imported documents to search
                    if result.imported_document_ids:
                        for rank, doc_id in enumerate(result.imported_document_ids, 1):
                            cur.execute(
                                """
                                INSERT INTO pubmed_api_search_documents
                                (search_id, document_id, relevance_rank)
                                VALUES (%s, %s, %s)
                                ON CONFLICT DO NOTHING
                                """,
                                (search_id, doc_id, rank),
                            )

                    logger.info(f"Recorded search session {session.session_id}")

        except Exception as e:
            logger.warning(f"Failed to record search session: {e}")

    def get_document_ids_for_pmids(self, pmids: List[str]) -> Dict[str, int]:
        """
        Get document IDs for a list of PMIDs.

        Useful for looking up existing records.

        Args:
            pmids: List of PMIDs to look up

        Returns:
            Dictionary mapping PMID to document ID
        """
        if not pmids:
            return {}

        result = {}

        with self.db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT external_id, id FROM document
                    WHERE source_id = %s AND external_id = ANY(%s)
                    """,
                    (self.source_id, pmids),
                )
                for row in cur.fetchall():
                    result[row[0]] = row[1]

        return result

    def get_documents_for_pmids(
        self,
        pmids: List[str],
    ) -> List[Dict[str, Any]]:
        """
        Get full document records for a list of PMIDs.

        Retrieves documents from local database for PMIDs that exist.

        Args:
            pmids: List of PMIDs to retrieve

        Returns:
            List of document dictionaries
        """
        if not pmids:
            return []

        documents = []

        with self.db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, external_id, doi, title, abstract,
                           authors, publication, publication_date,
                           url, mesh_terms, keywords, pdf_filename
                    FROM document
                    WHERE source_id = %s AND external_id = ANY(%s)
                    """,
                    (self.source_id, pmids),
                )

                columns = [
                    "id", "pmid", "doi", "title", "abstract",
                    "authors", "publication", "publication_date",
                    "url", "mesh_terms", "keywords", "pdf_filename",
                ]

                for row in cur.fetchall():
                    doc = dict(zip(columns, row))
                    documents.append(doc)

        return documents

    def update_document_pdf_path(
        self,
        document_id: int,
        pdf_filename: str,
    ) -> bool:
        """
        Update the PDF filename for a document.

        Args:
            document_id: Database ID of the document
            pdf_filename: Filename of the downloaded PDF

        Returns:
            True if update was successful
        """
        try:
            with self.db_manager.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        UPDATE document SET pdf_filename = %s
                        WHERE id = %s
                        """,
                        (pdf_filename, document_id),
                    )
                    return cur.rowcount > 0
        except Exception as e:
            logger.error(f"Failed to update PDF path for doc {document_id}: {e}")
            return False


class SearchAndImportOrchestrator:
    """
    Orchestrates the complete PubMed API search and import workflow.

    Combines query conversion, search, and import into a single
    coordinated workflow with progress tracking and error handling.
    """

    def __init__(
        self,
        query_converter: Optional[Any] = None,  # QueryConverter
        search_client: Optional[Any] = None,  # PubMedSearchClient
        result_processor: Optional[ResultProcessor] = None,
    ) -> None:
        """
        Initialize the orchestrator.

        Args:
            query_converter: Optional QueryConverter instance
            search_client: Optional PubMedSearchClient instance
            result_processor: Optional ResultProcessor instance
        """
        # Lazy imports to avoid circular dependencies
        self._query_converter = query_converter
        self._search_client = search_client
        self._result_processor = result_processor or ResultProcessor()

    @property
    def query_converter(self) -> Any:
        """Get or create QueryConverter."""
        if self._query_converter is None:
            from .query_converter import QueryConverter
            self._query_converter = QueryConverter()
        return self._query_converter

    @property
    def search_client(self) -> Any:
        """Get or create PubMedSearchClient."""
        if self._search_client is None:
            from .search_client import PubMedSearchClient
            self._search_client = PubMedSearchClient()
        return self._search_client

    def search_and_import(
        self,
        question: str,
        max_results: int = 200,
        download_fulltext: bool = False,
        progress_callback: Optional[Callable[[str, str], None]] = None,
        cancel_check: Optional[Callable[[], bool]] = None,
    ) -> SearchSession:
        """
        Complete workflow: convert question → search → import.

        Args:
            question: Natural language research question
            max_results: Maximum articles to retrieve
            download_fulltext: Whether to download PDFs (not implemented here)
            progress_callback: Optional progress callback
            cancel_check: Optional cancellation check

        Returns:
            SearchSession with complete workflow results
        """
        def report_progress(step: str, message: str) -> None:
            logger.info(f"[{step}] {message}")
            if progress_callback:
                progress_callback(step, message)

        def should_cancel() -> bool:
            return cancel_check() if cancel_check else False

        # Create session
        session = SearchSession(research_question=question)
        session.status = SearchStatus.IN_PROGRESS

        try:
            # Step 1: Convert question to PubMed query
            report_progress("convert", "Converting question to PubMed query...")
            conversion_result = self.query_converter.convert(
                question,
                progress_callback=progress_callback,
            )

            if should_cancel():
                session.mark_failed("Cancelled by user")
                return session

            query = conversion_result.primary_query
            session.queries_executed.append(query)

            report_progress("query", f"Generated query: {query.query_string[:100]}...")

            # Step 2: Search PubMed
            report_progress("search", "Searching PubMed...")
            search_result = self.search_client.search(
                query,
                max_results=max_results,
                progress_callback=progress_callback,
            )

            if should_cancel():
                session.mark_failed("Cancelled by user")
                return session

            if search_result.total_count == 0:
                report_progress("empty", "No results found")
                session.import_result = ImportResult()
                session.mark_completed()
                return session

            report_progress(
                "found",
                f"Found {search_result.total_count} articles, "
                f"retrieving {search_result.retrieved_count}..."
            )

            # Step 3: Fetch article metadata
            report_progress("fetch", "Fetching article metadata...")
            articles = self.search_client.fetch_articles(
                search_result.pmids,
                progress_callback=progress_callback,
            )

            if should_cancel():
                session.mark_failed("Cancelled by user")
                return session

            # Step 4: Import to database
            report_progress("import", "Importing articles to database...")
            import_result = self._result_processor.import_articles(
                articles,
                session=session,
                progress_callback=progress_callback,
                cancel_check=cancel_check,
            )

            session.import_result = import_result
            session.mark_completed()

            report_progress("complete", import_result.get_summary())

            return session

        except Exception as e:
            logger.error(f"Search and import workflow failed: {e}")
            session.mark_failed(str(e))
            return session
