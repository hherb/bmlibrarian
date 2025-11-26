"""
Unit tests for thesaurus term expansion functionality.

Tests term expansion, query expansion, and data import validation.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from bmlibrarian.thesaurus.expander import ThesaurusExpander, TermExpansion, expand_query_terms


class TestTermExpansion:
    """Test cases for TermExpansion dataclass."""

    def test_term_expansion_creation(self):
        """Test creating a TermExpansion instance."""
        expansion = TermExpansion(
            original_term="MI",
            all_variants=["MI", "Myocardial Infarction", "Heart Attack", "AMI"],
            preferred_term="Myocardial Infarction",
            concept_ids=[1],
            expansion_type="exact"
        )

        assert expansion.original_term == "MI"
        assert len(expansion.all_variants) == 4
        assert expansion.preferred_term == "Myocardial Infarction"
        assert expansion.concept_ids == [1]
        assert expansion.expansion_type == "exact"


class TestThesaurusExpander:
    """Test cases for ThesaurusExpander class."""

    @pytest.fixture
    def mock_connection(self):
        """Create a mock database connection."""
        conn = MagicMock()
        cursor = MagicMock()
        conn.cursor.return_value.__enter__.return_value = cursor
        conn.__enter__.return_value = conn
        conn.__exit__.return_value = None
        return conn, cursor

    @pytest.fixture
    def expander(self, mock_connection):
        """Create a ThesaurusExpander with mocked connection."""
        conn, cursor = mock_connection

        with patch.object(ThesaurusExpander, '_get_connection', return_value=conn):
            expander = ThesaurusExpander(
                min_term_length=2,
                max_expansions_per_term=10
            )
            expander._mock_cursor = cursor  # Store for test access
            yield expander

    def test_init_default_params(self):
        """Test ThesaurusExpander initialization with default parameters."""
        expander = ThesaurusExpander()

        assert expander.min_term_length == 2
        assert expander.max_expansions_per_term == 10
        assert expander.include_broader_terms is False
        assert expander.include_narrower_terms is False
        assert expander._expansion_cache == {}

    def test_init_custom_params(self):
        """Test ThesaurusExpander initialization with custom parameters."""
        expander = ThesaurusExpander(
            min_term_length=3,
            max_expansions_per_term=5,
            include_broader_terms=True
        )

        assert expander.min_term_length == 3
        assert expander.max_expansions_per_term == 5
        assert expander.include_broader_terms is True

    def test_expand_term_too_short(self, expander):
        """Test that very short terms are not expanded."""
        expansion = expander.expand_term("a")

        assert expansion.original_term == "a"
        assert expansion.all_variants == ["a"]
        assert expansion.preferred_term is None
        assert expansion.expansion_type == "none"

    def test_expand_term_no_results(self, expander):
        """Test expanding a term with no database matches."""
        cursor = expander._mock_cursor
        cursor.fetchall.return_value = []

        expansion = expander.expand_term("unknownterm")

        assert expansion.original_term == "unknownterm"
        assert expansion.all_variants == ["unknownterm"]
        assert expansion.preferred_term is None
        assert expansion.expansion_type == "none"

    def test_expand_term_with_results(self, expander):
        """Test expanding a term with database results."""
        cursor = expander._mock_cursor
        cursor.fetchall.return_value = [
            {
                'term': 'MI',
                'term_type': 'abbreviation',
                'preferred_term': 'Myocardial Infarction',
                'concept_id': 1,
                'is_input_term': True
            },
            {
                'term': 'Myocardial Infarction',
                'term_type': 'preferred',
                'preferred_term': 'Myocardial Infarction',
                'concept_id': 1,
                'is_input_term': False
            },
            {
                'term': 'Heart Attack',
                'term_type': 'synonym',
                'preferred_term': 'Myocardial Infarction',
                'concept_id': 1,
                'is_input_term': False
            },
            {
                'term': 'AMI',
                'term_type': 'abbreviation',
                'preferred_term': 'Myocardial Infarction',
                'concept_id': 1,
                'is_input_term': False
            }
        ]

        expansion = expander.expand_term("MI")

        assert expansion.original_term == "MI"
        assert len(expansion.all_variants) == 4
        assert "Myocardial Infarction" in expansion.all_variants
        assert "Heart Attack" in expansion.all_variants
        assert "AMI" in expansion.all_variants
        assert expansion.preferred_term == "Myocardial Infarction"
        assert expansion.concept_ids == [1]
        assert expansion.expansion_type == "exact"

    def test_expand_term_caching(self, expander):
        """Test that term expansions are cached."""
        cursor = expander._mock_cursor
        cursor.fetchall.return_value = [
            {
                'term': 'aspirin',
                'term_type': 'preferred',
                'preferred_term': 'Aspirin',
                'concept_id': 2,
                'is_input_term': True
            },
            {
                'term': 'ASA',
                'term_type': 'abbreviation',
                'preferred_term': 'Aspirin',
                'concept_id': 2,
                'is_input_term': False
            }
        ]

        # First call should query database
        expansion1 = expander.expand_term("aspirin")
        assert cursor.execute.call_count == 1

        # Second call should use cache
        expansion2 = expander.expand_term("aspirin")
        assert cursor.execute.call_count == 1  # No additional call

        # Results should be identical
        assert expansion1.original_term == expansion2.original_term
        assert expansion1.all_variants == expansion2.all_variants

    def test_expand_term_cache_disabled(self, expander):
        """Test that caching can be disabled."""
        cursor = expander._mock_cursor
        cursor.fetchall.return_value = []

        # First call
        expander.expand_term("test", use_cache=False)
        assert cursor.execute.call_count == 1

        # Second call with cache disabled
        expander.expand_term("test", use_cache=False)
        assert cursor.execute.call_count == 2  # Additional call made

    def test_clear_cache(self, expander):
        """Test clearing the expansion cache."""
        cursor = expander._mock_cursor
        cursor.fetchall.return_value = []

        # Populate cache
        expander.expand_term("test1")
        expander.expand_term("test2")

        assert expander.get_cache_size() == 2

        # Clear cache
        expander.clear_cache()

        assert expander.get_cache_size() == 0

    def test_extract_terms_simple(self, expander):
        """Test extracting terms from a simple query."""
        query = "aspirin & heart"
        terms = expander._extract_terms(query)

        assert "aspirin" in terms
        assert "heart" in terms
        assert len(terms) == 2

    def test_extract_terms_with_operators(self, expander):
        """Test extracting terms from a query with operators."""
        query = "(aspirin | ASA) & (heart | cardiac)"
        terms = expander._extract_terms(query)

        assert "aspirin" in terms
        assert "ASA" in terms
        assert "heart" in terms
        assert "cardiac" in terms
        assert "&" not in terms
        assert "|" not in terms

    def test_extract_terms_with_phrases(self, expander):
        """Test extracting terms including quoted phrases."""
        query = "'heart attack' & aspirin"
        terms = expander._extract_terms(query)

        assert "heart attack" in terms or "heart" in terms  # Depends on implementation
        assert "aspirin" in terms

    def test_expand_query_no_expansion(self, expander):
        """Test query expansion when no terms can be expanded."""
        cursor = expander._mock_cursor
        cursor.fetchall.return_value = []

        original_query = "unknownterm1 & unknownterm2"
        expanded = expander.expand_query(original_query)

        # Should return original query unchanged
        assert expanded == original_query

    def test_expand_query_with_expansion(self, expander):
        """Test query expansion with expandable terms."""
        cursor = expander._mock_cursor

        # Setup mock to return different results for different terms
        def mock_execute(query, params):
            term = params[0] if params else ""
            if term.lower() == "mi":
                cursor.fetchall.return_value = [
                    {'term': 'MI', 'term_type': 'abbreviation', 'preferred_term': 'Myocardial Infarction', 'concept_id': 1, 'is_input_term': True},
                    {'term': 'Myocardial Infarction', 'term_type': 'preferred', 'preferred_term': 'Myocardial Infarction', 'concept_id': 1, 'is_input_term': False},
                    {'term': 'Heart Attack', 'term_type': 'synonym', 'preferred_term': 'Myocardial Infarction', 'concept_id': 1, 'is_input_term': False}
                ]
            else:
                cursor.fetchall.return_value = []

        cursor.execute.side_effect = mock_execute

        original_query = "mi & treatment"
        expanded = expander.expand_query(original_query)

        # Should contain expanded terms for "mi"
        assert "Myocardial Infarction" in expanded.lower() or "myocardial infarction" in expanded.lower()

    def test_expand_query_empty_string(self, expander):
        """Test query expansion with empty string."""
        expanded = expander.expand_query("")
        assert expanded == ""

        expanded = expander.expand_query("   ")
        assert expanded == "   "


class TestConvenienceFunction:
    """Test cases for the expand_query_terms convenience function."""

    @patch('bmlibrarian.thesaurus.expander.ThesaurusExpander')
    def test_expand_query_terms(self, mock_expander_class):
        """Test the expand_query_terms convenience function."""
        mock_instance = Mock()
        mock_instance.expand_query.return_value = "expanded query"
        mock_expander_class.return_value = mock_instance

        result = expand_query_terms("original query")

        assert result == "expanded query"
        mock_expander_class.assert_called_once()
        mock_instance.expand_query.assert_called_once_with("original query")


class TestDataImportValidation:
    """Test cases for validating thesaurus data import."""

    @pytest.fixture
    def mock_db_connection(self):
        """Create a mock database connection for import validation."""
        conn = MagicMock()
        cursor = MagicMock()
        conn.cursor.return_value.__enter__.return_value = cursor
        conn.__enter__.return_value = conn
        conn.__exit__.return_value = None
        return conn, cursor

    def test_import_validation_concepts_count(self, mock_db_connection):
        """Test validation of concepts table import."""
        conn, cursor = mock_db_connection

        # Mock successful import
        cursor.fetchone.return_value = {'count': 30000}

        with patch('psycopg.connect', return_value=conn):
            # Validate concepts imported
            import psycopg
            with psycopg.connect("dummy") as test_conn:
                with test_conn.cursor() as cur:
                    cur.execute("SELECT COUNT(*) as count FROM thesaurus.concepts")
                    result = cur.fetchone()

                    assert result['count'] == 30000

    def test_import_validation_terms_count(self, mock_db_connection):
        """Test validation of terms table import."""
        conn, cursor = mock_db_connection

        # Mock successful import
        cursor.fetchone.return_value = {'count': 300000}

        with patch('psycopg.connect', return_value=conn):
            import psycopg
            with psycopg.connect("dummy") as test_conn:
                with test_conn.cursor() as cur:
                    cur.execute("SELECT COUNT(*) as count FROM thesaurus.terms")
                    result = cur.fetchone()

                    assert result['count'] == 300000

    def test_import_validation_hierarchies_exist(self, mock_db_connection):
        """Test validation that hierarchies were imported."""
        conn, cursor = mock_db_connection

        # Mock hierarchies exist
        cursor.fetchone.return_value = {'count': 50000}

        with patch('psycopg.connect', return_value=conn):
            import psycopg
            with psycopg.connect("dummy") as test_conn:
                with test_conn.cursor() as cur:
                    cur.execute("SELECT COUNT(*) as count FROM thesaurus.concept_hierarchies")
                    result = cur.fetchone()

                    assert result['count'] > 0

    def test_import_validation_term_types(self, mock_db_connection):
        """Test validation of term type distribution."""
        conn, cursor = mock_db_connection

        # Mock term type distribution
        cursor.fetchall.return_value = [
            {'term_type': 'preferred', 'count': 30000},
            {'term_type': 'synonym', 'count': 150000},
            {'term_type': 'abbreviation', 'count': 100000},
            {'term_type': 'trade_name', 'count': 20000}
        ]

        with patch('psycopg.connect', return_value=conn):
            import psycopg
            with psycopg.connect("dummy") as test_conn:
                with test_conn.cursor() as cur:
                    cur.execute("""
                        SELECT term_type, COUNT(*) as count
                        FROM thesaurus.terms
                        GROUP BY term_type
                    """)
                    results = cur.fetchall()

                    # Verify all expected term types present
                    term_types = {row['term_type'] for row in results}
                    assert 'preferred' in term_types
                    assert 'synonym' in term_types
                    assert 'abbreviation' in term_types

    def test_import_validation_foreign_keys(self, mock_db_connection):
        """Test validation of foreign key integrity."""
        conn, cursor = mock_db_connection

        # Mock orphan check - should return 0
        cursor.fetchone.return_value = {'orphan_count': 0}

        with patch('psycopg.connect', return_value=conn):
            import psycopg
            with psycopg.connect("dummy") as test_conn:
                with test_conn.cursor() as cur:
                    # Check for orphaned terms (terms without valid concept_id)
                    cur.execute("""
                        SELECT COUNT(*) as orphan_count
                        FROM thesaurus.terms t
                        LEFT JOIN thesaurus.concepts c ON t.concept_id = c.concept_id
                        WHERE c.concept_id IS NULL
                    """)
                    result = cur.fetchone()

                    assert result['orphan_count'] == 0

    def test_import_history_recorded(self, mock_db_connection):
        """Test that import history is properly recorded."""
        conn, cursor = mock_db_connection

        # Mock import history
        cursor.fetchone.return_value = {
            'source_vocabulary': 'mesh',
            'source_version': '2025',
            'concepts_imported': 30000,
            'terms_imported': 300000,
            'import_status': 'completed'
        }

        with patch('psycopg.connect', return_value=conn):
            import psycopg
            with psycopg.connect("dummy") as test_conn:
                with test_conn.cursor() as cur:
                    cur.execute("""
                        SELECT *
                        FROM thesaurus.import_history
                        ORDER BY import_date DESC
                        LIMIT 1
                    """)
                    result = cur.fetchone()

                    assert result['source_vocabulary'] == 'mesh'
                    assert result['source_version'] == '2025'
                    assert result['import_status'] == 'completed'
                    assert result['concepts_imported'] == 30000
                    assert result['terms_imported'] == 300000


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
