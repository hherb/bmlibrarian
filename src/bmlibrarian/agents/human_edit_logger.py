"""
Human Edit Logger

Captures human edits/approvals/rejections of LLM output for training and analysis.
Logs to the 'human_edited' table in PostgreSQL.
"""

import json
import logging
from typing import Optional, Dict, Any
from datetime import datetime

logger = logging.getLogger(__name__)


class HumanEditLogger:
    """Logger for capturing human edits to LLM outputs."""

    def __init__(self):
        """Initialize the human edit logger."""
        # Will use the database module's connection manager
        pass

    def log_edit(
        self,
        context: str,
        machine_output: str,
        human_edit: Optional[str] = None,
        log_all: bool = False,
        explicitly_approved: bool = False
    ) -> bool:
        """
        Log an LLM interaction with optional human edit or explicit approval.

        Args:
            context: The complete prompt/context fed to the LLM
            machine_output: The LLM's output/response
            human_edit: Optional human edit/override (None means accepted as-is)
            log_all: If True, log even when no human edit occurred (default: False)
            explicitly_approved: If True, user explicitly approved without changes

        Returns:
            True if logged successfully, False otherwise
        """
        try:
            # Log if there's a human edit, explicit approval, or log_all is True
            if human_edit is not None or explicitly_approved or log_all:
                # For explicit approval, set human to "APPROVED" to indicate no changes but active confirmation
                human_value = human_edit if human_edit is not None else ("APPROVED" if explicitly_approved else None)
                return self._insert_to_database(context, machine_output, human_value)
            else:
                logger.debug("No human interaction to log (machine output passively accepted)")
                return True

        except Exception as e:
            logger.error(f"Failed to log human edit: {e}")
            return False

    def log_document_score_edit(
        self,
        user_question: str,
        document: Dict[str, Any],
        ai_score: int,
        ai_reasoning: str,
        human_score: Optional[int] = None,
        explicitly_approved: bool = False
    ) -> bool:
        """
        Log a document scoring interaction with optional human override or approval.

        Args:
            user_question: The research question being asked
            document: The document being scored
            ai_score: The AI-generated relevance score (0-5)
            ai_reasoning: The AI's reasoning for the score
            human_score: Optional human override score (0-5)
            explicitly_approved: True if user explicitly approved AI score

        Returns:
            True if logged successfully, False otherwise
        """
        context = self._build_scoring_context(user_question, document)
        machine_output = json.dumps({'score': ai_score, 'reasoning': ai_reasoning}, indent=2)

        human_edit = None
        is_approved = explicitly_approved

        if human_score is not None:
            if human_score != ai_score:
                # User changed the score - this is an override
                human_edit = json.dumps({
                    'score': human_score,
                    'edit_type': 'override',
                    'original_ai_score': ai_score
                }, indent=2)
                is_approved = False  # Override, not approval
            else:
                # User entered same score - this is explicit approval
                human_edit = json.dumps({
                    'score': human_score,
                    'edit_type': 'approval',
                    'ai_score': ai_score
                }, indent=2)
                is_approved = True

        return self.log_edit(context, machine_output, human_edit, explicitly_approved=is_approved)

    def log_query_edit(
        self,
        user_question: str,
        system_prompt: str,
        ai_query: str,
        human_query: Optional[str] = None,
        explicitly_approved: bool = False
    ) -> bool:
        """
        Log a query generation interaction with optional human edit or approval.

        Args:
            user_question: The research question from the user
            system_prompt: The system prompt used for query generation
            ai_query: The AI-generated ts_query
            human_query: Optional human-edited query
            explicitly_approved: True if user explicitly approved AI query

        Returns:
            True if logged successfully, False otherwise
        """
        context = f"{system_prompt}\n\nUser Question: {user_question}"
        machine_output = ai_query

        human_edit = None
        is_approved = explicitly_approved

        if human_query:
            if human_query != ai_query:
                # User changed the query - this is an edit
                human_edit = human_query
                is_approved = False
            else:
                # User confirmed same query - this is explicit approval
                human_edit = "APPROVED"
                is_approved = True

        return self.log_edit(context, machine_output, human_edit, explicitly_approved=is_approved)

    def _build_scoring_context(self, user_question: str, document: Dict[str, Any]) -> str:
        """Build the context string showing what was fed to the LLM."""
        title = document.get('title', '')
        abstract = document.get('abstract', '')
        authors = document.get('authors', [])
        publication = document.get('publication', '')
        publication_date = document.get('publication_date', '')

        context_parts = [
            f"User Question: {user_question}",
            "",
            "Document to Evaluate:",
            f"Title: {title}",
            f"Abstract: {abstract}"
        ]

        if authors:
            author_list = ', '.join(authors[:5])
            if len(authors) > 5:
                author_list += f" (and {len(authors) - 5} others)"
            context_parts.append(f"Authors: {author_list}")

        if publication:
            context_parts.append(f"Publication: {publication}")

        if publication_date:
            context_parts.append(f"Publication Date: {publication_date}")

        return "\n".join(context_parts)

    def _insert_to_database(
        self,
        context: str,
        machine: str,
        human: Optional[str]
    ) -> bool:
        """Insert the edit log into the database."""
        try:
            from ..database import get_db_manager

            db_manager = get_db_manager()
            with db_manager.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO human_edited (context, machine, human)
                        VALUES (%s, %s, %s)
                        """,
                        (context, machine, human)
                    )
                    conn.commit()
                    logger.debug("Human edit logged to database")
                    return True

        except Exception as e:
            logger.error(f"Database insert failed: {e}")
            return False

    def log_citation_review(
        self,
        user_question: str,
        citation,
        review_status: Optional[str] = None
    ) -> bool:
        """
        Log a citation review interaction (accepted, refused, or unrated).

        Args:
            user_question: The research question
            citation: The Citation object being reviewed
            review_status: 'accepted', 'refused', or None (unrated)

        Returns:
            True if logged successfully, False otherwise
        """
        # Build context with citation details
        passage = citation.passage if hasattr(citation, 'passage') else citation.get('passage', '')
        summary = citation.summary if hasattr(citation, 'summary') else citation.get('summary', '')
        title = citation.document_title if hasattr(citation, 'document_title') else citation.get('document_title', '')
        abstract = citation.abstract if hasattr(citation, 'abstract') else citation.get('abstract', '')

        context = f"""User Question: {user_question}

Document: {title}

AI Summary: {summary}

Extracted Passage: {passage}

Full Abstract: {abstract}"""

        # Machine output is the citation extraction
        machine_output = json.dumps({
            'passage': passage,
            'summary': summary,
            'relevance_score': citation.relevance_score if hasattr(citation, 'relevance_score') else citation.get('relevance_score', 0)
        }, indent=2)

        # Human review
        human_edit = None
        is_approved = False

        if review_status == 'accepted':
            human_edit = "ACCEPTED"
            is_approved = True
        elif review_status == 'refused':
            human_edit = "REFUSED"
            is_approved = False
        # If None (unrated), we don't log it

        return self.log_edit(context, machine_output, human_edit, explicitly_approved=is_approved)


# Singleton instance
_human_edit_logger = None

def get_human_edit_logger() -> HumanEditLogger:
    """Get the singleton human edit logger instance."""
    global _human_edit_logger
    if _human_edit_logger is None:
        _human_edit_logger = HumanEditLogger()
    return _human_edit_logger
