# Step 11: Database Integration Implementation

## Context

All workflow components are now implemented. We need to persist results to the PostgreSQL database for analysis, auditing, and future reference.

## Objective

Implement PaperCheckDB class that:
- Saves complete PaperCheckResult to database
- Retrieves saved results
- Provides query interfaces for analysis
- Handles transactions properly
- Manages foreign key relationships

## Requirements

- psycopg3 for PostgreSQL connectivity
- Transaction management
- Error handling for database failures
- Efficient batch inserts
- Foreign key integrity

## Implementation Location

Create: `src/bmlibrarian/paperchecker/database.py`

## Class Design

```python
"""
Database interface for PaperChecker

Provides PostgreSQL persistence for all PaperChecker results.
"""

import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
import psycopg
from psycopg.rows import dict_row

from .data_models import (
    PaperCheckResult, Statement, CounterStatement,
    SearchResults, ScoredDocument, ExtractedCitation,
    CounterReport, Verdict
)

logger = logging.getLogger(__name__)


class PaperCheckDB:
    """
    Database interface for PaperChecker results

    Handles all PostgreSQL operations for the papercheck schema,
    including saving complete results and querying saved data.
    """

    def __init__(self, connection_string: Optional[str] = None):
        """
        Initialize PaperCheckDB

        Args:
            connection_string: PostgreSQL connection string
                              (uses default from env if None)
        """
        if connection_string:
            self.conn_string = connection_string
        else:
            # Build from environment variables
            import os
            self.conn_string = (
                f"dbname={os.getenv('POSTGRES_DB', 'knowledgebase')} "
                f"user={os.getenv('POSTGRES_USER', 'postgres')} "
                f"password={os.getenv('POSTGRES_PASSWORD', '')} "
                f"host={os.getenv('POSTGRES_HOST', 'localhost')} "
                f"port={os.getenv('POSTGRES_PORT', '5432')}"
            )

        self.conn = None
        self._connect()

    def _connect(self):
        """Establish database connection"""
        try:
            self.conn = psycopg.connect(self.conn_string)
            logger.info("Database connection established")
        except Exception as e:
            logger.error(f"Failed to connect to database: {e}")
            raise RuntimeError(f"Database connection failed: {e}") from e

    def test_connection(self) -> bool:
        """Test database connectivity"""
        try:
            with self.conn.cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()
            return True
        except Exception as e:
            logger.error(f"Database connection test failed: {e}")
            return False

    def save_complete_result(self, result: PaperCheckResult) -> int:
        """
        Save complete PaperCheckResult to database

        Args:
            result: PaperCheckResult object with all data

        Returns:
            abstract_id (primary key from papercheck.abstracts_checked)

        Raises:
            RuntimeError: If save fails
        """
        logger.info("Saving complete result to database")

        try:
            with self.conn.transaction():
                # 1. Save abstract
                abstract_id = self._save_abstract(result)

                # 2. Save statements and all related data
                for i, statement in enumerate(result.statements):
                    statement_id = self._save_statement(abstract_id, statement)

                    # Get corresponding data for this statement
                    counter_stmt = result.counter_statements[i]
                    search_results = result.search_results[i]
                    scored_docs = result.scored_documents[i]
                    counter_report = result.counter_reports[i]
                    verdict = result.verdicts[i]

                    # Save all related data
                    counter_stmt_id = self._save_counter_statement(
                        statement_id, counter_stmt
                    )

                    self._save_search_results(counter_stmt_id, search_results)
                    self._save_scored_documents(counter_stmt_id, scored_docs)
                    self._save_citations(counter_stmt_id, counter_report.citations)
                    self._save_counter_report(counter_stmt_id, counter_report)
                    self._save_verdict(statement_id, verdict)

                # 3. Update abstract with final status and overall assessment
                self._update_abstract_completion(abstract_id, result)

            logger.info(f"Complete result saved with abstract_id={abstract_id}")
            return abstract_id

        except Exception as e:
            logger.error(f"Failed to save result: {e}", exc_info=True)
            raise RuntimeError(f"Failed to save to database: {e}") from e

    def _save_abstract(self, result: PaperCheckResult) -> int:
        """Save to papercheck.abstracts_checked table"""
        with self.conn.cursor() as cur:
            cur.execute("""
                INSERT INTO papercheck.abstracts_checked (
                    abstract_text, source_pmid, source_doi, source_title,
                    source_authors, source_year, source_journal,
                    model_used, config, status
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (
                result.original_abstract,
                result.source_metadata.get("pmid"),
                result.source_metadata.get("doi"),
                result.source_metadata.get("title"),
                result.source_metadata.get("authors"),
                result.source_metadata.get("year"),
                result.source_metadata.get("journal"),
                result.processing_metadata.get("model"),
                result.processing_metadata.get("config"),
                "processing"
            ))

            abstract_id = cur.fetchone()[0]
            return abstract_id

    def _save_statement(self, abstract_id: int, statement: Statement) -> int:
        """Save to papercheck.statements table"""
        with self.conn.cursor() as cur:
            cur.execute("""
                INSERT INTO papercheck.statements (
                    abstract_id, statement_text, context, statement_type,
                    statement_order, extraction_confidence
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (
                abstract_id,
                statement.text,
                statement.context,
                statement.statement_type,
                statement.statement_order,
                statement.confidence
            ))

            statement_id = cur.fetchone()[0]
            return statement_id

    def _save_counter_statement(
        self, statement_id: int, counter_stmt: CounterStatement
    ) -> int:
        """Save to papercheck.counter_statements table"""
        with self.conn.cursor() as cur:
            cur.execute("""
                INSERT INTO papercheck.counter_statements (
                    statement_id, negated_text, hyde_abstracts, keywords,
                    generation_config
                )
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id
            """, (
                statement_id,
                counter_stmt.negated_text,
                counter_stmt.hyde_abstracts,
                counter_stmt.keywords,
                counter_stmt.generation_metadata
            ))

            counter_stmt_id = cur.fetchone()[0]
            return counter_stmt_id

    def _save_search_results(
        self, counter_stmt_id: int, search_results: SearchResults
    ):
        """Save to papercheck.search_results table"""
        # Prepare rows for batch insert
        rows = []

        for doc_id in search_results.deduplicated_docs:
            strategies = search_results.provenance.get(doc_id, [])

            for strategy in strategies:
                rows.append((
                    counter_stmt_id,
                    doc_id,
                    strategy
                ))

        # Batch insert
        if rows:
            with self.conn.cursor() as cur:
                cur.executemany("""
                    INSERT INTO papercheck.search_results (
                        counter_statement_id, doc_id, search_strategy
                    )
                    VALUES (%s, %s, %s)
                """, rows)

    def _save_scored_documents(
        self, counter_stmt_id: int, scored_docs: List[ScoredDocument]
    ):
        """Save to papercheck.scored_documents table"""
        rows = []

        for doc in scored_docs:
            rows.append((
                counter_stmt_id,
                doc.doc_id,
                doc.score,
                doc.explanation,
                doc.supports_counter,
                doc.found_by
            ))

        if rows:
            with self.conn.cursor() as cur:
                cur.executemany("""
                    INSERT INTO papercheck.scored_documents (
                        counter_statement_id, doc_id, relevance_score,
                        explanation, supports_counter, found_by
                    )
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, rows)

    def _save_citations(
        self, counter_stmt_id: int, citations: List[ExtractedCitation]
    ):
        """Save to papercheck.citations table"""
        rows = []

        for citation in citations:
            rows.append((
                counter_stmt_id,
                citation.doc_id,
                citation.passage,
                citation.relevance_score,
                citation.citation_order,
                citation.full_citation,
                citation.metadata
            ))

        if rows:
            with self.conn.cursor() as cur:
                cur.executemany("""
                    INSERT INTO papercheck.citations (
                        counter_statement_id, doc_id, passage, relevance_score,
                        citation_order, formatted_citation, doc_metadata
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, rows)

    def _save_counter_report(
        self, counter_stmt_id: int, counter_report: CounterReport
    ):
        """Save to papercheck.counter_reports table"""
        with self.conn.cursor() as cur:
            cur.execute("""
                INSERT INTO papercheck.counter_reports (
                    counter_statement_id, report_text, num_citations,
                    search_stats, generation_config
                )
                VALUES (%s, %s, %s, %s, %s)
            """, (
                counter_stmt_id,
                counter_report.summary,
                counter_report.num_citations,
                counter_report.search_stats,
                counter_report.generation_metadata
            ))

    def _save_verdict(self, statement_id: int, verdict: Verdict):
        """Save to papercheck.verdicts table"""
        with self.conn.cursor() as cur:
            cur.execute("""
                INSERT INTO papercheck.verdicts (
                    statement_id, verdict, rationale, confidence,
                    analysis_config
                )
                VALUES (%s, %s, %s, %s, %s)
            """, (
                statement_id,
                verdict.verdict,
                verdict.rationale,
                verdict.confidence,
                verdict.analysis_metadata
            ))

    def _update_abstract_completion(
        self, abstract_id: int, result: PaperCheckResult
    ):
        """Update abstract with completion status"""
        with self.conn.cursor() as cur:
            cur.execute("""
                UPDATE papercheck.abstracts_checked
                SET
                    status = 'completed',
                    num_statements = %s,
                    overall_assessment = %s,
                    processing_time_seconds = %s
                WHERE id = %s
            """, (
                len(result.statements),
                result.overall_assessment,
                result.processing_metadata.get("processing_time_seconds"),
                abstract_id
            ))

    def get_complete_result(self, abstract_id: int) -> Optional[PaperCheckResult]:
        """
        Retrieve complete result from database

        Args:
            abstract_id: Primary key from papercheck.abstracts_checked

        Returns:
            PaperCheckResult object or None if not found
        """
        # Implementation left for actual coding phase
        # Would query all related tables and reconstruct PaperCheckResult
        raise NotImplementedError("Retrieval implementation in actual coding phase")

    def list_recent_checks(self, limit: int = 100) -> List[Dict[str, Any]]:
        """
        List recent abstract checks with summary info

        Args:
            limit: Maximum number of results

        Returns:
            List of dicts with summary information
        """
        with self.conn.cursor(row_factory=dict_row) as cur:
            cur.execute("""
                SELECT
                    id,
                    source_pmid,
                    source_doi,
                    source_title,
                    checked_at,
                    num_statements,
                    overall_assessment,
                    status
                FROM papercheck.abstracts_checked
                ORDER BY checked_at DESC
                LIMIT %s
            """, (limit,))

            return cur.fetchall()

    def close(self):
        """Close database connection"""
        if self.conn:
            self.conn.close()
            logger.info("Database connection closed")

    def __enter__(self):
        """Context manager entry"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.close()
```

