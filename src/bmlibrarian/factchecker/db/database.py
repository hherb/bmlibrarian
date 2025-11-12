"""
Database manager for Fact Checker using PostgreSQL.

Provides database operations for storing:
- Biomedical statements for fact-checking
- AI-generated evaluations with evidence
- Human annotations from multiple reviewers
- Processing metadata and export history

Uses the centralized DatabaseManager and factcheck schema (no data duplication).
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timezone
from dataclasses import dataclass, asdict

from bmlibrarian.database import get_db_manager

logger = logging.getLogger(__name__)


# Database schema version for migrations
SCHEMA_VERSION = 1


@dataclass
class Statement:
    """Represents a biomedical statement to be fact-checked."""
    statement_id: Optional[int] = None
    statement_text: str = ""
    input_statement_id: Optional[str] = None
    expected_answer: Optional[str] = None
    created_at: Optional[str] = None
    source_file: Optional[str] = None
    review_status: str = "pending"


@dataclass
class Annotator:
    """Represents a human annotator."""
    annotator_id: Optional[int] = None
    username: str = ""
    full_name: Optional[str] = None
    email: Optional[str] = None
    expertise_level: Optional[str] = None
    institution: Optional[str] = None
    created_at: Optional[str] = None


@dataclass
class AIEvaluation:
    """Represents an AI-generated fact-check evaluation."""
    evaluation_id: Optional[int] = None
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
    agent_config: Optional[str] = None  # Will be converted to JSONB
    session_id: Optional[str] = None
    version: int = 1


@dataclass
class Evidence:
    """Represents a literature citation supporting an evaluation."""
    evidence_id: Optional[int] = None
    evaluation_id: int = 0
    citation_text: str = ""
    document_id: int = 0  # FK to public.document(id) - NO DUPLICATION!
    pmid: Optional[str] = None
    doi: Optional[str] = None
    relevance_score: Optional[float] = None
    supports_statement: Optional[str] = None  # 'supports', 'contradicts', 'neutral'
    created_at: Optional[str] = None


@dataclass
class HumanAnnotation:
    """Represents a human reviewer's annotation."""
    annotation_id: Optional[int] = None
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
    Database manager for fact-checker PostgreSQL operations.

    Handles CRUD operations using the centralized DatabaseManager
    and factcheck schema with NO data duplication.
    """

    def __init__(self):
        """
        Initialize the database manager.

        Uses the centralized DatabaseManager for connection pooling.
        """
        self.db_manager = get_db_manager()
        logger.info("FactCheckerDB initialized with centralized DatabaseManager")

    # ========== Statement Operations ==========

    def insert_statement(self, statement: Statement) -> int:
        """
        Insert a new statement or return existing ID if duplicate.

        Args:
            statement: Statement object

        Returns:
            Statement ID
        """
        with self.db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                # Use helper function for upsert
                cur.execute("""
                    SELECT factcheck.get_or_create_statement(%s, %s, %s, %s)
                """, (statement.statement_text, statement.input_statement_id,
                      statement.expected_answer, statement.source_file))
                statement_id = cur.fetchone()[0]
                return statement_id

    def get_statement(self, statement_id: int) -> Optional[Statement]:
        """Get a statement by ID."""
        with self.db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT statement_id, statement_text, input_statement_id, expected_answer,
                           created_at, source_file, review_status
                    FROM factcheck.statements
                    WHERE statement_id = %s
                """, (statement_id,))
                row = cur.fetchone()
                if row:
                    return Statement(
                        statement_id=row[0],
                        statement_text=row[1],
                        input_statement_id=row[2],
                        expected_answer=row[3],
                        created_at=row[4].isoformat() if row[4] else None,
                        source_file=row[5],
                        review_status=row[6]
                    )
                return None

    def update_statement_review_status(self, statement_id: int, status: str):
        """Update the review status of a statement."""
        with self.db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE factcheck.statements
                    SET review_status = %s
                    WHERE statement_id = %s
                """, (status, statement_id))

    # ========== Annotator Operations ==========

    def insert_or_get_annotator(self, annotator: Annotator) -> int:
        """
        Insert a new annotator or return existing ID.

        Args:
            annotator: Annotator object

        Returns:
            Annotator ID
        """
        with self.db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                # Use ON CONFLICT to handle duplicates atomically without transaction errors
                cur.execute("""
                    INSERT INTO factcheck.annotators (username, full_name, email, expertise_level, institution)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (username) DO UPDATE SET
                        full_name = EXCLUDED.full_name,
                        email = EXCLUDED.email,
                        expertise_level = EXCLUDED.expertise_level,
                        institution = EXCLUDED.institution
                    RETURNING annotator_id
                """, (annotator.username, annotator.full_name, annotator.email,
                      annotator.expertise_level, annotator.institution))
                result = cur.fetchone()
                if result:
                    return result[0]
                raise RuntimeError(f"Failed to insert or get annotator: {annotator.username}")

    def get_annotator(self, username: str) -> Optional[Annotator]:
        """Get an annotator by username."""
        with self.db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT annotator_id, username, full_name, email, expertise_level, institution, created_at
                    FROM factcheck.annotators
                    WHERE username = %s
                """, (username,))
                row = cur.fetchone()
                if row:
                    return Annotator(
                        annotator_id=row[0],
                        username=row[1],
                        full_name=row[2],
                        email=row[3],
                        expertise_level=row[4],
                        institution=row[5],
                        created_at=row[6].isoformat() if row[6] else None
                    )
                return None

    # ========== AI Evaluation Operations ==========

    def insert_ai_evaluation(self, evaluation: AIEvaluation) -> int:
        """
        Insert a new AI evaluation.

        Args:
            evaluation: AIEvaluation object

        Returns:
            Evaluation ID
        """
        with self.db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                # Convert agent_config to JSONB if it's a string
                agent_config_jsonb = None
                if evaluation.agent_config:
                    if isinstance(evaluation.agent_config, str):
                        agent_config_jsonb = json.loads(evaluation.agent_config)
                    else:
                        agent_config_jsonb = evaluation.agent_config

                cur.execute("""
                    INSERT INTO factcheck.ai_evaluations (
                        statement_id, evaluation, reason, confidence, documents_reviewed,
                        supporting_citations, contradicting_citations, neutral_citations,
                        matches_expected, model_used, model_version, agent_config, session_id, version
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING evaluation_id
                """, (evaluation.statement_id, evaluation.evaluation, evaluation.reason, evaluation.confidence,
                      evaluation.documents_reviewed, evaluation.supporting_citations, evaluation.contradicting_citations,
                      evaluation.neutral_citations, evaluation.matches_expected, evaluation.model_used,
                      evaluation.model_version, json.dumps(agent_config_jsonb) if agent_config_jsonb else None,
                      evaluation.session_id, evaluation.version))
                return cur.fetchone()[0]

    def get_latest_ai_evaluation(self, statement_id: int) -> Optional[AIEvaluation]:
        """Get the latest AI evaluation for a statement."""
        with self.db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT evaluation_id, statement_id, evaluation, reason, confidence,
                           documents_reviewed, supporting_citations, contradicting_citations, neutral_citations,
                           matches_expected, evaluated_at, model_used, model_version, agent_config, session_id, version
                    FROM factcheck.ai_evaluations
                    WHERE statement_id = %s
                    ORDER BY version DESC, evaluated_at DESC
                    LIMIT 1
                """, (statement_id,))
                row = cur.fetchone()
                if row:
                    return AIEvaluation(
                        evaluation_id=row[0],
                        statement_id=row[1],
                        evaluation=row[2],
                        reason=row[3],
                        confidence=row[4],
                        documents_reviewed=row[5],
                        supporting_citations=row[6],
                        contradicting_citations=row[7],
                        neutral_citations=row[8],
                        matches_expected=row[9],
                        evaluated_at=row[10].isoformat() if row[10] else None,
                        model_used=row[11],
                        model_version=row[12],
                        agent_config=row[13],  # Already JSONB
                        session_id=row[14],
                        version=row[15]
                    )
                return None

    def get_all_ai_evaluations(self, statement_id: int) -> List[AIEvaluation]:
        """Get all AI evaluations for a statement (all versions)."""
        with self.db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT evaluation_id, statement_id, evaluation, reason, confidence,
                           documents_reviewed, supporting_citations, contradicting_citations, neutral_citations,
                           matches_expected, evaluated_at, model_used, model_version, agent_config, session_id, version
                    FROM factcheck.ai_evaluations
                    WHERE statement_id = %s
                    ORDER BY version DESC, evaluated_at DESC
                """, (statement_id,))
                results = []
                for row in cur.fetchall():
                    results.append(AIEvaluation(
                        evaluation_id=row[0],
                        statement_id=row[1],
                        evaluation=row[2],
                        reason=row[3],
                        confidence=row[4],
                        documents_reviewed=row[5],
                        supporting_citations=row[6],
                        contradicting_citations=row[7],
                        neutral_citations=row[8],
                        matches_expected=row[9],
                        evaluated_at=row[10].isoformat() if row[10] else None,
                        model_used=row[11],
                        model_version=row[12],
                        agent_config=row[13],
                        session_id=row[14],
                        version=row[15]
                    ))
                return results

    # ========== Evidence Operations ==========

    def insert_evidence(self, evidence: Evidence) -> int:
        """Insert a new evidence citation."""
        with self.db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO factcheck.evidence (
                        evaluation_id, citation_text, document_id, pmid, doi,
                        relevance_score, supports_statement
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                    RETURNING evidence_id
                """, (evidence.evaluation_id, evidence.citation_text, evidence.document_id,
                      evidence.pmid, evidence.doi, evidence.relevance_score, evidence.supports_statement))
                return cur.fetchone()[0]

    def get_evidence_for_evaluation(self, evaluation_id: int) -> List[Evidence]:
        """Get all evidence citations for an AI evaluation."""
        with self.db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT evidence_id, evaluation_id, citation_text, document_id, pmid, doi,
                           relevance_score, supports_statement, created_at
                    FROM factcheck.evidence
                    WHERE evaluation_id = %s
                """, (evaluation_id,))
                results = []
                for row in cur.fetchall():
                    results.append(Evidence(
                        evidence_id=row[0],
                        evaluation_id=row[1],
                        citation_text=row[2],
                        document_id=row[3],
                        pmid=row[4],
                        doi=row[5],
                        relevance_score=row[6],
                        supports_statement=row[7],
                        created_at=row[8].isoformat() if row[8] else None
                    ))
                return results

    # ========== Human Annotation Operations ==========

    def insert_human_annotation(self, annotation: HumanAnnotation) -> int:
        """
        Insert or update a human annotation.

        Args:
            annotation: HumanAnnotation object

        Returns:
            Annotation ID
        """
        with self.db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                # Upsert using ON CONFLICT
                cur.execute("""
                    INSERT INTO factcheck.human_annotations (
                        statement_id, annotator_id, annotation, explanation, confidence,
                        review_duration_seconds, session_id
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (statement_id, annotator_id)
                    DO UPDATE SET
                        annotation = EXCLUDED.annotation,
                        explanation = EXCLUDED.explanation,
                        confidence = EXCLUDED.confidence,
                        review_duration_seconds = EXCLUDED.review_duration_seconds,
                        review_date = NOW(),
                        session_id = EXCLUDED.session_id
                    RETURNING annotation_id
                """, (annotation.statement_id, annotation.annotator_id, annotation.annotation,
                      annotation.explanation, annotation.confidence, annotation.review_duration_seconds,
                      annotation.session_id))
                return cur.fetchone()[0]

    def get_human_annotations(self, statement_id: int) -> List[HumanAnnotation]:
        """Get all human annotations for a statement."""
        with self.db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT annotation_id, statement_id, annotator_id, annotation, explanation,
                           confidence, review_duration_seconds, review_date, session_id
                    FROM factcheck.human_annotations
                    WHERE statement_id = %s
                """, (statement_id,))
                results = []
                for row in cur.fetchall():
                    results.append(HumanAnnotation(
                        annotation_id=row[0],
                        statement_id=row[1],
                        annotator_id=row[2],
                        annotation=row[3],
                        explanation=row[4],
                        confidence=row[5],
                        review_duration_seconds=row[6],
                        review_date=row[7].isoformat() if row[7] else None,
                        session_id=row[8]
                    ))
                return results

    # ========== Processing Metadata Operations ==========

    def insert_processing_session(self, session_data: Dict[str, Any]) -> int:
        """Insert a new processing session."""
        with self.db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                # Convert config_snapshot to JSONB
                config_jsonb = None
                if session_data.get('config_snapshot'):
                    if isinstance(session_data['config_snapshot'], str):
                        config_jsonb = json.loads(session_data['config_snapshot'])
                    else:
                        config_jsonb = session_data['config_snapshot']

                cur.execute("""
                    INSERT INTO factcheck.processing_metadata (
                        session_id, input_file, total_statements, start_time, status, config_snapshot
                    ) VALUES (%s, %s, %s, %s, %s, %s)
                    RETURNING metadata_id
                """, (session_data['session_id'], session_data['input_file'], session_data['total_statements'],
                      session_data['start_time'], session_data['status'], json.dumps(config_jsonb) if config_jsonb else None))
                return cur.fetchone()[0]

    def update_processing_session(self, session_id: str, updates: Dict[str, Any]):
        """Update a processing session."""
        with self.db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                # Build dynamic UPDATE query
                set_clauses = []
                values = []
                for key, value in updates.items():
                    set_clauses.append(f"{key} = %s")
                    values.append(value)
                values.append(session_id)

                query = f"""
                    UPDATE factcheck.processing_metadata
                    SET {', '.join(set_clauses)}
                    WHERE session_id = %s
                """
                cur.execute(query, values)

    # ========== Query Operations ==========

    def get_all_statements_with_evaluations(self) -> List[Dict[str, Any]]:
        """
        Get all statements with their latest AI evaluations and evidence.

        Returns:
            List of dictionaries containing statement, evaluation, and evidence data
        """
        with self.db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT
                        s.statement_id as id,
                        s.statement_text,
                        s.input_statement_id,
                        s.expected_answer,
                        s.created_at,
                        s.source_file,
                        s.review_status,
                        ae.evaluation_id as eval_id,
                        ae.evaluation,
                        ae.reason,
                        ae.confidence,
                        ae.documents_reviewed,
                        ae.supporting_citations,
                        ae.contradicting_citations,
                        ae.neutral_citations,
                        ae.matches_expected,
                        ae.model_used
                    FROM factcheck.statements s
                    LEFT JOIN factcheck.ai_evaluations ae ON s.statement_id = ae.statement_id
                    LEFT JOIN (
                        SELECT statement_id, MAX(version) as max_version
                        FROM factcheck.ai_evaluations
                        GROUP BY statement_id
                    ) latest ON ae.statement_id = latest.statement_id AND ae.version = latest.max_version
                    ORDER BY s.statement_id
                """)

                results = []
                for row in cur.fetchall():
                    row_dict = {
                        'id': row[0],
                        'statement_text': row[1],
                        'input_statement_id': row[2],
                        'expected_answer': row[3],
                        'created_at': row[4].isoformat() if row[4] else None,
                        'source_file': row[5],
                        'review_status': row[6],
                        'eval_id': row[7],
                        'evaluation': row[8],
                        'reason': row[9],
                        'confidence': row[10],
                        'documents_reviewed': row[11],
                        'supporting_citations': row[12],
                        'contradicting_citations': row[13],
                        'neutral_citations': row[14],
                        'matches_expected': row[15],
                        'model_used': row[16]
                    }

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

    def get_statements_needing_evaluation(self, statement_texts: List[str]) -> List[str]:
        """
        Check which statements from the list need AI evaluation.

        Args:
            statement_texts: List of statement texts to check

        Returns:
            List of statement texts that don't have AI evaluations yet
        """
        if not statement_texts:
            return []

        with self.db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                # Use helper function
                cur.execute("""
                    SELECT * FROM factcheck.get_statements_needing_evaluation(%s)
                """, (statement_texts,))
                return [row[0] for row in cur.fetchall()]

    def get_inter_annotator_agreement(self) -> Dict[str, Any]:
        """
        Calculate inter-annotator agreement statistics.

        Returns:
            Dictionary with agreement metrics
        """
        with self.db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                # Use helper function
                cur.execute("SELECT * FROM factcheck.calculate_inter_annotator_agreement()")
                row = cur.fetchone()
                if row:
                    return {
                        "total_pairs": row[0],
                        "agreements": row[1],
                        "disagreements": row[2],
                        "agreement_percentage": float(row[3])
                    }
                return {"total_pairs": 0, "agreements": 0, "disagreements": 0, "agreement_percentage": 0.0}

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
                "database": "PostgreSQL factcheck schema"
            }
        }

        # Write to file
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, indent=2)

        # Record export in history
        with self.db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO factcheck.export_history (export_type, output_file, statement_count, requested_by)
                    VALUES (%s, %s, %s, %s)
                """, (export_type, str(output_path), len(data), requested_by))

        logger.info(f"Exported {len(data)} statements to {output_path}")
        return str(output_path)

    def import_json_results(self, json_file: str, skip_existing: bool = True) -> Dict[str, int]:
        """
        Import fact-check results from legacy JSON format.

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

            # Handle both formats
            if isinstance(data, dict) and 'results' in data:
                results = data['results']
            elif isinstance(data, list):
                results = data
            else:
                raise ValueError("Invalid JSON format")

            stats['total_in_file'] = len(results)

            with self.db_manager.get_connection() as conn:
                with conn.cursor() as cur:
                    for result in results:
                        try:
                            statement_text = result.get('statement', '')
                            if not statement_text:
                                stats['errors'] += 1
                                continue

                            # Check if statement exists and has evaluation
                            cur.execute("""
                                SELECT s.statement_id, ae.evaluation_id
                                FROM factcheck.statements s
                                LEFT JOIN factcheck.ai_evaluations ae ON s.statement_id = ae.statement_id
                                WHERE s.statement_text = %s
                                LIMIT 1
                            """, (statement_text,))
                            existing = cur.fetchone()

                            if existing and existing[1] and skip_existing:
                                # Statement exists with evaluation - skip
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
                                    # Extract document_id (convert to int if needed)
                                    doc_id_str = evidence_data.get('document_id')
                                    if doc_id_str:
                                        try:
                                            doc_id = int(doc_id_str) if isinstance(doc_id_str, str) else doc_id_str
                                        except (ValueError, TypeError):
                                            logger.warning(f"Invalid document_id: {doc_id_str}")
                                            continue

                                        evidence = Evidence(
                                            evaluation_id=eval_id,
                                            citation_text=evidence_data.get('citation', ''),
                                            document_id=doc_id,
                                            pmid=evidence_data.get('pmid', '').replace('PMID:', ''),
                                            doi=evidence_data.get('doi', '').replace('DOI:', ''),
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
