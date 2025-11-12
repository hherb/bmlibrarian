"""
Tests for MedRxiv Importer

These tests verify the basic functionality of the MedRxiv importer module.
"""

import pytest
from datetime import datetime
from unittest.mock import Mock, MagicMock, patch
from src.bmlibrarian.importers.medrxiv_importer import MedRxivImporter


class TestMedRxivImporter:
    """Test cases for MedRxivImporter class."""

    def test_split_date_range_into_weeks(self):
        """Test that date ranges are correctly split into weekly chunks."""
        with patch('src.bmlibrarian.importers.medrxiv_importer.get_db_manager'):
            importer = MedRxivImporter()

            # Test a simple 2-week range
            ranges = importer._split_date_range_into_weeks('2024-01-01', '2024-01-14')

            assert len(ranges) == 2
            assert ranges[0] == ('2024-01-01', '2024-01-07')
            assert ranges[1] == ('2024-01-08', '2024-01-14')

    def test_split_date_range_partial_week(self):
        """Test that partial weeks are handled correctly."""
        with patch('src.bmlibrarian.importers.medrxiv_importer.get_db_manager'):
            importer = MedRxivImporter()

            # Test a range that doesn't end on a week boundary
            ranges = importer._split_date_range_into_weeks('2024-01-01', '2024-01-10')

            assert len(ranges) == 2
            assert ranges[0] == ('2024-01-01', '2024-01-07')
            assert ranges[1] == ('2024-01-08', '2024-01-10')

    def test_split_date_range_single_day(self):
        """Test that a single-day range works correctly."""
        with patch('src.bmlibrarian.importers.medrxiv_importer.get_db_manager'):
            importer = MedRxivImporter()

            ranges = importer._split_date_range_into_weeks('2024-01-01', '2024-01-01')

            assert len(ranges) == 1
            assert ranges[0] == ('2024-01-01', '2024-01-01')

    @patch('src.bmlibrarian.importers.medrxiv_importer.requests.get')
    @patch('src.bmlibrarian.importers.medrxiv_importer.get_db_manager')
    def test_fetch_metadata_success(self, mock_db, mock_get):
        """Test successful metadata fetching from API."""
        # Mock the API response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'messages': [{'total': 2}],
            'collection': [
                {
                    'doi': '10.1101/2024.01.01.12345678',
                    'title': 'Test Paper 1',
                    'abstract': 'Test abstract 1',
                    'authors': [{'author': 'Smith J'}, {'author': 'Doe J'}],
                    'date': '2024-01-01',
                    'category': 'Infectious Diseases',
                    'version': '1'
                },
                {
                    'doi': '10.1101/2024.01.02.87654321',
                    'title': 'Test Paper 2',
                    'abstract': 'Test abstract 2',
                    'authors': [{'author': 'Brown A'}],
                    'date': '2024-01-02',
                    'category': 'Cardiology',
                    'version': '1'
                }
            ]
        }
        mock_get.return_value = mock_response

        importer = MedRxivImporter()

        papers = importer.fetch_metadata(
            start_date='2024-01-01',
            end_date='2024-01-02'
        )

        assert len(papers) == 2
        assert papers[0]['doi'] == '10.1101/2024.01.01.12345678'
        assert papers[1]['doi'] == '10.1101/2024.01.02.87654321'

    @patch('src.bmlibrarian.importers.medrxiv_importer.requests.get')
    @patch('src.bmlibrarian.importers.medrxiv_importer.get_db_manager')
    def test_fetch_metadata_empty_response(self, mock_db, mock_get):
        """Test handling of empty API response."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'messages': [{'total': 0}],
            'collection': []
        }
        mock_get.return_value = mock_response

        importer = MedRxivImporter()

        papers = importer.fetch_metadata(
            start_date='2024-01-01',
            end_date='2024-01-02'
        )

        assert len(papers) == 0

    @patch('src.bmlibrarian.importers.medrxiv_importer.get_db_manager')
    def test_get_source_id_from_cache(self, mock_db):
        """Test getting source ID from cache."""
        mock_db.return_value.get_cached_source_ids.return_value = {'medrxiv': 42}

        importer = MedRxivImporter()

        assert importer.source_id == 42

    @patch('src.bmlibrarian.importers.medrxiv_importer.get_db_manager')
    def test_initialization_with_custom_pdf_dir(self, mock_db):
        """Test initialization with custom PDF directory."""
        mock_db.return_value.get_cached_source_ids.return_value = {'medrxiv': 1}

        importer = MedRxivImporter(pdf_base_dir='/custom/pdf/dir')

        assert str(importer.pdf_base_dir) == '/custom/pdf/dir'

    @patch('src.bmlibrarian.importers.medrxiv_importer.get_db_manager')
    def test_initialization_with_env_var(self, mock_db):
        """Test initialization using environment variable."""
        mock_db.return_value.get_cached_source_ids.return_value = {'medrxiv': 1}

        with patch.dict('os.environ', {'PDF_BASE_DIR': '~/test_pdfs'}):
            importer = MedRxivImporter()

            # Should expand the tilde
            assert 'test_pdfs' in str(importer.pdf_base_dir)


def test_module_constants():
    """Test that module constants are correctly defined."""
    assert MedRxivImporter.MEDRXIV_API_BASE == "https://api.biorxiv.org/details/medrxiv"
    assert MedRxivImporter.MEDRXIV_LAUNCH_DATE == "2019-06-06"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
