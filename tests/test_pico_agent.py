"""
Tests for PICOAgent

Tests PICO component extraction from biomedical research papers.
"""

import pytest
import json
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

from bmlibrarian.agents import PICOAgent, PICOExtraction


# Sample document for testing
SAMPLE_DOCUMENT = {
    'id': '12345678',
    'title': 'Effect of Metformin on Glycemic Control in Type 2 Diabetes: A Randomized Controlled Trial',
    'abstract': """
    Background: Type 2 diabetes mellitus is a major public health concern. Metformin is widely used as first-line therapy.

    Methods: We conducted a randomized, double-blind, placebo-controlled trial involving 150 adults aged 40-65 years
    with type 2 diabetes and HbA1c levels >7.0%. Participants were recruited from 5 primary care clinics in Boston, MA.
    Patients were randomly assigned to receive either metformin 1000mg twice daily (n=75) or matching placebo tablets
    twice daily (n=75) for 12 weeks. The primary outcome was change in HbA1c from baseline to week 12. Secondary outcomes
    included fasting plasma glucose, body weight, and adverse events.

    Results: At 12 weeks, the metformin group showed a mean reduction in HbA1c of -1.2% (95% CI: -1.5 to -0.9) compared
    to -0.3% (95% CI: -0.5 to -0.1) in the placebo group (p<0.001). Fasting glucose decreased by 28 mg/dL in the metformin
    group vs 8 mg/dL in placebo (p<0.01). Body weight decreased by 2.1 kg in metformin vs 0.4 kg in placebo (p<0.05).
    Gastrointestinal side effects were more common in the metformin group (23% vs 8%, p<0.05).

    Conclusions: Metformin 1000mg twice daily for 12 weeks significantly reduced HbA1c and fasting glucose in adults
    with type 2 diabetes compared to placebo, with acceptable tolerability.
    """,
    'pmid': '12345678',
    'doi': '10.1000/example.12345',
    'publication_date': '2023-06-15'
}

# Expected PICO extraction
EXPECTED_PICO = {
    "population": "Adults aged 40-65 years with type 2 diabetes and HbA1c > 7%, recruited from primary care clinics",
    "intervention": "Metformin 1000mg twice daily for 12 weeks",
    "comparison": "Matching placebo tablets twice daily for 12 weeks",
    "outcome": "Change in HbA1c from baseline to week 12 (primary); fasting plasma glucose, body weight, adverse events (secondary)",
    "study_type": "RCT",
    "sample_size": "N=150",
    "population_confidence": 0.95,
    "intervention_confidence": 0.98,
    "comparison_confidence": 0.95,
    "outcome_confidence": 0.92,
    "overall_confidence": 0.95
}


