"""
Tests for PRISMA2020Agent

Tests PRISMA 2020 compliance assessment and systematic review reporting quality evaluation.
"""

import pytest
import json
from unittest.mock import Mock, patch
from datetime import datetime

from bmlibrarian.agents.prisma2020_agent import (
    PRISMA2020Agent, PRISMA2020Assessment, SuitabilityAssessment
)


# Sample systematic review document for testing
SAMPLE_SYSTEMATIC_REVIEW_DOCUMENT = {
    'id': '12345678',
    'title': 'Effectiveness of Exercise for Cardiovascular Health: A Systematic Review and Meta-Analysis',
    'abstract': """
    Background: Physical exercise is widely recommended for cardiovascular health, but the optimal
    type, intensity, and duration remain unclear.

    Objectives: To systematically review evidence on exercise interventions for cardiovascular health
    outcomes in adults (PICO: Population=adults 18-75, Intervention=structured exercise programs,
    Comparison=usual care or no exercise, Outcome=cardiovascular events and biomarkers).

    Methods: We searched MEDLINE, Embase, CENTRAL, and Web of Science from inception to December 2023
    without language restrictions. We included randomized controlled trials comparing structured exercise
    programs with usual care. Two reviewers independently screened titles and abstracts, assessed full
    texts for eligibility, extracted data using standardized forms, and assessed risk of bias using the
    Cochrane Risk of Bias tool 2.0. We performed random-effects meta-analysis and assessed certainty
    of evidence using GRADE.

    Results: We identified 4,523 records, screened 389 full texts, and included 45 RCTs (N=8,234
    participants). Exercise significantly reduced systolic blood pressure (MD -5.2 mmHg, 95% CI -7.1
    to -3.3, I²=45%, moderate certainty evidence) and improved VO2 max (MD 3.5 mL/kg/min, 95% CI 2.8
    to 4.2, I²=62%, moderate certainty evidence). PRISMA flow diagram shows detailed screening process.
    Publication bias was assessed using funnel plots and Egger's test (p=0.23).

    Conclusions: Moderate to high certainty evidence supports exercise for improving cardiovascular
    biomarkers in adults. Limitations include heterogeneity in exercise protocols and short follow-up
    periods.

    Registration: PROSPERO CRD42023123456
    Funding: National Heart Foundation (no role in study design or interpretation)
    """,
    'pmid': '12345678',
    'doi': '10.1234/systematic-review.2024.001'
}

# Expected suitability assessment for systematic review
EXPECTED_SUITABILITY_SYSTEMATIC_REVIEW = {
    "is_systematic_review": True,
    "is_meta_analysis": True,
    "is_suitable": True,
    "confidence": 0.95,
    "rationale": "This document is a systematic review with meta-analysis as evidenced by comprehensive literature search across multiple databases, systematic study selection with duplicate screening, risk of bias assessment using Cochrane tool, and statistical meta-analysis with forest plots. PROSPERO registration confirms systematic review methodology.",
    "document_type": "systematic review with meta-analysis"
}

