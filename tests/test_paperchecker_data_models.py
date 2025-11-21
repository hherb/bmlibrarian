"""
Unit tests for PaperChecker data models.

Tests all validation logic, factory methods, and conversion methods for
the data models used in the PaperChecker workflow.
"""

import pytest
from bmlibrarian.paperchecker.data_models import (
    Statement,
    CounterStatement,
    SearchResults,
    ScoredDocument,
    ExtractedCitation,
    CounterReport,
    Verdict,
    PaperCheckResult
)


class TestStatement:
    """Tests for Statement dataclass."""

    def test_valid_statement_creation(self):
        """Test creating a valid statement."""
        stmt = Statement(
            text="Metformin reduces cardiovascular risk in diabetic patients.",
            context="Prior studies have shown benefits. Metformin reduces cardiovascular risk in diabetic patients. This finding is significant.",
            statement_type="finding",
            confidence=0.95,
            statement_order=1
        )
        assert stmt.text == "Metformin reduces cardiovascular risk in diabetic patients."
        assert stmt.statement_type == "finding"
        assert stmt.confidence == 0.95
        assert stmt.statement_order == 1

    def test_invalid_confidence_low(self):
        """Test that confidence < 0 raises error."""
        with pytest.raises(AssertionError, match="Confidence must be 0.0-1.0"):
            Statement(
                text="Test statement",
                context="Test context",
                statement_type="finding",
                confidence=-0.1,
                statement_order=1
            )

    def test_invalid_confidence_high(self):
        """Test that confidence > 1 raises error."""
        with pytest.raises(AssertionError, match="Confidence must be 0.0-1.0"):
            Statement(
                text="Test statement",
                context="Test context",
                statement_type="finding",
                confidence=1.5,
                statement_order=1
            )

    def test_invalid_statement_type(self):
        """Test that invalid statement_type raises error."""
        with pytest.raises(AssertionError, match="Invalid statement type"):
            Statement(
                text="Test statement",
                context="Test context",
                statement_type="invalid_type",
                confidence=0.9,
                statement_order=1
            )

    def test_invalid_order(self):
        """Test that order < 1 raises error."""
        with pytest.raises(AssertionError, match="Order must be >= 1"):
            Statement(
                text="Test statement",
                context="Test context",
                statement_type="finding",
                confidence=0.9,
                statement_order=0
            )

    def test_valid_statement_types(self):
        """Test all valid statement types."""
        for stmt_type in ["hypothesis", "finding", "conclusion"]:
            stmt = Statement(
                text="Test",
                context="Context",
                statement_type=stmt_type,
                confidence=0.9,
                statement_order=1
            )
            assert stmt.statement_type == stmt_type


class TestCounterStatement:
    """Tests for CounterStatement dataclass."""

    def test_valid_counter_statement_creation(self):
        """Test creating a valid counter-statement."""
        stmt = Statement(
            text="Metformin reduces risk.",
            context="Context",
            statement_type="finding",
            confidence=0.9,
            statement_order=1
        )
        counter = CounterStatement(
            original_statement=stmt,
            negated_text="Metformin does not reduce risk or increases risk.",
            hyde_abstracts=["Abstract 1", "Abstract 2"],
            keywords=["metformin", "risk", "ineffective"],
            generation_metadata={"model": "gpt-oss:20b", "temperature": 0.3}
        )
        assert counter.negated_text == "Metformin does not reduce risk or increases risk."
        assert len(counter.hyde_abstracts) == 2
        assert len(counter.keywords) == 3

    def test_empty_negated_text(self):
        """Test that empty negated_text raises error."""
        stmt = Statement(
            text="Test",
            context="Context",
            statement_type="finding",
            confidence=0.9,
            statement_order=1
        )
        with pytest.raises(AssertionError, match="Negated text cannot be empty"):
            CounterStatement(
                original_statement=stmt,
                negated_text="   ",
                hyde_abstracts=["Abstract"],
                keywords=["keyword"],
                generation_metadata={}
            )

    def test_empty_hyde_abstracts(self):
        """Test that empty hyde_abstracts raises error."""
        stmt = Statement(
            text="Test",
            context="Context",
            statement_type="finding",
            confidence=0.9,
            statement_order=1
        )
        with pytest.raises(AssertionError, match="Must have at least one HyDE abstract"):
            CounterStatement(
                original_statement=stmt,
                negated_text="Counter claim",
                hyde_abstracts=[],
                keywords=["keyword"],
                generation_metadata={}
            )

    def test_empty_keywords(self):
        """Test that empty keywords raises error."""
        stmt = Statement(
            text="Test",
            context="Context",
            statement_type="finding",
            confidence=0.9,
            statement_order=1
        )
        with pytest.raises(AssertionError, match="Must have at least one keyword"):
            CounterStatement(
                original_statement=stmt,
                negated_text="Counter claim",
                hyde_abstracts=["Abstract"],
                keywords=[],
                generation_metadata={}
            )