class TestPICOAgent:
    """Test suite for PICOAgent."""

    @pytest.fixture
    def mock_ollama_client(self):
        """Create a mock Ollama client."""
        with patch('bmlibrarian.agents.base.ollama.Client') as mock_client:
            yield mock_client

    @pytest.fixture
    def pico_agent(self, mock_ollama_client):
        """Create a PICOAgent instance with mocked Ollama."""
        agent = PICOAgent(
            model="gpt-oss:20b",
            show_model_info=False
        )
        # Mock the client
        agent.client = Mock()
        return agent

    def test_agent_initialization(self):
        """Test PICOAgent initialization."""
        with patch('bmlibrarian.agents.base.ollama.Client'):
            agent = PICOAgent(
                model="gpt-oss:20b",
                temperature=0.1,
                top_p=0.9,
                max_tokens=2000,
                show_model_info=False
            )

            assert agent.model == "gpt-oss:20b"
            assert agent.temperature == 0.1
            assert agent.top_p == 0.9
            assert agent.max_tokens == 2000
            assert agent.get_agent_type() == "pico_agent"

    def test_extract_pico_success(self, pico_agent):
        """Test successful PICO extraction."""
        # Mock successful LLM response
        pico_agent.client.generate = Mock(return_value={
            'response': json.dumps(EXPECTED_PICO)
        })

        # Mock connection test
        pico_agent.test_connection = Mock(return_value=True)

        # Extract PICO
        extraction = pico_agent.extract_pico_from_document(
            document=SAMPLE_DOCUMENT,
            min_confidence=0.5
        )

        # Verify extraction
        assert extraction is not None
        assert isinstance(extraction, PICOExtraction)
        assert extraction.population == EXPECTED_PICO['population']
        assert extraction.intervention == EXPECTED_PICO['intervention']
        assert extraction.comparison == EXPECTED_PICO['comparison']
        assert extraction.outcome == EXPECTED_PICO['outcome']
        assert extraction.study_type == EXPECTED_PICO['study_type']
        assert extraction.sample_size == EXPECTED_PICO['sample_size']
        assert extraction.extraction_confidence == EXPECTED_PICO['overall_confidence']
        assert extraction.document_id == '12345678'
        assert extraction.document_title == SAMPLE_DOCUMENT['title']
        assert extraction.pmid == '12345678'
        assert extraction.doi == '10.1000/example.12345'

    def test_extract_pico_low_confidence(self, pico_agent):
        """Test PICO extraction with low confidence."""
        # Mock LLM response with low confidence
        low_confidence_pico = EXPECTED_PICO.copy()
        low_confidence_pico['overall_confidence'] = 0.3

        pico_agent.client.generate = Mock(return_value={
            'response': json.dumps(low_confidence_pico)
        })
        pico_agent.test_connection = Mock(return_value=True)

        # Should return None due to low confidence
        extraction = pico_agent.extract_pico_from_document(
            document=SAMPLE_DOCUMENT,
            min_confidence=0.5
        )

        assert extraction is None
        assert pico_agent._extraction_stats['low_confidence_extractions'] == 1

    def test_extract_pico_no_abstract(self, pico_agent):
        """Test PICO extraction with missing abstract."""
        # Document without abstract
        empty_doc = {'id': '123', 'title': 'Test', 'abstract': ''}

        pico_agent.test_connection = Mock(return_value=True)

        extraction = pico_agent.extract_pico_from_document(
            document=empty_doc,
            min_confidence=0.5
        )

        assert extraction is None

    def test_extract_pico_missing_fields(self, pico_agent):
        """Test PICO extraction with missing required fields."""
        # Mock incomplete response
        incomplete_pico = {
            "population": "Some population",
            "intervention": "Some intervention"
            # Missing comparison and outcome
        }

        pico_agent.client.generate = Mock(return_value={
            'response': json.dumps(incomplete_pico)
        })
        pico_agent.test_connection = Mock(return_value=True)

        extraction = pico_agent.extract_pico_from_document(
            document=SAMPLE_DOCUMENT,
            min_confidence=0.5
        )

        assert extraction is None
        assert pico_agent._extraction_stats['failed_extractions'] == 1

    def test_extract_pico_json_parse_error(self, pico_agent):
        """Test PICO extraction with invalid JSON response."""
        # Mock invalid JSON response
        pico_agent.client.generate = Mock(return_value={
            'response': "This is not valid JSON {broken"
        })
        pico_agent.test_connection = Mock(return_value=True)

        extraction = pico_agent.extract_pico_from_document(
            document=SAMPLE_DOCUMENT,
            min_confidence=0.5
        )

        assert extraction is None
        assert pico_agent._extraction_stats['parse_failures'] == 1

    def test_extract_pico_connection_failure(self, pico_agent):
        """Test PICO extraction with Ollama connection failure."""
        # Mock connection failure
        pico_agent.test_connection = Mock(return_value=False)

        extraction = pico_agent.extract_pico_from_document(
            document=SAMPLE_DOCUMENT,
            min_confidence=0.5
        )

        assert extraction is None

    def test_extract_pico_batch(self, pico_agent):
        """Test batch PICO extraction."""
        # Create multiple documents
        documents = [SAMPLE_DOCUMENT.copy() for _ in range(3)]
        for i, doc in enumerate(documents):
            doc['id'] = str(i)

        # Mock successful extractions
        pico_agent.extract_pico_from_document = Mock(
            side_effect=[
                PICOExtraction(
                    population="Pop", intervention="Int", comparison="Cmp",
                    outcome="Out", document_id=str(i), document_title=f"Title {i}",
                    extraction_confidence=0.9
                )
                for i in range(3)
            ]
        )

        extractions = pico_agent.extract_pico_batch(
            documents=documents,
            min_confidence=0.5
        )

        assert len(extractions) == 3
        assert all(isinstance(e, PICOExtraction) for e in extractions)

    def test_extract_pico_batch_with_progress(self, pico_agent):
        """Test batch extraction with progress callback."""
        documents = [SAMPLE_DOCUMENT.copy()]
        progress_callback = Mock()

        pico_agent.extract_pico_from_document = Mock(return_value=PICOExtraction(
            population="Pop", intervention="Int", comparison="Cmp",
            outcome="Out", document_id="1", document_title="Title",
            extraction_confidence=0.9
        ))

        extractions = pico_agent.extract_pico_batch(
            documents=documents,
            progress_callback=progress_callback
        )

        # Verify progress callback was called
        progress_callback.assert_called_once_with(1, 1, SAMPLE_DOCUMENT['title'])

    def test_get_extraction_stats(self, pico_agent):
        """Test extraction statistics."""
        # Manually set some statistics
        pico_agent._extraction_stats = {
            'total_extractions': 10,
            'successful_extractions': 8,
            'failed_extractions': 1,
            'low_confidence_extractions': 1,
            'parse_failures': 0
        }

        stats = pico_agent.get_extraction_stats()

        assert stats['total_extractions'] == 10
        assert stats['successful_extractions'] == 8
        assert stats['success_rate'] == 0.8

    def test_get_extraction_stats_empty(self, pico_agent):
        """Test extraction statistics with no extractions."""
        stats = pico_agent.get_extraction_stats()

        assert stats['total_extractions'] == 0
        assert stats['success_rate'] == 0.0

    def test_format_pico_summary(self, pico_agent):
        """Test formatting PICO extraction as summary."""
        extraction = PICOExtraction(
            population="Adults with diabetes",
            intervention="Metformin 1000mg",
            comparison="Placebo",
            outcome="HbA1c reduction",
            document_id="123",
            document_title="Test Study",
            extraction_confidence=0.95,
            study_type="RCT",
            sample_size="N=150",
            pmid="12345",
            doi="10.1000/test",
            population_confidence=0.9,
            intervention_confidence=0.95,
            comparison_confidence=0.9,
            outcome_confidence=0.95
        )

        summary = pico_agent.format_pico_summary(extraction)

        # Verify key components are in summary
        assert "PICO EXTRACTION" in summary
        assert "Test Study" in summary
        assert "Adults with diabetes" in summary
        assert "Metformin 1000mg" in summary
        assert "Placebo" in summary
        assert "HbA1c reduction" in summary
        assert "RCT" in summary
        assert "N=150" in summary
        assert "PMID: 12345" in summary
        assert "DOI: 10.1000/test" in summary

    def test_export_to_json(self, pico_agent, tmp_path):
        """Test exporting PICO extractions to JSON."""
        extractions = [
            PICOExtraction(
                population="Pop1", intervention="Int1", comparison="Cmp1",
                outcome="Out1", document_id="1", document_title="Title1",
                extraction_confidence=0.9
            ),
            PICOExtraction(
                population="Pop2", intervention="Int2", comparison="Cmp2",
                outcome="Out2", document_id="2", document_title="Title2",
                extraction_confidence=0.85
            )
        ]

        output_file = tmp_path / "pico_extractions.json"
        pico_agent.export_to_json(extractions, str(output_file))

        # Verify file was created
        assert output_file.exists()

        # Verify content
        with open(output_file, 'r') as f:
            data = json.load(f)

        assert 'extractions' in data
        assert 'metadata' in data
        assert len(data['extractions']) == 2
        assert data['metadata']['total_extractions'] == 2
        assert data['extractions'][0]['population'] == "Pop1"
        assert data['extractions'][1]['population'] == "Pop2"

    def test_export_to_csv(self, pico_agent, tmp_path):
        """Test exporting PICO extractions to CSV."""
        extractions = [
            PICOExtraction(
                population="Pop1", intervention="Int1", comparison="Cmp1",
                outcome="Out1", document_id="1", document_title="Title1",
                extraction_confidence=0.9, study_type="RCT", sample_size="N=100",
                pmid="111", doi="10.1/test1"
            ),
            PICOExtraction(
                population="Pop2", intervention="Int2", comparison="Cmp2",
                outcome="Out2", document_id="2", document_title="Title2",
                extraction_confidence=0.85, study_type="Cohort", sample_size="N=200",
                pmid="222", doi="10.1/test2"
            )
        ]

        output_file = tmp_path / "pico_extractions.csv"
        pico_agent.export_to_csv(extractions, str(output_file))

        # Verify file was created
        assert output_file.exists()

        # Verify content
        import csv
        with open(output_file, 'r') as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        assert len(rows) == 2
        assert rows[0]['document_id'] == '1'
        assert rows[0]['population'] == 'Pop1'
        assert rows[0]['study_type'] == 'RCT'
        assert rows[1]['document_id'] == '2'
        assert rows[1]['population'] == 'Pop2'
        assert rows[1]['study_type'] == 'Cohort'

    def test_pico_extraction_dataclass(self):
        """Test PICOExtraction dataclass."""
        extraction = PICOExtraction(
            population="Test population",
            intervention="Test intervention",
            comparison="Test comparison",
            outcome="Test outcome",
            document_id="123",
            document_title="Test Title",
            extraction_confidence=0.95
        )

        # Verify fields
        assert extraction.population == "Test population"
        assert extraction.intervention == "Test intervention"
        assert extraction.comparison == "Test comparison"
        assert extraction.outcome == "Test outcome"
        assert extraction.document_id == "123"
        assert extraction.document_title == "Test Title"
        assert extraction.extraction_confidence == 0.95

        # Verify created_at is set
        assert extraction.created_at is not None
        assert isinstance(extraction.created_at, datetime)

        # Test to_dict()
        data = extraction.to_dict()
        assert 'population' in data
        assert 'intervention' in data
        assert 'comparison' in data
        assert 'outcome' in data
        assert 'created_at' in data
        assert isinstance(data['created_at'], str)

    def test_text_truncation(self, pico_agent):
        """Test that very long text is truncated."""
        # Create document with very long abstract
        long_doc = SAMPLE_DOCUMENT.copy()
        long_doc['abstract'] = "A" * 10000  # 10k characters

        pico_agent.client.generate = Mock(return_value={
            'response': json.dumps(EXPECTED_PICO)
        })
        pico_agent.test_connection = Mock(return_value=True)

        extraction = pico_agent.extract_pico_from_document(
            document=long_doc,
            min_confidence=0.5
        )

        # Verify extraction succeeded (text was truncated but processing worked)
        assert extraction is not None

        # Verify the generate call received truncated text
        call_args = pico_agent.client.generate.call_args
        prompt = call_args[1]['prompt']
        # Should contain truncation marker
        assert "..." in prompt or len(prompt) < 10000

    def test_callback_integration(self, pico_agent):
        """Test callback function integration."""
        callback = Mock()
        pico_agent.set_callback(callback)

        pico_agent.client.generate = Mock(return_value={
            'response': json.dumps(EXPECTED_PICO)
        })
        pico_agent.test_connection = Mock(return_value=True)

        extraction = pico_agent.extract_pico_from_document(
            document=SAMPLE_DOCUMENT,
            min_confidence=0.5
        )

        # Verify callbacks were called
        assert callback.call_count >= 2
        # Check for started and completed callbacks
        call_args_list = [call[0] for call in callback.call_args_list]
        assert any("started" in str(args) for args in call_args_list)
        assert any("completed" in str(args) for args in call_args_list)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
