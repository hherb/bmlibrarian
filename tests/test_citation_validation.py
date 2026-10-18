"""
Test citation validation and auto-correction functionality.

Tests that the CitationFinderAgent properly validates citation passages
against source abstracts and auto-corrects fuzzy matches.
"""

import json
import logging
from unittest.mock import patch

import pytest

from bmlibrarian.agents.citation_agent import (
    FAILED_PASSAGE_STORED_CHARS,
    REJECT_BAD_RELEVANCE,
    REJECT_BELOW_THRESHOLD,
    REJECT_INCOMPLETE_SENTENCE,
    REJECT_MISSING_SUMMARY,
    REJECT_NOT_JSON_OBJECT,
    REJECT_PASSAGE_EMPTY,
    REJECT_PASSAGE_NOT_FOUND,
    REJECT_PASSAGE_NOT_TEXT,
    CitationFinderAgent,
)

ABSTRACT = (
    "Background: cardiovascular disease is common. Aspirin reduces the risk "
    "of heart attack in patients with cardiovascular disease, however it may "
    "increase bleeding risk. Conclusions: weigh benefits and harms."
)
GOOD_PASSAGE = (
    "Aspirin reduces the risk of heart attack in patients with cardiovascular "
    "disease, however it may increase bleeding risk."
)


def test_exact_match():
    """Test that exact matches return similarity=1.0 and original text."""
    agent = CitationFinderAgent(model="gpt-oss:20b", show_model_info=False)

    abstract = "Aspirin reduces the risk of heart attack in patients with cardiovascular disease. However, it may increase bleeding risk in some populations."
    llm_passage = "Aspirin reduces the risk of heart attack in patients with cardiovascular disease."

    match = agent._validate_and_extract_exact_match(
        llm_passage, abstract
    )

    assert match.matched is True
    assert match.similarity == 1.0
    assert match.exact
    assert match.text == llm_passage


def test_fuzzy_match_with_autocorrection():
    """Test that minor punctuation/whitespace differences are handled."""
    agent = CitationFinderAgent(model="gpt-oss:20b", show_model_info=False)

    abstract = "Aspirin reduces the risk of heart attack in patients with cardiovascular disease, however it may increase bleeding risk."
    # Minor punctuation difference (comma instead of period)
    llm_passage = "Aspirin reduces the risk of heart attack in patients with cardiovascular disease; however it may increase bleeding risk."

    match = agent._validate_and_extract_exact_match(
        llm_passage, abstract
    )

    # Should find a match (fuzzy)
    assert match.matched is True
    assert match.similarity >= 0.95
    # Should return text from original abstract, not LLM's version
    assert "cardiovascular disease" in match.text


def test_hallucination_rejected():
    """Test that completely fabricated text is rejected."""
    agent = CitationFinderAgent(model="gpt-oss:20b", show_model_info=False)

    abstract = "Aspirin reduces the risk of heart attack in patients with cardiovascular disease."
    llm_passage = "Statins are the most effective treatment for lowering cholesterol levels."

    match = agent._validate_and_extract_exact_match(
        llm_passage, abstract
    )

    assert match.matched is False
    assert match.similarity < 0.95
    assert match.text is None


def test_paraphrasing_rejected():
    """Test that paraphrased text is rejected (even if semantically similar)."""
    agent = CitationFinderAgent(model="gpt-oss:20b", show_model_info=False)

    abstract = "Liver transplantation with living related donor has been recently developed to compensate for the insufficient number of liver grafts for children."
    # Paraphrased: donor→donors, compensate for→address
    llm_passage = "Liver transplantation with living related donors has recently been developed to address the insufficient number of liver grafts for children"

    match = agent._validate_and_extract_exact_match(
        llm_passage, abstract
    )

    # Should reject paraphrases to ensure we only use exact text
    assert match.matched is False
    assert match.similarity < 0.95  # Similarity is ~0.90, below threshold
    assert match.text is None


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
    assert 'errors' in stats


