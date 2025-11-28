"""
Data Manager for Audit Validation GUI.

Provides data loading and persistence for the audit validation interface,
including research questions, audit items, and validation records.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict, Any

import psycopg
from psycopg.rows import dict_row

from bmlibrarian.audit import (
    ValidationTracker,
    TargetType,
    ValidationStatus,
    Severity,
    ValidationCategory,
    HumanValidation,
    UnvalidatedCounts
)

logger = logging.getLogger(__name__)


@dataclass
class ResearchQuestionSummary:
    """Summary of a research question for list display."""

    research_question_id: int
    question_text: str
    created_at: datetime
    last_activity_at: datetime
    total_sessions: int
    status: str
    validation_progress: Dict[str, int] = field(default_factory=dict)


@dataclass
class QueryAuditItem:
    """A generated query audit item for validation."""

    query_id: int
    research_question_id: int
    session_id: int
    query_text: str
    query_text_sanitized: str
    human_edited: bool
    original_ai_query: Optional[str]
    documents_found_count: Optional[int]
    created_at: datetime
    evaluator_name: Optional[str] = None
    validation: Optional[HumanValidation] = None


@dataclass
class ScoreAuditItem:
    """A document score audit item for validation."""

    scoring_id: int
    research_question_id: int
    document_id: int
    session_id: int
    evaluator_id: int
    evaluator_name: str
    relevance_score: int
    reasoning: Optional[str]
    scored_at: datetime
    # Document info
    document_title: Optional[str] = None
    document_authors: Optional[str] = None
    document_year: Optional[int] = None
    document_abstract: Optional[str] = None
    validation: Optional[HumanValidation] = None


@dataclass
class CitationAuditItem:
    """An extracted citation audit item for validation."""

    citation_id: int
    research_question_id: int
    document_id: int
    session_id: int
    scoring_id: int
    evaluator_id: int
    evaluator_name: str
    passage: str
    summary: str
    relevance_confidence: Optional[float]
    human_review_status: Optional[str]
    extracted_at: datetime
    # Document info
    document_title: Optional[str] = None
    document_authors: Optional[str] = None
    validation: Optional[HumanValidation] = None


@dataclass
class ReportAuditItem:
    """A generated report audit item for validation."""

    report_id: int
    research_question_id: int
    session_id: int
    report_type: str
    evaluator_id: Optional[int]
    evaluator_name: Optional[str]
    citation_count: Optional[int]
    report_text: str
    report_format: str
    generated_at: datetime
    human_edited: bool
    is_final: bool
    validation: Optional[HumanValidation] = None


@dataclass
class CounterfactualAuditItem:
    """A counterfactual question audit item for validation."""

    question_id: int
    research_question_id: int
    analysis_id: int
    question_text: str
    target_claim: Optional[str]
    priority: Optional[str]
    query_generated: Optional[str]
    documents_found_count: Optional[int]
    validation: Optional[HumanValidation] = None


class AuditValidationDataManager:
    """
    Manages data loading and persistence for the audit validation GUI.

    Provides methods to:
    - Load research questions and their audit items
    - Load audit items by type (queries, scores, citations, reports, counterfactuals)
    - Record and update validations
    - Get validation statistics
    """

    def __init__(self, conn: psycopg.Connection):
        """
        Initialize the data manager.

        Args:
            conn: Active psycopg connection to PostgreSQL database
        """
        self.conn = conn
        self.validation_tracker = ValidationTracker(conn)

    def get_research_questions(
        self,
        status: Optional[str] = None,
        limit: int = 100
    ) -> List[ResearchQuestionSummary]:
        """
        Get list of research questions with validation progress.

        Args:
            status: Optional filter by status ('active', 'archived', 'superseded')
            limit: Maximum number of questions to return

        Returns:
            List of ResearchQuestionSummary records
        """
        query = """
            SELECT
                rq.research_question_id,
                rq.question_text,
                rq.created_at,
                rq.last_activity_at,
                rq.total_sessions,
                rq.status
            FROM audit.research_questions rq
            WHERE 1=1
        """
        params: List[Any] = []

        if status:
            query += " AND rq.status = %s"
            params.append(status)

        query += " ORDER BY rq.last_activity_at DESC LIMIT %s"
        params.append(limit)

        results = []
        with self.conn.cursor(row_factory=dict_row) as cur:
            cur.execute(query, params)
            for row in cur.fetchall():
                summary = ResearchQuestionSummary(
                    research_question_id=row['research_question_id'],
                    question_text=row['question_text'],
                    created_at=row['created_at'],
                    last_activity_at=row['last_activity_at'],
                    total_sessions=row['total_sessions'],
                    status=row['status'],
                    validation_progress={}
                )
                # Load validation progress
                counts = self.validation_tracker.get_unvalidated_counts(
                    row['research_question_id']
                )
                for count in counts:
                    summary.validation_progress[count.target_type.value] = {
                        'total': count.total_count,
                        'validated': count.validated_count,
                        'unvalidated': count.unvalidated_count
                    }
                results.append(summary)

        return results

    def get_queries_for_question(
        self,
        research_question_id: int,
        include_validated: bool = True
    ) -> List[QueryAuditItem]:
        """
        Get generated queries for a research question.

        Args:
            research_question_id: ID of the research question
            include_validated: Whether to include already-validated items

        Returns:
            List of QueryAuditItem records
        """
        query = """
            SELECT
                gq.query_id,
                gq.research_question_id,
                gq.session_id,
                gq.query_text,
                gq.query_text_sanitized,
                gq.human_edited,
                gq.original_ai_query,
                gq.documents_found_count,
                gq.created_at,
                e.name as evaluator_name
            FROM audit.generated_queries gq
            LEFT JOIN public.evaluators e ON gq.evaluator_id = e.id
            WHERE gq.research_question_id = %s
            ORDER BY gq.created_at DESC
        """

        items = []
        with self.conn.cursor(row_factory=dict_row) as cur:
            cur.execute(query, (research_question_id,))
            for row in cur.fetchall():
                item = QueryAuditItem(
                    query_id=row['query_id'],
                    research_question_id=row['research_question_id'],
                    session_id=row['session_id'],
                    query_text=row['query_text'],
                    query_text_sanitized=row['query_text_sanitized'],
                    human_edited=row['human_edited'],
                    original_ai_query=row.get('original_ai_query'),
                    documents_found_count=row.get('documents_found_count'),
                    created_at=row['created_at'],
                    evaluator_name=row.get('evaluator_name'),
                    validation=self.validation_tracker.get_validation(
                        TargetType.QUERY, row['query_id']
                    )
                )
                if include_validated or item.validation is None:
                    items.append(item)

        return items

    def get_scores_for_question(
        self,
        research_question_id: int,
        include_validated: bool = True
    ) -> List[ScoreAuditItem]:
        """
        Get document scores for a research question.

        Args:
            research_question_id: ID of the research question
            include_validated: Whether to include already-validated items

        Returns:
            List of ScoreAuditItem records

        Note:
            Document metadata is fetched via JOIN for bulk efficiency rather than
            individual get_document_details() calls (golden rule #18 exception
            for performance in data layer bulk operations).
        """
        query = """
            SELECT
                ds.scoring_id,
                ds.research_question_id,
                ds.document_id,
                ds.session_id,
                ds.evaluator_id,
                e.name as evaluator_name,
                ds.relevance_score,
                ds.reasoning,
                ds.scored_at,
                d.title as document_title,
                d.authors as document_authors,
                d.year as document_year,
                d.abstract as document_abstract
            FROM audit.document_scores ds
            LEFT JOIN public.evaluators e ON ds.evaluator_id = e.id
            LEFT JOIN public.document d ON ds.document_id = d.id
            WHERE ds.research_question_id = %s
            ORDER BY ds.relevance_score DESC, ds.scored_at DESC
        """

        items = []
        with self.conn.cursor(row_factory=dict_row) as cur:
            cur.execute(query, (research_question_id,))
            for row in cur.fetchall():
                item = ScoreAuditItem(
                    scoring_id=row['scoring_id'],
                    research_question_id=row['research_question_id'],
                    document_id=row['document_id'],
                    session_id=row['session_id'],
                    evaluator_id=row['evaluator_id'],
                    evaluator_name=row['evaluator_name'] or 'Unknown',
                    relevance_score=row['relevance_score'],
                    reasoning=row.get('reasoning'),
                    scored_at=row['scored_at'],
                    document_title=row.get('document_title'),
                    document_authors=row.get('document_authors'),
                    document_year=row.get('document_year'),
                    document_abstract=row.get('document_abstract'),
                    validation=self.validation_tracker.get_validation(
                        TargetType.SCORE, row['scoring_id']
                    )
                )
                if include_validated or item.validation is None:
                    items.append(item)

        return items

    def get_citations_for_question(
        self,
        research_question_id: int,
        include_validated: bool = True
    ) -> List[CitationAuditItem]:
        """
        Get extracted citations for a research question.

        Args:
            research_question_id: ID of the research question
            include_validated: Whether to include already-validated items

        Returns:
            List of CitationAuditItem records

        Note:
            Document metadata is fetched via JOIN for bulk efficiency rather than
            individual get_document_details() calls (golden rule #18 exception
            for performance in data layer bulk operations).
        """
        query = """
            SELECT
                ec.citation_id,
                ec.research_question_id,
                ec.document_id,
                ec.session_id,
                ec.scoring_id,
                ec.evaluator_id,
                e.name as evaluator_name,
                ec.passage,
                ec.summary,
                ec.relevance_confidence,
                ec.human_review_status,
                ec.extracted_at,
                d.title as document_title,
                d.authors as document_authors
            FROM audit.extracted_citations ec
            LEFT JOIN public.evaluators e ON ec.evaluator_id = e.id
            LEFT JOIN public.document d ON ec.document_id = d.id
            WHERE ec.research_question_id = %s
            ORDER BY ec.relevance_confidence DESC NULLS LAST, ec.extracted_at DESC
        """

        items = []
        with self.conn.cursor(row_factory=dict_row) as cur:
            cur.execute(query, (research_question_id,))
            for row in cur.fetchall():
                item = CitationAuditItem(
                    citation_id=row['citation_id'],
                    research_question_id=row['research_question_id'],
                    document_id=row['document_id'],
                    session_id=row['session_id'],
                    scoring_id=row['scoring_id'],
                    evaluator_id=row['evaluator_id'],
                    evaluator_name=row['evaluator_name'] or 'Unknown',
                    passage=row['passage'],
                    summary=row['summary'],
                    relevance_confidence=row.get('relevance_confidence'),
                    human_review_status=row.get('human_review_status'),
                    extracted_at=row['extracted_at'],
                    document_title=row.get('document_title'),
                    document_authors=row.get('document_authors'),
                    validation=self.validation_tracker.get_validation(
                        TargetType.CITATION, row['citation_id']
                    )
                )
                if include_validated or item.validation is None:
                    items.append(item)

        return items

    def get_reports_for_question(
        self,
        research_question_id: int,
        include_validated: bool = True
    ) -> List[ReportAuditItem]:
        """
        Get generated reports for a research question.

        Args:
            research_question_id: ID of the research question
            include_validated: Whether to include already-validated items

        Returns:
            List of ReportAuditItem records
        """
        query = """
            SELECT
                gr.report_id,
                gr.research_question_id,
                gr.session_id,
                gr.report_type,
                gr.evaluator_id,
                e.name as evaluator_name,
                gr.citation_count,
                gr.report_text,
                gr.report_format,
                gr.generated_at,
                gr.human_edited,
                gr.is_final
            FROM audit.generated_reports gr
            LEFT JOIN public.evaluators e ON gr.evaluator_id = e.id
            WHERE gr.research_question_id = %s
            ORDER BY gr.generated_at DESC
        """

        items = []
        with self.conn.cursor(row_factory=dict_row) as cur:
            cur.execute(query, (research_question_id,))
            for row in cur.fetchall():
                item = ReportAuditItem(
                    report_id=row['report_id'],
                    research_question_id=row['research_question_id'],
                    session_id=row['session_id'],
                    report_type=row['report_type'],
                    evaluator_id=row.get('evaluator_id'),
                    evaluator_name=row.get('evaluator_name'),
                    citation_count=row.get('citation_count'),
                    report_text=row['report_text'],
                    report_format=row['report_format'],
                    generated_at=row['generated_at'],
                    human_edited=row['human_edited'],
                    is_final=row['is_final'],
                    validation=self.validation_tracker.get_validation(
                        TargetType.REPORT, row['report_id']
                    )
                )
                if include_validated or item.validation is None:
                    items.append(item)

        return items

    def get_counterfactuals_for_question(
        self,
        research_question_id: int,
        include_validated: bool = True
    ) -> List[CounterfactualAuditItem]:
        """
        Get counterfactual questions for a research question.

        Args:
            research_question_id: ID of the research question
            include_validated: Whether to include already-validated items

        Returns:
            List of CounterfactualAuditItem records
        """
        query = """
            SELECT
                cq.question_id,
                ca.research_question_id,
                cq.analysis_id,
                cq.question_text,
                cq.target_claim,
                cq.priority,
                cq.query_generated,
                cq.documents_found_count
            FROM audit.counterfactual_questions cq
            JOIN audit.counterfactual_analyses ca ON cq.analysis_id = ca.analysis_id
            WHERE ca.research_question_id = %s
            ORDER BY cq.priority DESC NULLS LAST, cq.question_id
        """

        items = []
        with self.conn.cursor(row_factory=dict_row) as cur:
            cur.execute(query, (research_question_id,))
            for row in cur.fetchall():
                item = CounterfactualAuditItem(
                    question_id=row['question_id'],
                    research_question_id=row['research_question_id'],
                    analysis_id=row['analysis_id'],
                    question_text=row['question_text'],
                    target_claim=row.get('target_claim'),
                    priority=row.get('priority'),
                    query_generated=row.get('query_generated'),
                    documents_found_count=row.get('documents_found_count'),
                    validation=self.validation_tracker.get_validation(
                        TargetType.COUNTERFACTUAL, row['question_id']
                    )
                )
                if include_validated or item.validation is None:
                    items.append(item)

        return items

    def record_validation(
        self,
        research_question_id: int,
        target_type: TargetType,
        target_id: int,
        validation_status: ValidationStatus,
        reviewer_id: Optional[int],
        reviewer_name: str,
        session_id: Optional[int] = None,
        comment: Optional[str] = None,
        suggested_correction: Optional[str] = None,
        severity: Optional[Severity] = None,
        time_spent_seconds: Optional[int] = None,
        category_ids: Optional[List[int]] = None
    ) -> int:
        """
        Record a validation for an audit item.

        Delegates to ValidationTracker.record_validation().
        """
        return self.validation_tracker.record_validation(
            research_question_id=research_question_id,
            target_type=target_type,
            target_id=target_id,
            validation_status=validation_status,
            reviewer_id=reviewer_id,
            reviewer_name=reviewer_name,
            session_id=session_id,
            comment=comment,
            suggested_correction=suggested_correction,
            severity=severity,
            time_spent_seconds=time_spent_seconds,
            category_ids=category_ids
        )

    def get_categories(
        self,
        target_type: Optional[TargetType] = None
    ) -> List[ValidationCategory]:
        """Get validation categories."""
        return self.validation_tracker.get_categories(target_type)

    def get_validation_statistics(self) -> Dict[str, Any]:
        """
        Get comprehensive validation statistics for display.

        Returns:
            Dictionary with statistics by target type
        """
        stats = self.validation_tracker.get_validation_statistics()
        return {
            stat.target_type.value: {
                'total_validations': stat.total_validations,
                'validated_count': stat.validated_count,
                'incorrect_count': stat.incorrect_count,
                'uncertain_count': stat.uncertain_count,
                'needs_review_count': stat.needs_review_count,
                'validation_rate_percent': stat.validation_rate_percent,
                'unique_reviewers': stat.unique_reviewers,
                'avg_review_time_seconds': stat.avg_review_time_seconds
            }
            for stat in stats
        }
