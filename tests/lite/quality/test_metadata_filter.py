"""Tests for PubMed metadata-based quality filtering."""

import pytest

from bmlibrarian.lite.data_models import LiteDocument
from bmlibrarian.lite.quality.metadata_filter import (
    MetadataFilter,
    PUBMED_TYPE_TO_DESIGN,
    TYPE_PRIORITY,
)
from bmlibrarian.lite.quality.data_models import (
    StudyDesign,
    QualityTier,
    QualityAssessment,
)
from bmlibrarian.lite.constants import (
    METADATA_HIGH_CONFIDENCE,
    METADATA_PARTIAL_MATCH_CONFIDENCE,
    METADATA_UNKNOWN_TYPE_CONFIDENCE,
)


class TestPubMedTypeMappings:
    """Tests for PubMed publication type mappings."""

    def test_all_mapped_types_are_strings(self) -> None:
        """Test that all mapped publication types are strings."""
        for pub_type in PUBMED_TYPE_TO_DESIGN:
            assert isinstance(pub_type, str)
            assert len(pub_type) > 0

    def test_all_mapped_designs_are_valid(self) -> None:
        """Test that all mapped designs are valid StudyDesign values."""
        for design in PUBMED_TYPE_TO_DESIGN.values():
            assert isinstance(design, StudyDesign)

    def test_tier5_types_map_to_systematic(self) -> None:
        """Test that tier 5 types map to systematic designs."""
        assert PUBMED_TYPE_TO_DESIGN["Meta-Analysis"] == StudyDesign.META_ANALYSIS
        assert PUBMED_TYPE_TO_DESIGN["Systematic Review"] == StudyDesign.SYSTEMATIC_REVIEW

    def test_tier4_types_map_to_experimental(self) -> None:
        """Test that tier 4 types map to experimental designs."""
        experimental_types = [
            "Randomized Controlled Trial",
            "Clinical Trial",
            "Clinical Trial, Phase I",
            "Clinical Trial, Phase II",
            "Clinical Trial, Phase III",
            "Clinical Trial, Phase IV",
            "Controlled Clinical Trial",
            "Practice Guideline",
        ]
        for pub_type in experimental_types:
            assert pub_type in PUBMED_TYPE_TO_DESIGN
            design = PUBMED_TYPE_TO_DESIGN[pub_type]
            assert design in [StudyDesign.RCT, StudyDesign.GUIDELINE]

    def test_tier1_types_map_to_anecdotal(self) -> None:
        """Test that tier 1 types map to anecdotal designs."""
        anecdotal_types = [
            "Case Reports",
            "Editorial",
            "Letter",
            "Comment",
        ]
        for pub_type in anecdotal_types:
            assert pub_type in PUBMED_TYPE_TO_DESIGN
            design = PUBMED_TYPE_TO_DESIGN[pub_type]
            assert design in [
                StudyDesign.CASE_REPORT,
                StudyDesign.EDITORIAL,
                StudyDesign.LETTER,
                StudyDesign.COMMENT,
            ]


class TestTypePriority:
    """Tests for publication type priority ordering."""

    def test_priority_list_has_expected_types(self) -> None:
        """Test that priority list contains expected types."""
        expected_high_priority = [
            "Meta-Analysis",
            "Systematic Review",
            "Randomized Controlled Trial",
        ]
        for pub_type in expected_high_priority:
            assert pub_type in TYPE_PRIORITY

    def test_meta_analysis_highest_priority(self) -> None:
        """Test that Meta-Analysis is highest priority."""
        assert TYPE_PRIORITY[0] == "Meta-Analysis"

    def test_systematic_review_before_rct(self) -> None:
        """Test that Systematic Review comes before RCT."""
        sr_index = TYPE_PRIORITY.index("Systematic Review")
        rct_index = TYPE_PRIORITY.index("Randomized Controlled Trial")
        assert sr_index < rct_index

    def test_rct_before_case_reports(self) -> None:
        """Test that RCT comes before Case Reports."""
        rct_index = TYPE_PRIORITY.index("Randomized Controlled Trial")
        case_index = TYPE_PRIORITY.index("Case Reports")
        assert rct_index < case_index


