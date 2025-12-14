"""Tests for BMLibrarian Lite agents."""

import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

import pytest

from bmlibrarian.lite.config import LiteConfig, StorageConfig
from bmlibrarian.lite.data_models import (
    LiteDocument,
    DocumentSource,
    ScoredDocument,
    Citation,
)
from bmlibrarian.lite.agents import (
    LiteBaseAgent,
    LiteScoringAgent,
    LiteCitationAgent,
    LiteReportingAgent,
)


@pytest.fixture
def mock_config() -> LiteConfig:
    """Create a test configuration."""
    config = LiteConfig()
    config.llm.provider = "anthropic"
    config.llm.model = "claude-3-haiku-20240307"
    return config


@pytest.fixture
def sample_document() -> LiteDocument:
    """Create a sample document for testing."""
    return LiteDocument(
        id="pmid-12345678",
        title="Effects of Exercise on Cardiovascular Health",
        abstract=(
            "This randomized controlled trial examined the effects of moderate exercise "
            "on cardiovascular outcomes in 500 adults aged 45-65. Participants who "
            "exercised 150 minutes per week showed a 25% reduction in cardiovascular "
            "events compared to sedentary controls (p<0.001). Blood pressure decreased "
            "by an average of 8 mmHg systolic. These findings support current guidelines "
            "recommending regular physical activity for cardiovascular health."
        ),
        authors=["Smith J", "Jones A", "Brown B"],
        year=2023,
        journal="Journal of Cardiology",
        doi="10.1234/jcard.2023.12345",
        pmid="12345678",
        source=DocumentSource.PUBMED,
    )


@pytest.fixture
def scored_document(sample_document: LiteDocument) -> ScoredDocument:
    """Create a scored document for testing."""
    return ScoredDocument(
        document=sample_document,
        score=4,
        explanation="Highly relevant - directly addresses cardiovascular effects of exercise",
    )


class TestLiteBaseAgent:
    """Tests for LiteBaseAgent class."""

    def test_base_agent_initialization(self, mock_config: LiteConfig) -> None:
        """Test that base agent initializes correctly."""
        agent = LiteBaseAgent(config=mock_config)

        assert agent.config == mock_config
        assert agent._llm_client is None  # Lazy initialization

    def test_get_model_string(self, mock_config: LiteConfig) -> None:
        """Test model string generation."""
        agent = LiteBaseAgent(config=mock_config)

        model_string = agent._get_model()
        assert model_string == "anthropic:claude-3-haiku-20240307"

    def test_create_messages(self, mock_config: LiteConfig) -> None:
        """Test message creation helpers."""
        agent = LiteBaseAgent(config=mock_config)

        system_msg = agent._create_system_message("System prompt")
        assert system_msg.role == "system"
        assert system_msg.content == "System prompt"

        user_msg = agent._create_user_message("User message")
        assert user_msg.role == "user"
        assert user_msg.content == "User message"

        assistant_msg = agent._create_assistant_message("Assistant response")
        assert assistant_msg.role == "assistant"
        assert assistant_msg.content == "Assistant response"


