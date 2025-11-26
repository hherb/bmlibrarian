"""
Unit tests for MeSH XML importer.

Tests XML parsing, data extraction, database import, and error handling.
"""

import pytest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch, call
from datetime import datetime
import tempfile

# Import after path setup
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from thesaurus_import_cli import MeshImporter, ImportStats


class TestImportStats:
    """Test cases for ImportStats dataclass."""

    def test_import_stats_creation(self):
        """Test creating an ImportStats instance."""
        stats = ImportStats(
            concepts_imported=100,
            terms_imported=500,
            hierarchies_imported=200,
            errors=5
        )

        assert stats.concepts_imported == 100
        assert stats.terms_imported == 500
        assert stats.hierarchies_imported == 200
        assert stats.errors == 5

    def test_duration_calculation(self):
        """Test duration calculation in seconds."""
        stats = ImportStats()
        stats.start_time = datetime(2025, 1, 1, 10, 0, 0)
        stats.end_time = datetime(2025, 1, 1, 10, 5, 30)

        duration = stats.duration_seconds()

        assert duration == 330  # 5 minutes 30 seconds

    def test_duration_calculation_none(self):
        """Test duration calculation with no timestamps."""
        stats = ImportStats()

        duration = stats.duration_seconds()

        assert duration == 0


