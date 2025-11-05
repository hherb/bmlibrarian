"""
Demonstration of Audit Tracking with Evaluator Integration.

Shows how to use evaluators for proper multi-model tracking and resumption.
"""

import psycopg
from bmlibrarian.audit import (
    SessionTracker,
    DocumentTracker,
    CitationTracker,
    ReportTracker,
    EvaluatorManager
)


def demo_with_evaluators():
    """Demonstrate audit tracking with evaluator integration."""

    # Connect to database
    conn = psycopg.connect(
        dbname="bmlibrarian_dev",
        user="hherb",
        host="localhost"
    )

    try:
        # Initialize all trackers
        session_tracker = SessionTracker(conn)
        document_tracker = DocumentTracker(conn)
        citation_tracker = CitationTracker(conn)
        report_tracker = ReportTracker(conn)
        evaluator_manager = EvaluatorManager(conn)

        print("=" * 80)
        print("AUDIT TRACKING WITH EVALUATORS DEMO")
        print("=" * 80)

        # ====================================================================
        # SCENARIO 1: Initial research with Model A
        # ====================================================================

        print("\n" + "=" * 80)
        print("SCENARIO 1: Initial Research with MedGemma 27B")
        print("=" * 80)

        question = "What are the cardiovascular benefits of regular exercise?"
        print(f"\nResearch Question: {question}")

        # Step 1: Get or create research question
        question_id = session_tracker.get_or_create_research_question(question, user_id=1)
        print(f"Research Question ID: {question_id}")

        # Step 2: Create evaluator for MedGemma 27B with specific parameters
        evaluator_medgemma = evaluator_manager.get_evaluator_for_agent(
            agent_type='scoring',
            model_name='medgemma-27b-text-it-Q8_0:latest',
            temperature=0.1,
            top_p=0.9
        )
        print(f"Evaluator ID (MedGemma 27B): {evaluator_medgemma}")

        # Step 3: Start session
        session_id = session_tracker.start_session(
            question_id,
            session_type='initial',
            config_snapshot={'scoring_model': 'medgemma-27b', 'temperature': 0.1}
        )
        print(f"Session ID: {session_id}")

        # Step 4: Simulate finding documents
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO audit.generated_queries (
                    research_question_id, session_id, evaluator_id,
                    attempt_number, query_text, query_text_sanitized,
                    generation_time_ms, execution_time_ms, documents_found_count
                ) VALUES (%s, %s, %s, 1, 'cardiovascular & exercise', 'cardiovascular & exercise', 120.5, 250.3, 5)
                RETURNING query_id
            """, (question_id, session_id, evaluator_medgemma))
            query_id = cur.fetchone()[0]
            conn.commit()

        print(f"Generated Query ID: {query_id}")

        # Step 5: Record found documents
        document_ids = [100, 101, 102, 103, 104]
        document_tracker.record_query_documents(question_id, query_id, document_ids)
        print(f"Discovered {len(document_ids)} documents: {document_ids}")

        # Step 6: Check unscored documents for this evaluator
        unscored = document_tracker.get_unscored_documents(question_id, evaluator_medgemma)
        print(f"Unscored by MedGemma: {len(unscored)} documents")

        # Step 7: Score documents with MedGemma 27B
        print("\nScoring documents with MedGemma 27B...")
        for doc_id in document_ids:
            score = 4 if doc_id % 2 == 0 else 3  # Simulate varying scores
            scoring_id = document_tracker.record_document_score(
                question_id, doc_id, session_id, query_id,
                evaluator_medgemma, score,
                reasoning=f"Document {doc_id} relevance assessed by MedGemma"
            )
            print(f"  Doc {doc_id}: score={score}, scoring_id={scoring_id}")

        # Step 8: Complete session
        session_tracker.complete_session(session_id, status='completed')
        print("\nSession 1 completed")

        # ====================================================================
        # SCENARIO 2: Same question, different model (GPT-OSS)
        # ====================================================================

        print("\n" + "=" * 80)
        print("SCENARIO 2: Re-score with Different Model (GPT-OSS)")
        print("=" * 80)

        # Step 1: Same question returns same question_id
        question_id_2 = session_tracker.get_or_create_research_question(question, user_id=1)
        print(f"\nSame question → Same ID: {question_id_2} (matches {question_id}: {question_id_2 == question_id})")

        # Step 2: Create evaluator for GPT-OSS with different parameters
        evaluator_gptoss = evaluator_manager.get_evaluator_for_agent(
            agent_type='scoring',
            model_name='gpt-oss:20b',
            temperature=0.2,
            top_p=0.95
        )
        print(f"Evaluator ID (GPT-OSS): {evaluator_gptoss}")

        # Step 3: Start new session
        session_id_2 = session_tracker.start_session(
            question_id,
            session_type='reanalysis',
            user_notes="Re-scoring with GPT-OSS for comparison"
        )
        print(f"Session ID: {session_id_2}")

        # Step 4: Check unscored - ALL documents need scoring by GPT-OSS
        unscored_gptoss = document_tracker.get_unscored_documents(question_id, evaluator_gptoss)
        print(f"\nUnscored by GPT-OSS: {len(unscored_gptoss)} documents (ALL need scoring by this evaluator)")

        # Step 5: Score same documents with GPT-OSS
        print("\nScoring documents with GPT-OSS...")
        for doc_id in document_ids:
            # GPT-OSS might score differently
            score = 5 if doc_id % 2 == 0 else 2  # Different scores than MedGemma
            scoring_id = document_tracker.record_document_score(
                question_id, doc_id, session_id_2, query_id,
                evaluator_gptoss, score,
                reasoning=f"Document {doc_id} relevance assessed by GPT-OSS"
            )
            print(f"  Doc {doc_id}: score={score}, scoring_id={scoring_id}")

        session_tracker.complete_session(session_id_2, status='completed')

        # ====================================================================
        # SCENARIO 3: Resumption - Adding new documents with MedGemma
        # ====================================================================

        print("\n" + "=" * 80)
        print("SCENARIO 3: Resumption - Add New Documents (MedGemma)")
        print("=" * 80)

        # Step 1: Start expansion session
        session_id_3 = session_tracker.start_session(
            question_id,
            session_type='expansion',
            user_notes="Adding more recent studies"
        )
        print(f"\nExpansion session ID: {session_id_3}")

        # Step 2: New query finds some new documents + some old ones
        new_document_ids = [103, 104, 105, 106, 107]  # 103, 104 are old; 105, 106, 107 are new
        print(f"New query found {len(new_document_ids)} documents: {new_document_ids}")

        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO audit.generated_queries (
                    research_question_id, session_id, evaluator_id,
                    attempt_number, query_text, query_text_sanitized,
                    generation_time_ms, execution_time_ms, documents_found_count
                ) VALUES (%s, %s, %s, 1, 'cardiovascular & exercise & benefit',
                         'cardiovascular & exercise & benefit', 110.2, 230.1, 5)
                RETURNING query_id
            """, (question_id, session_id_3, evaluator_medgemma))
            query_id_2 = cur.fetchone()[0]
            conn.commit()

        document_tracker.record_query_documents(question_id, query_id_2, new_document_ids)

        # Step 3: Check unscored by MedGemma - RESUMPTION BENEFIT!
        unscored_medgemma = document_tracker.get_unscored_documents(question_id, evaluator_medgemma)
        print(f"\nUnscored by MedGemma: {len(unscored_medgemma)} documents")
        print(f"  Unscored IDs: {unscored_medgemma}")
        print(f"  → Only NEW documents ({len(unscored_medgemma)}) need scoring!")
        print(f"  → Documents 103, 104 already scored (SKIPPED)")

        # Step 4: Score only new documents
        print("\nScoring ONLY new documents...")
        for doc_id in unscored_medgemma:
            already_scored = document_tracker.is_document_scored(question_id, doc_id, evaluator_medgemma)
            print(f"  Doc {doc_id}: already_scored={already_scored}")

            if not already_scored:
                score = 4
                scoring_id = document_tracker.record_document_score(
                    question_id, doc_id, session_id_3, query_id_2,
                    evaluator_medgemma, score,
                    reasoning=f"New document {doc_id}"
                )
                print(f"    → Scored: {score}, scoring_id={scoring_id}")

        # ====================================================================
        # SCENARIO 4: View Score Comparisons
        # ====================================================================

        print("\n" + "=" * 80)
        print("SCENARIO 4: Compare Scores Across Evaluators")
        print("=" * 80)

        # Get evaluator names
        medgemma_info = evaluator_manager.get_evaluator_info(evaluator_medgemma)
        gptoss_info = evaluator_manager.get_evaluator_info(evaluator_gptoss)

        print(f"\nEvaluator A: {medgemma_info['name']}")
        print(f"Evaluator B: {gptoss_info['name']}")
        print("\nDocument Score Comparison:")
        print(f"{'Doc ID':<10} {'MedGemma':<15} {'GPT-OSS':<15}")
        print("-" * 40)

        for doc_id in [100, 101, 102, 103, 104]:
            # Get MedGemma score
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT relevance_score FROM audit.document_scores
                    WHERE research_question_id = %s
                      AND document_id = %s
                      AND evaluator_id = %s
                """, (question_id, doc_id, evaluator_medgemma))
                medgemma_score = cur.fetchone()
                medgemma_score = medgemma_score[0] if medgemma_score else "N/A"

                # Get GPT-OSS score
                cur.execute("""
                    SELECT relevance_score FROM audit.document_scores
                    WHERE research_question_id = %s
                      AND document_id = %s
                      AND evaluator_id = %s
                """, (question_id, doc_id, evaluator_gptoss))
                gptoss_score = cur.fetchone()
                gptoss_score = gptoss_score[0] if gptoss_score else "N/A"

            print(f"{doc_id:<10} {str(medgemma_score):<15} {str(gptoss_score):<15}")

        # ====================================================================
        # Summary
        # ====================================================================

        print("\n" + "=" * 80)
        print("SUMMARY")
        print("=" * 80)

        print("\nKey Benefits Demonstrated:")
        print("✓ Multiple evaluators can score same documents independently")
        print("✓ Resumption works per-evaluator (avoid re-scoring with same model)")
        print("✓ Model comparison: see how different models score same content")
        print("✓ Incremental research: add new documents without re-processing old ones")
        print("✓ Complete audit trail: track which model scored which document when")

        # Get statistics
        with conn.cursor() as cur:
            cur.execute("""
                SELECT COUNT(DISTINCT evaluator_id) as evaluator_count,
                       COUNT(*) as total_scores
                FROM audit.document_scores
                WHERE research_question_id = %s
            """, (question_id,))
            stats = cur.fetchone()

        print(f"\nStatistics for question {question_id}:")
        print(f"  Total evaluators used: {stats[0]}")
        print(f"  Total scores recorded: {stats[1]}")
        print(f"  Documents scored: {len(set(document_ids + new_document_ids))}")
        print(f"  Sessions conducted: 3")

    finally:
        conn.close()


if __name__ == "__main__":
    demo_with_evaluators()
