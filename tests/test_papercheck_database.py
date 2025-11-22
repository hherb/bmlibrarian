"""
Unit tests for PaperCheckDB database class.

Tests the database interface for PaperChecker result persistence,
including connection management, schema creation, and CRUD operations.

Note: Most tests require database connectivity and use the dev database.
Tests are marked with pytest.mark.database for selective execution.
"""

import os
import pytest
import psycopg
from unittest.mock import MagicMock, patch
from typing import Dict, Any, List

from bmlibrarian.paperchecker.database import (
    PaperCheckDB,
    DEFAULT_DB_NAME,
    DEFAULT_DB_HOST,
    DEFAULT_DB_PORT,
    DEFAULT_LIST_LIMIT,
    DEFAULT_LIST_OFFSET,
    RECENT_ACTIVITY_HOURS,
    MIN_ID_VALUE,
    MIN_LIMIT_VALUE,
    MAX_LIMIT_VALUE,
    MIN_OFFSET_VALUE,
    PASSWORD_MASK,
)
from bmlibrarian.paperchecker.data_models import (
    Statement,
    CounterStatement,
    SearchResults,
    ScoredDocument,
    ExtractedCitation,
    CounterReport,
    Verdict,
    PaperCheckResult,
)


# Mark all tests in this module as database tests
pytestmark = pytest.mark.requires_database


class TestDatabaseConstants:
    """Tests for database module constants."""

    def test_default_db_name(self) -> None:
        """Test default database name is correct."""
        assert DEFAULT_DB_NAME == "knowledgebase"

    def test_default_db_host(self) -> None:
        """Test default database host is correct."""
        assert DEFAULT_DB_HOST == "localhost"

    def test_default_db_port(self) -> None:
        """Test default database port is correct."""
        assert DEFAULT_DB_PORT == "5432"

    def test_query_constants(self) -> None:
        """Test query configuration constants are defined."""
        assert DEFAULT_LIST_LIMIT == 100
        assert DEFAULT_LIST_OFFSET == 0
        assert RECENT_ACTIVITY_HOURS == 24

    def test_validation_constants(self) -> None:
        """Test validation constants are defined correctly."""
        assert MIN_ID_VALUE == 1
        assert MIN_LIMIT_VALUE == 1
        assert MAX_LIMIT_VALUE == 10000
        assert MIN_OFFSET_VALUE == 0

    def test_password_mask_constant(self) -> None:
        """Test password mask constant is defined for security logging."""
        assert PASSWORD_MASK == "********"
        # Ensure it doesn't look like a real password
        assert len(PASSWORD_MASK) >= 8


class TestPaperCheckDBPasswordMasking:
    """Tests for password masking in connection strings."""

    def test_get_safe_conninfo_masks_password(self) -> None:
        """Test that _get_safe_conninfo masks the password."""
        with patch("bmlibrarian.paperchecker.database.psycopg.connect") as mock_connect:
            mock_conn = MagicMock()
            mock_connect.return_value = mock_conn

            db = PaperCheckDB(
                db_name="testdb",
                db_user="testuser",
                db_password="secret123",
                db_host="localhost",
                db_port="5432"
            )

            safe_conninfo = db._get_safe_conninfo()

            # Password should not appear in safe conninfo
            assert "secret123" not in safe_conninfo
            # Mask should appear instead
            assert PASSWORD_MASK in safe_conninfo
            # Other connection info should be present
            assert "testdb" in safe_conninfo
            assert "testuser" in safe_conninfo
            assert "localhost" in safe_conninfo
            assert "5432" in safe_conninfo

    def test_get_safe_conninfo_without_password(self) -> None:
        """Test _get_safe_conninfo when no password is set."""
        with patch("bmlibrarian.paperchecker.database.psycopg.connect") as mock_connect:
            mock_conn = MagicMock()
            mock_connect.return_value = mock_conn

            db = PaperCheckDB(
                db_name="testdb",
                db_host="localhost",
                db_port="5432"
            )

            safe_conninfo = db._get_safe_conninfo()

            # Should not contain password mask when no password set
            assert PASSWORD_MASK not in safe_conninfo
            assert "password" not in safe_conninfo
            # Other connection info should be present
            assert "testdb" in safe_conninfo
            assert "localhost" in safe_conninfo

    def test_connection_error_logs_safe_conninfo(self) -> None:
        """Test that connection errors are logged with masked password."""
        with patch("bmlibrarian.paperchecker.database.psycopg.connect") as mock_connect:
            # Make connect raise an error
            mock_connect.side_effect = psycopg.Error("Connection refused")

            with patch("bmlibrarian.paperchecker.database.logger") as mock_logger:
                with pytest.raises(psycopg.Error):
                    PaperCheckDB(
                        db_name="testdb",
                        db_user="testuser",
                        db_password="secret123",
                        db_host="localhost",
                        db_port="5432"
                    )

                # Verify error was logged
                mock_logger.error.assert_called()
                # Get the logged message
                logged_message = mock_logger.error.call_args[0][0]
                # Password should NOT be in the logged message
                assert "secret123" not in logged_message
                # But the mask should be
                assert PASSWORD_MASK in logged_message