def test_case_insensitive_matching():
    """Test that matching is case-insensitive but preserves original case."""
    agent = CitationFinderAgent(model="gpt-oss:20b", show_model_info=False)

    abstract = "The Mediterranean Diet has been shown to reduce cardiovascular risk."
    llm_passage = "the mediterranean diet has been shown to reduce cardiovascular risk"

    match = agent._validate_and_extract_exact_match(
        llm_passage, abstract
    )

    assert match.matched is True
    assert match.similarity == 1.0
    # Should preserve original capitalization
    assert "Mediterranean Diet" in match.text


def test_whitespace_normalization():
    """Test that extra whitespace doesn't break matching."""
    agent = CitationFinderAgent(model="gpt-oss:20b", show_model_info=False)

    abstract = "Type 2 diabetes   can often be   managed through lifestyle changes."
    llm_passage = "Type 2 diabetes can often be managed through lifestyle changes."

    match = agent._validate_and_extract_exact_match(
        llm_passage, abstract
    )

    assert match.matched is True
    assert match.similarity >= 0.95


def test_partial_match_rejection():
    """Test that partial overlaps below threshold are rejected."""
    agent = CitationFinderAgent(model="gpt-oss:20b", show_model_info=False)

    abstract = "Aspirin reduces the risk of heart attack in patients."
    # Only first part matches
    llm_passage = "Aspirin reduces the risk of stroke and improves overall cardiovascular health."

    match = agent._validate_and_extract_exact_match(
        llm_passage, abstract
    )

    # Should reject - insufficient similarity
    assert match.matched is False



def _extract_with_llm_responses(responses: list, abstract: object = ABSTRACT) -> tuple:
    """Run extract_citation_from_document with mocked LLM JSON responses."""
    agent = CitationFinderAgent(model="gpt-oss:20b", show_model_info=False, max_retries=2)
    document = {"id": 42, "title": "Aspirin trial", "abstract": abstract}
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


@pytest.mark.parametrize(
    "fragment",
    [
        "Aspirin",  # a bare key term
        "spirin reduces the risk of heart attack",  # starts mid-word
        "Aspirin reduces the risk of heart attack in patients with cardiovascular disease",
        "however it may increase bleeding risk.",  # starts mid-sentence
    ],
)
def test_fragments_are_rejected_as_incomplete_sentences(fragment: str) -> None:
    """Verbatim fragments are never verified citations (#289); they are retried."""
    agent, citation, llm = _extract_with_llm_responses([_llm_response(fragment)] * 3)

    assert citation is None
    assert llm.call_count == 3
    failed = agent.get_validation_stats()["failed_citations"]
    assert [entry["reason"] for entry in failed] == [REJECT_INCOMPLETE_SENTENCE]


def test_fragment_then_complete_sentence_succeeds() -> None:
    """A retry that quotes the whole sentence is accepted."""
    agent, citation, llm = _extract_with_llm_responses(
        [_llm_response("Aspirin reduces the risk of heart attack"), _llm_response(GOOD_PASSAGE)]
    )

    assert llm.call_count == 2
    assert citation is not None
    assert citation.passage == GOOD_PASSAGE


def test_missing_final_period_is_taken_from_the_abstract() -> None:
    """A sentence quoted without its full stop is stored with the source's full stop."""
    _, citation, _ = _extract_with_llm_responses([_llm_response(GOOD_PASSAGE[:-1])])

    assert citation is not None
    assert citation.passage == GOOD_PASSAGE


def test_extraction_retries_non_string_passage():
    """A missing/non-text passage is a validation failure that is retried."""
    agent, citation, llm = _extract_with_llm_responses(
        [_llm_response(None), _llm_response(GOOD_PASSAGE)]
    )

    assert llm.call_count == 2
    assert citation is not None
    assert citation.passage == GOOD_PASSAGE
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
    assert stats["failed_citations"][0]["reason"] == REJECT_PASSAGE_NOT_TEXT


def _with_summary(response: dict, summary: object) -> dict:
    """``response`` with its summary replaced."""
    return {**response, "summary": summary}


