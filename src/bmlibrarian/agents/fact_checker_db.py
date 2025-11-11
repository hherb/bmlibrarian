"""
Database manager for Fact Checker using SQLite.

Provides database schema creation and CRUD operations for storing:
- Biomedical statements for fact-checking
- AI-generated evaluations with evidence
- Human annotations from multiple reviewers
- Processing metadata and export history
"""

import sqlite3
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timezone
from contextlib import contextmanager
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)


# Database schema version for migrations
SCHEMA_VERSION = 1


@dataclass
class Statement:
    """Represents a biomedical statement to be fact-checked."""
    id: Optional[int] = None
    statement_text: str = ""
    input_statement_id: Optional[str] = None
    expected_answer: Optional[str] = None
    created_at: Optional[str] = None
    source_file: Optional[str] = None
    review_status: str = "pending"


@dataclass
class Annotator:
    """Represents a human annotator."""
    id: Optional[int] = None
    username: str = ""
    full_name: Optional[str] = None
    email: Optional[str] = None
    expertise_level: Optional[str] = None
    institution: Optional[str] = None
    created_at: Optional[str] = None


@dataclass
class AIEvaluation:
    """Represents an AI-generated fact-check evaluation."""
    id: Optional[int] = None
    statement_id: int = 0
    evaluation: str = ""
    reason: str = ""
    confidence: Optional[str] = None
    documents_reviewed: int = 0
    supporting_citations: int = 0
    contradicting_citations: int = 0
    neutral_citations: int = 0
    matches_expected: Optional[bool] = None
    evaluated_at: Optional[str] = None
    model_used: Optional[str] = None
    model_version: Optional[str] = None
    agent_config: Optional[str] = None
    session_id: Optional[str] = None
    version: int = 1


@dataclass
class Evidence:
    """Represents a literature citation supporting an evaluation."""
    id: Optional[int] = None
    ai_evaluation_id: int = 0
    citation_text: str = ""
    pmid: Optional[str] = None
    doi: Optional[str] = None
    document_id: Optional[str] = None
    relevance_score: Optional[float] = None
    supports_statement: Optional[str] = None
    created_at: Optional[str] = None


@dataclass
class HumanAnnotation:
    """Represents a human reviewer's annotation."""
    id: Optional[int] = None
    statement_id: int = 0
    annotator_id: int = 0
    annotation: str = ""
    explanation: Optional[str] = None
    confidence: Optional[str] = None
    review_duration_seconds: Optional[int] = None
    review_date: Optional[str] = None
    session_id: Optional[str] = None