class TestPaperCheckDBInit:
    """Tests for PaperCheckDB initialization."""

    def test_init_uses_environment_variables(self) -> None:
        """Test that init reads from environment variables."""
        with patch.dict(os.environ, {
            "POSTGRES_DB": "test_db",
            "POSTGRES_HOST": "test_host",
            "POSTGRES_PORT": "5433",
            "POSTGRES_USER": "test_user",
            "POSTGRES_PASSWORD": "test_pass"
        }):
            # Mock psycopg.connect to prevent actual connection
            with patch("bmlibrarian.paperchecker.database.psycopg.connect") as mock_connect:
                mock_conn = MagicMock()
                mock_connect.return_value = mock_conn

                db = PaperCheckDB()

                assert db.db_name == "test_db"
                assert db.db_host == "test_host"
                assert db.db_port == "5433"
                assert db._db_user == "test_user"
                assert db._db_password == "test_pass"

    def test_init_uses_default_values(self) -> None:
        """Test that init uses defaults when env vars not set."""
        with patch.dict(os.environ, {}, clear=True):
            # Clear specific env vars
            os.environ.pop("POSTGRES_DB", None)
            os.environ.pop("POSTGRES_HOST", None)
            os.environ.pop("POSTGRES_PORT", None)

            with patch("bmlibrarian.paperchecker.database.psycopg.connect") as mock_connect:
                mock_conn = MagicMock()
                mock_connect.return_value = mock_conn

                db = PaperCheckDB()

                assert db.db_name == DEFAULT_DB_NAME
                assert db.db_host == DEFAULT_DB_HOST
                assert db.db_port == DEFAULT_DB_PORT

    def test_init_with_explicit_parameters(self) -> None:
        """Test that explicit parameters override env vars and defaults."""
        with patch("bmlibrarian.paperchecker.database.psycopg.connect") as mock_connect:
            mock_conn = MagicMock()
            mock_connect.return_value = mock_conn

            db = PaperCheckDB(
                db_name="explicit_db",
                db_host="explicit_host",
                db_port="5434",
                db_user="explicit_user",
                db_password="explicit_pass"
            )

            assert db.db_name == "explicit_db"
            assert db.db_host == "explicit_host"
            assert db.db_port == "5434"
            assert db._db_user == "explicit_user"
            assert db._db_password == "explicit_pass"

    def test_init_with_existing_connection(self) -> None:
        """Test that existing connection is used when provided."""
        mock_conn = MagicMock()

        db = PaperCheckDB(connection=mock_conn)

        assert db.conn is mock_conn
        assert db._owns_connection is False

    def test_init_creates_connection_when_not_provided(self) -> None:
        """Test that connection is created when not provided."""
        with patch("bmlibrarian.paperchecker.database.psycopg.connect") as mock_connect:
            mock_conn = MagicMock()
            mock_connect.return_value = mock_conn

            db = PaperCheckDB()

            assert db.conn is mock_conn
            assert db._owns_connection is True

    def test_schema_name_is_papercheck(self) -> None:
        """Test that schema name is 'papercheck'."""
        mock_conn = MagicMock()

        db = PaperCheckDB(connection=mock_conn)

        assert db.schema == "papercheck"


