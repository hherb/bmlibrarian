"""
Tests for StudyAssessmentAgent

Tests study quality assessment and trustworthiness evaluation.
"""

import pytest
import json
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

from bmlibrarian.agents import StudyAssessmentAgent, StudyAssessment


# Sample RCT document for testing
SAMPLE_RCT_DOCUMENT = {
    'id': '12345678',
    'title': 'Efficacy of Drug X in Treating Hypertension: A Randomized Controlled Trial',
    'abstract': """
    Background: Hypertension is a major cardiovascular risk factor affecting millions worldwide.

    Methods: We conducted a multicenter, randomized, double-blind, placebo-controlled trial involving
    500 adults aged 45-75 years with stage 2 hypertension (systolic BP 140-180 mmHg). Participants
    were recruited from 12 cardiology centers across North America. Patients were randomly assigned
    1:1 to receive either Drug X 100mg daily (n=250) or matching placebo (n=250) for 24 weeks.
    Randomization was performed using computer-generated random sequences with allocation concealment.
    Primary outcome was mean change in systolic blood pressure from baseline to week 24. Secondary
    outcomes included diastolic BP, cardiovascular events, and quality of life (measured by SF-36).

    Results: At 24 weeks, the Drug X group showed mean systolic BP reduction of -15.2 mmHg (95% CI:
    -17.8 to -12.6) compared to -3.1 mmHg (95% CI: -5.2 to -1.0) in placebo (p<0.001). Diastolic BP
    decreased by -8.5 mmHg vs -2.1 mmHg (p<0.001). No significant difference in cardiovascular events
    was observed (3.2% vs 4.0%, p=0.65). Quality of life improved significantly in Drug X group.
    Dropout rate was 4.8% in Drug X vs 5.2% in placebo. Adverse events were similar between groups.

    Conclusions: Drug X 100mg daily for 24 weeks significantly reduced blood pressure in adults with
    hypertension, with good tolerability and safety profile.
    """,
    'pmid': '12345678',
    'doi': '10.1234/hypertension.2023.001'
}

# Expected assessment for high-quality RCT
EXPECTED_RCT_ASSESSMENT = {
    "study_type": "Randomized Controlled Trial (RCT)",
    "study_design": "Prospective, multicenter, randomized, double-blind, placebo-controlled trial",
    "quality_score": 8.5,
    "strengths": [
        "Multicenter design with 12 sites enhancing generalizability",
        "Large sample size (N=500) with adequate statistical power",
        "Appropriate randomization with allocation concealment",
        "Double-blinding of participants and assessors reducing bias",
        "Low dropout rate (4.8-5.2%) minimizing attrition bias",
        "Validated outcome measures (SF-36 for quality of life)"
    ],
    "limitations": [
        "Relatively short follow-up period (24 weeks) - long-term effects unknown",
        "No information on racial/ethnic diversity of participants",
        "Single dose tested - dose-response relationship not established"
    ],
    "overall_confidence": 0.85,
    "confidence_explanation": "High-quality RCT with rigorous methodology, appropriate blinding, adequate sample size, and low attrition. Confidence reduced slightly due to lack of long-term follow-up data.",
    "evidence_level": "Level 1 (high)",
    "is_prospective": True,
    "is_retrospective": False,
    "is_randomized": True,
    "is_controlled": True,
    "is_blinded": True,
    "is_double_blinded": True,
    "is_multi_center": True,
    "sample_size": "N=500",
    "follow_up_duration": "24 weeks",
    "selection_bias_risk": "low",
    "performance_bias_risk": "low",
    "detection_bias_risk": "low",
    "attrition_bias_risk": "low",
    "reporting_bias_risk": "low"
}

# Sample case report document
SAMPLE_CASE_REPORT_DOCUMENT = {
    'id': '87654321',
    'title': 'Rare Adverse Reaction to Common Antibiotic: A Case Report',
    'abstract': """
    We report a case of a 34-year-old woman who developed Stevens-Johnson syndrome following
    administration of amoxicillin for a respiratory tract infection. The patient had no prior
    history of drug allergies. She developed widespread skin lesions and mucosal involvement
    72 hours after starting the medication. Treatment with corticosteroids and supportive care
    led to gradual resolution over 3 weeks. This case highlights the importance of monitoring
    for severe cutaneous reactions even with commonly prescribed antibiotics.
    """,
    'pmid': '87654321',
    'doi': '10.5678/casereport.2023.042'
}

