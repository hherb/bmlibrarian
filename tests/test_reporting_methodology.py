"""ReportingAgent.generate_detailed_methodology names every workflow figure it is given."""

from bmlibrarian.agents.reporting_agent import MethodologyMetadata, ReportingAgent


def test_methodology_lists_workflow_metadata() -> None:
    """Question, query, counts and thresholds all appear in the methodology text."""
    metadata = MethodologyMetadata(
        human_question="What are the cardiovascular benefits of exercise?",
        generated_query="exercise & cardiovascular & (benefit | advantage | effect)",
        total_documents_found=150,
        scoring_threshold=2.5,
        documents_by_score={1: 20, 2: 35, 3: 45, 4: 30, 5: 20},
        documents_above_threshold=95,
        documents_processed_for_citations=95,
        citation_extraction_threshold=0.7,
        counterfactual_performed=True,
        counterfactual_queries_generated=8,
        counterfactual_documents_found=25,
        counterfactual_citations_extracted=12,
    )
    text = ReportingAgent(show_model_info=False).generate_detailed_methodology(metadata)
    for expected in (metadata.human_question, metadata.generated_query, "150", "2.5", "95", "8"):
        assert expected in text, expected