class TestLiteScoringAgent:
    """Tests for LiteScoringAgent class."""

    def test_scoring_agent_initialization(self, mock_config: LiteConfig) -> None:
        """Test that scoring agent initializes correctly."""
        agent = LiteScoringAgent(config=mock_config)

        assert agent.config == mock_config

    def test_parse_score_response_valid_json(self, mock_config: LiteConfig) -> None:
        """Test parsing valid JSON score response."""
        agent = LiteScoringAgent(config=mock_config)

        response = '{"score": 4, "explanation": "Highly relevant"}'
        result = agent._parse_score_response(response)

        assert result["score"] == 4
        assert result["explanation"] == "Highly relevant"

    def test_parse_score_response_json_with_markdown(self, mock_config: LiteConfig) -> None:
        """Test parsing JSON wrapped in markdown code blocks."""
        agent = LiteScoringAgent(config=mock_config)

        response = '''Here is my evaluation:
```json
{"score": 5, "explanation": "Directly answers the question"}
```'''
        result = agent._parse_score_response(response)

        assert result["score"] == 5

    def test_parse_score_response_clamps_score(self, mock_config: LiteConfig) -> None:
        """Test that scores are clamped to 1-5 range."""
        agent = LiteScoringAgent(config=mock_config)

        # Score too high
        result = agent._parse_score_response('{"score": 10, "explanation": ""}')
        assert result["score"] == 5

        # Score too low
        result = agent._parse_score_response('{"score": 0, "explanation": ""}')
        assert result["score"] == 1

    def test_parse_score_response_fallback(self, mock_config: LiteConfig) -> None:
        """Test fallback parsing when JSON fails."""
        agent = LiteScoringAgent(config=mock_config)

        response = "I would give this a score: 3 because it's moderately relevant."
        result = agent._parse_score_response(response)

        assert result["score"] == 3

    def test_filter_by_score(
        self,
        mock_config: LiteConfig,
        sample_document: LiteDocument,
    ) -> None:
        """Test filtering scored documents by minimum score."""
        agent = LiteScoringAgent(config=mock_config)

        # Create documents with different scores
        docs = [
            ScoredDocument(document=sample_document, score=5, explanation=""),
            ScoredDocument(document=sample_document, score=3, explanation=""),
            ScoredDocument(document=sample_document, score=2, explanation=""),
            ScoredDocument(document=sample_document, score=4, explanation=""),
            ScoredDocument(document=sample_document, score=1, explanation=""),
        ]

        filtered = agent.filter_by_score(docs, min_score=3)
        assert len(filtered) == 3
        assert all(d.score >= 3 for d in filtered)

    def test_get_top_documents(
        self,
        mock_config: LiteConfig,
        sample_document: LiteDocument,
    ) -> None:
        """Test getting top N documents."""
        agent = LiteScoringAgent(config=mock_config)

        docs = [
            ScoredDocument(document=sample_document, score=2, explanation=""),
            ScoredDocument(document=sample_document, score=5, explanation=""),
            ScoredDocument(document=sample_document, score=3, explanation=""),
            ScoredDocument(document=sample_document, score=4, explanation=""),
        ]

        top2 = agent.get_top_documents(docs, n=2)
        assert len(top2) == 2
        assert top2[0].score == 5
        assert top2[1].score == 4


class TestLiteCitationAgent:
    """Tests for LiteCitationAgent class."""

    def test_citation_agent_initialization(self, mock_config: LiteConfig) -> None:
        """Test that citation agent initializes correctly."""
        agent = LiteCitationAgent(config=mock_config)

        assert agent.config == mock_config

    def test_parse_citation_response_valid_json(self, mock_config: LiteConfig) -> None:
        """Test parsing valid citation JSON."""
        agent = LiteCitationAgent(config=mock_config)

        response = '''{"passages": [
            {"text": "25% reduction in cardiovascular events", "relevance": "Key finding"},
            {"text": "Blood pressure decreased by 8 mmHg", "relevance": "Specific data"}
        ]}'''

        passages = agent._parse_citation_response(response)

        assert len(passages) == 2
        assert passages[0]["text"] == "25% reduction in cardiovascular events"
        assert passages[1]["text"] == "Blood pressure decreased by 8 mmHg"

    def test_parse_citation_response_invalid_json(self, mock_config: LiteConfig) -> None:
        """Test handling of invalid JSON."""
        agent = LiteCitationAgent(config=mock_config)

        response = "This is not valid JSON"
        passages = agent._parse_citation_response(response)

        assert passages == []

    def test_group_citations_by_document(
        self,
        mock_config: LiteConfig,
        sample_document: LiteDocument,
    ) -> None:
        """Test grouping citations by document."""
        agent = LiteCitationAgent(config=mock_config)

        # Create another document
        other_doc = LiteDocument(
            id="pmid-87654321",
            title="Other Study",
            abstract="Other abstract",
            source=DocumentSource.PUBMED,
        )

        citations = [
            Citation(document=sample_document, passage="Passage 1", relevance_score=4),
            Citation(document=other_doc, passage="Passage 2", relevance_score=3),
            Citation(document=sample_document, passage="Passage 3", relevance_score=4),
        ]

        grouped = agent.group_citations_by_document(citations)

        assert len(grouped) == 2
        assert len(grouped["pmid-12345678"]) == 2
        assert len(grouped["pmid-87654321"]) == 1

    def test_deduplicate_citations(
        self,
        mock_config: LiteConfig,
        sample_document: LiteDocument,
    ) -> None:
        """Test citation deduplication."""
        agent = LiteCitationAgent(config=mock_config)

        citations = [
            Citation(document=sample_document, passage="Same passage", relevance_score=4),
            Citation(document=sample_document, passage="Different passage", relevance_score=4),
            Citation(document=sample_document, passage="Same passage", relevance_score=3),  # Duplicate
            Citation(document=sample_document, passage="SAME PASSAGE", relevance_score=4),  # Case variant
        ]

        unique = agent.deduplicate_citations(citations)

        assert len(unique) == 2  # "Same passage" and "Different passage"