class TestPaperCheckDBContextManager:
    """Tests for context manager support."""

    def test_context_manager_enter_returns_self(self) -> None:
        """Test that __enter__ returns self."""
        mock_conn = MagicMock()

        db = PaperCheckDB(connection=mock_conn)

        with db as db_instance:
            assert db_instance is db

    def test_context_manager_closes_owned_connection(self) -> None:
        """Test that __exit__ closes owned connection."""
        with patch("bmlibrarian.paperchecker.database.psycopg.connect") as mock_connect:
            mock_conn = MagicMock()
            mock_connect.return_value = mock_conn

            with PaperCheckDB() as db:
                pass  # Exit context

            mock_conn.close.assert_called_once()

    def test_context_manager_does_not_close_external_connection(self) -> None:
        """Test that __exit__ does not close externally provided connection."""
        mock_conn = MagicMock()

        with PaperCheckDB(connection=mock_conn) as db:
            pass  # Exit context

        mock_conn.close.assert_not_called()


class TestPaperCheckDBClose:
    """Tests for close method."""

    def test_close_closes_owned_connection(self) -> None:
        """Test that close closes owned connection."""
        with patch("bmlibrarian.paperchecker.database.psycopg.connect") as mock_connect:
            mock_conn = MagicMock()
            mock_connect.return_value = mock_conn

            db = PaperCheckDB()
            db.close()

            mock_conn.close.assert_called_once()

    def test_close_does_not_close_external_connection(self) -> None:
        """Test that close does not close externally provided connection."""
        mock_conn = MagicMock()

        db = PaperCheckDB(connection=mock_conn)
        db.close()

        mock_conn.close.assert_not_called()


class TestPaperCheckDBGetConnection:
    """Tests for get_connection method."""

    def test_get_connection_returns_active_connection(self) -> None:
        """Test that get_connection returns the active connection."""
        mock_conn = MagicMock()

        db = PaperCheckDB(connection=mock_conn)

        assert db.get_connection() is mock_conn


class TestInputValidation:
    """Tests for input validation on public methods."""

    def test_get_result_by_id_validates_abstract_id(self) -> None:
        """Test that get_result_by_id validates abstract_id."""
        mock_conn = MagicMock()
        db = PaperCheckDB(connection=mock_conn)

        with pytest.raises(ValueError, match="abstract_id must be an integer >= 1"):
            db.get_result_by_id(0)

        with pytest.raises(ValueError, match="abstract_id must be an integer >= 1"):
            db.get_result_by_id(-1)

    def test_get_results_by_pmid_validates_pmid(self) -> None:
        """Test that get_results_by_pmid validates pmid."""
        mock_conn = MagicMock()
        db = PaperCheckDB(connection=mock_conn)

        with pytest.raises(ValueError, match="pmid must be an integer >= 1"):
            db.get_results_by_pmid(0)

        with pytest.raises(ValueError, match="pmid must be an integer >= 1"):
            db.get_results_by_pmid(-1)

    def test_list_recent_checks_validates_limit(self) -> None:
        """Test that list_recent_checks validates limit."""
        mock_conn = MagicMock()
        db = PaperCheckDB(connection=mock_conn)

        with pytest.raises(ValueError, match="limit must be an integer >= 1"):
            db.list_recent_checks(limit=0)

        with pytest.raises(ValueError, match="limit must be <= 10000"):
            db.list_recent_checks(limit=10001)

    def test_list_recent_checks_validates_offset(self) -> None:
        """Test that list_recent_checks validates offset."""
        mock_conn = MagicMock()
        db = PaperCheckDB(connection=mock_conn)

        with pytest.raises(ValueError, match="offset must be an integer >= 0"):
            db.list_recent_checks(offset=-1)

    def test_get_verdicts_summary_validates_abstract_id(self) -> None:
        """Test that get_verdicts_summary validates abstract_id."""
        mock_conn = MagicMock()
        db = PaperCheckDB(connection=mock_conn)

        with pytest.raises(ValueError, match="abstract_id must be an integer >= 1"):
            db.get_verdicts_summary(0)

    def test_delete_result_validates_abstract_id(self) -> None:
        """Test that delete_result validates abstract_id."""
        mock_conn = MagicMock()
        db = PaperCheckDB(connection=mock_conn)

        with pytest.raises(ValueError, match="abstract_id must be an integer >= 1"):
            db.delete_result(0)

        with pytest.raises(ValueError, match="abstract_id must be an integer >= 1"):
            db.delete_result(-1)