class TestSearchResults:
    """Tests for SearchResults dataclass."""

    def test_factory_method_creates_correct_provenance(self):
        """Test that factory method correctly computes provenance."""
        semantic = [1, 2, 3]
        hyde = [2, 3, 4]
        keyword = [3, 4, 5]

        results = SearchResults.from_strategy_results(
            semantic=semantic,
            hyde=hyde,
            keyword=keyword,
            metadata={"limit": 50}
        )

        assert set(results.deduplicated_docs) == {1, 2, 3, 4, 5}
        assert results.provenance[1] == ["semantic"]
        assert set(results.provenance[2]) == {"semantic", "hyde"}
        assert set(results.provenance[3]) == {"semantic", "hyde", "keyword"}
        assert set(results.provenance[4]) == {"hyde", "keyword"}
        assert results.provenance[5] == ["keyword"]

    def test_provenance_matches_deduplicated_docs(self):
        """Test that provenance keys match deduplicated docs."""
        results = SearchResults.from_strategy_results(
            semantic=[1, 2],
            hyde=[2, 3],
            keyword=[3, 4]
        )
        assert set(results.provenance.keys()) == set(results.deduplicated_docs)

    def test_invalid_provenance_strategy_raises_error(self):
        """Test that invalid strategies raise errors."""
        with pytest.raises(AssertionError, match="Invalid strategy"):
            SearchResults(
                semantic_docs=[1],
                hyde_docs=[2],
                keyword_docs=[3],
                deduplicated_docs=[1, 2, 3],
                provenance={
                    1: ["semantic"],
                    2: ["invalid_strategy"],
                    3: ["keyword"]
                },
                search_metadata={}
            )

    def test_mismatched_provenance_raises_error(self):
        """Test that mismatched provenance and deduplicated docs raise error."""
        with pytest.raises(AssertionError, match="Provenance must include all deduplicated docs"):
            SearchResults(
                semantic_docs=[1],
                hyde_docs=[2],
                keyword_docs=[3],
                deduplicated_docs=[1, 2, 3],
                provenance={
                    1: ["semantic"],
                    2: ["hyde"]
                    # Missing doc 3
                },
                search_metadata={}
            )


