"""
Tests for TransparencyAgent

Tests transparency assessment, data models, pattern matching utilities,
and formatted output.
"""

import json
import pytest
from datetime import datetime, timezone
from unittest.mock import Mock, patch, MagicMock

from bmlibrarian.agents import TransparencyAgent, TransparencyAssessment, RiskLevel, DataAvailability
from bmlibrarian.agents.transparency_data import (
    SCORE_THRESHOLD_HIGH_RISK,
    SCORE_THRESHOLD_MEDIUM_RISK,
    KNOWN_PHARMA_COMPANIES,
    CORPORATE_INDICATOR_PATTERNS,
    TRIAL_REGISTRY_PATTERNS,
    is_likely_industry_funder,
    extract_trial_registry_ids,
)


# ──────────────────────────────────────────────────────────────────────────────
# Sample Documents
# ──────────────────────────────────────────────────────────────────────────────

SAMPLE_TRANSPARENT_DOCUMENT = {
    "id": "100001",
    "title": "Efficacy of Exercise on Cardiovascular Health: A Randomized Trial",
    "abstract": """
    Background: Regular exercise is associated with reduced cardiovascular risk.

    Methods: We conducted a randomized controlled trial of 300 adults.

    Results: Exercise group showed significant improvement in all outcomes.

    Conclusions: Regular exercise improves cardiovascular health markers.
    """,
    "full_text": """
    # Efficacy of Exercise on Cardiovascular Health: A Randomized Trial

    ## Abstract
    Background: Regular exercise is associated with reduced cardiovascular risk.

    ## Methods
    We conducted a randomized controlled trial of 300 adults aged 40-65.
    Trial registration: NCT12345678.

    ## Results
    Exercise group showed significant BP reduction of -12.5 mmHg (p<0.001).

    ## Discussion
    Our findings align with previous meta-analyses.

    ## Funding
    This work was supported by the National Institutes of Health (NIH) grant
    R01-HL-98765 and the American Heart Association grant 19CDA34660318.

    ## Conflict of Interest
    Dr. Smith reports no conflicts of interest. Dr. Johnson has received
    consulting fees from CardioHealth Inc. for work unrelated to this study.
    All other authors declare no competing interests.

    ## Data Availability
    All data generated during this study are available in the Zenodo repository
    at https://doi.org/10.5281/zenodo.1234567.

    ## Author Contributions
    JS: Conceptualization, Methodology, Writing - Original Draft.
    MJ: Data Curation, Formal Analysis.
    RW: Investigation, Writing - Review & Editing.

    ## References
    1. Smith et al. (2020) Exercise and cardiovascular health. Lancet.
    """,
    "pmid": "100001",
    "doi": "10.1234/cardio.2024.001",
}

SAMPLE_OPAQUE_DOCUMENT = {
    "id": "200002",
    "title": "Novel Drug Compound Shows Promise in Phase II Trial",
    "abstract": """
    Background: Drug Z is a novel compound developed for hypertension treatment.

    Methods: We enrolled 150 patients in a phase II trial.

    Results: Drug Z reduced systolic BP by 18 mmHg vs placebo (p<0.01).

    Conclusions: Drug Z shows promise for hypertension management.
    """,
    "full_text": "",  # No full text available
    "pmid": "200002",
    "doi": "10.1234/pharma.2024.002",
}

# Expected LLM response for transparent document
EXPECTED_TRANSPARENT_RESPONSE = {
    "has_funding_disclosure": True,
    "funding_statement": "This work was supported by the National Institutes of Health (NIH) grant R01-HL-98765 and the American Heart Association grant 19CDA34660318.",
    "funding_sources": ["National Institutes of Health (NIH)", "American Heart Association"],
    "is_industry_funded": False,
    "industry_funding_confidence": 0.95,
    "funding_disclosure_quality": 1.0,
    "has_coi_disclosure": True,
    "coi_statement": "Dr. Smith reports no conflicts of interest. Dr. Johnson has received consulting fees from CardioHealth Inc.",
    "conflicts_identified": ["Dr. Johnson: consulting fees from CardioHealth Inc."],
    "coi_disclosure_quality": 0.9,
    "data_availability": "open",
    "data_availability_statement": "All data generated during this study are available in the Zenodo repository.",
    "has_author_contributions": True,
    "contributions_statement": "JS: Conceptualization, Methodology. MJ: Data Curation. RW: Investigation.",
    "has_trial_registration": True,
    "trial_registry_ids": ["NCT12345678"],
    "transparency_score": 9.0,
    "overall_confidence": 0.9,
    "risk_indicators": [],
    "strengths": [
        "Complete funding disclosure with specific grant numbers",
        "Per-author COI declarations",
        "Open data in public repository",
        "CRediT author contributions",
        "Registered clinical trial",
    ],
    "weaknesses": [],
}

