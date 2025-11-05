"""
Report Tracker for managing generated reports and counterfactual analyses.

Tracks all reports generated for research questions, including preliminary,
comprehensive, and counterfactual reports.
"""

import logging
import json
from typing import Optional, List, Dict, Any
import psycopg
from psycopg.rows import dict_row

logger = logging.getLogger(__name__)


class ReportTracker:
    """
    Tracks generated reports and counterfactual analyses.

    Provides methods for:
    - Recording generated reports
    - Tracking counterfactual analyses
    - Getting latest/final reports
    - Managing report versioning
    """

    def __init__(self, conn: psycopg.Connection):
        """
        Initialize report tracker.

        Args:
            conn: Active psycopg connection to PostgreSQL database
        """
        self.conn = conn

    def record_report(
        self,
        research_question_id: int,
        session_id: int,
        report_type: str,
        model_name: str,
        temperature: float,
        report_text: str,
        citation_count: Optional[int] = None,
        methodology_metadata: Optional[Dict[str, Any]] = None,
        report_format: str = 'markdown',
        is_final: bool = False
    ) -> int:
        """
        Record a generated report.

        Args:
            research_question_id: ID of the research question
            session_id: ID of the session
            report_type: Type of report ('preliminary', 'comprehensive', 'counterfactual')
            model_name: Name of the reporting model
            temperature: Model temperature
            report_text: Full report text
            citation_count: Number of citations used
            methodology_metadata: Optional metadata about processing
            report_format: Report format (default: 'markdown')
            is_final: Mark as final version

        Returns:
            report_id (BIGINT)
        """
        with self.conn.cursor() as cur:
            cur.execute("""
                INSERT INTO audit.generated_reports (
                    research_question_id, session_id, report_type, model_name,
                    temperature, citation_count, report_text, report_format,
                    methodology_metadata, is_final
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING report_id
            """, (
                research_question_id, session_id, report_type, model_name,
                temperature, citation_count, report_text, report_format,
                json.dumps(methodology_metadata) if methodology_metadata else None,
                is_final
            ))
            report_id = cur.fetchone()[0]
            self.conn.commit()

            logger.info(f"Recorded {report_type} report {report_id} for research question {research_question_id}")
            return report_id

    def mark_report_as_final(
        self,
        report_id: int
    ) -> None:
        """
        Mark a report as the final version.

        Unmarks any other reports for the same research question.

        Args:
            report_id: ID of the report
        """
        with self.conn.cursor() as cur:
            # First, get the research_question_id
            cur.execute("""
                SELECT research_question_id FROM audit.generated_reports
                WHERE report_id = %s
            """, (report_id,))
            result = cur.fetchone()

            if result:
                research_question_id = result[0]

                # Unmark all other reports for this question
                cur.execute("""
                    UPDATE audit.generated_reports
                    SET is_final = FALSE
                    WHERE research_question_id = %s
                """, (research_question_id,))

                # Mark this report as final
                cur.execute("""
                    UPDATE audit.generated_reports
                    SET is_final = TRUE
                    WHERE report_id = %s
                """, (report_id,))

                self.conn.commit()
                logger.info(f"Marked report {report_id} as final")

    def get_latest_report(
        self,
        research_question_id: int,
        report_type: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Get the most recent report for a research question.

        Args:
            research_question_id: ID of the research question
            report_type: Optional filter by report type

        Returns:
            Dictionary with report data, or None if no reports exist
        """
        with self.conn.cursor(row_factory=dict_row) as cur:
            if report_type:
                cur.execute("""
                    SELECT * FROM audit.generated_reports
                    WHERE research_question_id = %s AND report_type = %s
                    ORDER BY generated_at DESC
                    LIMIT 1
                """, (research_question_id, report_type))
            else:
                cur.execute("""
                    SELECT * FROM audit.generated_reports
                    WHERE research_question_id = %s
                    ORDER BY generated_at DESC
                    LIMIT 1
                """, (research_question_id,))

            return cur.fetchone()

    def get_final_report(
        self,
        research_question_id: int
    ) -> Optional[Dict[str, Any]]:
        """
        Get the final report for a research question.

        Args:
            research_question_id: ID of the research question

        Returns:
            Dictionary with report data, or None if no final report exists
        """
        with self.conn.cursor(row_factory=dict_row) as cur:
            cur.execute("""
                SELECT * FROM audit.generated_reports
                WHERE research_question_id = %s AND is_final = TRUE
                LIMIT 1
            """, (research_question_id,))
            return cur.fetchone()

    def get_all_reports(
        self,
        research_question_id: int
    ) -> List[Dict[str, Any]]:
        """
        Get all reports for a research question.

        Args:
            research_question_id: ID of the research question

        Returns:
            List of dictionaries with report data
        """
        with self.conn.cursor(row_factory=dict_row) as cur:
            cur.execute("""
                SELECT * FROM audit.generated_reports
                WHERE research_question_id = %s
                ORDER BY generated_at DESC
            """, (research_question_id,))
            return cur.fetchall()

    def record_counterfactual_analysis(
        self,
        research_question_id: int,
        session_id: int,
        model_name: str,
        temperature: float,
        source_report_id: Optional[int] = None,
        num_questions_generated: Optional[int] = None,
        num_queries_executed: Optional[int] = None,
        num_documents_found: Optional[int] = None,
        num_citations_extracted: Optional[int] = None
    ) -> int:
        """
        Record a counterfactual analysis session.

        Args:
            research_question_id: ID of the research question
            session_id: ID of the session
            model_name: Name of the counterfactual model
            temperature: Model temperature
            source_report_id: ID of report analyzed (optional)
            num_questions_generated: Number of counterfactual questions generated
            num_queries_executed: Number of queries executed
            num_documents_found: Number of documents found
            num_citations_extracted: Number of citations extracted

        Returns:
            analysis_id (BIGINT)
        """
        with self.conn.cursor() as cur:
            cur.execute("""
                INSERT INTO audit.counterfactual_analyses (
                    research_question_id, session_id, source_report_id,
                    model_name, temperature, num_questions_generated,
                    num_queries_executed, num_documents_found,
                    num_citations_extracted
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING analysis_id
            """, (
                research_question_id, session_id, source_report_id,
                model_name, temperature, num_questions_generated,
                num_queries_executed, num_documents_found,
                num_citations_extracted
            ))
            analysis_id = cur.fetchone()[0]
            self.conn.commit()

            logger.info(f"Recorded counterfactual analysis {analysis_id} for research question {research_question_id}")
            return analysis_id

    def record_counterfactual_question(
        self,
        research_question_id: int,
        analysis_id: int,
        question_text: str,
        target_claim: Optional[str] = None,
        priority: Optional[str] = None,
        query_generated: Optional[str] = None,
        documents_found_count: Optional[int] = None
    ) -> int:
        """
        Record a counterfactual question.

        Args:
            research_question_id: ID of the research question
            analysis_id: ID of the analysis session
            question_text: The counterfactual question text
            target_claim: Claim being challenged
            priority: Priority level ('high', 'medium', 'low')
            query_generated: Database query for this question
            documents_found_count: Number of documents found

        Returns:
            question_id (BIGINT)
        """
        with self.conn.cursor() as cur:
            cur.execute("""
                INSERT INTO audit.counterfactual_questions (
                    research_question_id, analysis_id, question_text,
                    target_claim, priority, query_generated, documents_found_count
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING question_id
            """, (
                research_question_id, analysis_id, question_text,
                target_claim, priority, query_generated, documents_found_count
            ))
            question_id = cur.fetchone()[0]
            self.conn.commit()

            logger.debug(f"Recorded counterfactual question {question_id}")
            return question_id

    def get_counterfactual_analyses(
        self,
        research_question_id: int
    ) -> List[Dict[str, Any]]:
        """
        Get all counterfactual analyses for a research question.

        Args:
            research_question_id: ID of the research question

        Returns:
            List of dictionaries with analysis data
        """
        with self.conn.cursor(row_factory=dict_row) as cur:
            cur.execute("""
                SELECT * FROM audit.counterfactual_analyses
                WHERE research_question_id = %s
                ORDER BY performed_at DESC
            """, (research_question_id,))
            return cur.fetchall()

    def get_counterfactual_questions(
        self,
        analysis_id: int
    ) -> List[Dict[str, Any]]:
        """
        Get all counterfactual questions for an analysis.

        Args:
            analysis_id: ID of the analysis session

        Returns:
            List of dictionaries with question data
        """
        with self.conn.cursor(row_factory=dict_row) as cur:
            cur.execute("""
                SELECT * FROM audit.counterfactual_questions
                WHERE analysis_id = %s
                ORDER BY priority DESC, question_id
            """, (analysis_id,))
            return cur.fetchall()