class TestScoredDocument:
    """Tests for ScoredDocument dataclass."""

    def test_valid_scored_document_creation(self):
        """Test creating a valid scored document."""
        doc = ScoredDocument(
            doc_id=12345,
            document={"title": "Test Study", "abstract": "Abstract text"},
            score=4,
            explanation="Highly relevant to counter-statement.",
            supports_counter=True,
            found_by=["semantic", "hyde"]
        )
        assert doc.doc_id == 12345
        assert doc.score == 4
        assert doc.supports_counter is True
        assert set(doc.found_by) == {"semantic", "hyde"}

    def test_invalid_score_low(self):
        """Test that score < 1 raises error."""
        with pytest.raises(AssertionError, match="Score must be 1-5"):
            ScoredDocument(
                doc_id=1,
                document={},
                score=0,
                explanation="Test",
                supports_counter=False,
                found_by=["semantic"]
            )

    def test_invalid_score_high(self):
        """Test that score > 5 raises error."""
        with pytest.raises(AssertionError, match="Score must be 1-5"):
            ScoredDocument(
                doc_id=1,
                document={},
                score=6,
                explanation="Test",
                supports_counter=False,
                found_by=["semantic"]
            )

    def test_invalid_doc_id(self):
        """Test that doc_id <= 0 raises error."""
        with pytest.raises(AssertionError, match="Document ID must be positive"):
            ScoredDocument(
                doc_id=0,
                document={},
                score=3,
                explanation="Test",
                supports_counter=False,
                found_by=["semantic"]
            )

    def test_invalid_search_strategy(self):
        """Test that invalid search strategies raise errors."""
        with pytest.raises(AssertionError, match="Invalid search strategy"):
            ScoredDocument(
                doc_id=1,
                document={},
                score=3,
                explanation="Test",
                supports_counter=False,
                found_by=["invalid_strategy"]
            )

    def test_all_valid_scores(self):
        """Test all valid scores 1-5."""
        for score in range(1, 6):
            doc = ScoredDocument(
                doc_id=1,
                document={},
                score=score,
                explanation="Test",
                supports_counter=score >= 3,
                found_by=["semantic"]
            )
            assert doc.score == score


class TestExtractedCitation:
    """Tests for ExtractedCitation dataclass."""

    def test_valid_citation_creation(self):
        """Test creating a valid citation."""
        citation = ExtractedCitation(
            doc_id=12345,
            passage="This study found that metformin was ineffective.",
            relevance_score=4,
            full_citation="Smith J, Johnson A. Metformin efficacy study. JAMA. 2023;123(4):567-89.",
            metadata={"pmid": 98765, "doi": "10.1001/test.2023.123", "year": 2023},
            citation_order=1
        )
        assert citation.doc_id == 12345
        assert citation.relevance_score == 4
        assert citation.citation_order == 1

    def test_empty_passage_raises_error(self):
        """Test that empty passage raises error."""
        with pytest.raises(AssertionError, match="Passage cannot be empty"):
            ExtractedCitation(
                doc_id=1,
                passage="   ",
                relevance_score=3,
                full_citation="Test",
                metadata={},
                citation_order=1
            )

    def test_invalid_relevance_score(self):
        """Test that invalid scores raise errors."""
        with pytest.raises(AssertionError, match="Score must be 1-5"):
            ExtractedCitation(
                doc_id=1,
                passage="Test passage",
                relevance_score=6,
                full_citation="Test",
                metadata={},
                citation_order=1
            )

    def test_invalid_citation_order(self):
        """Test that order < 1 raises error."""
        with pytest.raises(AssertionError, match="Order must be >= 1"):
            ExtractedCitation(
                doc_id=1,
                passage="Test passage",
                relevance_score=3,
                full_citation="Test",
                metadata={},
                citation_order=0
            )

    def test_to_markdown_reference_with_pmid_and_doi(self):
        """Test markdown reference formatting with PMID and DOI."""
        citation = ExtractedCitation(
            doc_id=1,
            passage="Test",
            relevance_score=3,
            full_citation="Smith J. Test. JAMA. 2023;1:1.",
            metadata={"pmid": 12345, "doi": "10.1001/test"},
            citation_order=1
        )
        ref = citation.to_markdown_reference()
        assert "1. Smith J. Test. JAMA. 2023;1:1." in ref
        assert "[PMID: 12345]" in ref
        assert "[DOI: 10.1001/test]" in ref

    def test_to_markdown_reference_without_pmid_doi(self):
        """Test markdown reference formatting without PMID/DOI."""
        citation = ExtractedCitation(
            doc_id=1,
            passage="Test",
            relevance_score=3,
            full_citation="Smith J. Test. JAMA. 2023;1:1.",
            metadata={},
            citation_order=1
        )
        ref = citation.to_markdown_reference()
        assert ref == "1. Smith J. Test. JAMA. 2023;1:1."


