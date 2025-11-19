"""
Tests for PubMedQA Abstract Importer

These tests verify the import functionality for PubMedQA abstracts into the factcheck.statements table.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from pathlib import Path
import sys
import os

# Add parent directory to path for importing the script
sys.path.insert(0, str(Path(__file__).parent.parent))

# Mock the migrations module before importing
sys.modules['src.bmlibrarian.migrations'] = MagicMock()

from import_pubmedqa_abstracts import PubMedQAImporter


class TestPubMedQAImporter:
    """Test cases for PubMedQAImporter class."""

    @pytest.fixture
    def importer_params(self):
        """Fixture providing importer initialization parameters."""
        return {
            'host': 'localhost',
            'port': '5432',
            'user': 'testuser',
            'password': 'testpass',
            'database': 'testdb'
        }

    @pytest.fixture
    def importer(self, importer_params):
        """Fixture providing a PubMedQAImporter instance."""
        return PubMedQAImporter(**importer_params)

    @pytest.fixture
    def sample_json_data(self):
        """Fixture providing sample PubMedQA data."""
        return {
            "12345678": {
                "QUESTION": "Does vitamin D supplementation reduce risk of cardiovascular disease?",
                "CONTEXTS": [
                    "Background: Vitamin D deficiency is common in the general population.",
                    "Methods: We conducted a randomized controlled trial with 1000 participants.",
                    "Results: No significant difference was observed between groups."
                ],
                "LONG_ANSWER": "Our study found no evidence that vitamin D supplementation reduces cardiovascular disease risk.",
                "final_decision": "no"
            },
            "23456789": {
                "QUESTION": "Is metformin effective for weight loss in non-diabetic individuals?",
                "CONTEXTS": [
                    "Background: Metformin is widely used for diabetes management.",
                    "Objective: To assess metformin's effect on weight in non-diabetic patients."
                ],
                "LONG_ANSWER": "Metformin shows modest weight loss effects in non-diabetic individuals.",
                "final_decision": "yes"
            },
            "34567890": {
                "QUESTION": "Can probiotics prevent antibiotic-associated diarrhea?",
                "CONTEXTS": [
                    "Background: Antibiotic use often causes gastrointestinal side effects."
                ],
                "LONG_ANSWER": "Evidence suggests probiotics may help but more research is needed.",
                "final_decision": "maybe"
            }
        }

    def test_initialization(self, importer_params):
        """Test importer initialization with parameters."""
        importer = PubMedQAImporter(**importer_params)

        assert importer.conn_params['host'] == 'localhost'
        assert importer.conn_params['port'] == '5432'
        assert importer.conn_params['user'] == 'testuser'
        assert importer.conn_params['password'] == 'testpass'
        assert importer.conn_params['dbname'] == 'testdb'

    @patch.dict(os.environ, {
        'POSTGRES_HOST': 'testhost',
        'POSTGRES_PORT': '5433',
        'POSTGRES_USER': 'envuser',
        'POSTGRES_PASSWORD': 'envpass',
        'POSTGRES_DB': 'envdb'
    })
    def test_from_env(self):
        """Test initialization from environment variables."""
        importer = PubMedQAImporter.from_env()

        assert importer.conn_params['host'] == 'testhost'
        assert importer.conn_params['port'] == '5433'
        assert importer.conn_params['user'] == 'envuser'
        assert importer.conn_params['password'] == 'envpass'
        assert importer.conn_params['dbname'] == 'envdb'

    def test_from_env_missing_credentials(self):
        """Test from_env raises ValueError when credentials are missing."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError, match="Missing POSTGRES_USER or POSTGRES_PASSWORD"):
                PubMedQAImporter.from_env()

    @patch('psycopg.connect')
    def test_connection_error_handling(self, mock_connect, importer):
        """Test that database connection errors are sanitized."""
        import psycopg

        # Simulate connection failure
        mock_connect.side_effect = psycopg.OperationalError("FATAL: password authentication failed for user 'testuser'")

        with pytest.raises(ConnectionError) as exc_info:
            importer._get_connection()

        # Verify error message is sanitized (no password exposed)
        error_message = str(exc_info.value)
        assert 'testpass' not in error_message
        assert 'testdb' in error_message or 'localhost' in error_message

    def test_validate_json_structure_valid(self, importer, sample_json_data):
        """Test JSON validation with valid data."""
        success, message = importer.validate_json_structure(sample_json_data)

        assert success is True
        assert '3 entries' in message

    def test_validate_json_structure_empty(self, importer):
        """Test JSON validation with empty data."""
        success, message = importer.validate_json_structure({})

        assert success is False
        assert 'empty' in message.lower()

    def test_validate_json_structure_not_dict(self, importer):
        """Test JSON validation with non-dictionary data."""
        success, message = importer.validate_json_structure([])

        assert success is False
        assert 'dictionary' in message.lower()

    def test_validate_json_structure_missing_fields(self, importer):
        """Test JSON validation with missing required fields."""
        invalid_data = {
            "12345": {
                "QUESTION": "Test question?",
                # Missing CONTEXTS, LONG_ANSWER, final_decision
            }
        }

        success, message = importer.validate_json_structure(invalid_data)

        assert success is False
        assert 'missing fields' in message.lower()

    def test_validate_json_structure_invalid_decision(self, importer):
        """Test JSON validation with invalid final_decision."""
        invalid_data = {
            "12345": {
                "QUESTION": "Test question?",
                "CONTEXTS": ["Context 1"],
                "LONG_ANSWER": "Answer",
                "final_decision": "unknown"  # Invalid value
            }
        }

        success, message = importer.validate_json_structure(invalid_data)

        assert success is False
        assert 'yes/no/maybe' in message.lower()

    @patch('psycopg.connect')
    def test_validate_table_structure_success(self, mock_connect, importer):
        """Test table structure validation with correct schema."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_conn.__enter__.return_value = mock_conn
        mock_connect.return_value = mock_conn

        # Mock schema exists
        mock_cursor.fetchone.side_effect = [
            (True,),  # Schema exists
            (True,),  # Table exists
        ]

        # Mock column list
        mock_cursor.fetchall.return_value = [
            ('statement_id',), ('statement_text',), ('input_statement_id',),
            ('expected_answer',), ('created_at',), ('source_file',),
            ('review_status',), ('context',), ('long_answer',)
        ]

        success, message = importer.validate_table_structure()

        assert success is True
        assert 'validated successfully' in message.lower()

    @patch('psycopg.connect')
    def test_validate_table_structure_missing_schema(self, mock_connect, importer):
        """Test table validation when schema is missing."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_conn.__enter__.return_value = mock_conn
        mock_connect.return_value = mock_conn

        # Mock schema does not exist
        mock_cursor.fetchone.return_value = (False,)

        success, message = importer.validate_table_structure()

        assert success is False
        assert 'schema does not exist' in message.lower()

    @patch('psycopg.connect')
    def test_validate_table_structure_missing_columns(self, mock_connect, importer):
        """Test table validation when required columns are missing."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_conn.__enter__.return_value = mock_conn
        mock_connect.return_value = mock_conn

        # Mock schema and table exist
        mock_cursor.fetchone.side_effect = [(True,), (True,)]

        # Mock column list without context and long_answer
        mock_cursor.fetchall.return_value = [
            ('statement_id',), ('statement_text',), ('input_statement_id',),
            ('expected_answer',), ('created_at',), ('source_file',), ('review_status',)
        ]

        success, message = importer.validate_table_structure()

        assert success is False
        assert 'missing columns' in message.lower()
        assert 'context' in message.lower() or 'long_answer' in message.lower()

    @patch('psycopg.connect')
    def test_validate_table_structure_connection_error(self, mock_connect, importer):
        """Test table validation handles connection errors."""
        import psycopg
        mock_connect.side_effect = psycopg.OperationalError("Connection failed")

        success, message = importer.validate_table_structure()

        assert success is False
        assert 'connection failed' in message.lower()

    @patch('psycopg.connect')
    def test_count_existing_rows(self, mock_connect, importer):
        """Test counting existing rows in table."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_conn.__enter__.return_value = mock_conn
        mock_connect.return_value = mock_conn

        mock_cursor.fetchone.return_value = (42,)

        count = importer.count_existing_rows()

        assert count == 42

    @patch('psycopg.connect')
    def test_insert_data_dry_run(self, mock_connect, importer, sample_json_data):
        """Test insert operation in dry-run mode."""
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn

        inserted, updated, skipped, errors = importer._insert_data(
            sample_json_data,
            source_file='test.json',
            dry_run=True
        )

        # In dry-run, should report would-be inserts but not execute
        assert inserted == len(sample_json_data)
        assert updated == 0
        assert skipped == 0
        assert len(errors) == 0

        # Verify no actual database operations occurred
        mock_conn.cursor.assert_not_called()

    @patch('psycopg.connect')
    def test_insert_data_actual(self, mock_connect, importer, sample_json_data):
        """Test actual insert operation."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_conn.__enter__.return_value = mock_conn
        mock_connect.return_value = mock_conn

        # Mock successful inserts
        mock_cursor.rowcount = 1

        inserted, updated, skipped, errors = importer._insert_data(
            sample_json_data,
            source_file='test.json',
            dry_run=False
        )

        assert inserted == len(sample_json_data)
        assert len(errors) == 0

        # Verify commit was called
        mock_conn.commit.assert_called_once()

    @patch('psycopg.connect')
    def test_update_data_dry_run_batching(self, mock_connect, importer, sample_json_data):
        """Test update operation in dry-run mode uses batching."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_conn.__enter__.return_value = mock_conn
        mock_connect.return_value = mock_conn

        # Mock batch query result
        mock_cursor.fetchall.return_value = [
            (1, "Does vitamin D supplementation reduce risk of cardiovascular disease?", False, False),
        ]

        inserted, updated, skipped, errors = importer._update_data(
            sample_json_data,
            source_file='test.json',
            dry_run=True
        )

        # Verify batch query was used (WHERE statement_text = ANY(%s))
        calls = mock_cursor.execute.call_args_list
        assert len(calls) > 0
        assert 'ANY' in calls[0][0][0]  # First call should use batch query

        assert inserted == 0
        assert updated == 0
        assert len(errors) == 0

    @patch('psycopg.connect')
    def test_update_data_upsert(self, mock_connect, importer, sample_json_data):
        """Test UPSERT behavior (insert new, update existing)."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_conn.__enter__.return_value = mock_conn
        mock_connect.return_value = mock_conn

        # Mock UPSERT results: first is INSERT (xmax=0), second is UPDATE (xmax>0)
        mock_cursor.fetchone.side_effect = [
            (True,),   # First: INSERT (xmax = 0)
            (False,),  # Second: UPDATE (xmax > 0)
            (False,),  # Third: UPDATE (xmax > 0)
        ]

        inserted, updated, skipped, errors = importer._update_data(
            sample_json_data,
            source_file='test.json',
            dry_run=False
        )

        assert inserted == 1
        assert updated == 2
        assert len(errors) == 0

        # Verify commit was called
        mock_conn.commit.assert_called_once()

    @patch('psycopg.connect')
    def test_import_data_empty_table(self, mock_connect, importer, sample_json_data):
        """Test import_data routes to INSERT when table is empty."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_conn.__enter__.return_value = mock_conn
        mock_connect.return_value = mock_conn

        # Mock count query returns 0
        mock_cursor.fetchone.return_value = (0,)
        mock_cursor.rowcount = 1

        with patch.object(importer, '_insert_data', return_value=(3, 0, 0, [])) as mock_insert:
            inserted, updated, skipped, errors = importer.import_data(
                sample_json_data,
                source_file='test.json',
                dry_run=False
            )

            # Verify _insert_data was called
            mock_insert.assert_called_once()
            assert inserted == 3

    @patch('psycopg.connect')
    def test_import_data_existing_table(self, mock_connect, importer, sample_json_data):
        """Test import_data routes to UPDATE when table has data."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_conn.__enter__.return_value = mock_conn
        mock_connect.return_value = mock_conn

        # Mock count query returns > 0
        mock_cursor.fetchone.return_value = (100,)

        with patch.object(importer, '_update_data', return_value=(1, 2, 0, [])) as mock_update:
            inserted, updated, skipped, errors = importer.import_data(
                sample_json_data,
                source_file='test.json',
                dry_run=False
            )

            # Verify _update_data was called
            mock_update.assert_called_once()
            assert inserted == 1
            assert updated == 2

    @patch('psycopg.connect')
    def test_source_file_parameter(self, mock_connect, importer, sample_json_data):
        """Test that source_file parameter is used in INSERT/UPDATE."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_conn.__enter__.return_value = mock_conn
        mock_connect.return_value = mock_conn

        mock_cursor.rowcount = 1

        importer._insert_data(
            sample_json_data,
            source_file='custom_file.json',
            dry_run=False
        )

        # Verify source_file was passed in execute call
        calls = mock_cursor.execute.call_args_list
        assert len(calls) > 0

        # Check that 'custom_file.json' is in the parameters
        found_source_file = False
        for call in calls:
            if len(call[0]) > 1 and isinstance(call[0][1], tuple):
                if 'custom_file.json' in call[0][1]:
                    found_source_file = True
                    break

        assert found_source_file, "source_file parameter not found in database insert"

    @patch('psycopg.connect')
    def test_contexts_joining(self, mock_connect, importer):
        """Test that CONTEXTS array is properly joined with double newlines."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_conn.__enter__.return_value = mock_conn
        mock_connect.return_value = mock_conn

        mock_cursor.rowcount = 1

        data = {
            "12345": {
                "QUESTION": "Test?",
                "CONTEXTS": ["Line 1", "Line 2", "Line 3"],
                "LONG_ANSWER": "Answer",
                "final_decision": "yes"
            }
        }

        importer._insert_data(data, source_file='test.json', dry_run=False)

        # Find the execute call with the INSERT
        calls = mock_cursor.execute.call_args_list
        insert_params = None
        for call in calls:
            if len(call[0]) > 1 and isinstance(call[0][1], tuple):
                insert_params = call[0][1]
                break

        assert insert_params is not None
        # Context should be in the params tuple
        context_value = insert_params[4]  # context is 5th parameter (index 4)
        assert context_value == "Line 1\n\nLine 2\n\nLine 3"