# Expected LLM response for opaque document
EXPECTED_OPAQUE_RESPONSE = {
    "has_funding_disclosure": False,
    "funding_statement": None,
    "funding_sources": [],
    "is_industry_funded": None,
    "industry_funding_confidence": 0.0,
    "funding_disclosure_quality": 0.0,
    "has_coi_disclosure": False,
    "coi_statement": None,
    "conflicts_identified": [],
    "coi_disclosure_quality": 0.0,
    "data_availability": "not_stated",
    "data_availability_statement": None,
    "has_author_contributions": False,
    "contributions_statement": None,
    "has_trial_registration": False,
    "trial_registry_ids": [],
    "transparency_score": 0.5,
    "overall_confidence": 0.7,
    "risk_indicators": [
        "No funding disclosure for clinical trial",
        "No conflict of interest statement",
        "No data availability statement",
    ],
    "strengths": [],
    "weaknesses": [
        "Missing funding disclosure",
        "Missing COI declaration",
        "No data availability statement",
        "Abstract only - limited text for analysis",
    ],
}


# ──────────────────────────────────────────────────────────────────────────────
# Data Model Tests
# ──────────────────────────────────────────────────────────────────────────────

class TestTransparencyAssessment:
    """Tests for the TransparencyAssessment dataclass."""

    def test_default_values(self) -> None:
        """Test that defaults are set correctly."""
        assessment = TransparencyAssessment(
            document_id="1",
            document_title="Test",
        )
        assert assessment.has_funding_disclosure is False
        assert assessment.has_coi_disclosure is False
        assert assessment.data_availability == "not_stated"
        assert assessment.transparency_score == 0.0
        assert assessment.risk_level == "unknown"
        assert assessment.funding_sources == []
        assert assessment.created_at is not None

    def test_to_dict(self) -> None:
        """Test JSON serialization."""
        assessment = TransparencyAssessment(
            document_id="1",
            document_title="Test",
            transparency_score=7.5,
            risk_level="low",
        )
        data = assessment.to_dict()
        assert isinstance(data, dict)
        assert data["document_id"] == "1"
        assert data["transparency_score"] == 7.5
        assert "created_at" in data

    def test_classify_risk_high(self) -> None:
        """Test high risk classification."""
        assessment = TransparencyAssessment(
            document_id="1",
            document_title="Test",
            transparency_score=2.0,
        )
        assert assessment.classify_risk() == "high"

    def test_classify_risk_medium(self) -> None:
        """Test medium risk classification."""
        assessment = TransparencyAssessment(
            document_id="1",
            document_title="Test",
            transparency_score=4.5,
        )
        assert assessment.classify_risk() == "medium"

    def test_classify_risk_low(self) -> None:
        """Test low risk classification."""
        assessment = TransparencyAssessment(
            document_id="1",
            document_title="Test",
            transparency_score=8.0,
        )
        assert assessment.classify_risk() == "low"


# ──────────────────────────────────────────────────────────────────────────────
# Industry Funder Detection Tests
# ──────────────────────────────────────────────────────────────────────────────

class TestIndustryFunderDetection:
    """Tests for is_likely_industry_funder()."""

    def test_known_pharma_company(self) -> None:
        """Test detection of known pharmaceutical companies."""
        assert is_likely_industry_funder("Pfizer Inc.") is True
        assert is_likely_industry_funder("Novartis Pharmaceuticals") is True
        assert is_likely_industry_funder("AstraZeneca") is True
        assert is_likely_industry_funder("Eli Lilly and Company") is True

    def test_corporate_indicators(self) -> None:
        """Test detection via corporate indicator patterns."""
        assert is_likely_industry_funder("MedTech Therapeutics Inc.") is True
        assert is_likely_industry_funder("BioGenesis Pharma Ltd") is True
        assert is_likely_industry_funder("NeuroScience Corp") is True

    def test_academic_funders_not_flagged(self) -> None:
        """Test that academic funders are not flagged as industry."""
        assert is_likely_industry_funder("National Institutes of Health") is False
        assert is_likely_industry_funder("American Heart Association") is False
        assert is_likely_industry_funder("Wellcome Trust") is False
        assert is_likely_industry_funder("German Research Foundation") is False

    def test_government_funders_not_flagged(self) -> None:
        """Test that government funders are not flagged as industry."""
        assert is_likely_industry_funder("National Science Foundation") is False
        assert is_likely_industry_funder("European Research Council") is False

    def test_case_insensitive(self) -> None:
        """Test case-insensitive matching."""
        assert is_likely_industry_funder("PFIZER") is True
        assert is_likely_industry_funder("pfizer") is True

    def test_empty_string(self) -> None:
        """Test empty string input."""
        assert is_likely_industry_funder("") is False