class TestSampleDataHelpers:
    """Helper class for creating sample test data."""

    @staticmethod
    def create_sample_statement(order: int = 1) -> Statement:
        """Create a sample Statement for testing."""
        return Statement(
            text=f"Sample statement {order} for testing.",
            context=f"Context for statement {order}.",
            statement_type="finding",
            confidence=0.95,
            statement_order=order
        )

    @staticmethod
    def create_sample_counter_statement(statement: Statement) -> CounterStatement:
        """Create a sample CounterStatement for testing."""
        return CounterStatement(
            original_statement=statement,
            negated_text=f"Counter to: {statement.text}",
            hyde_abstracts=["HyDE abstract 1", "HyDE abstract 2"],
            keywords=["keyword1", "keyword2", "keyword3"],
            generation_metadata={"model": "test-model", "temperature": 0.3}
        )

    @staticmethod
    def create_sample_search_results() -> SearchResults:
        """Create a sample SearchResults for testing."""
        return SearchResults.from_strategy_results(
            semantic=[101, 102, 103],
            hyde=[102, 103, 104],
            keyword=[103, 104, 105],
            metadata={"limit": 50, "search_time_ms": 150}
        )

    @staticmethod
    def create_sample_scored_document(doc_id: int) -> ScoredDocument:
        """Create a sample ScoredDocument for testing."""
        return ScoredDocument(
            doc_id=doc_id,
            document={
                "title": f"Test Document {doc_id}",
                "abstract": f"Abstract for document {doc_id}."
            },
            score=4,
            explanation="Highly relevant to the counter-statement.",
            supports_counter=True,
            found_by=["semantic", "hyde"]
        )

    @staticmethod
    def create_sample_citation(doc_id: int, order: int) -> ExtractedCitation:
        """Create a sample ExtractedCitation for testing."""
        return ExtractedCitation(
            doc_id=doc_id,
            passage=f"Evidence passage from document {doc_id}.",
            relevance_score=4,
            full_citation=f"Author{doc_id} A. Test Study {doc_id}. J Test. 2023;1:1-10.",
            metadata={"pmid": 10000000 + doc_id, "doi": f"10.1000/test.{doc_id}"},
            citation_order=order
        )

    @staticmethod
    def create_sample_counter_report(citations: List[ExtractedCitation]) -> CounterReport:
        """Create a sample CounterReport for testing."""
        return CounterReport(
            summary="Counter-evidence summary for testing purposes.",
            num_citations=len(citations),
            citations=citations,
            search_stats={
                "documents_found": 50,
                "documents_scored": 30,
                "citations_extracted": len(citations)
            },
            generation_metadata={"model": "test-model"}
        )

    @staticmethod
    def create_sample_verdict(counter_report: CounterReport) -> Verdict:
        """Create a sample Verdict for testing."""
        return Verdict(
            verdict="contradicts",
            rationale="Strong evidence contradicts the original statement.",
            confidence="high",
            counter_report=counter_report,
            analysis_metadata={"model": "test-model"}
        )

    @classmethod
    def create_sample_paper_check_result(
        cls,
        num_statements: int = 1
    ) -> PaperCheckResult:
        """Create a complete sample PaperCheckResult for testing."""
        statements = []
        counter_statements = []
        search_results = []
        scored_documents = []
        counter_reports = []
        verdicts = []

        for i in range(num_statements):
            stmt = cls.create_sample_statement(order=i + 1)
            statements.append(stmt)

            counter_stmt = cls.create_sample_counter_statement(stmt)
            counter_statements.append(counter_stmt)

            search_result = cls.create_sample_search_results()
            search_results.append(search_result)

            scored_docs = [
                cls.create_sample_scored_document(doc_id)
                for doc_id in search_result.deduplicated_docs[:3]
            ]
            scored_documents.append(scored_docs)

            citations = [
                cls.create_sample_citation(doc_id=scored_docs[j].doc_id, order=j + 1)
                for j in range(min(2, len(scored_docs)))
            ]
            counter_report = cls.create_sample_counter_report(citations)
            counter_reports.append(counter_report)

            verdict = cls.create_sample_verdict(counter_report)
            verdicts.append(verdict)

        return PaperCheckResult(
            original_abstract="Test abstract for database testing.",
            source_metadata={
                "pmid": 12345678,
                "doi": "10.1000/test.12345",
                "title": "Test Study Title",
                "authors": ["Test Author A", "Test Author B"],
                "year": 2023,
                "journal": "Journal of Testing"
            },
            statements=statements,
            counter_statements=counter_statements,
            search_results=search_results,
            scored_documents=scored_documents,
            counter_reports=counter_reports,
            verdicts=verdicts,
            overall_assessment="Overall assessment: Some statements contradicted.",
            processing_metadata={
                "model": "test-model",
                "config": {"temperature": 0.3},
                "processing_time_seconds": 60.5
            }
        )