# Expected PRISMA assessment for high-quality systematic review
EXPECTED_PRISMA_ASSESSMENT = {
    "title_score": 2.0,
    "title_explanation": "Title clearly identifies this as a systematic review and meta-analysis",
    "abstract_score": 2.0,
    "abstract_explanation": "Abstract provides structured summary with background, objectives, data sources, study eligibility, assessment methods, results, limitations, conclusions, funding, and registration",
    "rationale_score": 2.0,
    "rationale_explanation": "Rationale clearly stated - optimal exercise parameters for cardiovascular health remain unclear",
    "objectives_score": 2.0,
    "objectives_explanation": "Objectives explicit with PICO elements fully specified (adults 18-75, exercise programs, usual care, CV outcomes)",
    "eligibility_criteria_score": 2.0,
    "eligibility_criteria_explanation": "Study characteristics clear (RCTs, structured exercise vs usual care, adults)",
    "information_sources_score": 2.0,
    "information_sources_explanation": "Multiple databases specified (MEDLINE, Embase, CENTRAL, Web of Science) with date ranges (inception to December 2023) and no language restrictions",
    "search_strategy_score": 0.0,
    "search_strategy_explanation": "Full search strategy not provided in abstract - would need full text",
    "selection_process_score": 2.0,
    "selection_process_explanation": "Two independent reviewers screened titles/abstracts and full texts",
    "data_collection_score": 2.0,
    "data_collection_explanation": "Data extraction using standardized forms mentioned",
    "data_items_score": 1.0,
    "data_items_explanation": "Some outcomes mentioned (BP, VO2 max) but not all variables detailed",
    "risk_of_bias_score": 2.0,
    "risk_of_bias_explanation": "Cochrane Risk of Bias tool 2.0 specified for bias assessment",
    "effect_measures_score": 2.0,
    "effect_measures_explanation": "Effect measures clearly defined (mean differences with 95% CI)",
    "synthesis_methods_score": 2.0,
    "synthesis_methods_explanation": "Random-effects meta-analysis described with I² for heterogeneity",
    "reporting_bias_assessment_score": 2.0,
    "reporting_bias_assessment_explanation": "Publication bias assessed using funnel plots and Egger's test",
    "certainty_assessment_score": 2.0,
    "certainty_assessment_explanation": "GRADE methodology used to assess certainty of evidence",
    "study_selection_score": 2.0,
    "study_selection_explanation": "PRISMA flow diagram mentioned showing screening process with numbers",
    "study_characteristics_score": 1.0,
    "study_characteristics_explanation": "Number of studies and participants provided, but detailed characteristics table not in abstract",
    "risk_of_bias_results_score": 0.0,
    "risk_of_bias_results_explanation": "Risk of bias results not reported in abstract",
    "individual_studies_results_score": 0.0,
    "individual_studies_results_explanation": "Individual study results not presented in abstract",
    "synthesis_results_score": 2.0,
    "synthesis_results_explanation": "Meta-analysis results presented with effect sizes, confidence intervals, and heterogeneity (I²)",
    "reporting_biases_results_score": 2.0,
    "reporting_biases_results_explanation": "Publication bias assessment results reported (Egger's test p=0.23)",
    "certainty_of_evidence_score": 2.0,
    "certainty_of_evidence_explanation": "Certainty of evidence reported as moderate for main outcomes",
    "discussion_score": 1.0,
    "discussion_explanation": "Conclusions provided but limited discussion in abstract",
    "limitations_score": 2.0,
    "limitations_explanation": "Limitations clearly stated (heterogeneity, short follow-up)",
    "conclusions_score": 2.0,
    "conclusions_explanation": "Conclusions aligned with evidence and objectives without overstatement",
    "registration_score": 2.0,
    "registration_explanation": "PROSPERO registration number provided (CRD42023123456)",
    "support_score": 2.0,
    "support_explanation": "Funding source stated (National Heart Foundation) with sponsor role clarified",
    "overall_confidence": 0.85
}

# Sample primary research document (not suitable for PRISMA)
SAMPLE_RCT_DOCUMENT = {
    'id': '87654321',
    'title': 'Effect of Exercise Training on Blood Pressure in Hypertensive Adults: A Randomized Controlled Trial',
    'abstract': """
    Background: Exercise is recommended for managing hypertension, but evidence is limited.

    Methods: We conducted a single-center, randomized, single-blind trial of 120 adults with
    stage 1-2 hypertension. Participants were randomly assigned to supervised aerobic exercise
    (3 sessions/week, 45 minutes, 12 weeks) or usual care. Primary outcome was change in systolic
    blood pressure at 12 weeks.

    Results: Exercise group showed significant reduction in systolic BP (-8.2 mmHg, 95% CI -11.3
    to -5.1) compared to control (-1.5 mmHg, 95% CI -4.2 to 1.2), p=0.002.

    Conclusions: Supervised aerobic exercise effectively reduces blood pressure in hypertensive adults.
    """,
    'pmid': '87654321',
    'doi': '10.5678/rct.2024.042'
}