# ──────────────────────────────────────────────────────────────────────────────
# Trial Registry ID Extraction Tests
# ──────────────────────────────────────────────────────────────────────────────

class TestTrialRegistryExtraction:
    """Tests for extract_trial_registry_ids()."""

    def test_nct_extraction(self) -> None:
        """Test NCT number extraction."""
        text = "This trial was registered at ClinicalTrials.gov (NCT12345678)."
        ids = extract_trial_registry_ids(text)
        assert "NCT12345678" in ids

    def test_isrctn_extraction(self) -> None:
        """Test ISRCTN extraction."""
        text = "Registered with ISRCTN12345678."
        ids = extract_trial_registry_ids(text)
        assert "ISRCTN12345678" in ids

    def test_eudract_extraction(self) -> None:
        """Test EudraCT extraction."""
        text = "EudraCT number: EudraCT 2020-001234-56."
        ids = extract_trial_registry_ids(text)
        assert len(ids) == 1
        assert "EudraCT 2020-001234-56" in ids

    def test_multiple_ids(self) -> None:
        """Test extraction of multiple registry IDs."""
        text = "Registered at NCT11111111 and NCT22222222, and also ISRCTN33333333."
        ids = extract_trial_registry_ids(text)
        assert len(ids) == 3

    def test_no_ids(self) -> None:
        """Test text with no registry IDs."""
        text = "This is a basic observational study with no registration."
        ids = extract_trial_registry_ids(text)
        assert len(ids) == 0

    def test_prospero_extraction(self) -> None:
        """Test PROSPERO ID extraction."""
        text = "Protocol registered with PROSPERO CRD42020123456."
        ids = extract_trial_registry_ids(text)
        assert len(ids) >= 1

    def test_no_duplicates(self) -> None:
        """Test that duplicate IDs are not returned."""
        text = "NCT12345678 was registered. See NCT12345678 for details."
        ids = extract_trial_registry_ids(text)
        assert ids.count("NCT12345678") == 1


# ──────────────────────────────────────────────────────────────────────────────
# TransparencyAgent Tests
# ──────────────────────────────────────────────────────────────────────────────