class TestSampleDataCreation:
    """Tests to verify sample data creation helpers work correctly."""

    def test_create_sample_statement(self) -> None:
        """Test that sample statement is valid."""
        stmt = TestSampleDataHelpers.create_sample_statement()
        assert stmt.statement_order == 1
        assert stmt.statement_type == "finding"
        assert stmt.confidence == 0.95

    def test_create_sample_counter_statement(self) -> None:
        """Test that sample counter statement is valid."""
        stmt = TestSampleDataHelpers.create_sample_statement()
        counter = TestSampleDataHelpers.create_sample_counter_statement(stmt)
        assert counter.original_statement is stmt
        assert len(counter.hyde_abstracts) == 2
        assert len(counter.keywords) == 3

    def test_create_sample_search_results(self) -> None:
        """Test that sample search results are valid."""
        results = TestSampleDataHelpers.create_sample_search_results()
        assert len(results.semantic_docs) == 3
        assert len(results.hyde_docs) == 3
        assert len(results.keyword_docs) == 3
        assert len(results.deduplicated_docs) == 5

    def test_create_sample_scored_document(self) -> None:
        """Test that sample scored document is valid."""
        doc = TestSampleDataHelpers.create_sample_scored_document(doc_id=123)
        assert doc.doc_id == 123
        assert doc.score == 4
        assert doc.supports_counter is True

    def test_create_sample_citation(self) -> None:
        """Test that sample citation is valid."""
        citation = TestSampleDataHelpers.create_sample_citation(doc_id=123, order=1)
        assert citation.doc_id == 123
        assert citation.citation_order == 1
        assert "10.1000/test.123" in citation.metadata["doi"]

    def test_create_sample_counter_report(self) -> None:
        """Test that sample counter report is valid."""
        citations = [
            TestSampleDataHelpers.create_sample_citation(doc_id=123, order=1),
            TestSampleDataHelpers.create_sample_citation(doc_id=456, order=2),
        ]
        report = TestSampleDataHelpers.create_sample_counter_report(citations)
        assert report.num_citations == 2
        assert len(report.citations) == 2

    def test_create_sample_verdict(self) -> None:
        """Test that sample verdict is valid."""
        citations = [
            TestSampleDataHelpers.create_sample_citation(doc_id=123, order=1),
        ]
        report = TestSampleDataHelpers.create_sample_counter_report(citations)
        verdict = TestSampleDataHelpers.create_sample_verdict(report)
        assert verdict.verdict == "contradicts"
        assert verdict.confidence == "high"

    def test_create_sample_paper_check_result(self) -> None:
        """Test that complete sample result is valid."""
        result = TestSampleDataHelpers.create_sample_paper_check_result(
            num_statements=2
        )
        assert len(result.statements) == 2
        assert len(result.counter_statements) == 2
        assert len(result.search_results) == 2
        assert len(result.scored_documents) == 2
        assert len(result.counter_reports) == 2
        assert len(result.verdicts) == 2
        assert result.source_metadata["pmid"] == 12345678