@pytest.mark.parametrize(
    ("bad_response", "reason"),
    [
        (["not", "an", "object"], REJECT_NOT_JSON_OBJECT),
        ({**_llm_response(GOOD_PASSAGE), "relevance_score": "high"}, REJECT_BAD_RELEVANCE),
        (_llm_response("   "), REJECT_PASSAGE_EMPTY),
        (_llm_response("Statins lower cholesterol in most adults."), REJECT_PASSAGE_NOT_FOUND),
        (
            _llm_response("Aspirin lowers the risk of heart attacks in people with heart disease"),
            REJECT_BELOW_THRESHOLD,
        ),
        (_with_summary(_llm_response(GOOD_PASSAGE), None), REJECT_MISSING_SUMMARY),
    ],
)
def test_rejection_reason_is_recorded(bad_response: object, reason: str) -> None:
    """Each malformed or unverifiable response is retried, then rejected with its reason."""
    agent, citation, llm = _extract_with_llm_responses([bad_response] * 3)

    assert citation is None
    assert llm.call_count == 3
    failed = agent.get_validation_stats()["failed_citations"]
    assert [entry["reason"] for entry in failed] == [reason]


def test_bad_response_then_good_response_succeeds() -> None:
    """A malformed response does not end extraction; the retry can succeed."""
    agent, citation, llm = _extract_with_llm_responses(
        [["not", "an", "object"], _llm_response(GOOD_PASSAGE)]
    )

    assert llm.call_count == 2
    assert citation is not None
    assert citation.passage == GOOD_PASSAGE
    assert citation.summary == "Aspirin lowers heart-attack risk."


def test_low_relevance_is_not_retried() -> None:
    """A response below min_relevance ends extraction without a retry."""
    agent, citation, llm = _extract_with_llm_responses(
        [{**_llm_response(GOOD_PASSAGE), "relevance_score": 0.2}]
    )

    assert citation is None
    assert llm.call_count == 1
    assert agent.get_validation_stats()["validations_failed"] == 0


@pytest.mark.parametrize("abstract", ["   \n ", None, {"text": "not a string"}])
def test_blank_or_non_text_abstract_skips_llm(abstract: object) -> None:
    """No LLM call is spent on a document without abstract text."""
    _, citation, llm = _extract_with_llm_responses([], abstract=abstract)

    assert citation is None
    assert llm.call_count == 0


