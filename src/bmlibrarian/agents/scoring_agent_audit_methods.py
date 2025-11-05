"""
Audit-aware methods for DocumentScoringAgent.

These methods should be added to the DocumentScoringAgent class.
"""

def batch_evaluate_with_audit(
    self,
    research_question_id: int,
    session_id: int,
    query_id: int,
    user_question: str,
    documents: list[Dict],
    skip_already_scored: bool = True
) -> list[tuple[Dict, ScoringResult, int]]:
    """
    Evaluate multiple documents WITH AUDIT TRACKING and resumption support.

    CRITICAL: Skips documents already scored by this evaluator (resumption).

    Args:
        research_question_id: ID of the research question
        session_id: ID of the current session
        query_id: ID of the query that found these documents
        user_question: The user's question
        documents: List of document dictionaries (must include 'id' field)
        skip_already_scored: If True, skip documents already scored by this evaluator

    Returns:
        List of tuples: (document, scoring_result, scoring_id)
        - scoring_id is the database ID for the score record

    Raises:
        RuntimeError: If audit tracking not enabled

    Example:
        >>> import psycopg
        >>> conn = psycopg.connect(dbname="knowledgebase", user="hherb")
        >>> agent = DocumentScoringAgent(audit_conn=conn)
        >>> results = agent.batch_evaluate_with_audit(
        ...     research_question_id=1,
        ...     session_id=1,
        ...     query_id=1,
        ...     user_question="What are the benefits of exercise?",
        ...     documents=doc_list
        ... )
        >>> for doc, score_result, scoring_id in results:
        ...     print(f"Doc {doc['id']}: score={score_result['score']}, scoring_id={scoring_id}")
    """
    if not self._document_tracker or not self._evaluator_id:
        raise RuntimeError("Audit tracking not enabled. Pass audit_conn to __init__()")

    if not user_question or not user_question.strip():
        raise ValueError("User question cannot be empty")

    if not documents or not isinstance(documents, list):
        raise ValueError("Documents must be a non-empty list")

    results = []
    skipped_count = 0

    self._call_callback("batch_evaluation_started", f"Evaluating {len(documents)} documents with audit tracking")

    for i, doc in enumerate(documents):
        try:
            doc_id = doc.get('id')
            if not doc_id:
                logger.error(f"Document {i+1} missing 'id' field - cannot track in audit")
                continue

            # RESUMPTION CHECK: Has this evaluator already scored this document for this question?
            if skip_already_scored and self._document_tracker.is_document_scored(
                research_question_id, doc_id, self._evaluator_id
            ):
                # Skip - already scored by this evaluator
                logger.debug(f"Skipping document {doc_id} - already scored by evaluator {self._evaluator_id}")
                skipped_count += 1
                continue

            self._call_callback("document_evaluation_progress", f"Document {i+1}/{len(documents)}")

            # Score the document
            scoring_result = self.evaluate_document(user_question, doc)

            # Record score in audit database
            scoring_id = self._document_tracker.record_document_score(
                research_question_id=research_question_id,
                document_id=doc_id,
                session_id=session_id,
                first_query_id=query_id,
                evaluator_id=self._evaluator_id,
                relevance_score=scoring_result['score'],
                reasoning=scoring_result['reasoning']
            )

            results.append((doc, scoring_result, scoring_id))

        except Exception as e:
            logger.error(f"Failed to evaluate document {i+1}: {e}")
            # Continue with other documents
            continue

    total_evaluated = len(results)
    self._call_callback(
        "batch_evaluation_completed",
        f"Evaluated {total_evaluated} documents, skipped {skipped_count} already scored"
    )

    logger.info(f"Scored {total_evaluated} documents, skipped {skipped_count} (resumption)")

    return results


def get_unscored_documents(
    self,
    research_question_id: int,
    documents: list[Dict]
) -> list[Dict]:
    """
    Filter documents to only those NOT YET SCORED by this evaluator.

    CRITICAL FOR RESUMPTION: Returns only documents that need scoring.

    Args:
        research_question_id: ID of the research question
        documents: List of document dictionaries (must include 'id' field)

    Returns:
        Filtered list of documents not yet scored by this evaluator

    Raises:
        RuntimeError: If audit tracking not enabled

    Example:
        >>> unscored = agent.get_unscored_documents(question_id, all_documents)
        >>> print(f"Need to score {len(unscored)} out of {len(all_documents)} documents")
    """
    if not self._document_tracker or not self._evaluator_id:
        raise RuntimeError("Audit tracking not enabled. Pass audit_conn to __init__()")

    # Get list of unscored document IDs from database
    unscored_ids_set = set(self._document_tracker.get_unscored_documents(
        research_question_id, self._evaluator_id
    ))

    # Filter documents to only unscored ones
    unscored_docs = [
        doc for doc in documents
        if doc.get('id') in unscored_ids_set
    ]

    logger.info(f"Found {len(unscored_docs)} unscored documents out of {len(documents)} total")

    return unscored_docs


def get_evaluator_id(self) -> Optional[int]:
    """
    Get the evaluator ID for this agent instance.

    Returns:
        Evaluator ID if audit tracking enabled, None otherwise
    """
    return self._evaluator_id
