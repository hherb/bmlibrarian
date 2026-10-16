"""
Test citation validation and auto-correction functionality.

Tests that the CitationFinderAgent properly validates citation passages
against source abstracts and auto-corrects fuzzy matches.
"""

from unittest.mock import patch

from bmlibrarian.agents.citation_agent import CitationFinderAgent


def test_exact_match():
    """Test that exact matches return similarity=1.0 and original text."""
    agent = CitationFinderAgent(model="gpt-oss:20b", show_model_info=False)

    abstract = "Aspirin reduces the risk of heart attack in patients with cardiovascular disease. However, it may increase bleeding risk in some populations."
    llm_passage = "Aspirin reduces the risk of heart attack in patients with cardiovascular disease."

    is_valid, similarity, exact_text = agent._validate_and_extract_exact_match(
        llm_passage, abstract
    )

    assert is_valid is True
    assert similarity == 1.0
    assert exact_text == llm_passage


def test_fuzzy_match_with_autocorrection():
    """Test that minor punctuation/whitespace differences are handled."""
    agent = CitationFinderAgent(model="gpt-oss:20b", show_model_info=False)

    abstract = "Aspirin reduces the risk of heart attack in patients with cardiovascular disease, however it may increase bleeding risk."
    # Minor punctuation difference (comma instead of period)
    llm_passage = "Aspirin reduces the risk of heart attack in patients with cardiovascular disease; however it may increase bleeding risk."

    is_valid, similarity, exact_text = agent._validate_and_extract_exact_match(
        llm_passage, abstract
    )

    # Should find a match (fuzzy)
    assert is_valid is True
    assert similarity >= 0.95
    # Should return text from original abstract, not LLM's version
    assert "cardiovascular disease" in exact_text


def test_hallucination_rejected():
    """Test that completely fabricated text is rejected."""
    agent = CitationFinderAgent(model="gpt-oss:20b", show_model_info=False)

    abstract = "Aspirin reduces the risk of heart attack in patients with cardiovascular disease."
    llm_passage = "Statins are the most effective treatment for lowering cholesterol levels."

    is_valid, similarity, exact_text = agent._validate_and_extract_exact_match(
        llm_passage, abstract
    )

    assert is_valid is False
    assert similarity < 0.95
    assert exact_text is None


def test_paraphrasing_rejected():
    """Test that paraphrased text is rejected (even if semantically similar)."""
    agent = CitationFinderAgent(model="gpt-oss:20b", show_model_info=False)

    abstract = "Liver transplantation with living related donor has been recently developed to compensate for the insufficient number of liver grafts for children."
    # Paraphrased: donor→donors, compensate for→address
    llm_passage = "Liver transplantation with living related donors has recently been developed to address the insufficient number of liver grafts for children"

    is_valid, similarity, exact_text = agent._validate_and_extract_exact_match(
        llm_passage, abstract
    )

    # Should reject paraphrases to ensure we only use exact text
    assert is_valid is False
    assert similarity < 0.95  # Similarity is ~0.90, below threshold
    assert exact_text is None


def test_validation_stats_tracking():
    """Test that validation statistics are properly tracked."""
    agent = CitationFinderAgent(model="gpt-oss:20b", show_model_info=False)

    abstract = "Aspirin reduces the risk of heart attack."

    # Test exact match
    agent._validate_and_extract_exact_match(
        "Aspirin reduces the risk of heart attack.", abstract
    )

    # Test rejection
    agent._validate_and_extract_exact_match(
        "Completely fabricated text.", abstract
    )

    stats = agent.get_validation_stats()

    # Stats not tracked in validation method itself, only in extract_citation_from_document
    # This test verifies the stats structure exists
    assert 'total_extractions' in stats
    assert 'validations_passed' in stats
    assert 'validations_failed' in stats
    assert 'exact_matches' in stats
    assert 'fuzzy_matches' in stats


def test_case_insensitive_matching():
    """Test that matching is case-insensitive but preserves original case."""
    agent = CitationFinderAgent(model="gpt-oss:20b", show_model_info=False)

    abstract = "The Mediterranean Diet has been shown to reduce cardiovascular risk."
    llm_passage = "the mediterranean diet has been shown to reduce cardiovascular risk"

    is_valid, similarity, exact_text = agent._validate_and_extract_exact_match(
        llm_passage, abstract
    )

    assert is_valid is True
    assert similarity == 1.0
    # Should preserve original capitalization
    assert "Mediterranean Diet" in exact_text