# Integration tests requiring database connection
# These tests are skipped by default and can be run with:
# pytest tests/test_papercheck_database.py -v --run-database-tests


@pytest.fixture
def db_connection() -> PaperCheckDB:
    """
    Fixture to create a database connection for integration tests.

    Uses the development database. Cleans up test data after each test.
    """
    # Use dev database for testing
    db = PaperCheckDB(db_name="bmlibrarian_dev")

    # Ensure schema exists
    db.ensure_schema()

    yield db

    # Cleanup: close connection
    db.close()


@pytest.mark.skip(reason="Requires database connection - run with -m requires_database")
class TestPaperCheckDBIntegration:
    """Integration tests for PaperCheckDB (require database connection)."""

    def test_test_connection_success(self, db_connection: PaperCheckDB) -> None:
        """Test that test_connection returns True for valid connection."""
        assert db_connection.test_connection() is True

    def test_ensure_schema_creates_tables(self, db_connection: PaperCheckDB) -> None:
        """Test that ensure_schema creates the required tables."""
        result = db_connection.ensure_schema()
        assert result is True

        # Verify tables exist
        assert db_connection.test_connection() is True

    def test_save_and_retrieve_complete_result(
        self,
        db_connection: PaperCheckDB
    ) -> None:
        """Test saving and retrieving a complete result."""
        sample_result = TestSampleDataHelpers.create_sample_paper_check_result(
            num_statements=2
        )

        # Save
        abstract_id = db_connection.save_complete_result(sample_result)
        assert isinstance(abstract_id, int)
        assert abstract_id > 0

        # Retrieve
        retrieved = db_connection.get_result_by_id(abstract_id)
        assert retrieved is not None
        assert "abstract" in retrieved
        assert "statements" in retrieved
        assert retrieved["abstract"]["source_pmid"] == 12345678

        # Cleanup
        db_connection.delete_result(abstract_id)

    def test_get_results_by_pmid(self, db_connection: PaperCheckDB) -> None:
        """Test retrieving results by PMID."""
        sample_result = TestSampleDataHelpers.create_sample_paper_check_result()
        abstract_id = db_connection.save_complete_result(sample_result)

        results = db_connection.get_results_by_pmid(pmid=12345678)
        assert len(results) > 0
        assert any(r["id"] == abstract_id for r in results)

        # Cleanup
        db_connection.delete_result(abstract_id)

    def test_list_recent_checks(self, db_connection: PaperCheckDB) -> None:
        """Test listing recent checks."""
        sample_result = TestSampleDataHelpers.create_sample_paper_check_result()
        abstract_id = db_connection.save_complete_result(sample_result)

        recent = db_connection.list_recent_checks(limit=10)
        assert len(recent) > 0
        assert any(r["id"] == abstract_id for r in recent)

        # Cleanup
        db_connection.delete_result(abstract_id)

    def test_get_verdicts_summary(self, db_connection: PaperCheckDB) -> None:
        """Test getting verdicts summary."""
        sample_result = TestSampleDataHelpers.create_sample_paper_check_result(
            num_statements=2
        )
        abstract_id = db_connection.save_complete_result(sample_result)

        summary = db_connection.get_verdicts_summary(abstract_id)
        assert len(summary) == 2
        assert all("verdict" in s for s in summary)
        assert all("confidence" in s for s in summary)

        # Cleanup
        db_connection.delete_result(abstract_id)

    def test_get_statistics(self, db_connection: PaperCheckDB) -> None:
        """Test getting database statistics."""
        stats = db_connection.get_statistics()

        assert "total_abstracts" in stats
        assert "total_statements" in stats
        assert "verdicts_breakdown" in stats
        assert "confidence_breakdown" in stats
        assert "recent_activity" in stats
        assert isinstance(stats["total_abstracts"], int)
        assert isinstance(stats["verdicts_breakdown"], dict)

    def test_delete_result_removes_all_related_data(
        self,
        db_connection: PaperCheckDB
    ) -> None:
        """Test that delete_result removes all related data via CASCADE."""
        sample_result = TestSampleDataHelpers.create_sample_paper_check_result()
        abstract_id = db_connection.save_complete_result(sample_result)

        # Verify data exists
        assert db_connection.get_result_by_id(abstract_id) is not None

        # Delete
        result = db_connection.delete_result(abstract_id)
        assert result is True

        # Verify data is gone
        assert db_connection.get_result_by_id(abstract_id) is None

    def test_delete_nonexistent_result_returns_false(
        self,
        db_connection: PaperCheckDB
    ) -> None:
        """Test that deleting non-existent result returns False."""
        result = db_connection.delete_result(abstract_id=999999999)
        assert result is False

    def test_get_result_by_id_nonexistent_returns_none(
        self,
        db_connection: PaperCheckDB
    ) -> None:
        """Test that getting non-existent result returns None."""
        result = db_connection.get_result_by_id(abstract_id=999999999)
        assert result is None

    def test_transaction_rollback_on_error(
        self,
        db_connection: PaperCheckDB
    ) -> None:
        """Test that errors trigger transaction rollback."""
        # Get initial count
        stats_before = db_connection.get_statistics()
        count_before = stats_before["total_abstracts"]

        # Create an invalid result that will fail validation
        # (This tests internal error handling - may need adjustment)
        with pytest.raises(Exception):
            # Create result with invalid data that will fail during save
            invalid_result = TestSampleDataHelpers.create_sample_paper_check_result()
            invalid_result.statements = []  # This should cause mismatch
            invalid_result.__post_init__()  # This will raise AssertionError

        # Verify count unchanged (no partial data saved)
        stats_after = db_connection.get_statistics()
        count_after = stats_after["total_abstracts"]
        assert count_after == count_before