class FactCheckerDB:
    """
    Database manager for fact-checker SQLite database.

    Handles schema creation, CRUD operations, and queries for
    fact-checking workflow with AI evaluations and human annotations.
    """

    def __init__(self, db_path: str):
        """
        Initialize the database manager.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize_database()

    @contextmanager
    def get_connection(self):
        """Context manager for database connections."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row  # Enable column access by name
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"Database error: {e}")
            raise
        finally:
            conn.close()

    def _initialize_database(self):
        """Create database schema if it doesn't exist."""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Create statements table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS statements (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    statement_text TEXT NOT NULL,
                    input_statement_id TEXT,
                    expected_answer TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    source_file TEXT,
                    review_status TEXT DEFAULT 'pending',
                    UNIQUE(statement_text)
                )
            """)

            # Create annotators table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS annotators (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    full_name TEXT,
                    email TEXT,
                    expertise_level TEXT,
                    institution TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Create ai_evaluations table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS ai_evaluations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    statement_id INTEGER NOT NULL,
                    evaluation TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    confidence TEXT,
                    documents_reviewed INTEGER,
                    supporting_citations INTEGER,
                    contradicting_citations INTEGER,
                    neutral_citations INTEGER,
                    matches_expected BOOLEAN,
                    evaluated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    model_used TEXT,
                    model_version TEXT,
                    agent_config TEXT,
                    session_id TEXT,
                    version INTEGER DEFAULT 1,
                    FOREIGN KEY (statement_id) REFERENCES statements(id) ON DELETE CASCADE
                )
            """)

            # Create evidence table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS evidence (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ai_evaluation_id INTEGER NOT NULL,
                    citation_text TEXT NOT NULL,
                    pmid TEXT,
                    doi TEXT,
                    document_id TEXT,
                    relevance_score REAL,
                    supports_statement TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (ai_evaluation_id) REFERENCES ai_evaluations(id) ON DELETE CASCADE
                )
            """)

            # Create human_annotations table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS human_annotations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    statement_id INTEGER NOT NULL,
                    annotator_id INTEGER NOT NULL,
                    annotation TEXT NOT NULL,
                    explanation TEXT,
                    confidence TEXT,
                    review_duration_seconds INTEGER,
                    review_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    session_id TEXT,
                    FOREIGN KEY (statement_id) REFERENCES statements(id) ON DELETE CASCADE,
                    FOREIGN KEY (annotator_id) REFERENCES annotators(id) ON DELETE CASCADE,
                    UNIQUE(statement_id, annotator_id)
                )
            """)

            # Create processing_metadata table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS processing_metadata (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT UNIQUE NOT NULL,
                    input_file TEXT NOT NULL,
                    output_file TEXT,
                    total_statements INTEGER,
                    processed_statements INTEGER,
                    start_time TIMESTAMP,
                    end_time TIMESTAMP,
                    status TEXT,
                    error_message TEXT,
                    config_snapshot TEXT
                )
            """)

            # Create export_history table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS export_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    export_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    export_type TEXT,
                    output_file TEXT,
                    statement_count INTEGER,
                    requested_by TEXT,
                    filters_applied TEXT
                )
            """)

            # Create indexes
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_statements_input_id ON statements(input_statement_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_statements_review_status ON statements(review_status)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_ai_eval_statement ON ai_evaluations(statement_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_ai_eval_session ON ai_evaluations(session_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_ai_eval_version ON ai_evaluations(statement_id, version)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_evidence_ai_eval ON evidence(ai_evaluation_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_human_annotation_statement ON human_annotations(statement_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_human_annotation_annotator ON human_annotations(annotator_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_annotators_username ON annotators(username)")

            logger.info(f"Database initialized: {self.db_path}")

    # ========== Statement Operations ==========

    def insert_statement(self, statement: Statement) -> int:
        """
        Insert a new statement or return existing ID if duplicate.

        Args:
            statement: Statement object

        Returns:
            Statement ID
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute("""
                    INSERT INTO statements (statement_text, input_statement_id, expected_answer, source_file, review_status)
                    VALUES (?, ?, ?, ?, ?)
                """, (statement.statement_text, statement.input_statement_id, statement.expected_answer,
                      statement.source_file, statement.review_status))
                return cursor.lastrowid
            except sqlite3.IntegrityError:
                # Statement already exists, return its ID
                cursor.execute("SELECT id FROM statements WHERE statement_text = ?", (statement.statement_text,))
                return cursor.fetchone()[0]

    def get_statement(self, statement_id: int) -> Optional[Statement]:
        """Get a statement by ID."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM statements WHERE id = ?", (statement_id,))
            row = cursor.fetchone()
            return Statement(**dict(row)) if row else None

    def update_statement_review_status(self, statement_id: int, status: str):
        """Update the review status of a statement."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE statements SET review_status = ? WHERE id = ?", (status, statement_id))

    # ========== Annotator Operations ==========

    def insert_or_get_annotator(self, annotator: Annotator) -> int:
        """
        Insert a new annotator or return existing ID.

        Args:
            annotator: Annotator object

        Returns:
            Annotator ID
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute("""
                    INSERT INTO annotators (username, full_name, email, expertise_level, institution)
                    VALUES (?, ?, ?, ?, ?)
                """, (annotator.username, annotator.full_name, annotator.email,
                      annotator.expertise_level, annotator.institution))
                return cursor.lastrowid
            except sqlite3.IntegrityError:
                # Annotator exists, return ID
                cursor.execute("SELECT id FROM annotators WHERE username = ?", (annotator.username,))
                return cursor.fetchone()[0]

    def get_annotator(self, username: str) -> Optional[Annotator]:
        """Get an annotator by username."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM annotators WHERE username = ?", (username,))
            row = cursor.fetchone()
            return Annotator(**dict(row)) if row else None

    # ========== AI Evaluation Operations ==========

    def insert_ai_evaluation(self, evaluation: AIEvaluation) -> int:
        """
        Insert a new AI evaluation.

        Args:
            evaluation: AIEvaluation object

        Returns:
            Evaluation ID
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO ai_evaluations (
                    statement_id, evaluation, reason, confidence, documents_reviewed,
                    supporting_citations, contradicting_citations, neutral_citations,
                    matches_expected, model_used, model_version, agent_config, session_id, version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (evaluation.statement_id, evaluation.evaluation, evaluation.reason, evaluation.confidence,
                  evaluation.documents_reviewed, evaluation.supporting_citations, evaluation.contradicting_citations,
                  evaluation.neutral_citations, evaluation.matches_expected, evaluation.model_used,
                  evaluation.model_version, evaluation.agent_config, evaluation.session_id, evaluation.version))
            return cursor.lastrowid

    def get_latest_ai_evaluation(self, statement_id: int) -> Optional[AIEvaluation]:
        """Get the latest AI evaluation for a statement."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM ai_evaluations
                WHERE statement_id = ?
                ORDER BY version DESC, evaluated_at DESC
                LIMIT 1
            """, (statement_id,))
            row = cursor.fetchone()
            return AIEvaluation(**dict(row)) if row else None

    def get_all_ai_evaluations(self, statement_id: int) -> List[AIEvaluation]:
        """Get all AI evaluations for a statement (all versions)."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM ai_evaluations
                WHERE statement_id = ?
                ORDER BY version DESC, evaluated_at DESC
            """, (statement_id,))
            return [AIEvaluation(**dict(row)) for row in cursor.fetchall()]

    # ========== Evidence Operations ==========

    def insert_evidence(self, evidence: Evidence) -> int:
        """Insert a new evidence citation."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO evidence (
                    ai_evaluation_id, citation_text, pmid, doi, document_id,
                    relevance_score, supports_statement
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (evidence.ai_evaluation_id, evidence.citation_text, evidence.pmid, evidence.doi,
                  evidence.document_id, evidence.relevance_score, evidence.supports_statement))
            return cursor.lastrowid

    def get_evidence_for_evaluation(self, evaluation_id: int) -> List[Evidence]:
        """Get all evidence citations for an AI evaluation."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM evidence WHERE ai_evaluation_id = ?", (evaluation_id,))
            return [Evidence(**dict(row)) for row in cursor.fetchall()]

    # ========== Human Annotation Operations ==========

    def insert_human_annotation(self, annotation: HumanAnnotation) -> int:
        """
        Insert or update a human annotation.

        Args:
            annotation: HumanAnnotation object

        Returns:
            Annotation ID
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute("""
                    INSERT INTO human_annotations (
                        statement_id, annotator_id, annotation, explanation, confidence,
                        review_duration_seconds, session_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (annotation.statement_id, annotation.annotator_id, annotation.annotation,
                      annotation.explanation, annotation.confidence, annotation.review_duration_seconds,
                      annotation.session_id))
                return cursor.lastrowid
            except sqlite3.IntegrityError:
                # Update existing annotation
                cursor.execute("""
                    UPDATE human_annotations
                    SET annotation = ?, explanation = ?, confidence = ?,
                        review_duration_seconds = ?, review_date = CURRENT_TIMESTAMP, session_id = ?
                    WHERE statement_id = ? AND annotator_id = ?
                """, (annotation.annotation, annotation.explanation, annotation.confidence,
                      annotation.review_duration_seconds, annotation.session_id,
                      annotation.statement_id, annotation.annotator_id))
                cursor.execute("""
                    SELECT id FROM human_annotations
                    WHERE statement_id = ? AND annotator_id = ?
                """, (annotation.statement_id, annotation.annotator_id))
                return cursor.fetchone()[0]

    def get_human_annotations(self, statement_id: int) -> List[HumanAnnotation]:
        """Get all human annotations for a statement."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM human_annotations WHERE statement_id = ?", (statement_id,))
            return [HumanAnnotation(**dict(row)) for row in cursor.fetchall()]

    # ========== Processing Metadata Operations ==========

    def insert_processing_session(self, session_data: Dict[str, Any]) -> int:
        """Insert a new processing session."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO processing_metadata (
                    session_id, input_file, total_statements, start_time, status, config_snapshot
                ) VALUES (?, ?, ?, ?, ?, ?)
            """, (session_data['session_id'], session_data['input_file'], session_data['total_statements'],
                  session_data['start_time'], session_data['status'], session_data.get('config_snapshot')))
            return cursor.lastrowid

    def update_processing_session(self, session_id: str, updates: Dict[str, Any]):
        """Update a processing session."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            set_clause = ", ".join([f"{k} = ?" for k in updates.keys()])
            values = list(updates.values()) + [session_id]
            cursor.execute(f"UPDATE processing_metadata SET {set_clause} WHERE session_id = ?", values)

    # ========== Query Operations ==========

    def get_all_statements_with_evaluations(self) -> List[Dict[str, Any]]:
        """
        Get all statements with their latest AI evaluations and evidence.

        Returns:
            List of dictionaries containing statement, evaluation, and evidence data
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT
                    s.*,
                    ae.id as eval_id,
                    ae.evaluation,
                    ae.reason,
                    ae.confidence,
                    ae.documents_reviewed,
                    ae.supporting_citations,
                    ae.contradicting_citations,
                    ae.neutral_citations,
                    ae.matches_expected,
                    ae.model_used
                FROM statements s
                LEFT JOIN ai_evaluations ae ON s.id = ae.statement_id
                LEFT JOIN (
                    SELECT statement_id, MAX(version) as max_version
                    FROM ai_evaluations
                    GROUP BY statement_id
                ) latest ON ae.statement_id = latest.statement_id AND ae.version = latest.max_version
                ORDER BY s.id
            """)

            results = []
            for row in cursor.fetchall():
                row_dict = dict(row)

                # Get evidence if evaluation exists
                if row_dict['eval_id']:
                    evidence = self.get_evidence_for_evaluation(row_dict['eval_id'])
                    row_dict['evidence'] = [asdict(e) for e in evidence]
                else:
                    row_dict['evidence'] = []

                # Get human annotations
                annotations = self.get_human_annotations(row_dict['id'])
                row_dict['human_annotations'] = [asdict(a) for a in annotations]

                results.append(row_dict)

            return results

    def get_inter_annotator_agreement(self) -> Dict[str, Any]:
        """
        Calculate inter-annotator agreement statistics.

        Returns:
            Dictionary with agreement metrics
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Get all annotation pairs
            cursor.execute("""
                SELECT
                    ha1.statement_id,
                    ha1.annotation as ann1,
                    ha2.annotation as ann2,
                    a1.username as annotator1,
                    a2.username as annotator2
                FROM human_annotations ha1
                JOIN human_annotations ha2 ON ha1.statement_id = ha2.statement_id
                JOIN annotators a1 ON ha1.annotator_id = a1.id
                JOIN annotators a2 ON ha2.annotator_id = a2.id
                WHERE ha1.annotator_id < ha2.annotator_id
            """)

            pairs = cursor.fetchall()
            total_pairs = len(pairs)

            if total_pairs == 0:
                return {"total_pairs": 0, "agreements": 0, "agreement_percentage": 0}

            agreements = sum(1 for row in pairs if row[1] == row[2])

            return {
                "total_pairs": total_pairs,
                "agreements": agreements,
                "agreement_percentage": round(100.0 * agreements / total_pairs, 2)
            }

    def export_to_json(self, output_file: str, export_type: str = "full",
                      requested_by: str = "system") -> str:
        """
        Export database contents to JSON file.

        Args:
            output_file: Path to output JSON file
            export_type: Type of export (full/ai_only/human_annotated/summary)
            requested_by: Username of requester

        Returns:
            Path to exported file
        """
        data = self.get_all_statements_with_evaluations()

        # Filter based on export type
        if export_type == "ai_only":
            data = [d for d in data if d.get('eval_id')]
        elif export_type == "human_annotated":
            data = [d for d in data if d.get('human_annotations')]

        # Prepare export data
        export_data = {
            "results": data,
            "export_metadata": {
                "export_date": datetime.now(timezone.utc).isoformat(),
                "export_type": export_type,
                "total_statements": len(data),
                "database_file": str(self.db_path)
            }
        }

        # Write to file
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, indent=2)

        # Record export in history
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO export_history (export_type, output_file, statement_count, requested_by)
                VALUES (?, ?, ?, ?)
            """, (export_type, str(output_path), len(data), requested_by))

        logger.info(f"Exported {len(data)} statements to {output_path}")
        return str(output_path)


    def import_json_results(self, json_file: str, skip_existing: bool = True) -> Dict[str, int]:
        """
        Import fact-check results from legacy JSON format.

        Intelligently merges data:
        - Skips statements that already have AI evaluations (no overwrite)
        - Skips statements that already have human annotations (no overwrite)
        - Only imports new/unprocessed statements

        Args:
            json_file: Path to JSON file with results
            skip_existing: If True, skip statements with existing evaluations

        Returns:
            Dictionary with import statistics
        """
        stats = {
            'total_in_file': 0,
            'new_statements': 0,
            'skipped_existing': 0,
            'imported_evaluations': 0,
            'imported_evidence': 0,
            'errors': 0
        }

        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # Handle both formats: {"results": [...]} or direct array
            if isinstance(data, dict) and 'results' in data:
                results = data['results']
            elif isinstance(data, list):
                results = data
            else:
                raise ValueError("Invalid JSON format")

            stats['total_in_file'] = len(results)

            with self.get_connection() as conn:
                cursor = conn.cursor()

                for result in results:
                    try:
                        statement_text = result.get('statement', '')
                        if not statement_text:
                            stats['errors'] += 1
                            continue

                        # Check if statement already exists
                        cursor.execute(
                            "SELECT id FROM statements WHERE statement_text = ?",
                            (statement_text,)
                        )
                        existing_stmt = cursor.fetchone()

                        if existing_stmt and skip_existing:
                            statement_id = existing_stmt[0]

                            # Check if it has AI evaluation
                            cursor.execute(
                                "SELECT COUNT(*) FROM ai_evaluations WHERE statement_id = ?",
                                (statement_id,)
                            )
                            has_evaluation = cursor.fetchone()[0] > 0

                            # Check if it has human annotations
                            cursor.execute(
                                "SELECT COUNT(*) FROM human_annotations WHERE statement_id = ?",
                                (statement_id,)
                            )
                            has_annotations = cursor.fetchone()[0] > 0

                            if has_evaluation or has_annotations:
                                stats['skipped_existing'] += 1
                                logger.debug(f"Skipping existing statement: {statement_text[:50]}")
                                continue

                        # Import new statement
                        stmt = Statement(
                            statement_text=statement_text,
                            input_statement_id=result.get('input_statement_id'),
                            expected_answer=result.get('expected_answer'),
                            source_file=json_file,
                            review_status='pending'
                        )
                        statement_id = self.insert_statement(stmt)
                        stats['new_statements'] += 1

                        # Import AI evaluation if present
                        if result.get('evaluation'):
                            ai_eval = AIEvaluation(
                                statement_id=statement_id,
                                evaluation=result['evaluation'],
                                reason=result.get('reason', ''),
                                confidence=result.get('confidence'),
                                documents_reviewed=result.get('metadata', {}).get('documents_reviewed', 0),
                                supporting_citations=result.get('metadata', {}).get('supporting_citations', 0),
                                contradicting_citations=result.get('metadata', {}).get('contradicting_citations', 0),
                                neutral_citations=result.get('metadata', {}).get('neutral_citations', 0),
                                matches_expected=result.get('matches_expected'),
                                model_used='imported',
                                session_id='json_import',
                                version=1
                            )
                            eval_id = self.insert_ai_evaluation(ai_eval)
                            stats['imported_evaluations'] += 1

                            # Import evidence
                            for evidence_data in result.get('evidence_list', []):
                                evidence = Evidence(
                                    ai_evaluation_id=eval_id,
                                    citation_text=evidence_data.get('citation', ''),
                                    pmid=evidence_data.get('pmid', '').replace('PMID:', ''),
                                    doi=evidence_data.get('doi', '').replace('DOI:', ''),
                                    document_id=evidence_data.get('document_id'),
                                    relevance_score=evidence_data.get('relevance_score'),
                                    supports_statement=evidence_data.get('stance')
                                )
                                self.insert_evidence(evidence)
                                stats['imported_evidence'] += 1

                    except Exception as e:
                        logger.error(f"Error importing result: {e}")
                        stats['errors'] += 1
                        continue

            logger.info(f"JSON import complete: {stats}")
            return stats

        except Exception as e:
            logger.error(f"Error reading JSON file: {e}")
            raise


def create_database_from_input_file(input_file: str) -> str:
    """
    Create a SQLite database based on the input filename.

    Args:
        input_file: Path to input JSON file

    Returns:
        Path to created database file
    """
    input_path = Path(input_file)
    db_path = input_path.parent / f"{input_path.stem}.db"

    db = FactCheckerDB(str(db_path))
    logger.info(f"Created database: {db_path}")

    return str(db_path)