class TestTransparencyAgent:
    """Tests for the TransparencyAgent."""

    @patch.object(TransparencyAgent, 'test_connection', return_value=True)
    @patch.object(TransparencyAgent, '_generate_and_parse_json')
    def test_assess_transparent_document(
        self, mock_generate: Mock, mock_conn: Mock,
    ) -> None:
        """Test assessment of a well-disclosed document."""
        mock_generate.return_value = EXPECTED_TRANSPARENT_RESPONSE

        agent = TransparencyAgent(show_model_info=False)
        assessment = agent.assess_transparency(SAMPLE_TRANSPARENT_DOCUMENT)

        assert assessment is not None
        assert assessment.document_id == "100001"
        assert assessment.has_funding_disclosure is True
        assert assessment.has_coi_disclosure is True
        assert assessment.data_availability == "open"
        assert assessment.has_author_contributions is True
        assert assessment.has_trial_registration is True
        assert assessment.transparency_score == 9.0
        assert assessment.risk_level == "low"
        assert len(assessment.funding_sources) == 2

    @patch.object(TransparencyAgent, 'test_connection', return_value=True)
    @patch.object(TransparencyAgent, '_generate_and_parse_json')
    def test_assess_opaque_document(
        self, mock_generate: Mock, mock_conn: Mock,
    ) -> None:
        """Test assessment of document with poor disclosures."""
        mock_generate.return_value = EXPECTED_OPAQUE_RESPONSE

        agent = TransparencyAgent(show_model_info=False)
        assessment = agent.assess_transparency(SAMPLE_OPAQUE_DOCUMENT)

        assert assessment is not None
        assert assessment.has_funding_disclosure is False
        assert assessment.has_coi_disclosure is False
        assert assessment.data_availability == "not_stated"
        assert assessment.transparency_score == 0.5
        assert assessment.risk_level == "high"
        assert len(assessment.risk_indicators) > 0

    @patch.object(TransparencyAgent, 'test_connection', return_value=True)
    @patch.object(TransparencyAgent, '_generate_and_parse_json')
    def test_industry_funding_pattern_match(
        self, mock_generate: Mock, mock_conn: Mock,
    ) -> None:
        """Test that pattern matching augments LLM industry detection."""
        response = {
            **EXPECTED_TRANSPARENT_RESPONSE,
            "funding_sources": ["Pfizer Inc.", "NIH"],
            "is_industry_funded": False,  # LLM missed it
            "industry_funding_confidence": 0.3,
        }
        mock_generate.return_value = response

        agent = TransparencyAgent(show_model_info=False)
        assessment = agent.assess_transparency(SAMPLE_TRANSPARENT_DOCUMENT)

        assert assessment is not None
        # Pattern matching should catch Pfizer even if LLM missed it
        assert assessment.is_industry_funded is True
        assert assessment.industry_funding_confidence >= 0.8

    @patch.object(TransparencyAgent, 'test_connection', return_value=True)
    @patch.object(TransparencyAgent, '_generate_and_parse_json')
    def test_registry_id_pre_extraction(
        self, mock_generate: Mock, mock_conn: Mock,
    ) -> None:
        """Test that pattern-extracted registry IDs merge with LLM results."""
        response = {
            **EXPECTED_TRANSPARENT_RESPONSE,
            "trial_registry_ids": ["ISRCTN99999999"],  # LLM found a different one
        }
        mock_generate.return_value = response

        agent = TransparencyAgent(show_model_info=False)
        assessment = agent.assess_transparency(SAMPLE_TRANSPARENT_DOCUMENT)

        assert assessment is not None
        # Should have both the pattern-extracted NCT and the LLM-found ISRCTN
        assert "NCT12345678" in assessment.trial_registry_ids
        assert "ISRCTN99999999" in assessment.trial_registry_ids

    @patch.object(TransparencyAgent, 'test_connection', return_value=False)
    def test_no_connection(self, mock_conn: Mock) -> None:
        """Test handling of no Ollama connection."""
        agent = TransparencyAgent(show_model_info=False)
        assessment = agent.assess_transparency(SAMPLE_TRANSPARENT_DOCUMENT)
        assert assessment is None

    def test_no_text(self) -> None:
        """Test handling of document with no text."""
        agent = TransparencyAgent(show_model_info=False)
        doc = {"id": "1", "title": "Test", "abstract": "", "full_text": ""}
        with patch.object(agent, 'test_connection', return_value=True):
            assessment = agent.assess_transparency(doc)
        assert assessment is None

    @patch.object(TransparencyAgent, 'test_connection', return_value=True)
    @patch.object(TransparencyAgent, '_generate_and_parse_json', side_effect=json.JSONDecodeError("", "", 0))
    def test_json_parse_failure(
        self, mock_generate: Mock, mock_conn: Mock,
    ) -> None:
        """Test handling of JSON parse failure."""
        agent = TransparencyAgent(show_model_info=False)
        assessment = agent.assess_transparency(SAMPLE_TRANSPARENT_DOCUMENT)
        assert assessment is None
        assert agent._assessment_stats["parse_failures"] == 1

    @patch.object(TransparencyAgent, 'test_connection', return_value=True)
    @patch.object(TransparencyAgent, '_generate_and_parse_json')
    def test_missing_required_fields(
        self, mock_generate: Mock, mock_conn: Mock,
    ) -> None:
        """Test handling of response missing required fields."""
        mock_generate.return_value = {"some_field": "value"}
        agent = TransparencyAgent(show_model_info=False)
        assessment = agent.assess_transparency(SAMPLE_TRANSPARENT_DOCUMENT)
        assert assessment is None
        assert agent._assessment_stats["failed_assessments"] == 1

    @patch.object(TransparencyAgent, 'test_connection', return_value=True)
    @patch.object(TransparencyAgent, '_generate_and_parse_json')
    def test_batch_assessment(
        self, mock_generate: Mock, mock_conn: Mock,
    ) -> None:
        """Test batch assessment of multiple documents."""
        mock_generate.return_value = EXPECTED_TRANSPARENT_RESPONSE

        agent = TransparencyAgent(show_model_info=False)
        progress_calls = []

        def track_progress(current: int, total: int, title: str) -> None:
            """Track progress callback calls."""
            progress_calls.append((current, total, title))

        documents = [SAMPLE_TRANSPARENT_DOCUMENT, SAMPLE_TRANSPARENT_DOCUMENT]
        assessments = agent.assess_batch(documents, progress_callback=track_progress)

        assert len(assessments) == 2
        assert len(progress_calls) == 2
        assert progress_calls[0] == (1, 2, SAMPLE_TRANSPARENT_DOCUMENT["title"])

    def test_get_agent_type(self) -> None:
        """Test agent type identifier."""
        agent = TransparencyAgent(show_model_info=False)
        assert agent.get_agent_type() == "transparency_agent"

    @patch.object(TransparencyAgent, 'test_connection', return_value=True)
    @patch.object(TransparencyAgent, '_generate_and_parse_json')
    def test_format_assessment_summary(
        self, mock_generate: Mock, mock_conn: Mock,
    ) -> None:
        """Test formatted summary output."""
        mock_generate.return_value = EXPECTED_TRANSPARENT_RESPONSE

        agent = TransparencyAgent(show_model_info=False)
        assessment = agent.assess_transparency(SAMPLE_TRANSPARENT_DOCUMENT)
        assert assessment is not None

        summary = agent.format_assessment_summary(assessment)
        assert "TRANSPARENCY ASSESSMENT" in summary
        assert "Transparency Score" in summary
        assert "FUNDING DISCLOSURE" in summary
        assert "CONFLICT OF INTEREST" in summary
        assert "DATA AVAILABILITY" in summary

    @patch.object(TransparencyAgent, 'test_connection', return_value=True)
    @patch.object(TransparencyAgent, '_generate_and_parse_json')
    def test_assessment_stats(
        self, mock_generate: Mock, mock_conn: Mock,
    ) -> None:
        """Test assessment statistics tracking."""
        mock_generate.return_value = EXPECTED_TRANSPARENT_RESPONSE

        agent = TransparencyAgent(show_model_info=False)
        agent.assess_transparency(SAMPLE_TRANSPARENT_DOCUMENT)

        stats = agent.get_assessment_stats()
        assert stats["total_assessments"] == 1
        assert stats["successful_assessments"] == 1
        assert stats["success_rate"] == 1.0

    @patch.object(TransparencyAgent, 'test_connection', return_value=True)
    @patch.object(TransparencyAgent, '_generate_and_parse_json')
    def test_risk_distribution(
        self, mock_generate: Mock, mock_conn: Mock,
    ) -> None:
        """Test risk distribution calculation."""
        mock_generate.return_value = EXPECTED_TRANSPARENT_RESPONSE

        agent = TransparencyAgent(show_model_info=False)
        assessment = agent.assess_transparency(SAMPLE_TRANSPARENT_DOCUMENT)
        assert assessment is not None

        distribution = agent.get_risk_distribution([assessment])
        assert distribution["low"] == 1
        assert distribution["high"] == 0

    @patch.object(TransparencyAgent, 'test_connection', return_value=True)
    @patch.object(TransparencyAgent, '_generate_and_parse_json')
    def test_export_to_json(
        self, mock_generate: Mock, mock_conn: Mock, tmp_path,
    ) -> None:
        """Test JSON export."""
        mock_generate.return_value = EXPECTED_TRANSPARENT_RESPONSE

        agent = TransparencyAgent(show_model_info=False)
        assessment = agent.assess_transparency(SAMPLE_TRANSPARENT_DOCUMENT)
        assert assessment is not None

        output_file = str(tmp_path / "test_export.json")
        agent.export_to_json([assessment], output_file)

        with open(output_file, "r") as f:
            data = json.load(f)
        assert data["metadata"]["total_assessments"] == 1
        assert len(data["assessments"]) == 1

    @patch.object(TransparencyAgent, 'test_connection', return_value=True)
    @patch.object(TransparencyAgent, '_generate_and_parse_json')
    def test_export_to_csv(
        self, mock_generate: Mock, mock_conn: Mock, tmp_path,
    ) -> None:
        """Test CSV export."""
        mock_generate.return_value = EXPECTED_TRANSPARENT_RESPONSE

        agent = TransparencyAgent(show_model_info=False)
        assessment = agent.assess_transparency(SAMPLE_TRANSPARENT_DOCUMENT)
        assert assessment is not None

        output_file = str(tmp_path / "test_export.csv")
        agent.export_to_csv([assessment], output_file)

        with open(output_file, "r") as f:
            lines = f.readlines()
        assert len(lines) == 2  # header + 1 row


