"""HyDE search wiring: utilities importable, agent methods have the expected parameters."""

import inspect

from bmlibrarian.agents.query_agent import QueryAgent
from bmlibrarian.agents.utils import hyde_search

HYDE_PARAMS = ('question', 'max_results', 'num_hypothetical_docs',
               'similarity_threshold', 'generation_model', 'embedding_model')


def test_hyde_utilities_exist() -> None:
    """The HyDE search module exposes its pipeline functions."""
    for name in ('generate_hypothetical_documents', 'embed_documents', 'search_with_embedding',
                 'reciprocal_rank_fusion', 'hyde_search'):
        assert callable(getattr(hyde_search, name)), name


def test_query_agent_hyde_signature() -> None:
    """QueryAgent.find_abstracts_hyde takes the HyDE parameters."""
    params = inspect.signature(QueryAgent.find_abstracts_hyde).parameters
    assert set(HYDE_PARAMS) <= set(params)


def test_base_agent_embedding_signature() -> None:
    """BaseAgent._generate_embedding takes text and model."""
    params = inspect.signature(QueryAgent._generate_embedding).parameters
    assert {'text', 'model'} <= set(params)