## Testing Strategy

Create `tests/test_papercheck_database.py`:

```python
"""Tests for PaperCheckDB class"""

import pytest
from bmlibrarian.paperchecker.database import PaperCheckDB
from bmlibrarian.paperchecker.data_models import (
    Statement, CounterStatement, SearchResults, ScoredDocument,
    ExtractedCitation, CounterReport, Verdict, PaperCheckResult
)


@pytest.fixture
def db():
    """Create test database connection"""
    # Use test database
    db = PaperCheckDB(connection_string="dbname=bmlibrarian_dev ...")
    yield db
    db.close()


@pytest.fixture
def sample_result():
    """Create sample PaperCheckResult"""
    statement = Statement(
        text="Metformin is superior to GLP-1",
        context="",
        statement_type="finding",
        confidence=0.9,
        statement_order=1
    )

    counter_stmt = CounterStatement(
        original_statement=statement,
        negated_text="GLP-1 is superior or equivalent",
        hyde_abstracts=["HyDE abstract 1"],
        keywords=["GLP-1", "metformin"],
        generation_metadata={}
    )

    search_results = SearchResults(
        semantic_docs=[1, 2],
        hyde_docs=[2, 3],
        keyword_docs=[3],
        deduplicated_docs=[1, 2, 3],
        provenance={1: ["semantic"], 2: ["semantic", "hyde"], 3: ["hyde", "keyword"]},
        search_metadata={}
    )

    scored_docs = [
        ScoredDocument(
            doc_id=1, document={}, score=5, explanation="Highly relevant",
            supports_counter=True, found_by=["semantic"]
        )
    ]

    citations = [
        ExtractedCitation(
            doc_id=1, passage="Evidence passage", relevance_score=5,
            full_citation="Smith 2023", metadata={}, citation_order=1
        )
    ]

    counter_report = CounterReport(
        summary="Counter-evidence summary",
        num_citations=1,
        citations=citations,
        search_stats={"documents_found": 3, "documents_scored": 1, "citations_extracted": 1},
        generation_metadata={}
    )

    verdict = Verdict(
        verdict="contradicts",
        rationale="Strong evidence contradicts original statement.",
        confidence="high",
        counter_report=counter_report,
        analysis_metadata={}
    )

    return PaperCheckResult(
        original_abstract="Test abstract about diabetes drugs.",
        source_metadata={"pmid": 12345678},
        statements=[statement],
        counter_statements=[counter_stmt],
        search_results=[search_results],
        scored_documents=[scored_docs],
        counter_reports=[counter_report],
        verdicts=[verdict],
        overall_assessment="Contradicted by literature",
        processing_metadata={"model": "gpt-oss:20b", "processing_time_seconds": 120.5}
    )


def test_database_connection(db):
    """Test database connection"""
    assert db.test_connection()


def test_save_complete_result(db, sample_result):
    """Test saving complete result"""
    abstract_id = db.save_complete_result(sample_result)

    assert isinstance(abstract_id, int)
    assert abstract_id > 0


def test_list_recent_checks(db, sample_result):
    """Test listing recent checks"""
    # Save a result
    abstract_id = db.save_complete_result(sample_result)

    # List recent
    recent = db.list_recent_checks(limit=10)

    assert len(recent) > 0
    assert any(r["id"] == abstract_id for r in recent)


def test_transaction_rollback_on_error(db):
    """Test that transaction rolls back on error"""
    # Create invalid result that will fail partway through save
    # (e.g., missing required field)

    # Attempt save
    try:
        db.save_complete_result(invalid_result)
    except:
        pass

    # Verify no partial data saved
    # (abstract count should be unchanged)
```

## Success Criteria

- [ ] PaperCheckDB class implemented
- [ ] All save methods working correctly
- [ ] Transaction management proper (rollback on errors)
- [ ] Foreign key relationships maintained
- [ ] Batch inserts efficient
- [ ] Connection management robust
- [ ] All unit tests passing
- [ ] Query methods working
- [ ] Context manager support
- [ ] Error handling comprehensive

## Next Steps

After completing this step, proceed to:
- **Step 12**: CLI Application (12_CLI_APPLICATION.md)
- Create paper_checker_cli.py for batch processing abstracts