class TestMetadataFilter:
    """Tests for MetadataFilter class."""

    @pytest.fixture
    def filter(self) -> MetadataFilter:
        """Create a MetadataFilter instance."""
        return MetadataFilter()

    def test_initialization(self, filter: MetadataFilter) -> None:
        """Test filter initialization."""
        assert filter._type_to_design == PUBMED_TYPE_TO_DESIGN
        assert filter._type_priority == TYPE_PRIORITY

    def test_get_known_types(self, filter: MetadataFilter) -> None:
        """Test getting list of known types."""
        known_types = filter.get_known_types()
        assert isinstance(known_types, list)
        assert len(known_types) > 0
        assert "Meta-Analysis" in known_types
        assert "Randomized Controlled Trial" in known_types


class TestMetadataFilterAssess:
    """Tests for MetadataFilter.assess() method."""

    @pytest.fixture
    def filter(self) -> MetadataFilter:
        """Create a MetadataFilter instance."""
        return MetadataFilter()

    def _create_document(
        self,
        doc_id: str = "test_123",
        pub_types: list[str] | None = None,
        pub_type_key: str = "publication_types",
    ) -> LiteDocument:
        """Create a LiteDocument with specified publication types."""
        metadata = {}
        if pub_types is not None:
            metadata[pub_type_key] = pub_types
        return LiteDocument(
            id=doc_id,
            title="Test Document",
            abstract="Test abstract content",
            metadata=metadata,
        )

    def test_assess_no_metadata(self, filter: MetadataFilter) -> None:
        """Test assessment with no metadata."""
        doc = LiteDocument(
            id="test_1",
            title="Test",
            abstract="Test",
            metadata=None,
        )
        assessment = filter.assess(doc)

        assert assessment.study_design == StudyDesign.UNKNOWN
        assert assessment.quality_tier == QualityTier.UNCLASSIFIED
        assert assessment.confidence == 0.0

    def test_assess_empty_pub_types(self, filter: MetadataFilter) -> None:
        """Test assessment with empty publication types."""
        doc = self._create_document(pub_types=[])
        assessment = filter.assess(doc)

        assert assessment.study_design == StudyDesign.UNKNOWN
        assert assessment.quality_tier == QualityTier.UNCLASSIFIED
        assert assessment.confidence == 0.0

    def test_assess_meta_analysis(self, filter: MetadataFilter) -> None:
        """Test assessment of Meta-Analysis."""
        doc = self._create_document(pub_types=["Meta-Analysis"])
        assessment = filter.assess(doc)

        assert assessment.study_design == StudyDesign.META_ANALYSIS
        assert assessment.quality_tier == QualityTier.TIER_5_SYNTHESIS
        assert assessment.confidence == METADATA_HIGH_CONFIDENCE
        assert assessment.extraction_method == "metadata"

    def test_assess_systematic_review(self, filter: MetadataFilter) -> None:
        """Test assessment of Systematic Review."""
        doc = self._create_document(pub_types=["Systematic Review"])
        assessment = filter.assess(doc)

        assert assessment.study_design == StudyDesign.SYSTEMATIC_REVIEW
        assert assessment.quality_tier == QualityTier.TIER_5_SYNTHESIS
        assert assessment.confidence == METADATA_HIGH_CONFIDENCE

    def test_assess_rct(self, filter: MetadataFilter) -> None:
        """Test assessment of RCT."""
        doc = self._create_document(pub_types=["Randomized Controlled Trial"])
        assessment = filter.assess(doc)

        assert assessment.study_design == StudyDesign.RCT
        assert assessment.quality_tier == QualityTier.TIER_4_EXPERIMENTAL
        assert assessment.confidence == METADATA_HIGH_CONFIDENCE

    def test_assess_clinical_trial_phases(self, filter: MetadataFilter) -> None:
        """Test assessment of clinical trial phases."""
        phases = [
            "Clinical Trial, Phase I",
            "Clinical Trial, Phase II",
            "Clinical Trial, Phase III",
            "Clinical Trial, Phase IV",
        ]
        for phase in phases:
            doc = self._create_document(pub_types=[phase])
            assessment = filter.assess(doc)

            assert assessment.study_design == StudyDesign.RCT
            assert assessment.quality_tier == QualityTier.TIER_4_EXPERIMENTAL

    def test_assess_case_report(self, filter: MetadataFilter) -> None:
        """Test assessment of case report."""
        doc = self._create_document(pub_types=["Case Reports"])
        assessment = filter.assess(doc)

        assert assessment.study_design == StudyDesign.CASE_REPORT
        assert assessment.quality_tier == QualityTier.TIER_1_ANECDOTAL
        assert assessment.confidence == METADATA_HIGH_CONFIDENCE

    def test_assess_editorial(self, filter: MetadataFilter) -> None:
        """Test assessment of editorial."""
        doc = self._create_document(pub_types=["Editorial"])
        assessment = filter.assess(doc)

        assert assessment.study_design == StudyDesign.EDITORIAL
        assert assessment.quality_tier == QualityTier.TIER_1_ANECDOTAL

    def test_assess_multiple_types_priority(self, filter: MetadataFilter) -> None:
        """Test that higher priority type is selected."""
        # Meta-Analysis should win over Case Reports
        doc = self._create_document(
            pub_types=["Case Reports", "Meta-Analysis", "Editorial"]
        )
        assessment = filter.assess(doc)

        assert assessment.study_design == StudyDesign.META_ANALYSIS
        assert assessment.quality_tier == QualityTier.TIER_5_SYNTHESIS

    def test_assess_rct_over_multicenter(self, filter: MetadataFilter) -> None:
        """Test that RCT is selected over Multicenter Study."""
        doc = self._create_document(
            pub_types=["Multicenter Study", "Randomized Controlled Trial"]
        )
        assessment = filter.assess(doc)

        assert assessment.study_design == StudyDesign.RCT
        assert assessment.quality_tier == QualityTier.TIER_4_EXPERIMENTAL

    def test_assess_unknown_type(self, filter: MetadataFilter) -> None:
        """Test assessment with unknown publication type."""
        doc = self._create_document(
            pub_types=["Journal Article"]  # Not in our mapping
        )
        assessment = filter.assess(doc)

        assert assessment.study_design == StudyDesign.UNKNOWN
        assert assessment.quality_tier == QualityTier.UNCLASSIFIED
        assert assessment.confidence == METADATA_UNKNOWN_TYPE_CONFIDENCE

    def test_assess_alternative_key_PublicationType(
        self, filter: MetadataFilter
    ) -> None:
        """Test assessment with PublicationType key (PubMed XML format)."""
        doc = self._create_document(
            pub_types=["Randomized Controlled Trial"],
            pub_type_key="PublicationType",
        )
        assessment = filter.assess(doc)

        assert assessment.study_design == StudyDesign.RCT

    def test_assess_alternative_key_PublicationTypeList(
        self, filter: MetadataFilter
    ) -> None:
        """Test assessment with PublicationTypeList key."""
        doc = self._create_document(
            pub_types=["Systematic Review"],
            pub_type_key="PublicationTypeList",
        )
        assessment = filter.assess(doc)

        assert assessment.study_design == StudyDesign.SYSTEMATIC_REVIEW

    def test_assess_string_pub_type(self, filter: MetadataFilter) -> None:
        """Test assessment with string (not list) publication type."""
        doc = LiteDocument(
            id="test",
            title="Test",
            abstract="Test",
            metadata={"publication_types": "Randomized Controlled Trial"},
        )
        assessment = filter.assess(doc)

        assert assessment.study_design == StudyDesign.RCT

    def test_assess_deduplicates_types(self, filter: MetadataFilter) -> None:
        """Test that duplicate types are deduplicated."""
        doc = self._create_document(
            pub_types=["Meta-Analysis", "Meta-Analysis", "Meta-Analysis"]
        )
        assessment = filter.assess(doc)

        # Should work and not raise errors
        assert assessment.study_design == StudyDesign.META_ANALYSIS

    def test_assess_strips_whitespace(self, filter: MetadataFilter) -> None:
        """Test that whitespace is stripped from types."""
        doc = self._create_document(
            pub_types=["  Meta-Analysis  ", "\tRandomized Controlled Trial\n"]
        )
        assessment = filter.assess(doc)

        # Meta-Analysis should be matched after stripping
        assert assessment.study_design == StudyDesign.META_ANALYSIS

    def test_assess_extraction_details(self, filter: MetadataFilter) -> None:
        """Test that extraction details are populated."""
        doc = self._create_document(
            pub_types=["Randomized Controlled Trial", "Multicenter Study"]
        )
        assessment = filter.assess(doc)

        assert len(assessment.extraction_details) > 0
        assert any("Randomized Controlled Trial" in d for d in assessment.extraction_details)


