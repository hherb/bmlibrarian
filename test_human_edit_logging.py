#!/usr/bin/env python3
"""
Test script for human edit logging functionality.

Tests the HumanEditLogger with document scoring and query editing scenarios.
"""

from bmlibrarian.agents import get_human_edit_logger
import json

def test_document_score_logging():
    """Test logging of document score edits."""
    print("Testing document score logging...")

    logger = get_human_edit_logger()

    # Sample document
    test_doc = {
        'id': 12345,
        'title': 'Cardiovascular Benefits of Exercise in Elderly Patients',
        'abstract': 'This randomized controlled trial examined the effects of regular aerobic exercise on cardiovascular health in patients over 65 years of age. Results showed significant improvements in blood pressure, heart rate variability, and overall cardiovascular function.',
        'authors': ['Smith, J.', 'Johnson, A.', 'Williams, B.'],
        'publication': 'Journal of Cardiology',
        'publication_date': '2023-05-15'
    }

    # Test case 1: Human override (AI scored 3, human changed to 4)
    result = logger.log_document_score_edit(
        user_question="What are the cardiovascular benefits of exercise in elderly populations?",
        document=test_doc,
        ai_score=3,
        ai_reasoning="Document provides relevant information on exercise and cardiovascular health in elderly, but lacks comprehensive data on all cardiovascular benefits.",
        human_score=4
    )

    if result:
        print("✅ Successfully logged document score edit (override: 3 → 4)")
    else:
        print("❌ Failed to log document score edit")

    # Test case 2: No human edit (AI score accepted)
    result = logger.log_document_score_edit(
        user_question="What are the cardiovascular benefits of exercise in elderly populations?",
        document=test_doc,
        ai_score=4,
        ai_reasoning="Document comprehensively addresses cardiovascular benefits of exercise in elderly patients.",
        human_score=None  # No override
    )

    if result:
        print("✅ Successfully handled no edit case (AI score accepted)")
    else:
        print("❌ Failed to handle no edit case")


def test_query_edit_logging():
    """Test logging of query edits."""
    print("\nTesting query edit logging...")

    logger = get_human_edit_logger()

    ai_query = "(cardiovascular | cardiac) & (exercise | physical activity) & elderly"
    human_query = "(cardiovascular | cardiac | heart) & exercise & (elderly | aged | geriatric)"

    result = logger.log_query_edit(
        user_question="What are the cardiovascular benefits of exercise in elderly populations?",
        system_prompt="Convert the user's medical research question into a PostgreSQL ts_query...",
        ai_query=ai_query,
        human_query=human_query
    )

    if result:
        print("✅ Successfully logged query edit")
    else:
        print("❌ Failed to log query edit")


def verify_database_entries():
    """Verify entries were written to the database."""
    print("\nVerifying database entries...")

    try:
        from bmlibrarian.database import get_db_manager

        db_manager = get_db_manager()
        with db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                # Count recent entries
                cur.execute("""
                    SELECT COUNT(*),
                           MAX(timestamp) as latest
                    FROM human_edited
                    WHERE timestamp > NOW() - INTERVAL '1 minute'
                """)
                count, latest = cur.fetchone()
                print(f"✅ Found {count} entries in the last minute")
                if latest:
                    print(f"   Latest entry at: {latest}")

                # Show most recent entry
                cur.execute("""
                    SELECT id,
                           LEFT(context, 100) as context_preview,
                           LEFT(machine, 100) as machine_preview,
                           LEFT(human, 100) as human_preview,
                           timestamp
                    FROM human_edited
                    ORDER BY timestamp DESC
                    LIMIT 1
                """)
                entry = cur.fetchone()
                if entry:
                    print(f"\n   Most recent entry (ID {entry[0]}):")
                    print(f"   Context: {entry[1]}...")
                    print(f"   Machine: {entry[2]}...")
                    print(f"   Human: {entry[3]}...")
                    print(f"   Time: {entry[4]}")

    except Exception as e:
        print(f"❌ Failed to verify database entries: {e}")


if __name__ == "__main__":
    print("=" * 60)
    print("Human Edit Logger Test Suite")
    print("=" * 60)

    test_document_score_logging()
    test_query_edit_logging()
    verify_database_entries()

    print("\n" + "=" * 60)
    print("Test suite completed!")
    print("=" * 60)