class TestMeshImporter:
    """Test cases for MeshImporter class."""

    @pytest.fixture
    def mock_db_manager(self):
        """Create a mock DatabaseManager."""
        db = MagicMock()
        conn = MagicMock()
        cursor = MagicMock()

        # Setup connection context manager
        conn.__enter__.return_value = conn
        conn.__exit__.return_value = None

        # Setup cursor context manager
        cursor.__enter__.return_value = cursor
        cursor.__exit__.return_value = None

        conn.cursor.return_value = cursor
        db.get_connection.return_value = conn

        return db, conn, cursor

    @pytest.fixture
    def importer(self, mock_db_manager):
        """Create a MeshImporter with mocked database."""
        db, conn, cursor = mock_db_manager
        importer = MeshImporter(db_manager=db)
        importer._mock_cursor = cursor  # Store for test access
        return importer

    @pytest.fixture
    def sample_xml(self):
        """Create a sample MeSH XML for testing."""
        xml_content = """<?xml version="1.0" encoding="UTF-8"?>
<DescriptorRecordSet>
  <DescriptorRecord DescriptorClass="1">
    <DescriptorUI>D000001</DescriptorUI>
    <DescriptorName>
      <String>Aspirin</String>
    </DescriptorName>
    <ConceptList>
      <Concept PreferredConceptYN="Y">
        <ConceptUI>M0001</ConceptUI>
        <ConceptName>
          <String>Aspirin</String>
        </ConceptName>
        <ScopeNote>A prototypical analgesic drug.</ScopeNote>
        <TermList>
          <Term LexicalTag="NON">
            <TermUI>T0001</TermUI>
            <String>Aspirin</String>
          </Term>
          <Term LexicalTag="ABB">
            <TermUI>T0002</TermUI>
            <String>ASA</String>
          </Term>
          <Term LexicalTag="SYN">
            <TermUI>T0003</TermUI>
            <String>Acetylsalicylic Acid</String>
          </Term>
        </TermList>
      </Concept>
    </ConceptList>
    <TreeNumberList>
      <TreeNumber>D02.455.426.559</TreeNumber>
      <TreeNumber>D03.383.663.283</TreeNumber>
    </TreeNumberList>
  </DescriptorRecord>
</DescriptorRecordSet>
"""
        # Create temporary file
        temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.xml', delete=False)
        temp_file.write(xml_content)
        temp_file.close()

        return Path(temp_file.name)

    def test_lexical_tag_mapping(self):
        """Test MeSH lexical tag to term type mapping."""
        assert MeshImporter.LEXICAL_TAG_MAPPING['NON'] == 'preferred'
        assert MeshImporter.LEXICAL_TAG_MAPPING['ABB'] == 'abbreviation'
        assert MeshImporter.LEXICAL_TAG_MAPPING['SYN'] == 'synonym'
        assert MeshImporter.LEXICAL_TAG_MAPPING['TRD'] == 'trade_name'
        assert MeshImporter.LEXICAL_TAG_MAPPING['OBS'] == 'obsolete'

    def test_importer_initialization(self, mock_db_manager):
        """Test MeshImporter initialization."""
        db, _, _ = mock_db_manager
        importer = MeshImporter(db_manager=db)

        assert importer.db == db
        assert isinstance(importer.stats, ImportStats)
        assert importer.stats.concepts_imported == 0

    def test_importer_initialization_default_db(self):
        """Test MeshImporter initialization with default DatabaseManager."""
        with patch('thesaurus_import_cli.DatabaseManager') as mock_db_class:
            mock_db_instance = MagicMock()
            mock_db_class.return_value = mock_db_instance

            importer = MeshImporter()

            assert importer.db == mock_db_instance
            mock_db_class.assert_called_once()

    def test_import_mesh_xml_file_not_found(self, importer):
        """Test import with non-existent file."""
        non_existent = Path('/tmp/nonexistent.xml')

        with pytest.raises(FileNotFoundError):
            importer.import_mesh_xml(non_existent)

    def test_import_mesh_xml_dry_run(self, importer, sample_xml):
        """Test dry run import (validation only)."""
        stats = importer.import_mesh_xml(
            xml_path=sample_xml,
            dry_run=True
        )

        # Should validate but not import
        assert stats.concepts_imported == 1  # Validated
        assert stats.terms_imported == 3  # 3 terms found
        assert stats.hierarchies_imported == 2  # 2 tree numbers

        # Database should not be called
        assert importer._mock_cursor.execute.call_count == 0

        # Cleanup
        sample_xml.unlink()

    def test_import_mesh_xml_successful(self, importer, sample_xml):
        """Test successful MeSH import."""
        cursor = importer._mock_cursor

        # Mock database responses
        cursor.fetchone.return_value = [123]  # concept_id

        stats = importer.import_mesh_xml(
            xml_path=sample_xml,
            dry_run=False,
            batch_size=10
        )

        # Verify import counts
        assert stats.concepts_imported == 1
        assert stats.terms_imported == 3
        assert stats.hierarchies_imported == 2
        assert stats.errors == 0

        # Verify database calls were made
        assert cursor.execute.call_count > 0

        # Cleanup
        sample_xml.unlink()

    def test_import_descriptor(self, importer):
        """Test importing a single descriptor."""
        cursor = importer._mock_cursor
        cursor.fetchone.return_value = [456]  # concept_id

        # Create descriptor XML element
        descriptor_xml = """
        <DescriptorRecord DescriptorClass="1">
            <DescriptorUI>D999999</DescriptorUI>
            <DescriptorName>
                <String>Test Descriptor</String>
            </DescriptorName>
            <ConceptList>
                <Concept>
                    <ScopeNote>Test definition</ScopeNote>
                    <TermList>
                        <Term LexicalTag="NON">
                            <TermUI>T999</TermUI>
                            <String>Test Term</String>
                        </Term>
                    </TermList>
                </Concept>
            </ConceptList>
            <TreeNumberList>
                <TreeNumber>Z99.999</TreeNumber>
            </TreeNumberList>
        </DescriptorRecord>
        """
        descriptor = ET.fromstring(descriptor_xml)

        # Import descriptor
        importer._import_descriptor(descriptor, '2025', cursor)

        # Verify concept was inserted
        assert importer.stats.concepts_imported == 1

        # Verify concept insert was called
        concept_insert_calls = [
            c for c in cursor.execute.call_args_list
            if 'INSERT INTO thesaurus.concepts' in str(c)
        ]
        assert len(concept_insert_calls) == 1

    def test_import_term(self, importer):
        """Test importing a single term."""
        cursor = importer._mock_cursor

        term_xml = """
        <Term LexicalTag="ABB">
            <TermUI>T12345</TermUI>
            <String>MI</String>
        </Term>
        """
        term = ET.fromstring(term_xml)

        importer._import_term(term, concept_id=100, cursor=cursor)

        # Verify term was imported
        assert importer.stats.terms_imported == 1

        # Verify correct SQL was executed
        cursor.execute.assert_called_once()
        call_args = cursor.execute.call_args[0]
        assert 'INSERT INTO thesaurus.terms' in call_args[0]
        assert call_args[1] == (100, 'MI', 'abbreviation', 'ABB', 'T12345')

    def test_import_tree_number(self, importer):
        """Test importing a tree number (hierarchy)."""
        cursor = importer._mock_cursor

        importer._import_tree_number('C14.280.647.500', concept_id=200, cursor=cursor)

        # Verify hierarchy was imported
        assert importer.stats.hierarchies_imported == 1

        # Verify correct SQL was executed
        cursor.execute.assert_called_once()
        call_args = cursor.execute.call_args[0]
        assert 'INSERT INTO thesaurus.concept_hierarchies' in call_args[0]
        # Tree level should be 4 (3 dots + 1)
        assert call_args[1] == (200, 'C14.280.647.500', 4)

    def test_tree_level_calculation(self, importer):
        """Test tree level calculation from tree number."""
        cursor = importer._mock_cursor

        test_cases = [
            ('A01', 1),  # Top level
            ('C14.280', 2),  # Level 2
            ('C14.280.647', 3),  # Level 3
            ('C14.280.647.500', 4),  # Level 4
        ]

        for tree_number, expected_level in test_cases:
            cursor.reset_mock()
            importer._import_tree_number(tree_number, 1, cursor)

            call_args = cursor.execute.call_args[0]
            actual_level = call_args[1][2]  # Third parameter
            assert actual_level == expected_level, f"Failed for {tree_number}"

    def test_record_import_history(self, importer, sample_xml):
        """Test recording import history."""
        cursor = importer._mock_cursor

        importer.stats.concepts_imported = 100
        importer.stats.terms_imported = 500
        importer.stats.hierarchies_imported = 200
        importer.stats.errors = 5
        importer.stats.start_time = datetime.now()
        importer.stats.end_time = datetime.now()

        importer._record_import_history('2025', sample_xml)

        # Verify import history was recorded
        history_insert_calls = [
            c for c in cursor.execute.call_args_list
            if 'INSERT INTO thesaurus.import_history' in str(c)
        ]
        assert len(history_insert_calls) == 1

        # Cleanup
        sample_xml.unlink()

    def test_error_handling_malformed_xml(self, importer):
        """Test handling of malformed XML."""
        # Create malformed XML file
        temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.xml', delete=False)
        temp_file.write("<malformed>")
        temp_file.close()
        malformed_xml = Path(temp_file.name)

        with pytest.raises(ValueError, match="Invalid MeSH XML format"):
            importer.import_mesh_xml(malformed_xml)

        # Cleanup
        malformed_xml.unlink()

    def test_batch_import(self, importer, sample_xml):
        """Test batch import with custom batch size."""
        cursor = importer._mock_cursor
        cursor.fetchone.return_value = [999]

        # Import with batch size of 1
        stats = importer.import_mesh_xml(
            xml_path=sample_xml,
            batch_size=1
        )

        # Should still import successfully
        assert stats.concepts_imported == 1

        # Cleanup
        sample_xml.unlink()