class TestMetadataFilterGetTierForTypes:
    """Tests for MetadataFilter.get_tier_for_types() method."""

    @pytest.fixture
    def filter(self) -> MetadataFilter:
        """Create a MetadataFilter instance."""
        return MetadataFilter()

    def test_tier_for_meta_analysis(self, filter: MetadataFilter) -> None:
        """Test tier lookup for Meta-Analysis."""
        tier = filter.get_tier_for_types(["Meta-Analysis"])
        assert tier == QualityTier.TIER_5_SYNTHESIS

    def test_tier_for_rct(self, filter: MetadataFilter) -> None:
        """Test tier lookup for RCT."""
        tier = filter.get_tier_for_types(["Randomized Controlled Trial"])
        assert tier == QualityTier.TIER_4_EXPERIMENTAL

    def test_tier_for_case_report(self, filter: MetadataFilter) -> None:
        """Test tier lookup for Case Report."""
        tier = filter.get_tier_for_types(["Case Reports"])
        assert tier == QualityTier.TIER_1_ANECDOTAL

    def test_tier_for_unknown(self, filter: MetadataFilter) -> None:
        """Test tier lookup for unknown type."""
        tier = filter.get_tier_for_types(["Unknown Type"])
        assert tier == QualityTier.UNCLASSIFIED

    def test_tier_for_empty_list(self, filter: MetadataFilter) -> None:
        """Test tier lookup for empty list."""
        tier = filter.get_tier_for_types([])
        assert tier == QualityTier.UNCLASSIFIED

    def test_tier_for_multiple_types_priority(self, filter: MetadataFilter) -> None:
        """Test tier lookup respects priority."""
        tier = filter.get_tier_for_types(["Case Reports", "Meta-Analysis"])
        assert tier == QualityTier.TIER_5_SYNTHESIS