class TestCounterReport:
    """Tests for CounterReport dataclass."""

    def test_valid_counter_report_creation(self):
        """Test creating a valid counter-report."""
        citations = [
            ExtractedCitation(
                doc_id=1,
                passage="Passage 1",
                relevance_score=4,
                full_citation="Citation 1",
                metadata={},
                citation_order=1
            ),
            ExtractedCitation(
                doc_id=2,
                passage="Passage 2",
                relevance_score=5,
                full_citation="Citation 2",
                metadata={},
                citation_order=2
            )
        ]
        report = CounterReport(
            summary="Counter-evidence summary text.",
            num_citations=2,
            citations=citations,
            search_stats={"documents_found": 50, "documents_scored": 30},
            generation_metadata={"model": "gpt-oss:20b"}
        )
        assert report.num_citations == 2
        assert len(report.citations) == 2

    def test_empty_summary_raises_error(self):
        """Test that empty summary raises error."""
        with pytest.raises(AssertionError, match="Summary cannot be empty"):
            CounterReport(
                summary="   ",
                num_citations=0,
                citations=[],
                search_stats={},
                generation_metadata={}
            )

    def test_mismatched_num_citations_raises_error(self):
        """Test that mismatched num_citations raises error."""
        citation = ExtractedCitation(
            doc_id=1,
            passage="Test",
            relevance_score=3,
            full_citation="Test",
            metadata={},
            citation_order=1
        )
        with pytest.raises(AssertionError, match="num_citations.*must match citations list length"):
            CounterReport(
                summary="Test summary",
                num_citations=5,  # Wrong count
                citations=[citation],
                search_stats={},
                generation_metadata={}
            )

    def test_to_markdown_generates_valid_output(self):
        """Test that to_markdown generates valid markdown."""
        citation = ExtractedCitation(
            doc_id=1,
            passage="Test passage",
            relevance_score=4,
            full_citation="Smith J. Test. 2023.",
            metadata={"pmid": 12345},
            citation_order=1
        )
        report = CounterReport(
            summary="Counter-evidence summary.",
            num_citations=1,
            citations=[citation],
            search_stats={"documents_found": 50, "documents_scored": 30},
            generation_metadata={}
        )
        md = report.to_markdown()
        assert "## Counter-Evidence Summary" in md
        assert "Counter-evidence summary." in md
        assert "## References" in md
        assert "1. Smith J. Test. 2023." in md
        assert "[PMID: 12345]" in md
        assert "50 found" in md
        assert "30 scored" in md
        assert "1 cited" in md