def test_unexpected_error_is_counted_and_logged_with_traceback(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """An unexpected exception is logged with its traceback and counted."""
    agent = CitationFinderAgent(model="gpt-oss:20b", show_model_info=False, max_retries=2)
    document = {"id": 7, "title": "t", "abstract": ABSTRACT}
    with patch.object(agent, "test_connection", return_value=True), patch.object(
        agent, "_generate_and_parse_json", return_value=_llm_response(GOOD_PASSAGE)
    ), patch.object(agent, "_check_response", side_effect=RuntimeError("boom")):
        with caplog.at_level(logging.ERROR):
            citation = agent.extract_citation_from_document("q", document)

    assert citation is None
    assert agent.get_validation_stats()["errors"] == 1
    assert any(record.exc_info for record in caplog.records)


@pytest.mark.parametrize(
    ("connected", "llm_error"),
    [
        (False, None),
        (True, ConnectionError("Ollama unreachable")),
        (True, ValueError("model not found")),
        (True, json.JSONDecodeError("Expecting value", "", 0)),
    ],
)
def test_llm_failures_are_counted_as_errors(
    connected: bool, llm_error: Exception | None
) -> None:
    """No connection or no usable LLM output is an error, not 'no passage'.

    Callers such as the fact-checker use the ``errors`` statistic to tell a
    failure from a document without relevant content.
    """
    agent = CitationFinderAgent(model="gpt-oss:20b", show_model_info=False)
    document = {"id": 7, "title": "t", "abstract": ABSTRACT}
    with patch.object(agent, "test_connection", return_value=connected), patch.object(
        agent, "_generate_and_parse_json", side_effect=llm_error
    ):
        citation = agent.extract_citation_from_document("q", document)

    assert citation is None
    assert agent.get_validation_stats()["errors"] == 1


def test_irrelevant_document_is_not_an_error() -> None:
    """A document judged irrelevant is a normal outcome, not an error."""
    agent, citation, _ = _extract_with_llm_responses(
        [{"has_relevant_content": False, "relevance_score": 0.0}]
    )

    assert citation is None
    assert agent.get_validation_stats()["errors"] == 0


def test_batch_summary_reports_rejections() -> None:
    """The completion callback says how many passages were rejected."""
    events = []
    agent = CitationFinderAgent(
        model="gpt-oss:20b",
        show_model_info=False,
        max_retries=0,
        callback=lambda step, data: events.append((step, data)),
    )
    documents = [
        ({"id": 1, "title": "a", "abstract": ABSTRACT}, {"score": 4}),
        ({"id": 2, "title": "b", "abstract": ABSTRACT}, {"score": 4}),
    ]
    responses = [_llm_response(GOOD_PASSAGE), _llm_response("Statins lower cholesterol.")]
    with patch.object(agent, "test_connection", return_value=True), patch.object(
        agent, "_generate_and_parse_json", side_effect=responses
    ):
        citations = agent.process_scored_documents_for_citations("q", documents)

    assert len(citations) == 1
    completed = [data for step, data in events if step == "citation_extraction_completed"]
    assert completed == [
        "Extracted 1 citations from 2 documents "
        "(1 rejected: passage not found in abstract ×1)"
    ]


def test_batch_summary_breaks_rejections_down_by_reason() -> None:
    """A fragment is not reported as an unverifiable passage."""
    events = []
    agent = CitationFinderAgent(
        model="gpt-oss:20b",
        show_model_info=False,
        max_retries=0,
        callback=lambda step, data: events.append((step, data)),
    )
    documents = [
        ({"id": i, "title": "t", "abstract": ABSTRACT}, {"score": 4}) for i in (1, 2, 3)
    ]
    responses = [
        _llm_response("Statins lower cholesterol."),
        _llm_response("Aspirin"),
        _llm_response("Aspirin"),
    ]
    with patch.object(agent, "test_connection", return_value=True), patch.object(
        agent, "_generate_and_parse_json", side_effect=responses
    ):
        agent.process_scored_documents_for_citations("q", documents)

    completed = [data for step, data in events if step == "citation_extraction_completed"]
    assert completed == [
        "Extracted 0 citations from 3 documents (3 rejected: "
        f"{REJECT_PASSAGE_NOT_FOUND} ×1, {REJECT_INCOMPLETE_SENTENCE} ×2)"
    ]


def test_retry_tells_the_model_why_its_passage_was_rejected() -> None:
    """A retry is not the identical prompt: it names the rejection reason."""
    _, citation, llm = _extract_with_llm_responses(
        [_llm_response("Aspirin"), _llm_response(GOOD_PASSAGE)]
    )

    assert citation is not None
    first_prompt = llm.call_args_list[0].args[0]
    retry_prompt = llm.call_args_list[1].args[0]
    assert REJECT_INCOMPLETE_SENTENCE not in first_prompt
    assert REJECT_INCOMPLETE_SENTENCE in retry_prompt
    assert 'Your previous passage was: "Aspirin"' in retry_prompt


def test_retry_quotes_a_paraphrase_with_its_similarity() -> None:
    """A below-threshold paraphrase is quoted back with its similarity (#290)."""
    paraphrase = "Aspirin lowers the risk of heart attacks in people with heart disease"
    _, citation, llm = _extract_with_llm_responses(
        [_llm_response(paraphrase), _llm_response(GOOD_PASSAGE)]
    )

    assert citation is not None
    retry_prompt = llm.call_args_list[1].args[0]
    assert f"{REJECT_BELOW_THRESHOLD} (similarity=" in retry_prompt
    assert f'Your previous passage was: "{paraphrase}"' in retry_prompt



def test_retry_quotes_the_latest_rejected_passage() -> None:
    """The third prompt quotes the second attempt's passage, not the first."""
    _, citation, llm = _extract_with_llm_responses(
        [_llm_response("Aspirin"), _llm_response("Heart disease"), _llm_response(GOOD_PASSAGE)]
    )

    assert citation is not None
    third_prompt = llm.call_args_list[2].args[0]
    assert 'Your previous passage was: "Heart disease"' in third_prompt
    assert '"Aspirin"' not in third_prompt


def test_retry_marks_a_shortened_quote() -> None:
    """A rejected passage longer than the quote limit is cut and marked with …."""
    long_passage = "Aspirin " * 60
    _, _, llm = _extract_with_llm_responses(
        [_llm_response(long_passage), _llm_response(GOOD_PASSAGE)]
    )

    retry_prompt = llm.call_args_list[1].args[0]
    quoted = long_passage.strip()[:FAILED_PASSAGE_STORED_CHARS]
    assert f'Your previous passage was: "{quoted}…"' in retry_prompt


@pytest.mark.parametrize(
    "bad_response",
    [["not", "an", "object"], _llm_response(None)],
)
def test_retry_does_not_quote_a_non_text_answer(bad_response: object) -> None:
    """A repr of a non-text answer is not quoted back as 'your passage'."""
    _, citation, llm = _extract_with_llm_responses([bad_response, _llm_response(GOOD_PASSAGE)])

    assert citation is not None
    retry_prompt = llm.call_args_list[1].args[0]
    assert "REJECTED" in retry_prompt
    assert "Your previous passage was" not in retry_prompt

def test_connection_outage_is_retried_with_backoff(_no_backoff_waits: list) -> None:
    """A dropped LLM connection is retried; success on retry is not an error."""
    agent = CitationFinderAgent(model="gpt-oss:20b", show_model_info=False)
    document = {"id": 7, "title": "t", "abstract": ABSTRACT}
    with patch.object(agent, "test_connection", return_value=True), patch.object(
        agent,
        "_generate_and_parse_json",
        side_effect=[ConnectionError("Ollama restarting"), _llm_response(GOOD_PASSAGE)],
    ) as llm:
        citation = agent.extract_citation_from_document("q", document)

    assert citation is not None
    assert citation.passage == GOOD_PASSAGE
    assert llm.call_count == 2
    assert agent.get_validation_stats()["errors"] == 0
    assert len(_no_backoff_waits) == 1


def test_unreachable_server_is_retried_before_counting_an_error(_no_backoff_waits: list) -> None:
    """A failed connection test is retried with backoff too."""
    agent = CitationFinderAgent(model="gpt-oss:20b", show_model_info=False)
    document = {"id": 7, "title": "t", "abstract": ABSTRACT}
    with patch.object(agent, "test_connection", side_effect=[False, True]), patch.object(
        agent, "_generate_and_parse_json", return_value=_llm_response(GOOD_PASSAGE)
    ):
        citation = agent.extract_citation_from_document("q", document)

    assert citation is not None
    assert agent.get_validation_stats()["errors"] == 0
    assert len(_no_backoff_waits) == 1


def test_persistent_outage_is_one_error_naming_the_document(_no_backoff_waits: list) -> None:
    """When every attempt fails, the error is counted once and the document recorded."""
    agent = CitationFinderAgent(
        model="gpt-oss:20b", show_model_info=False, transient_retry_attempts=3
    )
    document = {"id": 7, "title": "t", "abstract": ABSTRACT}
    with patch.object(agent, "test_connection", return_value=True), patch.object(
        agent, "_generate_and_parse_json", side_effect=ConnectionError("Ollama down")
    ) as llm:
        citation = agent.extract_citation_from_document("q", document)

    assert citation is None
    assert llm.call_count == 3
    stats = agent.get_validation_stats()
    assert stats["errors"] == 1
    assert [entry["document_id"] for entry in stats["errored_documents"]] == [7]
    assert "Ollama down" in stats["errored_documents"][0]["error"]
    assert len(_no_backoff_waits) == 2

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
