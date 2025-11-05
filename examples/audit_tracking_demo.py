"""
Demonstration of the Audit Tracking System.

Shows how to use the audit tracking classes to track a complete research workflow.
"""

import psycopg
from bmlibrarian.audit import SessionTracker, DocumentTracker, CitationTracker, ReportTracker


def demo_audit_tracking():
    """Demonstrate the audit tracking system."""

    # Connect to database
    conn = psycopg.connect(
        dbname="bmlibrarian_dev",
        user="hherb",
        host="localhost"
    )

    try:
        # Initialize trackers
        session_tracker = SessionTracker(conn)
        document_tracker = DocumentTracker(conn)
        citation_tracker = CitationTracker(conn)
        report_tracker = ReportTracker(conn)

        print("=" * 80)
        print("AUDIT TRACKING DEMO")
        print("=" * 80)

        # Step 1: Create research question
        print("\n1. Creating research question...")
        question = "What are the cardiovascular benefits of regular exercise?"
        question_id = session_tracker.get_or_create_research_question(question)
        print(f"   Research Question ID: {question_id}")

        # Step 2: Start session
        print("\n2. Starting research session...")
        session_id = session_tracker.start_session(
            question_id,
            session_type='initial',
            config_snapshot={'model': 'gpt-oss:20b', 'temperature': 0.1}
        )
        print(f"   Session ID: {session_id}")

        # Step 3: Simulate query generation (would be done by QueryAgent)
        print("\n3. Recording generated query...")
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO audit.generated_queries (
                    research_question_id, session_id, model_name, temperature, top_p,
                    attempt_number, query_text, query_text_sanitized, generation_time_ms, execution_time_ms
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING query_id
            """, (
                question_id, session_id, 'medgemma-27b-text-it-Q8_0:latest', 0.1, 0.9,
                1, 'cardiovascular & exercise & benefit', 'cardiovascular & exercise & benefit',
                150.5, 320.8
            ))
            query_id = cur.fetchone()[0]
            conn.commit()
        print(f"   Query ID: {query_id}")

        # Step 4: Record found documents
        print("\n4. Recording discovered documents...")
        document_ids = [12345, 12346, 12347]
        document_tracker.record_query_documents(question_id, query_id, document_ids)
        print(f"   Recorded {len(document_ids)} documents")

        # Step 5: Check which documents need scoring
        print("\n5. Checking for unscored documents...")
        unscored = document_tracker.get_unscored_documents(question_id)
        print(f"   Unscored documents: {len(unscored)}")

        # Step 6: Score documents
        print("\n6. Scoring documents...")
        for doc_id in document_ids[:2]:  # Score first 2
            scoring_id = document_tracker.record_document_score(
                question_id, doc_id, session_id, query_id,
                'medgemma-27b-text-it-Q8_0:latest', 0.1,
                relevance_score=4,
                reasoning="Highly relevant to cardiovascular exercise benefits"
            )
            print(f"   Scored document {doc_id}: scoring_id={scoring_id}")

        # Step 7: Check again - should be only 1 unscored now
        print("\n7. Checking unscored documents again...")
        unscored = document_tracker.get_unscored_documents(question_id)
        print(f"   Unscored documents: {len(unscored)} (was 3, now should be 1)")

        # Step 8: Extract citation
        print("\n8. Extracting citation from high-scoring document...")
        # Get scoring_id for first document
        score_info = document_tracker.get_document_score(question_id, document_ids[0])
        citation_id = citation_tracker.record_citation(
            question_id, document_ids[0], session_id, score_info['scoring_id'],
            'gpt-oss:20b', 0.1,
            passage="Regular aerobic exercise significantly reduces cardiovascular disease risk.",
            summary="Exercise reduces CVD risk",
            relevance_confidence=0.92
        )
        print(f"   Citation ID: {citation_id}")

        # Step 9: Generate report
        print("\n9. Generating preliminary report...")
        report_id = report_tracker.record_report(
            question_id, session_id, 'preliminary',
            'gpt-oss:20b', 0.2,
            report_text="# Cardiovascular Benefits of Exercise\n\nRegular exercise provides...",
            citation_count=1
        )
        print(f"   Report ID: {report_id}")

        # Step 10: Query statistics
        print("\n10. Getting statistics...")
        score_dist = document_tracker.count_documents_by_score(question_id)
        print(f"   Document score distribution: {score_dist}")

        citation_counts = citation_tracker.count_citations(question_id)
        print(f"   Citation counts: {citation_counts}")

        # Step 11: Complete session
        print("\n11. Completing session...")
        session_tracker.complete_session(session_id, status='completed')
        print("   Session marked as completed")

        # Step 12: Demonstrate resumption
        print("\n12. DEMONSTRATING RESUMPTION...")
        print("   Starting new 'expansion' session for same question...")

        session_id_2 = session_tracker.start_session(
            question_id,
            session_type='expansion',
            user_notes="Adding more recent studies"
        )
        print(f"   New session ID: {session_id_2}")

        # Check if we've already scored our original documents
        for doc_id in document_ids:
            already_scored = document_tracker.is_document_scored(question_id, doc_id)
            print(f"   Document {doc_id} already scored: {already_scored}")

        print("\n   RESUMPTION BENEFIT: Documents 12345 and 12346 won't be re-scored!")
        print("   Only document 12347 (and any new ones) need scoring.")

        # Get existing citations for reuse
        existing_citations = citation_tracker.get_accepted_citations(question_id)
        print(f"\n   Found {len(existing_citations)} existing accepted citations to reuse")

        print("\n" + "=" * 80)
        print("DEMO COMPLETE")
        print("=" * 80)
        print("\nKey Features Demonstrated:")
        print("✓ Research question deduplication")
        print("✓ Session tracking (initial + expansion)")
        print("✓ Query and document tracking")
        print("✓ Document scoring with resumption support")
        print("✓ Citation extraction and tracking")
        print("✓ Report generation")
        print("✓ Statistics and analytics")
        print("✓ RESUMPTION: Avoid re-scoring already processed documents")

    finally:
        conn.close()


if __name__ == "__main__":
    demo_audit_tracking()