class TestVerdict:
    """Tests for Verdict dataclass."""

    def test_valid_verdict_creation(self):
        """Test creating a valid verdict."""
        citation = ExtractedCitation(
            doc_id=1,
            passage="Test",
            relevance_score=3,
            full_citation="Test",
            metadata={},
            citation_order=1
        )
        report = CounterReport(
            summary="Summary",
            num_citations=1,
            citations=[citation],
            search_stats={},
            generation_metadata={}
        )
        verdict = Verdict(
            verdict="contradicts",
            rationale="The counter-evidence strongly contradicts the original claim.",
            confidence="high",
            counter_report=report,
            analysis_metadata={"model": "gpt-oss:20b"}
        )
        assert verdict.verdict == "contradicts"
        assert verdict.confidence == "high"

    def test_invalid_verdict_value_raises_error(self):
        """Test that invalid verdict values raise errors."""
        citation = ExtractedCitation(
            doc_id=1,
            passage="Test",
            relevance_score=3,
            full_citation="Test",
            metadata={},
            citation_order=1
        )
        report = CounterReport(
            summary="Summary",
            num_citations=1,
            citations=[citation],
            search_stats={},
            generation_metadata={}
        )
        with pytest.raises(AssertionError, match="Invalid verdict value"):
            Verdict(
                verdict="invalid",
                rationale="Test",
                confidence="high",
                counter_report=report,
                analysis_metadata={}
            )

    def test_invalid_confidence_value_raises_error(self):
        """Test that invalid confidence values raise errors."""
        citation = ExtractedCitation(
            doc_id=1,
            passage="Test",
            relevance_score=3,
            full_citation="Test",
            metadata={},
            citation_order=1
        )
        report = CounterReport(
            summary="Summary",
            num_citations=1,
            citations=[citation],
            search_stats={},
            generation_metadata={}
        )
        with pytest.raises(AssertionError, match="Invalid confidence value"):
            Verdict(
                verdict="supports",
                rationale="Test",
                confidence="invalid",
                counter_report=report,
                analysis_metadata={}
            )

    def test_empty_rationale_raises_error(self):
        """Test that empty rationale raises error."""
        citation = ExtractedCitation(
            doc_id=1,
            passage="Test",
            relevance_score=3,
            full_citation="Test",
            metadata={},
            citation_order=1
        )
        report = CounterReport(
            summary="Summary",
            num_citations=1,
            citations=[citation],
            search_stats={},
            generation_metadata={}
        )
        with pytest.raises(AssertionError, match="Rationale cannot be empty"):
            Verdict(
                verdict="supports",
                rationale="   ",
                confidence="high",
                counter_report=report,
                analysis_metadata={}
            )

    def test_all_valid_verdict_values(self):
        """Test all valid verdict values."""
        citation = ExtractedCitation(
            doc_id=1,
            passage="Test",
            relevance_score=3,
            full_citation="Test",
            metadata={},
            citation_order=1
        )
        report = CounterReport(
            summary="Summary",
            num_citations=1,
            citations=[citation],
            search_stats={},
            generation_metadata={}
        )
        for verdict_value in ["supports", "contradicts", "undecided"]:
            verdict = Verdict(
                verdict=verdict_value,
                rationale="Test rationale",
                confidence="medium",
                counter_report=report,
                analysis_metadata={}
            )
            assert verdict.verdict == verdict_value

    def test_to_dict_serialization(self):
        """Test to_dict method for JSON serialization."""
        citation = ExtractedCitation(
            doc_id=1,
            passage="Test",
            relevance_score=3,
            full_citation="Test",
            metadata={},
            citation_order=1
        )
        report = CounterReport(
            summary="Summary",
            num_citations=1,
            citations=[citation],
            search_stats={"documents_found": 50},
            generation_metadata={}
        )
        verdict = Verdict(
            verdict="contradicts",
            rationale="Strong contradiction",
            confidence="high",
            counter_report=report,
            analysis_metadata={}
        )
        d = verdict.to_dict()
        assert d["verdict"] == "contradicts"
        assert d["rationale"] == "Strong contradiction"
        assert d["confidence"] == "high"
        assert d["num_citations"] == 1
        assert d["search_stats"]["documents_found"] == 50