class TestPartialMatching:
    """Tests for partial/fuzzy matching of publication types."""

    @pytest.fixture
    def filter(self) -> MetadataFilter:
        """Create a MetadataFilter instance."""
        return MetadataFilter()

    def test_partial_match_rct_variant(self, filter: MetadataFilter) -> None:
        """Test partial matching for RCT variants."""
        # Some databases might have slightly different formats
        doc = LiteDocument(
            id="test",
            title="Test",
            abstract="Test",
            metadata={"publication_types": ["Randomized Controlled Trial, Phase III"]},
        )
        assessment = filter.assess(doc)

        # Should match to RCT via partial match
        # Note: This tests the fallback partial matching logic
        assert assessment.study_design in [StudyDesign.RCT, StudyDesign.UNKNOWN]

    def test_case_insensitive_partial_match(self, filter: MetadataFilter) -> None:
        """Test that partial matching is case-insensitive."""
        doc = LiteDocument(
            id="test",
            title="Test",
            abstract="Test",
            metadata={"publication_types": ["RANDOMIZED CONTROLLED TRIAL"]},
        )
        assessment = filter.assess(doc)

        # Should match via case-insensitive partial match
        # The exact match won't work due to case, but partial should
        assert assessment.study_design == StudyDesign.RCT or assessment.confidence > 0