# Expected suitability for RCT (not suitable for PRISMA)
EXPECTED_SUITABILITY_RCT = {
    "is_systematic_review": False,
    "is_meta_analysis": False,
    "is_suitable": False,
    "confidence": 0.9,
    "rationale": "This document is not suitable for PRISMA 2020 assessment because it is a primary randomized controlled trial, not a systematic review or meta-analysis. It reports original research findings rather than synthesizing evidence from multiple studies.",
    "document_type": "randomized controlled trial (RCT)"
}


class TestPRISMA2020Agent:
    """Test suite for PRISMA2020Agent."""

    @pytest.fixture
    def mock_ollama_client(self):
        """Create a mock Ollama client."""
        with patch('bmlibrarian.agents.base.ollama.Client') as mock_client:
            yield mock_client

    @pytest.fixture
    def prisma_agent(self, mock_ollama_client):
        """Create a PRISMA2020Agent instance with mocked Ollama."""
        with patch('bmlibrarian.config.get_config'):
            agent = PRISMA2020Agent(
                model="gpt-oss:20b",
                show_model_info=False
            )
            # Mock the client
            agent.client = Mock()
            return agent

    def test_agent_initialization(self):
        """Test PRISMA2020Agent initialization."""
        with patch('bmlibrarian.agents.base.ollama.Client'):
            with patch('bmlibrarian.config.get_config'):
                agent = PRISMA2020Agent(
                    model="gpt-oss:20b",
                    temperature=0.1,
                    top_p=0.9,
                    max_tokens=4000,
                    show_model_info=False
                )

                assert agent.model == "gpt-oss:20b"
                assert agent.temperature == 0.1
                assert agent.top_p == 0.9
                assert agent.max_tokens == 4000
                assert agent.get_agent_type() == "prisma2020_agent"

    def test_check_suitability_systematic_review(self, prisma_agent):
        """Test suitability check identifies systematic review correctly."""
        # Mock connection test
        prisma_agent.test_connection = Mock(return_value=True)

        # Mock successful LLM response
        prisma_agent.client.generate = Mock(return_value={
            'response': json.dumps(EXPECTED_SUITABILITY_SYSTEMATIC_REVIEW)
        })

        # Perform suitability check
        suitability = prisma_agent.check_suitability(SAMPLE_SYSTEMATIC_REVIEW_DOCUMENT)

        # Verify suitability assessment
        assert suitability is not None
        assert isinstance(suitability, SuitabilityAssessment)
        assert suitability.is_systematic_review is True
        assert suitability.is_meta_analysis is True
        assert suitability.is_suitable is True
        assert suitability.confidence >= 0.9
        assert "systematic review" in suitability.document_type.lower()

    def test_check_suitability_rejects_rct(self, prisma_agent):
        """Test suitability check correctly rejects primary research."""
        # Mock connection test
        prisma_agent.test_connection = Mock(return_value=True)

        # Mock LLM response rejecting RCT
        prisma_agent.client.generate = Mock(return_value={
            'response': json.dumps(EXPECTED_SUITABILITY_RCT)
        })

        # Perform suitability check
        suitability = prisma_agent.check_suitability(SAMPLE_RCT_DOCUMENT)

        # Verify rejection
        assert suitability is not None
        assert suitability.is_suitable is False
        assert suitability.is_systematic_review is False
        assert "RCT" in suitability.document_type or "trial" in suitability.document_type.lower()

    def test_assess_prisma_compliance_success(self, prisma_agent):
        """Test successful PRISMA 2020 compliance assessment."""
        # Mock connection test
        prisma_agent.test_connection = Mock(return_value=True)

        # Mock suitability check and assessment
        prisma_agent.client.generate = Mock(side_effect=[
            {'response': json.dumps(EXPECTED_SUITABILITY_SYSTEMATIC_REVIEW)},
            {'response': json.dumps(EXPECTED_PRISMA_ASSESSMENT)}
        ])

        # Perform assessment
        assessment = prisma_agent.assess_prisma_compliance(
            SAMPLE_SYSTEMATIC_REVIEW_DOCUMENT,
            min_confidence=0.5
        )

        # Verify assessment was successful
        assert assessment is not None
        assert isinstance(assessment, PRISMA2020Assessment)

        # Verify suitability info
        assert assessment.is_systematic_review is True
        assert assessment.is_meta_analysis is True

        # Verify compliance scores
        assert 0 <= assessment.overall_compliance_percentage <= 100
        assert assessment.overall_compliance_score >= 0
        assert assessment.overall_confidence >= 0.7

        # Verify item counts
        assert assessment.total_applicable_items == 27
        assert assessment.fully_reported_items > 0
        assert assessment.not_reported_items >= 0

        # Verify metadata
        assert assessment.document_id == '12345678'
        assert assessment.pmid == '12345678'

    def test_assess_unsuitable_document(self, prisma_agent):
        """Test that unsuitable documents are rejected."""
        # Mock connection test
        prisma_agent.test_connection = Mock(return_value=True)

        # Mock suitability check rejecting document
        prisma_agent.client.generate = Mock(return_value={
            'response': json.dumps(EXPECTED_SUITABILITY_RCT)
        })

        # Should return None for unsuitable document
        assessment = prisma_agent.assess_prisma_compliance(SAMPLE_RCT_DOCUMENT)

        assert assessment is None

    def test_assess_skip_suitability_check(self, prisma_agent):
        """Test assessment with suitability check skipped."""
        # Mock connection test
        prisma_agent.test_connection = Mock(return_value=True)

        # Mock only assessment (no suitability check)
        prisma_agent.client.generate = Mock(return_value={
            'response': json.dumps(EXPECTED_PRISMA_ASSESSMENT)
        })

        # Perform assessment with skip
        assessment = prisma_agent.assess_prisma_compliance(
            SAMPLE_SYSTEMATIC_REVIEW_DOCUMENT,
            skip_suitability_check=True
        )

        # Verify assessment succeeded
        assert assessment is not None
        # Should have default suitability values
        assert assessment.suitability_rationale == "Suitability check skipped by user request"

    def test_assess_missing_text(self, prisma_agent):
        """Test assessment fails gracefully with missing text."""
        document_no_text = {
            'id': '999',
            'title': 'Document with no abstract'
        }

        assessment = prisma_agent.assess_prisma_compliance(document_no_text)

        # Should return None when no text available
        assert assessment is None

    def test_assess_low_confidence_threshold(self, prisma_agent):
        """Test that low confidence assessments are logged."""
        # Mock connection test
        prisma_agent.test_connection = Mock(return_value=True)

        # Mock responses with low confidence
        low_confidence_assessment = EXPECTED_PRISMA_ASSESSMENT.copy()
        low_confidence_assessment['overall_confidence'] = 0.3

        prisma_agent.client.generate = Mock(side_effect=[
            {'response': json.dumps(EXPECTED_SUITABILITY_SYSTEMATIC_REVIEW)},
            {'response': json.dumps(low_confidence_assessment)}
        ])

        # Should still return assessment (but log warning)
        assessment = prisma_agent.assess_prisma_compliance(
            SAMPLE_SYSTEMATIC_REVIEW_DOCUMENT,
            min_confidence=0.5
        )

        assert assessment is not None
        assert assessment.overall_confidence == 0.3
        # Verify stats tracked low confidence
        stats = prisma_agent.get_assessment_stats()
        assert stats['low_confidence_assessments'] == 1

    def test_assess_batch_success(self, prisma_agent):
        """Test successful batch assessment."""
        # Mock connection test
        prisma_agent.test_connection = Mock(return_value=True)

        # Mock multiple assessments
        prisma_agent.client.generate = Mock(side_effect=[
            {'response': json.dumps(EXPECTED_SUITABILITY_SYSTEMATIC_REVIEW)},
            {'response': json.dumps(EXPECTED_PRISMA_ASSESSMENT)},
            {'response': json.dumps(EXPECTED_SUITABILITY_SYSTEMATIC_REVIEW)},
            {'response': json.dumps(EXPECTED_PRISMA_ASSESSMENT)}
        ])

        documents = [SAMPLE_SYSTEMATIC_REVIEW_DOCUMENT, SAMPLE_SYSTEMATIC_REVIEW_DOCUMENT]

        # Test progress callback
        progress_calls = []

        def progress_callback(current, total, title):
            progress_calls.append((current, total, title))

        # Perform batch assessment
        assessments = prisma_agent.assess_batch(
            documents,
            min_confidence=0.4,
            progress_callback=progress_callback
        )

        # Verify results
        assert len(assessments) == 2
        assert all(isinstance(a, PRISMA2020Assessment) for a in assessments)

        # Verify progress callback was called
        assert len(progress_calls) == 2
        assert progress_calls[0][0] == 1
        assert progress_calls[1][0] == 2

    def test_format_assessment_summary(self, prisma_agent):
        """Test formatting assessment as human-readable summary."""
        # Create assessment object
        assessment = PRISMA2020Assessment(
            is_systematic_review=True,
            is_meta_analysis=True,
            suitability_rationale="Systematic review with meta-analysis",
            title_score=2.0,
            title_explanation="Title identifies as systematic review",
            abstract_score=2.0,
            abstract_explanation="Structured abstract present",
            rationale_score=2.0,
            rationale_explanation="Clear rationale provided",
            objectives_score=2.0,
            objectives_explanation="PICO elements specified",
            eligibility_criteria_score=2.0,
            eligibility_criteria_explanation="Inclusion/exclusion criteria clear",
            information_sources_score=2.0,
            information_sources_explanation="Multiple databases searched",
            search_strategy_score=2.0,
            search_strategy_explanation="Full search strategy provided",
            selection_process_score=2.0,
            selection_process_explanation="Duplicate screening described",
            data_collection_score=2.0,
            data_collection_explanation="Standardized extraction forms used",
            data_items_score=2.0,
            data_items_explanation="Variables clearly defined",
            risk_of_bias_score=2.0,
            risk_of_bias_explanation="Cochrane RoB tool used",
            effect_measures_score=2.0,
            effect_measures_explanation="Effect measures defined",
            synthesis_methods_score=2.0,
            synthesis_methods_explanation="Random-effects meta-analysis",
            reporting_bias_assessment_score=2.0,
            reporting_bias_assessment_explanation="Funnel plots used",
            certainty_assessment_score=2.0,
            certainty_assessment_explanation="GRADE assessment performed",
            study_selection_score=2.0,
            study_selection_explanation="PRISMA flow diagram provided",
            study_characteristics_score=2.0,
            study_characteristics_explanation="Study characteristics table",
            risk_of_bias_results_score=2.0,
            risk_of_bias_results_explanation="RoB results presented",
            individual_studies_results_score=2.0,
            individual_studies_results_explanation="Individual study results shown",
            synthesis_results_score=2.0,
            synthesis_results_explanation="Forest plots provided",
            reporting_biases_results_score=2.0,
            reporting_biases_results_explanation="Publication bias assessed",
            certainty_of_evidence_score=2.0,
            certainty_of_evidence_explanation="GRADE ratings reported",
            discussion_score=2.0,
            discussion_explanation="Results interpreted in context",
            limitations_score=2.0,
            limitations_explanation="Limitations discussed",
            conclusions_score=2.0,
            conclusions_explanation="Conclusions aligned with evidence",
            registration_score=2.0,
            registration_explanation="PROSPERO registration",
            support_score=2.0,
            support_explanation="Funding sources stated",
            overall_compliance_score=2.0,
            overall_compliance_percentage=100.0,
            total_applicable_items=27,
            fully_reported_items=27,
            partially_reported_items=0,
            not_reported_items=0,
            overall_confidence=0.9,
            document_id="12345",
            document_title="Test Systematic Review",
            pmid="12345678"
        )

        # Format summary
        summary = prisma_agent.format_assessment_summary(assessment)

        # Verify key elements present
        assert "PRISMA 2020 COMPLIANCE ASSESSMENT" in summary
        assert "Test Systematic Review" in summary
        assert "100.0%" in summary
        assert "Excellent" in summary  # Compliance category
        assert "PROSPERO" in summary
        assert "Item 1: Title" in summary

    def test_export_to_json(self, prisma_agent, tmp_path):
        """Test exporting assessments to JSON file."""
        # Create test assessment
        assessment = PRISMA2020Assessment(
            is_systematic_review=True,
            is_meta_analysis=False,
            suitability_rationale="Systematic review",
            title_score=2.0,
            title_explanation="Clear title",
            abstract_score=1.5,
            abstract_explanation="Partial abstract",
            # ... (all other required fields with minimal values)
            rationale_score=2.0, rationale_explanation="Clear",
            objectives_score=2.0, objectives_explanation="Clear",
            eligibility_criteria_score=2.0, eligibility_criteria_explanation="Clear",
            information_sources_score=2.0, information_sources_explanation="Clear",
            search_strategy_score=1.0, search_strategy_explanation="Partial",
            selection_process_score=2.0, selection_process_explanation="Clear",
            data_collection_score=2.0, data_collection_explanation="Clear",
            data_items_score=2.0, data_items_explanation="Clear",
            risk_of_bias_score=2.0, risk_of_bias_explanation="Clear",
            effect_measures_score=2.0, effect_measures_explanation="Clear",
            synthesis_methods_score=2.0, synthesis_methods_explanation="Clear",
            reporting_bias_assessment_score=1.0, reporting_bias_assessment_explanation="Partial",
            certainty_assessment_score=2.0, certainty_assessment_explanation="Clear",
            study_selection_score=2.0, study_selection_explanation="Clear",
            study_characteristics_score=2.0, study_characteristics_explanation="Clear",
            risk_of_bias_results_score=2.0, risk_of_bias_results_explanation="Clear",
            individual_studies_results_score=1.0, individual_studies_results_explanation="Partial",
            synthesis_results_score=2.0, synthesis_results_explanation="Clear",
            reporting_biases_results_score=2.0, reporting_biases_results_explanation="Clear",
            certainty_of_evidence_score=2.0, certainty_of_evidence_explanation="Clear",
            discussion_score=2.0, discussion_explanation="Clear",
            limitations_score=2.0, limitations_explanation="Clear",
            conclusions_score=2.0, conclusions_explanation="Clear",
            registration_score=2.0, registration_explanation="Clear",
            support_score=2.0, support_explanation="Clear",
            overall_compliance_score=1.9,
            overall_compliance_percentage=95.0,
            total_applicable_items=27,
            fully_reported_items=24,
            partially_reported_items=3,
            not_reported_items=0,
            overall_confidence=0.85,
            document_id="1",
            document_title="Test Review"
        )

        # Export to JSON
        output_file = tmp_path / "assessments.json"
        prisma_agent.export_to_json([assessment], str(output_file))

        # Verify file was created
        assert output_file.exists()

        # Verify JSON structure
        with open(output_file, 'r') as f:
            data = json.load(f)

        assert 'assessments' in data
        assert 'metadata' in data
        assert len(data['assessments']) == 1
        assert data['assessments'][0]['overall_compliance_percentage'] == 95.0

    def test_get_assessment_stats(self, prisma_agent):
        """Test assessment statistics tracking."""
        # Initial stats should be zero
        stats = prisma_agent.get_assessment_stats()
        assert stats['total_assessments'] == 0
        assert stats['success_rate'] == 0.0

        # Mock successful assessment
        prisma_agent.test_connection = Mock(return_value=True)
        prisma_agent.client.generate = Mock(side_effect=[
            {'response': json.dumps(EXPECTED_SUITABILITY_SYSTEMATIC_REVIEW)},
            {'response': json.dumps(EXPECTED_PRISMA_ASSESSMENT)}
        ])

        # Perform assessment
        prisma_agent.assess_prisma_compliance(SAMPLE_SYSTEMATIC_REVIEW_DOCUMENT)

        # Check updated stats
        stats = prisma_agent.get_assessment_stats()
        assert stats['total_assessments'] == 1
        assert stats['successful_assessments'] == 1
        assert stats['success_rate'] == 1.0

    def test_connection_failure(self, prisma_agent):
        """Test assessment handles connection failures gracefully."""
        # Mock connection test failure
        prisma_agent.test_connection = Mock(return_value=False)

        # Should return None
        suitability = prisma_agent.check_suitability(SAMPLE_SYSTEMATIC_REVIEW_DOCUMENT)
        assessment = prisma_agent.assess_prisma_compliance(SAMPLE_SYSTEMATIC_REVIEW_DOCUMENT)

        assert suitability is None
        assert assessment is None

    def test_json_parse_failure_retry(self, prisma_agent):
        """Test that JSON parse failures trigger retry."""
        # Ensure max_retries is set to a real value (not a Mock object)
        prisma_agent.max_retries = 3

        # Mock connection test
        prisma_agent.test_connection = Mock(return_value=True)

        # Mock responses: first invalid JSON, then valid
        prisma_agent.client.generate = Mock(side_effect=[
            {'response': 'This is not valid JSON'},
            {'response': json.dumps(EXPECTED_SUITABILITY_SYSTEMATIC_REVIEW)}
        ])

        # Should succeed on retry
        suitability = prisma_agent.check_suitability(SAMPLE_SYSTEMATIC_REVIEW_DOCUMENT)

        # Verify suitability succeeded on retry
        assert suitability is not None
        assert prisma_agent.client.generate.call_count == 2

    def test_validate_suitability_schema(self, prisma_agent):
        """Test JSON schema validation for suitability responses."""
        # Valid data
        valid_data = {
            'is_systematic_review': True,
            'is_meta_analysis': False,
            'is_suitable': True,
            'confidence': 0.9,
            'rationale': 'Clear systematic review',
            'document_type': 'systematic review'
        }
        assert prisma_agent._validate_suitability_schema(valid_data, 'test') is True

        # Missing fields
        invalid_data_missing = {
            'is_systematic_review': True,
            'is_suitable': True
        }
        assert prisma_agent._validate_suitability_schema(invalid_data_missing, 'test') is False

        # Wrong type
        invalid_data_type = {
            'is_systematic_review': 'yes',  # Should be bool
            'is_meta_analysis': False,
            'is_suitable': True,
            'confidence': 0.9,
            'rationale': 'Text',
            'document_type': 'review'
        }
        assert prisma_agent._validate_suitability_schema(invalid_data_type, 'test') is False

        # Confidence out of range
        invalid_data_range = {
            'is_systematic_review': True,
            'is_meta_analysis': False,
            'is_suitable': True,
            'confidence': 1.5,  # Out of range
            'rationale': 'Text',
            'document_type': 'review'
        }
        assert prisma_agent._validate_suitability_schema(invalid_data_range, 'test') is False

    def test_validate_assessment_data(self, prisma_agent):
        """Test JSON schema validation for assessment responses."""
        # Create valid minimal assessment data
        valid_data = {field: 2.0 for field in [
            'title_score', 'abstract_score', 'rationale_score', 'objectives_score',
            'eligibility_criteria_score', 'information_sources_score', 'search_strategy_score',
            'selection_process_score', 'data_collection_score', 'data_items_score',
            'risk_of_bias_score', 'effect_measures_score', 'synthesis_methods_score',
            'reporting_bias_assessment_score', 'certainty_assessment_score',
            'study_selection_score', 'study_characteristics_score', 'risk_of_bias_results_score',
            'individual_studies_results_score', 'synthesis_results_score',
            'reporting_biases_results_score', 'certainty_of_evidence_score',
            'discussion_score', 'limitations_score', 'conclusions_score',
            'registration_score', 'support_score'
        ]}
        # Add explanations
        for field in list(valid_data.keys()):
            valid_data[field.replace('_score', '_explanation')] = 'Explanation text'
        valid_data['overall_confidence'] = 0.9

        assert prisma_agent._validate_assessment_data(valid_data, 'test') is True

        # Test score out of range
        invalid_data_range = valid_data.copy()
        invalid_data_range['title_score'] = 3.0  # Out of range (max 2.0)
        assert prisma_agent._validate_assessment_data(invalid_data_range, 'test') is False

        # Test wrong type
        invalid_data_type = valid_data.copy()
        invalid_data_type['title_score'] = 'two'  # Should be numeric
        assert prisma_agent._validate_assessment_data(invalid_data_type, 'test') is False

    def test_map_prisma_fields(self, prisma_agent):
        """Test automatic field mapping helper method."""
        # Create test data with ALL PRISMA fields (27 items)
        prisma_items = [
            'title', 'abstract', 'rationale', 'objectives',
            'eligibility_criteria', 'information_sources', 'search_strategy',
            'selection_process', 'data_collection', 'data_items',
            'risk_of_bias', 'effect_measures', 'synthesis_methods',
            'reporting_bias_assessment', 'certainty_assessment',
            'study_selection', 'study_characteristics', 'risk_of_bias_results',
            'individual_studies_results', 'synthesis_results',
            'reporting_biases_results', 'certainty_of_evidence',
            'discussion', 'limitations', 'conclusions',
            'registration', 'support'
        ]

        test_data = {}
        for item in prisma_items:
            test_data[f"{item}_score"] = 2.0
            test_data[f"{item}_explanation"] = f"{item} explanation"

        # Map fields
        mapped = prisma_agent._map_prisma_fields(test_data)

        # Verify mapping for a few items
        assert mapped['title_score'] == 2.0
        assert mapped['title_explanation'] == "title explanation"
        assert mapped['abstract_score'] == 2.0
        assert mapped['abstract_explanation'] == "abstract explanation"
        assert len(mapped) == 27 * 2  # 27 items x 2 fields each

    def test_compliance_category(self):
        """Test compliance category classification."""
        # Excellent
        assessment_excellent = PRISMA2020Assessment(
            is_systematic_review=True, is_meta_analysis=False,
            suitability_rationale="Test",
            **{f"{item}_score": 2.0 for item in ['title', 'abstract', 'rationale', 'objectives',
                'eligibility_criteria', 'information_sources', 'search_strategy',
                'selection_process', 'data_collection', 'data_items', 'risk_of_bias',
                'effect_measures', 'synthesis_methods', 'reporting_bias_assessment',
                'certainty_assessment', 'study_selection', 'study_characteristics',
                'risk_of_bias_results', 'individual_studies_results', 'synthesis_results',
                'reporting_biases_results', 'certainty_of_evidence', 'discussion',
                'limitations', 'conclusions', 'registration', 'support']},
            **{f"{item}_explanation": "Test" for item in ['title', 'abstract', 'rationale',
                'objectives', 'eligibility_criteria', 'information_sources', 'search_strategy',
                'selection_process', 'data_collection', 'data_items', 'risk_of_bias',
                'effect_measures', 'synthesis_methods', 'reporting_bias_assessment',
                'certainty_assessment', 'study_selection', 'study_characteristics',
                'risk_of_bias_results', 'individual_studies_results', 'synthesis_results',
                'reporting_biases_results', 'certainty_of_evidence', 'discussion',
                'limitations', 'conclusions', 'registration', 'support']},
            overall_compliance_score=2.0, overall_compliance_percentage=100.0,
            total_applicable_items=27, fully_reported_items=27,
            partially_reported_items=0, not_reported_items=0,
            overall_confidence=0.9, document_id="1", document_title="Test"
        )
        assert "Excellent" in assessment_excellent.get_compliance_category()