class TestPaperCheckResult:
    """Tests for PaperCheckResult dataclass."""

    def create_minimal_result(self, num_statements: int = 1) -> PaperCheckResult:
        """Helper to create a minimal valid PaperCheckResult."""
        statements = []
        counter_statements = []
        search_results = []
        scored_documents = []
        counter_reports = []
        verdicts = []

        for i in range(num_statements):
            stmt = Statement(
                text=f"Statement {i+1}",
                context="Context",
                statement_type="finding",
                confidence=0.9,
                statement_order=i+1
            )
            statements.append(stmt)

            counter = CounterStatement(
                original_statement=stmt,
                negated_text=f"Counter statement {i+1}",
                hyde_abstracts=["Abstract"],
                keywords=["keyword"],
                generation_metadata={}
            )
            counter_statements.append(counter)

            search = SearchResults.from_strategy_results(
                semantic=[1],
                hyde=[2],
                keyword=[3]
            )
            search_results.append(search)

            scored = [
                ScoredDocument(
                    doc_id=1,
                    document={},
                    score=4,
                    explanation="Test",
                    supports_counter=True,
                    found_by=["semantic"]
                )
            ]
            scored_documents.append(scored)

            citation = ExtractedCitation(
                doc_id=1,
                passage="Test passage",
                relevance_score=4,
                full_citation="Test citation",
                metadata={},
                citation_order=1
            )
            report = CounterReport(
                summary="Summary",
                num_citations=1,
                citations=[citation],
                search_stats={},
                generation_metadata={}
            )
            counter_reports.append(report)

            verdict = Verdict(
                verdict="contradicts",
                rationale="Test rationale",
                confidence="high",
                counter_report=report,
                analysis_metadata={}
            )
            verdicts.append(verdict)

        return PaperCheckResult(
            original_abstract="Test abstract",
            source_metadata={"pmid": 12345},
            statements=statements,
            counter_statements=counter_statements,
            search_results=search_results,
            scored_documents=scored_documents,
            counter_reports=counter_reports,
            verdicts=verdicts,
            overall_assessment="Overall assessment",
            processing_metadata={}
        )

    def test_valid_result_creation(self):
        """Test creating a valid paper check result."""
        result = self.create_minimal_result()
        assert len(result.statements) == 1
        assert len(result.verdicts) == 1
        assert result.overall_assessment == "Overall assessment"

    def test_mismatched_counter_statements_raises_error(self):
        """Test that mismatched counter_statements raises error."""
        result = self.create_minimal_result()
        result.counter_statements = []  # Mismatch
        with pytest.raises(AssertionError, match="Mismatched counter_statements"):
            result.__post_init__()

    def test_mismatched_search_results_raises_error(self):
        """Test that mismatched search_results raises error."""
        result = self.create_minimal_result()
        result.search_results = []  # Mismatch
        with pytest.raises(AssertionError, match="Mismatched search_results"):
            result.__post_init__()

    def test_mismatched_scored_documents_raises_error(self):
        """Test that mismatched scored_documents raises error."""
        result = self.create_minimal_result()
        result.scored_documents = []  # Mismatch
        with pytest.raises(AssertionError, match="Mismatched scored_documents"):
            result.__post_init__()

    def test_mismatched_counter_reports_raises_error(self):
        """Test that mismatched counter_reports raises error."""
        result = self.create_minimal_result()
        result.counter_reports = []  # Mismatch
        with pytest.raises(AssertionError, match="Mismatched counter_reports"):
            result.__post_init__()

    def test_mismatched_verdicts_raises_error(self):
        """Test that mismatched verdicts raises error."""
        result = self.create_minimal_result()
        result.verdicts = []  # Mismatch
        with pytest.raises(AssertionError, match="Mismatched verdicts"):
            result.__post_init__()

    def test_multiple_statements_validation(self):
        """Test validation with multiple statements."""
        result = self.create_minimal_result(num_statements=3)
        assert len(result.statements) == 3
        assert len(result.counter_statements) == 3
        assert len(result.search_results) == 3
        assert len(result.scored_documents) == 3
        assert len(result.counter_reports) == 3
        assert len(result.verdicts) == 3

    def test_to_json_dict_structure(self):
        """Test to_json_dict generates valid structure."""
        result = self.create_minimal_result()
        d = result.to_json_dict()

        assert "original_abstract" in d
        assert "source_metadata" in d
        assert "statements" in d
        assert "results" in d
        assert "overall_assessment" in d
        assert "metadata" in d

        assert len(d["statements"]) == 1
        assert len(d["results"]) == 1

        stmt = d["statements"][0]
        assert "text" in stmt
        assert "type" in stmt
        assert "confidence" in stmt

        res = d["results"][0]
        assert "statement" in res
        assert "counter_statement" in res
        assert "search_stats" in res
        assert "scoring_stats" in res
        assert "counter_report" in res
        assert "verdict" in res

    def test_to_markdown_report_format(self):
        """Test to_markdown_report generates readable output."""
        result = self.create_minimal_result()
        md = result.to_markdown_report()

        assert "# PaperChecker Report" in md
        assert "## Original Abstract" in md
        assert "Test abstract" in md
        assert "**PMID:** 12345" in md
        assert "## Analysis Results" in md
        assert "### Statement 1" in md
        assert "**Claim:** Statement 1" in md
        assert "**Verdict:** CONTRADICTS" in md
        assert "**Confidence:** high" in md
        assert "**Rationale:** Test rationale" in md
        assert "## Overall Assessment" in md
        assert "Overall assessment" in md
