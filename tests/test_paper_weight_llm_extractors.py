"""Failure handling in the paper-weight LLM extractors and chunk helpers.

A failure must raise rather than become a neutral (study design) or zero
(sample size) score, because assess_paper stores and caches whatever it
gets (#345, #347).
"""

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from bmlibrarian.agents.paper_weight.extractors import UNKNOWN_STUDY_TYPE_SCORE
from bmlibrarian.agents.paper_weight.llm_extractors import (
    extract_sample_size_llm,
    extract_study_type_llm,
)
from bmlibrarian.agents.paper_weight.validators import (
    get_all_document_chunks,
    search_chunks_by_query,
)

EXTRACTORS_MODULE = 'bmlibrarian.agents.paper_weight.llm_extractors'
CHUNKS = [{'chunk_no': 0, 'chunk_text': 'We conducted a randomized controlled trial of 120 adults.'}]
EXTRACTORS = [extract_study_type_llm, extract_sample_size_llm]


def failing_db() -> Any:
    """Patch the shared DB manager so every connection attempt fails."""
    manager = MagicMock()
    manager.get_connection.side_effect = Exception('Database connection failed')
    return patch('bmlibrarian.database.get_db_manager', return_value=manager)


def llm_returning(content: str) -> MagicMock:
    """Return a mock LLM client whose generate() responds with ``content``."""
    client = MagicMock()
    client.generate.return_value = MagicMock(content=content)
    return client


class TestChunkHelpersRaise:
    """Chunk queries no longer turn a database error into 'no chunks'."""

    def test_search_chunks_by_query(self) -> None:
        """A failed semantic search raises."""
        with failing_db(), pytest.raises(Exception, match='Database connection failed'):
            search_chunks_by_query(document_id=1, query='study design')

    def test_get_all_document_chunks(self) -> None:
        """A failed positional chunk query raises."""
        with failing_db(), pytest.raises(Exception, match='Database connection failed'):
            get_all_document_chunks(document_id=1)


@pytest.mark.parametrize('extract', EXTRACTORS)
class TestExtractorsRaise:
    """LLM extraction failures raise instead of returning a fallback score."""

    def test_chunk_search_failure_propagates(self, extract: Any) -> None:
        """A DB error in the chunk search is not scored as 'no text available'."""
        with patch(f'{EXTRACTORS_MODULE}.search_chunks_by_query',
                   side_effect=Exception('Database connection failed')), \
             pytest.raises(Exception, match='Database connection failed'):
            extract(document_id=1, llm_client=llm_returning('{}'), model='m',
                    document={'full_text': 'body'})

    def test_unparseable_response_raises(self, extract: Any) -> None:
        """A response without JSON raises ValueError."""
        with patch(f'{EXTRACTORS_MODULE}.search_chunks_by_query', return_value=CHUNKS), \
             pytest.raises(ValueError, match='Could not parse LLM'):
            extract(document_id=1, llm_client=llm_returning('I cannot tell.'), model='m')

    def test_empty_json_raises(self, extract: Any) -> None:
        """A JSON reply without the requested field raises instead of defaulting (#345)."""
        with patch(f'{EXTRACTORS_MODULE}.search_chunks_by_query', return_value=CHUNKS), \
             pytest.raises(ValueError):
            extract(document_id=1, llm_client=llm_returning('{}'), model='m')

    def test_no_text_raises(self, extract: Any) -> None:
        """A document with no chunks and no abstract raises instead of a placeholder score."""
        with patch(f'{EXTRACTORS_MODULE}.search_chunks_by_query', return_value=[]), \
             patch(f'{EXTRACTORS_MODULE}.get_all_document_chunks', return_value=[]), \
             pytest.raises(ValueError, match='No text available'):
            extract(document_id=1, llm_client=llm_returning('{}'), model='m',
                    document={'title': 'Only a title'})

    def test_llm_error_propagates(self, extract: Any) -> None:
        """An LLM call failure propagates."""
        client = MagicMock()
        client.generate.side_effect = RuntimeError('LLM timeout')
        with patch(f'{EXTRACTORS_MODULE}.search_chunks_by_query', return_value=CHUNKS), \
             pytest.raises(RuntimeError, match='LLM timeout'):
            extract(document_id=1, llm_client=client, model='m')


class TestExtractorsSucceed:
    """A parseable response still yields a score."""

    def test_study_type(self) -> None:
        """A valid study-type response is scored from the hierarchy."""
        client = llm_returning('{"study_type": "rct", "confidence": 0.9}')
        with patch(f'{EXTRACTORS_MODULE}.search_chunks_by_query', return_value=CHUNKS):
            score = extract_study_type_llm(document_id=1, llm_client=client, model='m',
                                           hierarchy_config={'rct': 8.0})
        assert score.score == 8.0

    def test_study_type_unknown_is_neutral(self) -> None:
        """'unknown' is an answer the prompt offers; it gets the neutral score."""
        client = llm_returning('{"study_type": "unknown", "confidence": 0.3}')
        with patch(f'{EXTRACTORS_MODULE}.search_chunks_by_query', return_value=CHUNKS):
            score = extract_study_type_llm(document_id=1, llm_client=client, model='m',
                                           hierarchy_config={'rct': 8.0})
        assert score.score == UNKNOWN_STUDY_TYPE_SCORE

    def test_sample_size_not_reported(self) -> None:
        """'No sample size reported' is a real finding, not a failure."""
        client = llm_returning('{"sample_size": null, "reasoning": "not stated"}')
        with patch(f'{EXTRACTORS_MODULE}.search_chunks_by_query', return_value=CHUNKS):
            score = extract_sample_size_llm(document_id=1, llm_client=client, model='m')
        assert score.score == 0.0
        assert 'not stated' in score.details[0].reasoning


def test_off_list_study_type_raises() -> None:
    """A study type outside the hierarchy is a bad reply, not a neutral 5.0 (#345)."""
    client = llm_returning('{"study_type": "randomized controlled trial", "confidence": 0.9}')
    with patch(f'{EXTRACTORS_MODULE}.search_chunks_by_query', return_value=CHUNKS), \
         pytest.raises(ValueError, match='invalid study type'):
        extract_study_type_llm(document_id=1, llm_client=client, model='m',
                               hierarchy_config={'rct': 8.0})