def test_whitespace_normalization():
    """Test that extra whitespace doesn't break matching."""
    agent = CitationFinderAgent(model="gpt-oss:20b", show_model_info=False)

    abstract = "Type 2 diabetes   can often be   managed through lifestyle changes."
    llm_passage = "Type 2 diabetes can often be managed through lifestyle changes."

    is_valid, similarity, exact_text = agent._validate_and_extract_exact_match(
        llm_passage, abstract
    )

    assert is_valid is True
    assert similarity >= 0.95


def test_partial_match_rejection():
    """Test that partial overlaps below threshold are rejected."""
    agent = CitationFinderAgent(model="gpt-oss:20b", show_model_info=False)

    abstract = "Aspirin reduces the risk of heart attack in patients."
    # Only first part matches
    llm_passage = "Aspirin reduces the risk of stroke and improves overall cardiovascular health."

    is_valid, similarity, exact_text = agent._validate_and_extract_exact_match(
        llm_passage, abstract
    )

    # Should reject - insufficient similarity
    assert is_valid is False



def _extract_with_llm_responses(responses: list) -> tuple:
    """Run extract_citation_from_document with mocked LLM JSON responses."""
    agent = CitationFinderAgent(model="gpt-oss:20b", show_model_info=False, max_retries=2)
    document = {
        "id": 42,
        "title": "Aspirin trial",
        "abstract": (
            "Background: cardiovascular disease is common. Aspirin reduces the risk "
            "of heart attack in patients with cardiovascular disease, however it may "
            "increase bleeding risk. Conclusions: weigh benefits and harms."
        ),
    }
    with patch.object(agent, "test_connection", return_value=True), patch.object(
        agent, "_generate_and_parse_json", side_effect=responses
    ) as llm:
        citation = agent.extract_citation_from_document("Does aspirin help?", document)
    return agent, citation, llm


def _llm_response(passage: object) -> dict:
    """A positive citation-extraction response carrying ``passage``."""
    return {
        "has_relevant_content": True,
        "relevant_passage": passage,
        "summary": "Aspirin lowers heart-attack risk.",
        "relevance_score": 0.9,
    }


def test_extraction_stores_source_text_for_fuzzy_passage():
    """A near-verbatim LLM passage is replaced by the abstract's own wording."""
    llm_passage = (
        "Aspirin reduces the risk of heart attack in patients with cardiovascular "
        "disease; however it may increase bleeding risk."
    )
    agent, citation, _ = _extract_with_llm_responses([_llm_response(llm_passage)])

    assert citation is not None
    assert citation.passage == (
        "Aspirin reduces the risk of heart attack in patients with cardiovascular "
        "disease, however it may increase bleeding risk."
    )
    assert agent.get_validation_stats()["fuzzy_matches"] == 1


def test_extraction_retries_non_string_passage():
    """A missing/non-text passage is a validation failure that is retried."""
    good = "Aspirin reduces the risk of heart attack in patients with cardiovascular disease"
    agent, citation, llm = _extract_with_llm_responses(
        [_llm_response(None), _llm_response(good)]
    )

    assert llm.call_count == 2
    assert citation is not None
    assert citation.passage == good
    assert agent.get_validation_stats()["exact_matches"] == 1


def test_extraction_rejects_after_exhausting_retries():
    """Unmatchable passages are rejected once all attempts are used."""
    agent, citation, llm = _extract_with_llm_responses(
        [_llm_response(["not", "text"])] * 3
    )

    assert citation is None
    assert llm.call_count == 3
    stats = agent.get_validation_stats()
    assert stats["validations_failed"] == 1
    assert stats["failed_citations"][0]["similarity"] == 0.0

if __name__ == "__main__":
    # Run tests
    print("Testing citation validation...")

    test_exact_match()
    print("✓ Exact match test passed")

    test_fuzzy_match_with_autocorrection()
    print("✓ Fuzzy match with auto-correction test passed")

    test_hallucination_rejected()
    print("✓ Hallucination rejection test passed")

    test_paraphrasing_rejected()
    print("✓ Paraphrasing rejection test passed")

    test_validation_stats_tracking()
    print("✓ Validation stats tracking test passed")

    test_case_insensitive_matching()
    print("✓ Case-insensitive matching test passed")

    test_whitespace_normalization()
    print("✓ Whitespace normalization test passed")

    test_partial_match_rejection()
    print("✓ Partial match rejection test passed")

    print("\n✅ All validation tests passed!")