class TestLiteReportingAgent:
    """Tests for LiteReportingAgent class."""

    def test_reporting_agent_initialization(self, mock_config: LiteConfig) -> None:
        """Test that reporting agent initializes correctly."""
        agent = LiteReportingAgent(config=mock_config)

        assert agent.config == mock_config

    def test_generate_no_evidence_report(self, mock_config: LiteConfig) -> None:
        """Test report generation with no citations."""
        agent = LiteReportingAgent(config=mock_config)

        report = agent._generate_no_evidence_report("What is the effect of X on Y?")

        assert "No relevant evidence" in report
        assert "What is the effect of X on Y?" in report
        assert "Recommendations" in report

    def test_format_citations_for_prompt(
        self,
        mock_config: LiteConfig,
        sample_document: LiteDocument,
    ) -> None:
        """Test citation formatting for prompts."""
        agent = LiteReportingAgent(config=mock_config)

        citations = [
            Citation(
                document=sample_document,
                passage="Test passage 1",
                relevance_score=4,
            ),
            Citation(
                document=sample_document,
                passage="Test passage 2",
                relevance_score=4,
            ),
        ]

        formatted = agent._format_citations_for_prompt(citations)

        assert "[1]" in formatted
        assert "[2]" in formatted
        assert "Smith J" in formatted
        assert "2023" in formatted
        assert "Test passage 1" in formatted

    def test_format_references(
        self,
        mock_config: LiteConfig,
        sample_document: LiteDocument,
    ) -> None:
        """Test reference list formatting."""
        agent = LiteReportingAgent(config=mock_config)

        citations = [
            Citation(document=sample_document, passage="P1", relevance_score=4),
            Citation(document=sample_document, passage="P2", relevance_score=4),  # Same doc
        ]

        references = agent._format_references(citations)

        # Should only have one reference (deduplicated)
        assert references.count("1.") == 1
        assert "2." not in references
        assert "Smith J" in references
        assert "DOI:" in references
        assert "PMID:" in references

    def test_get_citation_count(
        self,
        mock_config: LiteConfig,
        sample_document: LiteDocument,
    ) -> None:
        """Test unique document counting."""
        agent = LiteReportingAgent(config=mock_config)

        other_doc = LiteDocument(
            id="pmid-99999999",
            title="Other",
            abstract="Other",
            source=DocumentSource.PUBMED,
        )

        citations = [
            Citation(document=sample_document, passage="P1", relevance_score=4),
            Citation(document=sample_document, passage="P2", relevance_score=4),
            Citation(document=other_doc, passage="P3", relevance_score=3),
        ]

        count = agent.get_citation_count(citations)
        assert count == 2  # Two unique documents

    def test_export_report_with_metadata(
        self,
        mock_config: LiteConfig,
        sample_document: LiteDocument,
    ) -> None:
        """Test report export with metadata."""
        agent = LiteReportingAgent(config=mock_config)

        citations = [
            Citation(document=sample_document, passage="Test passage", relevance_score=4),
        ]

        export = agent.export_report_with_metadata(
            question="Test question",
            report="# Test Report\n\nContent here",
            citations=citations,
        )

        assert export["research_question"] == "Test question"
        assert export["report"] == "# Test Report\n\nContent here"
        assert export["citation_count"] == 1
        assert export["unique_source_count"] == 1
        assert len(export["sources"]) == 1
        assert export["sources"][0]["pmid"] == "12345678"
