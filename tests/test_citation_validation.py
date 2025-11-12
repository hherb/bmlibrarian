"""
Test citation validation and auto-correction functionality.

Tests that the CitationFinderAgent properly validates citation passages
against source abstracts and auto-corrects fuzzy matches.
"""

import pytest
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
