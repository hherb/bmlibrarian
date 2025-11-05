"""
Demo script for multi-model query performance tracking.

This example demonstrates how to use the QueryPerformanceTracker to analyze
which models with which parameters find the most relevant documents.
"""

import hashlib
from bmlibrarian.agents import QueryAgent
from bmlibrarian.agents.query_generation import QueryPerformanceTracker
from bmlibrarian.config import get_query_generation_config


def demo_query_performance_tracking():
    """Demonstrate query performance tracking with multi-model queries."""

    print("="*80)
    print("MULTI-MODEL QUERY PERFORMANCE TRACKING DEMO")
    print("="*80)

    # Example research question
    research_question = "What are the cardiovascular benefits of regular exercise?"
    print(f"\nResearch Question: {research_question}\n")

    # Create session ID from research question
    session_id = hashlib.md5(research_question.encode()).hexdigest()
    print(f"Session ID: {session_id}\n")

    # Initialize performance tracker (in-memory database)
    tracker = QueryPerformanceTracker()
    tracker.start_session(session_id)
    print("✓ Performance tracker initialized\n")

    # Check if multi-model is enabled
    qg_config = get_query_generation_config()
    if not qg_config.get('multi_model_enabled', False):
        print("❌ Multi-model query generation is not enabled!")
        print("   Enable it in ~/.bmlibrarian/config.json:")
        print('   "query_generation": {"multi_model_enabled": true, ...}')
        return

    print(f"✓ Multi-model enabled: {len(qg_config.get('models', []))} models")
    print(f"   Models: {', '.join(qg_config.get('models', []))}")
    print(f"   Queries per model: {qg_config.get('queries_per_model', 1)}\n")

    # Initialize query agent
    query_agent = QueryAgent()

    # Execute multi-query search with performance tracking
    print("="*80)
    print("EXECUTING MULTI-QUERY SEARCH")
    print("="*80)

    documents = list(query_agent.find_abstracts_multi_query(
        question=research_question,
        max_rows=50,
        performance_tracker=tracker,
        session_id=session_id
    ))

    print(f"\n✓ Found {len(documents)} unique documents\n")

    # Simulate document scoring (in a real workflow, this would use DocumentScoringAgent)
    print("="*80)
    print("SIMULATING DOCUMENT SCORING")
    print("="*80)

    # For demo purposes, assign random-ish scores based on document ID
    document_scores = {}
    for doc in documents:
        doc_id = doc.get('id')
        if doc_id:
            # Deterministic "score" based on doc_id for demo
            score = (doc_id % 5) + 1  # Scores 1-5
            document_scores[doc_id] = float(score)

    print(f"✓ Generated scores for {len(document_scores)} documents\n")

    # Update performance tracker with scores
    tracker.update_document_scores(session_id, document_scores)
    print("✓ Updated performance tracker with document scores\n")

    # Get and display performance statistics
    print("="*80)
    print("QUERY PERFORMANCE STATISTICS")
    print("="*80)

    score_threshold = 3.0
    stats = tracker.get_query_statistics(session_id, score_threshold=score_threshold)

    if stats:
        formatted_stats = QueryAgent.format_query_performance_stats(
            stats, score_threshold=score_threshold
        )
        print(formatted_stats)
    else:
        print("No statistics available")

    # Get model performance summary
    print("\n" + "="*80)
    print("MODEL PERFORMANCE SUMMARY")
    print("="*80)

    model_summary = tracker.get_model_performance_summary(
        session_id=session_id,
        score_threshold=score_threshold
    )

    if model_summary:
        for model, metrics in model_summary.items():
            print(f"\n{model}:")
            print(f"  Queries executed: {metrics['queries_executed']}")
            print(f"  Avg documents found: {metrics['avg_documents']:.1f}")
            print(f"  Avg high-scoring: {metrics['avg_high_scoring']:.1f}")
            print(f"  Avg execution time: {metrics['avg_execution_time']:.2f}s")
            print(f"  Total documents: {metrics['total_documents_found']}")
    else:
        print("No model summary available")

    print("\n" + "="*80)
    print("DEMO COMPLETE")
    print("="*80)

    # Clean up
    tracker.close()


if __name__ == "__main__":
    try:
        demo_query_performance_tracking()
    except KeyboardInterrupt:
        print("\n\nDemo interrupted by user")
    except Exception as e:
        print(f"\n\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