# ──────────────────────────────────────────────────────────────────────────────
# PDF Processor Section Type Tests
# ──────────────────────────────────────────────────────────────────────────────

class TestPDFProcessorExtension:
    """Tests for the transparency-related PDF section types."""

    def test_funding_section_type_exists(self) -> None:
        """Test that FUNDING section type is defined."""
        from bmlibrarian.pdf_processor.models import SectionType
        assert hasattr(SectionType, "FUNDING")
        assert SectionType.FUNDING.value == "funding"

    def test_conflicts_section_type_exists(self) -> None:
        """Test that CONFLICTS section type is defined."""
        from bmlibrarian.pdf_processor.models import SectionType
        assert hasattr(SectionType, "CONFLICTS")
        assert SectionType.CONFLICTS.value == "conflicts"

    def test_data_availability_section_type_exists(self) -> None:
        """Test that DATA_AVAILABILITY section type is defined."""
        from bmlibrarian.pdf_processor.models import SectionType
        assert hasattr(SectionType, "DATA_AVAILABILITY")
        assert SectionType.DATA_AVAILABILITY.value == "data_availability"

    def test_author_contributions_section_type_exists(self) -> None:
        """Test that AUTHOR_CONTRIBUTIONS section type is defined."""
        from bmlibrarian.pdf_processor.models import SectionType
        assert hasattr(SectionType, "AUTHOR_CONTRIBUTIONS")
        assert SectionType.AUTHOR_CONTRIBUTIONS.value == "author_contributions"

    def test_segmenter_has_funding_patterns(self) -> None:
        """Test that segmenter recognizes funding headers."""
        from bmlibrarian.pdf_processor.segmenter import SectionSegmenter
        from bmlibrarian.pdf_processor.models import SectionType

        segmenter = SectionSegmenter()
        section_type, confidence = segmenter._match_section_type("Funding")
        assert section_type == SectionType.FUNDING
        assert confidence == 1.0

    def test_segmenter_has_conflicts_patterns(self) -> None:
        """Test that segmenter recognizes COI headers."""
        from bmlibrarian.pdf_processor.segmenter import SectionSegmenter
        from bmlibrarian.pdf_processor.models import SectionType

        segmenter = SectionSegmenter()
        section_type, confidence = segmenter._match_section_type("Conflicts of Interest")
        assert section_type == SectionType.CONFLICTS
        assert confidence == 1.0

    def test_segmenter_has_data_availability_patterns(self) -> None:
        """Test that segmenter recognizes data availability headers."""
        from bmlibrarian.pdf_processor.segmenter import SectionSegmenter
        from bmlibrarian.pdf_processor.models import SectionType

        segmenter = SectionSegmenter()
        section_type, confidence = segmenter._match_section_type("Data Availability")
        assert section_type == SectionType.DATA_AVAILABILITY
        assert confidence == 1.0

    def test_segmenter_competing_interests_variant(self) -> None:
        """Test competing interests variant."""
        from bmlibrarian.pdf_processor.segmenter import SectionSegmenter
        from bmlibrarian.pdf_processor.models import SectionType

        segmenter = SectionSegmenter()
        section_type, confidence = segmenter._match_section_type("Competing Interests")
        assert section_type == SectionType.CONFLICTS
        assert confidence == 1.0

    def test_segmenter_financial_disclosure_variant(self) -> None:
        """Test financial disclosure variant."""
        from bmlibrarian.pdf_processor.segmenter import SectionSegmenter
        from bmlibrarian.pdf_processor.models import SectionType

        segmenter = SectionSegmenter()
        section_type, confidence = segmenter._match_section_type("Financial Disclosures")
        assert section_type == SectionType.CONFLICTS
        assert confidence == 1.0

    def test_segmenter_author_contributions_variant(self) -> None:
        """Test author contributions variant."""
        from bmlibrarian.pdf_processor.segmenter import SectionSegmenter
        from bmlibrarian.pdf_processor.models import SectionType

        segmenter = SectionSegmenter()
        section_type, confidence = segmenter._match_section_type("Author Contributions")
        assert section_type == SectionType.AUTHOR_CONTRIBUTIONS
        assert confidence == 1.0
