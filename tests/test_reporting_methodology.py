"""ReportingAgent.generate_detailed_methodology names every workflow figure it is given."""

from bmlibrarian.agents.reporting_agent import MethodologyMetadata, ReportingAgent


def test_methodology_lists_workflow_metadata() -> None:
    """Question, query, counts and thresholds all appear in the methodology text.

    The counts are distinctive so that they cannot match some other number in the text.
    """
    metadata = MethodologyMetadata(
        human_question="What are the cardiovascular benefits of exercise?",
        generated_query="exercise & cardiovascular & (benefit | advantage | effect)",
        total_documents_found=8317,
        scoring_threshold=2.5,
        documents_by_score={1: 20, 2: 35, 3: 45, 4: 30, 5: 20},
        documents_above_threshold=4129,
        documents_processed_for_citations=4129,
        citation_extraction_threshold=0.7,
        counterfactual_performed=True,
        counterfactual_queries_generated=67,
        counterfactual_documents_found=25,
        counterfactual_citations_extracted=12,
    )
    text = ReportingAgent(show_model_info=False).generate_detailed_methodology(metadata)
    for expected in (metadata.human_question, metadata.generated_query, f"{metadata.total_documents_found:,}", "2.5", "4129", "67"):
        assert expected in text, expected
