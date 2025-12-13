"""
Unit tests for query converter.

Tests the QueryConverter class for natural language to PubMed query conversion.
"""

import pytest
import json
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

from bmlibrarian.pubmed_search.query_converter import QueryConverter
from bmlibrarian.pubmed_search.data_types import (
    QueryConcept,
    PublicationType,
    DateRange,
)
from bmlibrarian.llm import LLMResponse


class TestQueryConverterInit:
    """Tests for QueryConverter initialization."""

    @patch("bmlibrarian.pubmed_search.query_converter.get_llm_client")
    @patch("bmlibrarian.pubmed_search.query_converter.MeSHLookup")
    def test_init_default_model(self, mock_mesh: MagicMock, mock_client: MagicMock) -> None:
        """Test initialization with default model."""
        converter = QueryConverter()
        assert converter.model is not None

    @patch("bmlibrarian.pubmed_search.query_converter.get_llm_client")
    @patch("bmlibrarian.pubmed_search.query_converter.MeSHLookup")
    def test_init_custom_model(self, mock_mesh: MagicMock, mock_client: MagicMock) -> None:
        """Test initialization with custom model."""
        converter = QueryConverter(model="custom-model:latest")
        assert converter.model == "custom-model:latest"


class TestQueryConverterConversion:
    """Tests for query conversion."""

    @pytest.fixture
    def mock_llm_response(self) -> dict:
        """Create a mock LLM response."""
        return {
            "concepts": [
                {
                    "name": "Exercise",
                    "mesh_terms": ["Exercise", "Physical Activity"],
                    "keywords": ["workout", "physical exercise"],
                    "synonyms": ["training"],
                    "pico_role": "intervention",
                },
                {
                    "name": "Cardiovascular",
                    "mesh_terms": ["Cardiovascular Diseases"],
                    "keywords": ["heart", "cardiac"],
                    "synonyms": [],
                    "pico_role": "outcome",
                },
            ],
            "suggested_filters": {
                "publication_types": ["Clinical Trial"],
                "humans_only": True,
                "has_abstract": True,
            },
            "confidence": 0.85,
            "notes": "Test query",
        }

    @patch("bmlibrarian.pubmed_search.query_converter.get_llm_client")
    @patch("bmlibrarian.pubmed_search.query_converter.MeSHLookup")
    def test_convert_basic_question(
        self,
        mock_mesh_class: MagicMock,
        mock_client_func: MagicMock,
        mock_llm_response: dict,
    ) -> None:
        """Test basic question conversion."""
        # Setup mock LLM client
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = json.dumps(mock_llm_response)
        mock_client.chat.return_value = mock_response
        mock_client_func.return_value = mock_client

        # Setup mock MeSH lookup (all terms valid)
        mock_mesh = MagicMock()
        mock_mesh.validate_term.return_value = MagicMock(is_valid=True)
        mock_mesh_class.return_value = mock_mesh

        converter = QueryConverter(validate_mesh=True, expand_keywords=False)
        result = converter.convert("What are the cardiovascular benefits of exercise?")

        assert result.primary_query is not None
        assert result.primary_query.original_question is not None
        assert len(result.concepts_extracted) > 0

    @patch("bmlibrarian.pubmed_search.query_converter.get_llm_client")
    @patch("bmlibrarian.pubmed_search.query_converter.MeSHLookup")
    def test_convert_empty_question_raises(
        self,
        mock_mesh: MagicMock,
        mock_client: MagicMock,
    ) -> None:
        """Test that empty question raises ValueError."""
        converter = QueryConverter()

        with pytest.raises(ValueError, match="empty"):
            converter.convert("")

    @patch("bmlibrarian.pubmed_search.query_converter.get_llm_client")
    @patch("bmlibrarian.pubmed_search.query_converter.MeSHLookup")
    def test_convert_with_filters(
        self,
        mock_mesh_class: MagicMock,
        mock_client_func: MagicMock,
        mock_llm_response: dict,
    ) -> None:
        """Test conversion with explicit filters."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = json.dumps(mock_llm_response)
        mock_client.chat.return_value = mock_response
        mock_client_func.return_value = mock_client

        mock_mesh = MagicMock()
        mock_mesh.validate_term.return_value = MagicMock(is_valid=True)
        mock_mesh_class.return_value = mock_mesh

        converter = QueryConverter(validate_mesh=False, expand_keywords=False)
        result = converter.convert(
            "Test question",
            publication_types=[PublicationType.RCT],
            humans_only=True,
        )

        assert result.primary_query.humans_only is True
        assert PublicationType.RCT in result.primary_query.publication_types


class TestQueryConverterFallback:
    """Tests for fallback query generation."""

    @patch("bmlibrarian.pubmed_search.query_converter.get_llm_client")
    @patch("bmlibrarian.pubmed_search.query_converter.MeSHLookup")
    def test_fallback_on_llm_failure(
        self,
        mock_mesh_class: MagicMock,
        mock_client_func: MagicMock,
    ) -> None:
        """Test fallback generation when LLM fails."""
        # Setup mock LLM to fail
        mock_client = MagicMock()
        mock_client.chat.side_effect = Exception("LLM error")
        mock_client_func.return_value = mock_client

        mock_mesh_class.return_value = MagicMock()

        converter = QueryConverter()
        result = converter.convert("cardiovascular exercise benefits")

        # Should return fallback result
        assert result.primary_query is not None
        assert result.primary_query.generation_model == "fallback"
        assert any("fallback" in w.lower() for w in result.warnings)


class TestQueryConverterParsing:
    """Tests for LLM response parsing."""

    @patch("bmlibrarian.pubmed_search.query_converter.get_llm_client")
    @patch("bmlibrarian.pubmed_search.query_converter.MeSHLookup")
    def test_parse_json_from_markdown(
        self,
        mock_mesh_class: MagicMock,
        mock_client_func: MagicMock,
    ) -> None:
        """Test parsing JSON from markdown code blocks."""
        mock_client = MagicMock()
        # LLM response with markdown code block
        response_with_markdown = """
        Here's the query:
        ```json
        {
            "concepts": [{"name": "test", "mesh_terms": [], "keywords": ["test"]}],
            "confidence": 0.8,
            "notes": "test"
        }
        ```
        """
        mock_response = MagicMock()
        mock_response.content = response_with_markdown
        mock_client.chat.return_value = mock_response
        mock_client_func.return_value = mock_client

        mock_mesh = MagicMock()
        mock_mesh.validate_term.return_value = MagicMock(is_valid=True)
        mock_mesh_class.return_value = mock_mesh

        converter = QueryConverter(validate_mesh=False, expand_keywords=False)
        result = converter.convert("test question")

        # Should successfully parse the JSON from markdown
        assert result.primary_query is not None


class TestQueryConverterQueryBuilding:
    """Tests for query string building."""

    def test_build_query_single_concept(self) -> None:
        """Test building query with single concept."""
        concept = QueryConcept(
            name="Exercise",
            mesh_terms=["Exercise"],
            keywords=["workout"],
        )

        with patch("bmlibrarian.pubmed_search.query_converter.get_llm_client"):
            with patch("bmlibrarian.pubmed_search.query_converter.MeSHLookup"):
                converter = QueryConverter()
                query = converter._build_query_string([concept])

                assert '"Exercise"[MeSH Terms]' in query
                assert "workout[Title/Abstract]" in query

    def test_build_query_with_humans_filter(self) -> None:
        """Test building query with humans filter."""
        concept = QueryConcept(name="Test", keywords=["test"])

        with patch("bmlibrarian.pubmed_search.query_converter.get_llm_client"):
            with patch("bmlibrarian.pubmed_search.query_converter.MeSHLookup"):
                converter = QueryConverter()
                query = converter._build_query_string([concept], humans_only=True)

                assert "humans[MeSH Terms]" in query

    def test_build_query_with_publication_types(self) -> None:
        """Test building query with publication type filters."""
        concept = QueryConcept(name="Test", keywords=["test"])

        with patch("bmlibrarian.pubmed_search.query_converter.get_llm_client"):
            with patch("bmlibrarian.pubmed_search.query_converter.MeSHLookup"):
                converter = QueryConverter()
                query = converter._build_query_string(
                    [concept],
                    publication_types=[PublicationType.RCT, PublicationType.META_ANALYSIS],
                )

                assert "[Publication Type]" in query
