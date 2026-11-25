"""
Tests for MedRxiv Importer

These tests verify the basic functionality of the MedRxiv importer module.
"""

import pytest
from datetime import datetime
from unittest.mock import Mock, MagicMock, patch
from src.bmlibrarian.importers.medrxiv_importer import (
    MedRxivImporter,
    parse_preprint_version,
    stored_preprint_version,
)


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
    def test_initialization_with_custom_pdf_dir(self, mock_db, tmp_path):
        """Test initialization with custom PDF directory."""
        mock_db.return_value.get_cached_source_ids.return_value = {'medrxiv': 1}
        custom_dir = tmp_path / 'custom' / 'pdf' / 'dir'  # the importer creates it

        importer = MedRxivImporter(pdf_base_dir=str(custom_dir))

        assert importer.pdf_base_dir == custom_dir
        assert custom_dir.is_dir()

    @patch('src.bmlibrarian.importers.medrxiv_importer.get_db_manager')
    def test_initialization_with_env_var(self, mock_db, tmp_path):
        """Test initialization using environment variable."""
        mock_db.return_value.get_cached_source_ids.return_value = {'medrxiv': 1}

        # HOME points at tmp_path so the importer's mkdir stays out of the real home
        with patch.dict('os.environ', {'PDF_BASE_DIR': '~/test_pdfs', 'HOME': str(tmp_path)}):
            importer = MedRxivImporter()

            # Should expand the tilde
            assert importer.pdf_base_dir == tmp_path / 'test_pdfs'


class TestPreprintVersions:
    """Newer preprint versions replace older ones (#446)."""

    @pytest.mark.parametrize("raw, expected", [
        ("2", 2), (3, 3), (" 1 ", 1), ("0", None), ("-1", None), ("v2", None), (None, None),
    ])
    def test_parse_preprint_version(self, raw, expected):
        assert parse_preprint_version(raw) == expected

    @pytest.mark.parametrize("url, expected", [
        ("https://www.medrxiv.org/content/10.1101/2024.01.01.24300001v2.full.pdf", 2),
        ("https://www.medrxiv.org/content/10.1101/2024.01.01.24300001v12.full.pdf", 12),
        ("https://www.medrxiv.org/content/10.1101/2024.01.01.24300001", 1),
        (None, 1),
    ])
    def test_stored_preprint_version(self, url, expected):
        assert stored_preprint_version(url) == expected

    @staticmethod
    def _run(existing, version):
        """Process one paper against a stored row ``existing``; return executed SQL."""
        cur = MagicMock()
        cur.fetchone.side_effect = [existing, (99,)]
        importer = object.__new__(MedRxivImporter)
        importer.db_manager = MagicMock()
        conn = importer.db_manager.get_connection.return_value.__enter__.return_value
        conn.cursor.return_value.__enter__.return_value = cur
        importer.source_id = 1
        importer.extraction_strategy = "pdf_only"  # no network extraction
        paper = {
            "doi": "10.1101/x", "title": "New title", "abstract": "New abstract",
            "authors": [], "date": "2024-02-01", "version": version,
        }
        count = importer._process_papers([paper], download_pdfs=False)
        sqls = [c.args[0] for c in cur.execute.call_args_list]
        return count, sqls, cur

    def test_newer_version_updates_existing_row(self):
        count, sqls, cur = self._run((5, "https://www.medrxiv.org/content/10.1101/xv1.full.pdf"), "2")
        assert count == 1
        update = [c for c in cur.execute.call_args_list if "UPDATE document" in c.args[0]]
        assert len(update) == 1
        params = update[0].args[1]
        assert params[0] == "New title"
        assert params[3] == "https://www.medrxiv.org/content/10.1101/xv2.full.pdf"
        assert params[-1] == 5
        assert not any("INSERT INTO document" in s for s in sqls)

    def test_same_or_older_version_is_skipped(self):
        for version in ("1", "2"):
            count, sqls, _ = self._run((5, "https://www.medrxiv.org/content/10.1101/xv2.full.pdf"), version)
            assert count == 0
            assert not any("UPDATE document" in s or "INSERT INTO document" in s for s in sqls)

    def test_new_paper_is_inserted(self):
        count, sqls, _ = self._run(None, "1")
        assert count == 1
        assert any("INSERT INTO document" in s for s in sqls)

    def test_invalid_version_is_skipped(self):
        count, sqls, _ = self._run(None, "abc")
        assert count == 0
        assert not any("INSERT INTO document" in s for s in sqls)

    def test_pdf_filename_carries_version_after_v1(self, tmp_path):
        importer = object.__new__(MedRxivImporter)
        importer.pdf_base_dir = tmp_path
        (tmp_path / "10.1101_x.pdf").write_bytes(b"%PDF-1.4")
        (tmp_path / "10.1101_xv2.pdf").write_bytes(b"%PDF-1.4")
        assert importer.download_pdf({"doi": "10.1101/x", "version": "1"}) == ("10.1101_x.pdf", False)
        assert importer.download_pdf({"doi": "10.1101/x", "version": "2"}) == ("10.1101_xv2.pdf", False)


def test_module_constants():
    """Test that module constants are correctly defined."""
    assert MedRxivImporter.MEDRXIV_API_BASE == "https://api.biorxiv.org/details/medrxiv"
    assert MedRxivImporter.MEDRXIV_LAUNCH_DATE == "2019-06-06"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
