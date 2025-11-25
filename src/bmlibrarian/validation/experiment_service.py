"""
Experiment Service for BMLibrarian.

Provides CRUD operations for validation experiments and their associated documents.
Used for managing test cases, benchmark datasets, and validation collections.

Usage:
    from bmlibrarian.validation.experiment_service import ExperimentService

    service = ExperimentService()

    # Create an experiment
    exp_id = service.create_experiment("Chunking Test Set", "Documents for testing chunking")

    # Add documents to experiment
    service.add_document(exp_id, document_id, comment="Good example of long abstract")

    # Get all documents in an experiment
    docs = service.get_experiment_documents(exp_id)

    # List all experiments
    experiments = service.list_experiments()
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

from bmlibrarian.database import get_db_manager

logger = logging.getLogger(__name__)


@dataclass
class Experiment:
    """Represents a validation experiment."""

    id: int
    name: str
    description: Optional[str]
    created_at: datetime
    updated_at: datetime
    document_count: int = 0


@dataclass
class ExperimentDocument:
    """Represents a document in an experiment."""

    id: int
    experiment_id: int
    document_id: int
    comment: Optional[str]
    added_at: datetime
    # Document metadata (populated when fetching)
    title: Optional[str] = None
    doi: Optional[str] = None
    pmid: Optional[str] = None


class ExperimentService:
    """
    Service for managing validation experiments and their documents.

    Provides methods for creating experiments, adding/removing documents,
    and querying experiment contents.
    """

    def __init__(self) -> None:
        """Initialize the experiment service."""
        self.db_manager = get_db_manager()

    def create_experiment(
        self, name: str, description: Optional[str] = None
    ) -> int:
        """
        Create a new experiment.

        Args:
            name: Unique name for the experiment.
            description: Optional description of the experiment's purpose.

        Returns:
            The ID of the created experiment.

        Raises:
            ValueError: If an experiment with this name already exists.
        """
        with self.db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                try:
                    cur.execute(
                        """
                        INSERT INTO validation.experiment (name, description)
                        VALUES (%s, %s)
                        RETURNING id
                        """,
                        (name, description),
                    )
                    result = cur.fetchone()
                    experiment_id = result[0] if result else 0
                    conn.commit()
                    logger.info(f"Created experiment '{name}' with ID {experiment_id}")
                    return experiment_id
                except Exception as e:
                    conn.rollback()
                    if "unique" in str(e).lower():
                        raise ValueError(f"Experiment '{name}' already exists") from e
                    raise

    def get_experiment(self, experiment_id: int) -> Optional[Experiment]:
        """
        Get an experiment by ID.

        Args:
            experiment_id: The experiment ID.

        Returns:
            Experiment object or None if not found.
        """
        with self.db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT e.id, e.name, e.description, e.created_at, e.updated_at,
                           COUNT(ed.id) as doc_count
                    FROM validation.experiment e
                    LEFT JOIN validation.experiment_document ed ON e.id = ed.experiment_id
                    WHERE e.id = %s
                    GROUP BY e.id
                    """,
                    (experiment_id,),
                )
                row = cur.fetchone()
                if row:
                    return Experiment(
                        id=row[0],
                        name=row[1],
                        description=row[2],
                        created_at=row[3],
                        updated_at=row[4],
                        document_count=row[5],
                    )
                return None

    def get_experiment_by_name(self, name: str) -> Optional[Experiment]:
        """
        Get an experiment by name.

        Args:
            name: The experiment name.

        Returns:
            Experiment object or None if not found.
        """
        with self.db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT e.id, e.name, e.description, e.created_at, e.updated_at,
                           COUNT(ed.id) as doc_count
                    FROM validation.experiment e
                    LEFT JOIN validation.experiment_document ed ON e.id = ed.experiment_id
                    WHERE e.name = %s
                    GROUP BY e.id
                    """,
                    (name,),
                )
                row = cur.fetchone()
                if row:
                    return Experiment(
                        id=row[0],
                        name=row[1],
                        description=row[2],
                        created_at=row[3],
                        updated_at=row[4],
                        document_count=row[5],
                    )
                return None

    def list_experiments(self) -> List[Experiment]:
        """
        List all experiments.

        Returns:
            List of Experiment objects ordered by creation date (newest first).
        """
        with self.db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT e.id, e.name, e.description, e.created_at, e.updated_at,
                           COUNT(ed.id) as doc_count
                    FROM validation.experiment e
                    LEFT JOIN validation.experiment_document ed ON e.id = ed.experiment_id
                    GROUP BY e.id
                    ORDER BY e.created_at DESC
                    """
                )
                return [
                    Experiment(
                        id=row[0],
                        name=row[1],
                        description=row[2],
                        created_at=row[3],
                        updated_at=row[4],
                        document_count=row[5],
                    )
                    for row in cur.fetchall()
                ]

    def update_experiment(
        self,
        experiment_id: int,
        name: Optional[str] = None,
        description: Optional[str] = None,
    ) -> bool:
        """
        Update an experiment's name and/or description.

        Args:
            experiment_id: The experiment ID.
            name: New name (optional).
            description: New description (optional).

        Returns:
            True if updated, False if experiment not found.
        """
        if name is None and description is None:
            return False

        with self.db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                updates = []
                params = []
                if name is not None:
                    updates.append("name = %s")
                    params.append(name)
                if description is not None:
                    updates.append("description = %s")
                    params.append(description)
                updates.append("updated_at = CURRENT_TIMESTAMP")
                params.append(experiment_id)

                cur.execute(
                    f"""
                    UPDATE validation.experiment
                    SET {", ".join(updates)}
                    WHERE id = %s
                    """,
                    params,
                )
                conn.commit()
                return cur.rowcount > 0

    def delete_experiment(self, experiment_id: int) -> bool:
        """
        Delete an experiment and all its document associations.

        Args:
            experiment_id: The experiment ID.

        Returns:
            True if deleted, False if experiment not found.
        """
        with self.db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM validation.experiment WHERE id = %s",
                    (experiment_id,),
                )
                conn.commit()
                deleted = cur.rowcount > 0
                if deleted:
                    logger.info(f"Deleted experiment {experiment_id}")
                return deleted

    def add_document(
        self,
        experiment_id: int,
        document_id: int,
        comment: Optional[str] = None,
    ) -> int:
        """
        Add a document to an experiment.

        Args:
            experiment_id: The experiment ID.
            document_id: The document ID from public.document.
            comment: Optional comment about why this document was added.

        Returns:
            The ID of the created association.

        Raises:
            ValueError: If the document is already in the experiment.
        """
        with self.db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                try:
                    cur.execute(
                        """
                        INSERT INTO validation.experiment_document
                            (experiment_id, document_id, comment)
                        VALUES (%s, %s, %s)
                        RETURNING id
                        """,
                        (experiment_id, document_id, comment),
                    )
                    result = cur.fetchone()
                    assoc_id = result[0] if result else 0

                    # Update experiment timestamp
                    cur.execute(
                        """
                        UPDATE validation.experiment
                        SET updated_at = CURRENT_TIMESTAMP
                        WHERE id = %s
                        """,
                        (experiment_id,),
                    )
                    conn.commit()
                    logger.info(
                        f"Added document {document_id} to experiment {experiment_id}"
                    )
                    return assoc_id
                except Exception as e:
                    conn.rollback()
                    if "unique" in str(e).lower():
                        raise ValueError(
                            f"Document {document_id} already in experiment {experiment_id}"
                        ) from e
                    raise

    def remove_document(self, experiment_id: int, document_id: int) -> bool:
        """
        Remove a document from an experiment.

        Args:
            experiment_id: The experiment ID.
            document_id: The document ID.

        Returns:
            True if removed, False if association not found.
        """
        with self.db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    DELETE FROM validation.experiment_document
                    WHERE experiment_id = %s AND document_id = %s
                    """,
                    (experiment_id, document_id),
                )
                if cur.rowcount > 0:
                    cur.execute(
                        """
                        UPDATE validation.experiment
                        SET updated_at = CURRENT_TIMESTAMP
                        WHERE id = %s
                        """,
                        (experiment_id,),
                    )
                conn.commit()
                return cur.rowcount > 0

    def update_document_comment(
        self, experiment_id: int, document_id: int, comment: Optional[str]
    ) -> bool:
        """
        Update the comment for a document in an experiment.

        Args:
            experiment_id: The experiment ID.
            document_id: The document ID.
            comment: New comment (or None to clear).

        Returns:
            True if updated, False if association not found.
        """
        with self.db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE validation.experiment_document
                    SET comment = %s
                    WHERE experiment_id = %s AND document_id = %s
                    """,
                    (comment, experiment_id, document_id),
                )
                conn.commit()
                return cur.rowcount > 0

    def get_experiment_documents(
        self, experiment_id: int
    ) -> List[ExperimentDocument]:
        """
        Get all documents in an experiment with their metadata.

        Args:
            experiment_id: The experiment ID.

        Returns:
            List of ExperimentDocument objects with document metadata.
        """
        with self.db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT ed.id, ed.experiment_id, ed.document_id, ed.comment,
                           ed.added_at, d.title, d.doi, d.pmid
                    FROM validation.experiment_document ed
                    JOIN public.document d ON ed.document_id = d.id
                    WHERE ed.experiment_id = %s
                    ORDER BY ed.added_at DESC
                    """,
                    (experiment_id,),
                )
                return [
                    ExperimentDocument(
                        id=row[0],
                        experiment_id=row[1],
                        document_id=row[2],
                        comment=row[3],
                        added_at=row[4],
                        title=row[5],
                        doi=row[6],
                        pmid=row[7],
                    )
                    for row in cur.fetchall()
                ]

    def get_experiment_document_ids(self, experiment_id: int) -> List[int]:
        """
        Get just the document IDs for an experiment.

        Args:
            experiment_id: The experiment ID.

        Returns:
            List of document IDs.
        """
        with self.db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT document_id
                    FROM validation.experiment_document
                    WHERE experiment_id = %s
                    ORDER BY added_at
                    """,
                    (experiment_id,),
                )
                return [row[0] for row in cur.fetchall()]

    def is_document_in_experiment(
        self, experiment_id: int, document_id: int
    ) -> bool:
        """
        Check if a document is in an experiment.

        Args:
            experiment_id: The experiment ID.
            document_id: The document ID.

        Returns:
            True if document is in experiment.
        """
        with self.db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT 1 FROM validation.experiment_document
                    WHERE experiment_id = %s AND document_id = %s
                    """,
                    (experiment_id, document_id),
                )
                return cur.fetchone() is not None

    def get_document_experiments(self, document_id: int) -> List[Experiment]:
        """
        Get all experiments that contain a specific document.

        Args:
            document_id: The document ID.

        Returns:
            List of Experiment objects.
        """
        with self.db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT e.id, e.name, e.description, e.created_at, e.updated_at,
                           (SELECT COUNT(*) FROM validation.experiment_document
                            WHERE experiment_id = e.id) as doc_count
                    FROM validation.experiment e
                    JOIN validation.experiment_document ed ON e.id = ed.experiment_id
                    WHERE ed.document_id = %s
                    ORDER BY e.name
                    """,
                    (document_id,),
                )
                return [
                    Experiment(
                        id=row[0],
                        name=row[1],
                        description=row[2],
                        created_at=row[3],
                        updated_at=row[4],
                        document_count=row[5],
                    )
                    for row in cur.fetchall()
                ]