# Expected assessment for case report
EXPECTED_CASE_REPORT_ASSESSMENT = {
    "study_type": "Case report",
    "study_design": "Single patient descriptive report",
    "quality_score": 2.5,
    "strengths": [
        "Detailed clinical description of rare adverse event",
        "Clear temporal relationship between drug exposure and reaction"
    ],
    "limitations": [
        "Single case - no generalizability",
        "No comparison group or control",
        "Cannot establish causation definitively",
        "Limited clinical details provided",
        "No long-term follow-up data"
    ],
    "overall_confidence": 0.75,
    "confidence_explanation": "Clear description of case but inherently limited by study design. Confidence in assessment accuracy is high, but confidence in the evidence quality is low due to case report design.",
    "evidence_level": "Level 5 (low)",
    "is_prospective": False,
    "is_retrospective": True,
    "is_randomized": False,
    "is_controlled": False,
    "is_blinded": False,
    "is_double_blinded": False,
    "is_multi_center": False,
    "sample_size": "N=1",
    "follow_up_duration": "3 weeks",
    "selection_bias_risk": "high",
    "performance_bias_risk": "unclear",
    "detection_bias_risk": "unclear",
    "attrition_bias_risk": "low",
    "reporting_bias_risk": "unclear"
}


class TestStudyAssessmentAgent:
    """Test suite for StudyAssessmentAgent."""

    @pytest.fixture
    def mock_ollama_client(self):
        """Create a mock Ollama client."""
        with patch('bmlibrarian.agents.base.ollama.Client') as mock_client:
            yield mock_client

    @pytest.fixture
    def assessment_agent(self, mock_ollama_client):
        """Create a StudyAssessmentAgent instance with mocked Ollama."""
        agent = StudyAssessmentAgent(
            model="gpt-oss:20b",
            show_model_info=False
        )
        # Mock the client
        agent.client = Mock()
        return agent

    def test_agent_initialization(self):
        """Test StudyAssessmentAgent initialization."""
        with patch('bmlibrarian.agents.base.ollama.Client'):
            agent = StudyAssessmentAgent(
                model="gpt-oss:20b",
                temperature=0.1,
                top_p=0.9,
                max_tokens=3000,
                show_model_info=False
            )

            assert agent.model == "gpt-oss:20b"
            assert agent.temperature == 0.1
            assert agent.top_p == 0.9
            assert agent.max_tokens == 3000
            assert agent.get_agent_type() == "study_assessment_agent"

    def test_assess_rct_success(self, assessment_agent):
        """Test successful assessment of high-quality RCT."""
        # Mock successful LLM response
        assessment_agent.client.generate = Mock(return_value={
            'response': json.dumps(EXPECTED_RCT_ASSESSMENT)
        })

        # Perform assessment
        assessment = assessment_agent.assess_study(
            SAMPLE_RCT_DOCUMENT,
            min_confidence=0.5
        )

        # Verify assessment was successful
        assert assessment is not None
        assert isinstance(assessment, StudyAssessment)

        # Verify study classification
        assert 'RCT' in assessment.study_type or 'randomized' in assessment.study_type.lower()
        assert assessment.is_randomized is True
        assert assessment.is_controlled is True
        assert assessment.is_double_blinded is True
        assert assessment.is_multi_center is True

        # Verify quality metrics
        assert assessment.quality_score >= 7.0
        assert assessment.overall_confidence >= 0.7
        assert 'Level 1' in assessment.evidence_level

        # Verify lists populated
        assert len(assessment.strengths) > 0
        assert len(assessment.limitations) > 0

        # Verify bias assessment
        assert assessment.selection_bias_risk == 'low'
        assert assessment.attrition_bias_risk == 'low'

        # Verify metadata
        assert assessment.document_id == '12345678'
        assert assessment.document_title == SAMPLE_RCT_DOCUMENT['title']
        assert assessment.pmid == '12345678'
        assert assessment.sample_size == 'N=500'

    def test_assess_case_report(self, assessment_agent):
        """Test assessment of case report (low-quality evidence)."""
        # Mock LLM response for case report
        assessment_agent.client.generate = Mock(return_value={
            'response': json.dumps(EXPECTED_CASE_REPORT_ASSESSMENT)
        })

        # Perform assessment
        assessment = assessment_agent.assess_study(
            SAMPLE_CASE_REPORT_DOCUMENT,
            min_confidence=0.4
        )

        # Verify assessment was successful
        assert assessment is not None
        assert isinstance(assessment, StudyAssessment)

        # Verify study classification
        assert 'case report' in assessment.study_type.lower()
        assert assessment.is_randomized is False
        assert assessment.is_controlled is False

        # Verify quality metrics (should be low)
        assert assessment.quality_score <= 4.0
        assert 'Level 5' in assessment.evidence_level or 'Level 4' in assessment.evidence_level

        # Verify limitations > strengths (typical for case reports)
        assert len(assessment.limitations) >= len(assessment.strengths)

    def test_assess_missing_text(self, assessment_agent):
        """Test assessment fails gracefully with missing text."""
        document_no_text = {
            'id': '999',
            'title': 'Study with no abstract'
        }

        assessment = assessment_agent.assess_study(document_no_text)

        # Should return None when no text available
        assert assessment is None

    def test_assess_low_confidence_threshold(self, assessment_agent):
        """Test that assessments below confidence threshold are still returned."""
        # Mock response with low confidence
        low_confidence_assessment = EXPECTED_RCT_ASSESSMENT.copy()
        low_confidence_assessment['overall_confidence'] = 0.3

        assessment_agent.client.generate = Mock(return_value={
            'response': json.dumps(low_confidence_assessment)
        })

        # Even with min_confidence=0.5, low confidence assessments are returned
        # (unlike PICOAgent which returns None)
        assessment = assessment_agent.assess_study(
            SAMPLE_RCT_DOCUMENT,
            min_confidence=0.5
        )

        # Should still return assessment (logged as low confidence)
        assert assessment is not None
        assert assessment.overall_confidence == 0.3

    def test_assess_batch_success(self, assessment_agent):
        """Test successful batch assessment."""
        # Mock LLM responses
        assessment_agent.client.generate = Mock(side_effect=[
            {'response': json.dumps(EXPECTED_RCT_ASSESSMENT)},
            {'response': json.dumps(EXPECTED_CASE_REPORT_ASSESSMENT)}
        ])

        documents = [SAMPLE_RCT_DOCUMENT, SAMPLE_CASE_REPORT_DOCUMENT]

        # Test progress callback
        progress_calls = []

        def progress_callback(current, total, title):
            progress_calls.append((current, total, title))

        # Perform batch assessment
        assessments = assessment_agent.assess_batch(
            documents,
            min_confidence=0.4,
            progress_callback=progress_callback
        )

        # Verify results
        assert len(assessments) == 2
        assert all(isinstance(a, StudyAssessment) for a in assessments)

        # Verify progress callback was called
        assert len(progress_calls) == 2
        assert progress_calls[0] == (1, 2, SAMPLE_RCT_DOCUMENT['title'])
        assert progress_calls[1] == (2, 2, SAMPLE_CASE_REPORT_DOCUMENT['title'])

    def test_format_assessment_summary(self, assessment_agent):
        """Test formatting assessment as human-readable summary."""
        # Create assessment object
        assessment = StudyAssessment(
            study_type="Randomized Controlled Trial (RCT)",
            study_design="Prospective, double-blind",
            quality_score=8.5,
            strengths=["Large sample size", "Good randomization"],
            limitations=["Short follow-up", "Single center"],
            overall_confidence=0.85,
            confidence_explanation="High-quality RCT with good methodology",
            evidence_level="Level 1 (high)",
            document_id="12345",
            document_title="Test Study",
            is_randomized=True,
            is_double_blinded=True,
            sample_size="N=500",
            selection_bias_risk="low",
            pmid="12345678"
        )

        # Format summary
        summary = assessment_agent.format_assessment_summary(assessment)

        # Verify key elements present
        assert "STUDY QUALITY ASSESSMENT" in summary
        assert "Test Study" in summary
        assert "Randomized Controlled Trial" in summary
        assert "Quality Score: 8.5/10" in summary
        assert "Overall Confidence: 85.00%" in summary
        assert "Level 1 (high)" in summary
        assert "Large sample size" in summary
        assert "Short follow-up" in summary
        assert "Selection: low" in summary

    def test_export_to_json(self, assessment_agent, tmp_path):
        """Test exporting assessments to JSON file."""
        # Create test assessments
        assessments = [
            StudyAssessment(
                study_type="RCT",
                study_design="Randomized",
                quality_score=8.0,
                strengths=["Good design"],
                limitations=["Short duration"],
                overall_confidence=0.8,
                confidence_explanation="Well designed",
                evidence_level="Level 1 (high)",
                document_id="1",
                document_title="Study 1"
            ),
            StudyAssessment(
                study_type="Cohort",
                study_design="Prospective cohort",
                quality_score=6.5,
                strengths=["Large sample"],
                limitations=["Observational"],
                overall_confidence=0.7,
                confidence_explanation="Adequate methodology",
                evidence_level="Level 3 (moderate)",
                document_id="2",
                document_title="Study 2"
            )
        ]

        # Export to JSON
        output_file = tmp_path / "assessments.json"
        assessment_agent.export_to_json(assessments, str(output_file))

        # Verify file was created
        assert output_file.exists()

        # Verify JSON structure
        with open(output_file, 'r') as f:
            data = json.load(f)

        assert 'assessments' in data
        assert 'metadata' in data
        assert len(data['assessments']) == 2
        assert data['metadata']['total_assessments'] == 2
        assert data['metadata']['agent_model'] == 'gpt-oss:20b'

        # Verify assessment data
        assert data['assessments'][0]['study_type'] == 'RCT'
        assert data['assessments'][1]['study_type'] == 'Cohort'

    def test_export_to_csv(self, assessment_agent, tmp_path):
        """Test exporting assessments to CSV file."""
        import csv

        # Create test assessments
        assessments = [
            StudyAssessment(
                study_type="RCT",
                study_design="Randomized",
                quality_score=8.0,
                strengths=["Strength 1", "Strength 2"],
                limitations=["Limitation 1"],
                overall_confidence=0.8,
                confidence_explanation="Well designed",
                evidence_level="Level 1 (high)",
                document_id="1",
                document_title="Study 1",
                is_randomized=True
            )
        ]

        # Export to CSV
        output_file = tmp_path / "assessments.csv"
        assessment_agent.export_to_csv(assessments, str(output_file))

        # Verify file was created
        assert output_file.exists()

        # Read and verify CSV
        with open(output_file, 'r') as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        assert len(rows) == 1
        assert rows[0]['study_type'] == 'RCT'
        assert rows[0]['quality_score'] == '8.0'
        assert rows[0]['is_randomized'] == 'True'
        # Lists should be joined with semicolons
        assert 'Strength 1; Strength 2' in rows[0]['strengths']

    def test_get_assessment_stats(self, assessment_agent):
        """Test assessment statistics tracking."""
        # Initial stats should be zero
        stats = assessment_agent.get_assessment_stats()
        assert stats['total_assessments'] == 0
        assert stats['success_rate'] == 0.0

        # Mock successful assessment
        assessment_agent.client.generate = Mock(return_value={
            'response': json.dumps(EXPECTED_RCT_ASSESSMENT)
        })

        # Perform assessment
        assessment_agent.assess_study(SAMPLE_RCT_DOCUMENT)

        # Check updated stats
        stats = assessment_agent.get_assessment_stats()
        assert stats['total_assessments'] == 1
        assert stats['successful_assessments'] == 1
        assert stats['success_rate'] == 1.0

    def test_get_quality_distribution(self, assessment_agent):
        """Test quality score distribution calculation."""
        # Create assessments with varying quality scores
        assessments = [
            StudyAssessment(
                study_type="RCT", study_design="Randomized",
                quality_score=9.5, strengths=[], limitations=[],
                overall_confidence=0.9, confidence_explanation="",
                evidence_level="Level 1", document_id="1", document_title="Study 1"
            ),
            StudyAssessment(
                study_type="Cohort", study_design="Cohort",
                quality_score=7.5, strengths=[], limitations=[],
                overall_confidence=0.7, confidence_explanation="",
                evidence_level="Level 3", document_id="2", document_title="Study 2"
            ),
            StudyAssessment(
                study_type="Case report", study_design="Case",
                quality_score=2.0, strengths=[], limitations=[],
                overall_confidence=0.5, confidence_explanation="",
                evidence_level="Level 5", document_id="3", document_title="Study 3"
            )
        ]

        # Get distribution
        distribution = assessment_agent.get_quality_distribution(assessments)

        # Verify counts
        assert distribution['exceptional (9-10)'] == 1
        assert distribution['high (7-8)'] == 1
        assert distribution['moderate (5-6)'] == 0
        assert distribution['low (3-4)'] == 0
        assert distribution['very_low (0-2)'] == 1

    def test_get_evidence_level_distribution(self, assessment_agent):
        """Test evidence level distribution calculation."""
        # Create assessments with varying evidence levels
        assessments = [
            StudyAssessment(
                study_type="RCT", study_design="Randomized",
                quality_score=9.0, strengths=[], limitations=[],
                overall_confidence=0.9, confidence_explanation="",
                evidence_level="Level 1 (high)", document_id="1", document_title="Study 1"
            ),
            StudyAssessment(
                study_type="RCT", study_design="Randomized",
                quality_score=8.0, strengths=[], limitations=[],
                overall_confidence=0.8, confidence_explanation="",
                evidence_level="Level 1 (high)", document_id="2", document_title="Study 2"
            ),
            StudyAssessment(
                study_type="Cohort", study_design="Cohort",
                quality_score=6.0, strengths=[], limitations=[],
                overall_confidence=0.7, confidence_explanation="",
                evidence_level="Level 3 (moderate)", document_id="3", document_title="Study 3"
            )
        ]

        # Get distribution
        distribution = assessment_agent.get_evidence_level_distribution(assessments)

        # Verify counts
        assert distribution['Level 1 (high)'] == 2
        assert distribution['Level 3 (moderate)'] == 1

    def test_json_parse_failure_retry(self, assessment_agent):
        """Test that JSON parse failures trigger retry."""
        # Mock responses: first invalid JSON, then valid
        assessment_agent.client.generate = Mock(side_effect=[
            {'response': 'This is not valid JSON'},
            {'response': json.dumps(EXPECTED_RCT_ASSESSMENT)}
        ])

        # Should succeed on retry
        assessment = assessment_agent.assess_study(SAMPLE_RCT_DOCUMENT)

        # Verify assessment succeeded on retry
        assert assessment is not None
        assert assessment_agent.client.generate.call_count == 2

    def test_connection_failure(self, assessment_agent):
        """Test assessment handles connection failures gracefully."""
        # Mock connection test failure
        assessment_agent.test_connection = Mock(return_value=False)

        # Should return None
        assessment = assessment_agent.assess_study(SAMPLE_RCT_DOCUMENT)

        assert assessment is None

    def test_text_truncation(self, assessment_agent):
        """Test that very long texts are truncated appropriately."""
        # Create document with very long abstract
        long_document = {
            'id': '999',
            'title': 'Long study',
            'abstract': 'A' * 20000  # 20,000 characters
        }

        assessment_agent.client.generate = Mock(return_value={
            'response': json.dumps(EXPECTED_RCT_ASSESSMENT)
        })

        # Should not fail due to text length
        assessment = assessment_agent.assess_study(long_document)

        # Verify LLM was called (text was truncated but assessment proceeded)
        assert assessment_agent.client.generate.called

    def test_study_assessment_dataclass_to_dict(self):
        """Test StudyAssessment dataclass conversion to dictionary."""
        assessment = StudyAssessment(
            study_type="RCT",
            study_design="Randomized, double-blind",
            quality_score=8.5,
            strengths=["Large sample"],
            limitations=["Short duration"],
            overall_confidence=0.85,
            confidence_explanation="High quality",
            evidence_level="Level 1 (high)",
            document_id="12345",
            document_title="Test Study",
            pmid="12345678"
        )

        # Convert to dict
        data = assessment.to_dict()

        # Verify structure
        assert isinstance(data, dict)
        assert data['study_type'] == 'RCT'
        assert data['quality_score'] == 8.5
        assert data['overall_confidence'] == 0.85
        assert data['pmid'] == '12345678'
        assert 'created_at' in data
        assert isinstance(data['created_at'], str)  # ISO format

    def test_missing_required_fields(self, assessment_agent):
        """Test that missing required fields in LLM response causes failure."""
        # Mock response missing required fields
        incomplete_assessment = {
            "study_type": "RCT",
            # Missing: study_design, quality_score, strengths, limitations, etc.
        }

        assessment_agent.client.generate = Mock(return_value={
            'response': json.dumps(incomplete_assessment)
        })

        # Should return None due to missing fields
        assessment = assessment_agent.assess_study(SAMPLE_RCT_DOCUMENT)

        assert assessment is None

    def test_assessment_with_full_text(self, assessment_agent):
        """Test that full text is preferred over abstract when available."""
        # Document with both abstract and full_text
        document_with_full_text = {
            'id': '123',
            'title': 'Study with full text',
            'abstract': 'Short abstract',
            'full_text': 'This is the full text with much more detail about the methodology...'
        }

        assessment_agent.client.generate = Mock(return_value={
            'response': json.dumps(EXPECTED_RCT_ASSESSMENT)
        })

        assessment = assessment_agent.assess_study(document_with_full_text)

        # Verify LLM was called
        assert assessment_agent.client.generate.called

        # Verify the prompt contained full text (not just abstract)
        call_args = assessment_agent.client.generate.call_args
        prompt = call_args[1]['prompt']
        assert 'full text with much more detail' in prompt
        assert 'Short abstract' not in prompt