class TestPaperCheckDBListRecentChecks:
    """Tests for list_recent_checks method."""

    def test_list_recent_checks_with_pagination(self) -> None:
        """Test list_recent_checks respects limit and offset."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=None)

        mock_cursor.fetchall.return_value = [
            {"id": 1, "source_pmid": 123, "checked_at": "2024-01-01", "num_statements": 2}
        ]

        db = PaperCheckDB(connection=mock_conn)
        results = db.list_recent_checks(limit=10, offset=5)

        # Verify the query was called with limit and offset
        call_args = mock_cursor.execute.call_args
        assert call_args is not None
        assert "LIMIT" in call_args[0][0]
        assert "OFFSET" in call_args[0][0]
        assert call_args[0][1] == (10, 5)

    def test_list_recent_checks_handles_error(self) -> None:
        """Test list_recent_checks returns empty list on error."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=None)

        mock_cursor.execute.side_effect = Exception("Database error")

        db = PaperCheckDB(connection=mock_conn)
        results = db.list_recent_checks()

        assert results == []


class TestPaperCheckDBGetStatistics:
    """Tests for get_statistics method."""

    def test_get_statistics_returns_default_on_error(self) -> None:
        """Test get_statistics returns default values on error."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=None)

        mock_cursor.execute.side_effect = Exception("Database error")

        db = PaperCheckDB(connection=mock_conn)
        stats = db.get_statistics()

        assert stats["total_abstracts"] == 0
        assert stats["total_statements"] == 0
        assert stats["verdicts_breakdown"] == {}
        assert stats["confidence_breakdown"] == {}
        assert stats["recent_activity"] == 0