class TestImportCLI:
    """Test cases for CLI interface."""

    def test_cli_help(self):
        """Test CLI help output."""
        with patch('sys.argv', ['thesaurus_import_cli.py', '--help']):
            with pytest.raises(SystemExit) as exc_info:
                import thesaurus_import_cli
                thesaurus_import_cli.main()

            assert exc_info.value.code == 0

    @patch('thesaurus_import_cli.MeshImporter')
    def test_cli_successful_import(self, mock_importer_class):
        """Test successful CLI import."""
        # Create temporary XML file
        temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.xml', delete=False)
        temp_file.write('<?xml version="1.0"?><DescriptorRecordSet></DescriptorRecordSet>')
        temp_file.close()
        temp_path = Path(temp_file.name)

        # Mock importer
        mock_instance = MagicMock()
        mock_stats = ImportStats(concepts_imported=10, errors=0)
        mock_instance.import_mesh_xml.return_value = mock_stats
        mock_importer_class.return_value = mock_instance

        # Run CLI
        with patch('sys.argv', ['thesaurus_import_cli.py', str(temp_path)]):
            import thesaurus_import_cli
            exit_code = thesaurus_import_cli.main()

        assert exit_code == 0

        # Cleanup
        temp_path.unlink()

    @patch('thesaurus_import_cli.MeshImporter')
    def test_cli_import_with_errors(self, mock_importer_class):
        """Test CLI import with errors."""
        # Create temporary XML file
        temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.xml', delete=False)
        temp_file.write('<?xml version="1.0"?><DescriptorRecordSet></DescriptorRecordSet>')
        temp_file.close()
        temp_path = Path(temp_file.name)

        # Mock importer with errors
        mock_instance = MagicMock()
        mock_stats = ImportStats(concepts_imported=10, errors=5)
        mock_instance.import_mesh_xml.return_value = mock_stats
        mock_importer_class.return_value = mock_instance

        # Run CLI
        with patch('sys.argv', ['thesaurus_import_cli.py', str(temp_path)]):
            import thesaurus_import_cli
            exit_code = thesaurus_import_cli.main()

        assert exit_code == 1  # Should exit with error

        # Cleanup
        temp_path.unlink()


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
