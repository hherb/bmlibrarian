"""
Validation Tracker for human review of audit trail items.

Provides functionality for:
- Recording human validations of automated evaluations
- Tracking validation categories and assignments
- Querying validation statistics for benchmarking
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict, Any

import psycopg
from psycopg.rows import dict_row

logger = logging.getLogger(__name__)


class TargetType(Enum):
    """Types of audit items that can be validated."""

    QUERY = "query"
    SCORE = "score"
    CITATION = "citation"
    REPORT = "report"
    COUNTERFACTUAL = "counterfactual"


class ValidationStatus(Enum):
    """Possible validation outcomes."""

    VALIDATED = "validated"
    INCORRECT = "incorrect"
    UNCERTAIN = "uncertain"
    NEEDS_REVIEW = "needs_review"


class Severity(Enum):
    """Severity levels for incorrect items."""

    MINOR = "minor"
    MODERATE = "moderate"
    MAJOR = "major"
    CRITICAL = "critical"


@dataclass
class ValidationCategory:
    """A predefined category for classifying incorrect evaluations."""

    category_id: int
    target_type: TargetType
    category_code: str
    category_name: str
    description: Optional[str] = None
    is_active: bool = True


@dataclass
class HumanValidation:
    """A human validation record for an audit item."""

    validation_id: Optional[int] = None
    research_question_id: int = 0
    session_id: Optional[int] = None
    target_type: TargetType = TargetType.SCORE
    target_id: int = 0
    validation_status: ValidationStatus = ValidationStatus.VALIDATED
    reviewer_id: Optional[int] = None
    reviewer_name: str = ""
    comment: Optional[str] = None
    suggested_correction: Optional[str] = None
    severity: Optional[Severity] = None
    validated_at: Optional[datetime] = None
    time_spent_seconds: Optional[int] = None
    categories: List[ValidationCategory] = field(default_factory=list)


@dataclass
class ValidationStatistics:
    """Aggregated validation statistics for a target type."""

    target_type: TargetType
    total_validations: int
    validated_count: int
    incorrect_count: int
    uncertain_count: int
    needs_review_count: int
    validation_rate_percent: float
    unique_reviewers: int
    avg_review_time_seconds: Optional[float] = None


@dataclass
class UnvalidatedCounts:
    """Counts of validated vs unvalidated items."""

    target_type: TargetType
    total_count: int
    validated_count: int
    unvalidated_count: int


class ValidationTracker:
    """
    Tracks human validations of audit trail items.

    Provides methods for:
    - Recording and updating validations
    - Querying validation status
    - Getting validation statistics
    - Managing validation categories
    """

    def __init__(self, conn: psycopg.Connection):
        """
        Initialize validation tracker.

        Args:
            conn: Active psycopg connection to PostgreSQL database
        """
        self.conn = conn

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
        Record a human validation of an audit item.

        Args:
            research_question_id: ID of the research question
            target_type: Type of item being validated
            target_id: ID of the target record
            validation_status: Validation outcome
            reviewer_id: ID of the reviewer (optional)
            reviewer_name: Name of the reviewer
            session_id: ID of the session (optional)
            comment: Explanation of validation decision
            suggested_correction: What the correct value should be
            severity: Severity level for incorrect items
            time_spent_seconds: Time spent reviewing
            category_ids: List of validation category IDs

        Returns:
            validation_id (BIGINT)
        """
        severity_value = severity.value if severity else None

        with self.conn.cursor() as cur:
            cur.execute("""
                INSERT INTO audit.human_validations (
                    research_question_id, session_id, target_type, target_id,
                    validation_status, reviewer_id, reviewer_name,
                    comment, suggested_correction, severity, time_spent_seconds
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (target_type, target_id, reviewer_id) DO UPDATE
                SET validation_status = EXCLUDED.validation_status,
                    comment = EXCLUDED.comment,
                    suggested_correction = EXCLUDED.suggested_correction,
                    severity = EXCLUDED.severity,
                    time_spent_seconds = EXCLUDED.time_spent_seconds,
                    validated_at = NOW()
                RETURNING validation_id
            """, (
                research_question_id, session_id, target_type.value, target_id,
                validation_status.value, reviewer_id, reviewer_name,
                comment, suggested_correction, severity_value, time_spent_seconds
            ))
            validation_id = cur.fetchone()[0]

            # Record category assignments if provided
            if category_ids:
                self._assign_categories(cur, validation_id, category_ids)

            self.conn.commit()
            logger.info(
                f"Recorded validation {validation_id} for {target_type.value} "
                f"{target_id}: {validation_status.value}"
            )
            return validation_id

    def _assign_categories(
        self,
        cur: psycopg.Cursor,
        validation_id: int,
        category_ids: List[int]
    ) -> None:
        """Assign validation categories to a validation record."""
        # Remove existing assignments
        cur.execute(
            "DELETE FROM audit.validation_category_assignments WHERE validation_id = %s",
            (validation_id,)
        )

        # Insert new assignments
        if category_ids:
            cur.executemany("""
                INSERT INTO audit.validation_category_assignments
                    (validation_id, category_id)
                VALUES (%s, %s)
                ON CONFLICT DO NOTHING
            """, [(validation_id, cat_id) for cat_id in category_ids])

    def update_validation(
        self,
        validation_id: int,
        validation_status: Optional[ValidationStatus] = None,
        comment: Optional[str] = None,
        suggested_correction: Optional[str] = None,
        severity: Optional[Severity] = None,
        category_ids: Optional[List[int]] = None
    ) -> None:
        """
        Update an existing validation record.

        Args:
            validation_id: ID of the validation to update
            validation_status: New validation status
            comment: Updated comment
            suggested_correction: Updated correction
            severity: Updated severity
            category_ids: Updated category IDs
        """
        updates = []
        params = []

        if validation_status is not None:
            updates.append("validation_status = %s")
            params.append(validation_status.value)
        if comment is not None:
            updates.append("comment = %s")
            params.append(comment)
        if suggested_correction is not None:
            updates.append("suggested_correction = %s")
            params.append(suggested_correction)
        if severity is not None:
            updates.append("severity = %s")
            params.append(severity.value)

        if updates:
            updates.append("validated_at = NOW()")
            params.append(validation_id)

            with self.conn.cursor() as cur:
                cur.execute(f"""
                    UPDATE audit.human_validations
                    SET {', '.join(updates)}
                    WHERE validation_id = %s
                """, params)

                if category_ids is not None:
                    self._assign_categories(cur, validation_id, category_ids)

                self.conn.commit()
                logger.info(f"Updated validation {validation_id}")

    def get_validation(
        self,
        target_type: TargetType,
        target_id: int,
        reviewer_id: Optional[int] = None
    ) -> Optional[HumanValidation]:
        """
        Get validation record for a specific target.

        Args:
            target_type: Type of the target item
            target_id: ID of the target record
            reviewer_id: Optional filter by reviewer

        Returns:
            HumanValidation or None if not found
        """
        with self.conn.cursor(row_factory=dict_row) as cur:
            if reviewer_id is not None:
                cur.execute("""
                    SELECT * FROM audit.human_validations
                    WHERE target_type = %s AND target_id = %s AND reviewer_id = %s
                """, (target_type.value, target_id, reviewer_id))
            else:
                cur.execute("""
                    SELECT * FROM audit.human_validations
                    WHERE target_type = %s AND target_id = %s
                    ORDER BY validated_at DESC
                    LIMIT 1
                """, (target_type.value, target_id))

            row = cur.fetchone()
            if row:
                return self._row_to_validation(row)
            return None

    def get_validations_for_question(
        self,
        research_question_id: int,
        target_type: Optional[TargetType] = None,
        validation_status: Optional[ValidationStatus] = None
    ) -> List[HumanValidation]:
        """
        Get all validations for a research question.

        Args:
            research_question_id: ID of the research question
            target_type: Optional filter by target type
            validation_status: Optional filter by validation status

        Returns:
            List of HumanValidation records
        """
        query = "SELECT * FROM audit.human_validations WHERE research_question_id = %s"
        params = [research_question_id]

        if target_type is not None:
            query += " AND target_type = %s"
            params.append(target_type.value)

        if validation_status is not None:
            query += " AND validation_status = %s"
            params.append(validation_status.value)

        query += " ORDER BY validated_at DESC"

        with self.conn.cursor(row_factory=dict_row) as cur:
            cur.execute(query, params)
            return [self._row_to_validation(row) for row in cur.fetchall()]

    def is_validated(
        self,
        target_type: TargetType,
        target_id: int,
        reviewer_id: Optional[int] = None
    ) -> bool:
        """
        Check if an item has been validated.

        Args:
            target_type: Type of the target item
            target_id: ID of the target record
            reviewer_id: Optional filter by specific reviewer

        Returns:
            True if validated, False otherwise
        """
        with self.conn.cursor() as cur:
            if reviewer_id is not None:
                cur.execute(
                    "SELECT audit.is_validated_by_reviewer(%s, %s, %s)",
                    (target_type.value, target_id, reviewer_id)
                )
            else:
                cur.execute("""
                    SELECT EXISTS(
                        SELECT 1 FROM audit.human_validations
                        WHERE target_type = %s AND target_id = %s
                    )
                """, (target_type.value, target_id))
            return cur.fetchone()[0]

    def get_categories(
        self,
        target_type: Optional[TargetType] = None,
        active_only: bool = True
    ) -> List[ValidationCategory]:
        """
        Get validation categories.

        Args:
            target_type: Optional filter by target type
            active_only: Only return active categories

        Returns:
            List of ValidationCategory records
        """
        query = "SELECT * FROM audit.validation_categories WHERE 1=1"
        params = []

        if target_type is not None:
            query += " AND target_type = %s"
            params.append(target_type.value)

        if active_only:
            query += " AND is_active = TRUE"

        query += " ORDER BY target_type, category_name"

        with self.conn.cursor(row_factory=dict_row) as cur:
            cur.execute(query, params)
            return [
                ValidationCategory(
                    category_id=row['category_id'],
                    target_type=TargetType(row['target_type']),
                    category_code=row['category_code'],
                    category_name=row['category_name'],
                    description=row.get('description'),
                    is_active=row['is_active']
                )
                for row in cur.fetchall()
            ]

    def get_validation_statistics(
        self,
        target_type: Optional[TargetType] = None
    ) -> List[ValidationStatistics]:
        """
        Get aggregated validation statistics.

        Args:
            target_type: Optional filter by target type

        Returns:
            List of ValidationStatistics records
        """
        query = "SELECT * FROM audit.v_validation_statistics"
        params = []

        if target_type is not None:
            query += " WHERE target_type = %s"
            params.append(target_type.value)

        with self.conn.cursor(row_factory=dict_row) as cur:
            cur.execute(query, params)
            return [
                ValidationStatistics(
                    target_type=TargetType(row['target_type']),
                    total_validations=row['total_validations'],
                    validated_count=row['validated_count'],
                    incorrect_count=row['incorrect_count'],
                    uncertain_count=row['uncertain_count'],
                    needs_review_count=row['needs_review_count'],
                    validation_rate_percent=float(row['validation_rate_percent'] or 0),
                    unique_reviewers=row['unique_reviewers'],
                    avg_review_time_seconds=float(row['avg_review_time_seconds']) if row['avg_review_time_seconds'] else None
                )
                for row in cur.fetchall()
            ]

    def get_unvalidated_counts(
        self,
        research_question_id: int
    ) -> List[UnvalidatedCounts]:
        """
        Get counts of validated vs unvalidated items for a question.

        Args:
            research_question_id: ID of the research question

        Returns:
            List of UnvalidatedCounts records
        """
        with self.conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT * FROM audit.get_unvalidated_counts(%s)",
                (research_question_id,)
            )
            return [
                UnvalidatedCounts(
                    target_type=TargetType(row['target_type']),
                    total_count=row['total_count'],
                    validated_count=row['validated_count'],
                    unvalidated_count=row['unvalidated_count']
                )
                for row in cur.fetchall()
            ]

    def _row_to_validation(self, row: Dict[str, Any]) -> HumanValidation:
        """Convert database row to HumanValidation dataclass."""
        return HumanValidation(
            validation_id=row['validation_id'],
            research_question_id=row['research_question_id'],
            session_id=row.get('session_id'),
            target_type=TargetType(row['target_type']),
            target_id=row['target_id'],
            validation_status=ValidationStatus(row['validation_status']),
            reviewer_id=row.get('reviewer_id'),
            reviewer_name=row['reviewer_name'],
            comment=row.get('comment'),
            suggested_correction=row.get('suggested_correction'),
            severity=Severity(row['severity']) if row.get('severity') else None,
            validated_at=row.get('validated_at'),
            time_spent_seconds=row.get('time_spent_seconds'),
            categories=[]  # Categories loaded separately if needed
        )

    def delete_validation(self, validation_id: int) -> bool:
        """
        Delete a validation record.

        Args:
            validation_id: ID of the validation to delete

        Returns:
            True if deleted, False if not found
        """
        with self.conn.cursor() as cur:
            cur.execute(
                "DELETE FROM audit.human_validations WHERE validation_id = %s",
                (validation_id,)
            )
            self.conn.commit()
            deleted = cur.rowcount > 0
            if deleted:
                logger.info(f"Deleted validation {validation_id}")
            return deleted
