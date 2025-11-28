"""
Document store for persisting writing documents and versions.

Provides database operations for the writing schema including:
- Document CRUD operations
- Version management (autosave, manual save)
- Version cleanup
"""

import json
import logging
from datetime import datetime
from typing import List, Optional, Dict, Any, TYPE_CHECKING

from .models import WritingDocument, DocumentVersion
from .constants import MAX_VERSIONS

if TYPE_CHECKING:
    from bmlibrarian.database import DatabaseManager

logger = logging.getLogger(__name__)


class DocumentStore:
    """
    Database operations for writing documents and versions.

    Handles persistence to the writing schema in PostgreSQL.
    """

    def __init__(self) -> None:
        """Initialize document store."""
        self._db_manager = None

    def _get_db_manager(self) -> "DatabaseManager":
        """
        Lazy load database manager.

        Returns:
            DatabaseManager instance
        """
        if self._db_manager is None:
            from bmlibrarian.database import get_db_manager
            self._db_manager = get_db_manager()
        return self._db_manager

    def create_document(
        self,
        title: str = "Untitled Document",
        content: str = "",
        user_id: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> WritingDocument:
        """
        Create a new document.

        Args:
            title: Document title
            content: Initial content
            user_id: Optional user association
            metadata: Optional metadata dictionary

        Returns:
            Created WritingDocument with ID
        """
        db = self._get_db_manager()

        with db.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO writing.documents (title, content, user_id, metadata)
                    VALUES (%s, %s, %s, %s)
                    RETURNING id, created_at, updated_at
                    """,
                    (title, content, user_id, json.dumps(metadata or {}))
                )
                row = cur.fetchone()

        return WritingDocument(
            id=row[0],
            title=title,
            content=content,
            user_id=user_id,
            metadata=metadata or {},
            created_at=row[1],
            updated_at=row[2]
        )

    def save_document(
        self,
        document: WritingDocument,
        version_type: str = "manual"
    ) -> WritingDocument:
        """
        Save a document (create or update).

        Args:
            document: Document to save
            version_type: Type of save (autosave, manual, export)

        Returns:
            Updated document
        """
        if document.is_new:
            return self.create_document(
                title=document.title,
                content=document.content,
                user_id=document.user_id,
                metadata=document.metadata
            )

        db = self._get_db_manager()

        with db.get_connection() as conn:
            with conn.cursor() as cur:
                # Update document
                cur.execute(
                    """
                    UPDATE writing.documents
                    SET title = %s, content = %s, metadata = %s
                    WHERE id = %s
                    RETURNING updated_at
                    """,
                    (
                        document.title,
                        document.content,
                        json.dumps(document.metadata),
                        document.id
                    )
                )
                row = cur.fetchone()
                if row:
                    document.updated_at = row[0]

                # Create version snapshot
                cur.execute(
                    """
                    INSERT INTO writing.document_versions
                        (document_id, content, title, version_type)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (document.id, document.content, document.title, version_type)
                )

                # Cleanup old versions if this is an autosave
                if version_type == "autosave":
                    cur.execute(
                        "SELECT writing.cleanup_old_versions(%s, %s)",
                        (document.id, MAX_VERSIONS)
                    )

        return document

    def autosave_document(
        self,
        document: WritingDocument
    ) -> WritingDocument:
        """
        Autosave a document (only saves if content changed).

        Args:
            document: Document to autosave

        Returns:
            Updated document
        """
        if document.is_new:
            # For new documents, only save if there's content
            if not document.content.strip():
                return document
            return self.create_document(
                title=document.title,
                content=document.content,
                user_id=document.user_id,
                metadata=document.metadata
            )

        # Check if content has changed
        current = self.load_document(document.id)
        if current and current.content == document.content:
            # No changes, skip autosave
            return document

        return self.save_document(document, version_type="autosave")

    def load_document(self, document_id: int) -> Optional[WritingDocument]:
        """
        Load a document by ID.

        Args:
            document_id: Document ID

        Returns:
            WritingDocument or None if not found
        """
        db = self._get_db_manager()

        with db.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, title, content, metadata, created_at, updated_at, user_id
                    FROM writing.documents
                    WHERE id = %s
                    """,
                    (document_id,)
                )
                row = cur.fetchone()

        if not row:
            return None

        metadata = row[3] if isinstance(row[3], dict) else json.loads(row[3] or '{}')

        return WritingDocument(
            id=row[0],
            title=row[1],
            content=row[2],
            metadata=metadata,
            created_at=row[4],
            updated_at=row[5],
            user_id=row[6]
        )

    def delete_document(self, document_id: int) -> bool:
        """
        Delete a document and all its versions.

        Args:
            document_id: Document ID to delete

        Returns:
            True if deleted, False if not found
        """
        db = self._get_db_manager()

        with db.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM writing.documents WHERE id = %s RETURNING id",
                    (document_id,)
                )
                row = cur.fetchone()

        return row is not None

    def list_documents(
        self,
        user_id: Optional[int] = None,
        limit: int = 50,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        List documents with summary information.

        Args:
            user_id: Optional filter by user
            limit: Maximum results
            offset: Offset for pagination

        Returns:
            List of document summaries
        """
        db = self._get_db_manager()

        with db.get_connection() as conn:
            with conn.cursor() as cur:
                if user_id is not None:
                    cur.execute(
                        """
                        SELECT id, title, LENGTH(content) as content_length,
                               created_at, updated_at, user_id
                        FROM writing.documents
                        WHERE user_id = %s
                        ORDER BY updated_at DESC
                        LIMIT %s OFFSET %s
                        """,
                        (user_id, limit, offset)
                    )
                else:
                    cur.execute(
                        """
                        SELECT id, title, LENGTH(content) as content_length,
                               created_at, updated_at, user_id
                        FROM writing.documents
                        ORDER BY updated_at DESC
                        LIMIT %s OFFSET %s
                        """,
                        (limit, offset)
                    )
                rows = cur.fetchall()

        return [
            {
                'id': row[0],
                'title': row[1],
                'content_length': row[2],
                'created_at': row[3],
                'updated_at': row[4],
                'user_id': row[5]
            }
            for row in rows
        ]

    def get_versions(
        self,
        document_id: int,
        limit: int = 20
    ) -> List[DocumentVersion]:
        """
        Get version history for a document.

        Args:
            document_id: Document ID
            limit: Maximum versions to return

        Returns:
            List of DocumentVersion objects (most recent first)
        """
        db = self._get_db_manager()

        with db.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, document_id, content, title, version_type, saved_at
                    FROM writing.document_versions
                    WHERE document_id = %s
                    ORDER BY saved_at DESC
                    LIMIT %s
                    """,
                    (document_id, limit)
                )
                rows = cur.fetchall()

        return [
            DocumentVersion(
                id=row[0],
                document_id=row[1],
                content=row[2],
                title=row[3],
                version_type=row[4],
                saved_at=row[5]
            )
            for row in rows
        ]

    def restore_version(
        self,
        document_id: int,
        version_id: int
    ) -> Optional[WritingDocument]:
        """
        Restore a document to a previous version.

        Creates a new version snapshot before restoring.

        Args:
            document_id: Document ID
            version_id: Version ID to restore

        Returns:
            Updated document or None if not found
        """
        db = self._get_db_manager()

        with db.get_connection() as conn:
            with conn.cursor() as cur:
                # Get the version to restore
                cur.execute(
                    """
                    SELECT content, title
                    FROM writing.document_versions
                    WHERE id = %s AND document_id = %s
                    """,
                    (version_id, document_id)
                )
                version_row = cur.fetchone()

                if not version_row:
                    return None

                content, title = version_row

                # Create backup of current state
                cur.execute(
                    """
                    INSERT INTO writing.document_versions
                        (document_id, content, title, version_type)
                    SELECT id, content, title, 'manual'
                    FROM writing.documents
                    WHERE id = %s
                    """,
                    (document_id,)
                )

                # Update document with restored content
                cur.execute(
                    """
                    UPDATE writing.documents
                    SET content = %s, title = COALESCE(%s, title)
                    WHERE id = %s
                    RETURNING id, title, content, metadata, created_at, updated_at, user_id
                    """,
                    (content, title, document_id)
                )
                row = cur.fetchone()

        if not row:
            return None

        metadata = row[3] if isinstance(row[3], dict) else json.loads(row[3] or '{}')

        return WritingDocument(
            id=row[0],
            title=row[1],
            content=row[2],
            metadata=metadata,
            created_at=row[4],
            updated_at=row[5],
            user_id=row[6]
        )

    def cleanup_old_versions(
        self,
        document_id: int,
        max_versions: int = MAX_VERSIONS
    ) -> int:
        """
        Clean up old autosave versions for a document.

        Args:
            document_id: Document ID
            max_versions: Maximum autosave versions to keep

        Returns:
            Number of versions deleted
        """
        db = self._get_db_manager()

        with db.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT writing.cleanup_old_versions(%s, %s)",
                    (document_id, max_versions)
                )
                row = cur.fetchone()

        return row[0] if row else 0

    def update_metadata(
        self,
        document_id: int,
        metadata: Dict[str, Any]
    ) -> bool:
        """
        Update document metadata without changing content.

        Args:
            document_id: Document ID
            metadata: New metadata dictionary

        Returns:
            True if updated successfully
        """
        db = self._get_db_manager()

        with db.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE writing.documents
                    SET metadata = %s
                    WHERE id = %s
                    RETURNING id
                    """,
                    (json.dumps(metadata), document_id)
                )
                row = cur.fetchone()

        return row is not None

    def get_most_recent_document(
        self,
        user_id: Optional[int] = None
    ) -> Optional[WritingDocument]:
        """
        Get the most recently updated document.

        Args:
            user_id: Optional filter by user

        Returns:
            Most recent WritingDocument or None if no documents exist
        """
        db = self._get_db_manager()

        with db.get_connection() as conn:
            with conn.cursor() as cur:
                if user_id is not None:
                    cur.execute(
                        """
                        SELECT id, title, content, metadata, created_at, updated_at, user_id
                        FROM writing.documents
                        WHERE user_id = %s
                        ORDER BY updated_at DESC
                        LIMIT 1
                        """,
                        (user_id,)
                    )
                else:
                    cur.execute(
                        """
                        SELECT id, title, content, metadata, created_at, updated_at, user_id
                        FROM writing.documents
                        ORDER BY updated_at DESC
                        LIMIT 1
                        """
                    )
                row = cur.fetchone()

        if not row:
            return None

        metadata = row[3] if isinstance(row[3], dict) else json.loads(row[3] or '{}')

        return WritingDocument(
            id=row[0],
            title=row[1],
            content=row[2],
            metadata=metadata,
            created_at=row[4],
            updated_at=row[5],
            user_id=row[6]
        )

    def search_documents(
        self,
        query: str,
        user_id: Optional[int] = None,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Search documents by title.

        Args:
            query: Search query
            user_id: Optional filter by user
            limit: Maximum results

        Returns:
            List of matching document summaries
        """
        db = self._get_db_manager()

        search_pattern = f"%{query}%"

        with db.get_connection() as conn:
            with conn.cursor() as cur:
                if user_id is not None:
                    cur.execute(
                        """
                        SELECT id, title, LENGTH(content) as content_length,
                               created_at, updated_at
                        FROM writing.documents
                        WHERE user_id = %s AND title ILIKE %s
                        ORDER BY updated_at DESC
                        LIMIT %s
                        """,
                        (user_id, search_pattern, limit)
                    )
                else:
                    cur.execute(
                        """
                        SELECT id, title, LENGTH(content) as content_length,
                               created_at, updated_at
                        FROM writing.documents
                        WHERE title ILIKE %s
                        ORDER BY updated_at DESC
                        LIMIT %s
                        """,
                        (search_pattern, limit)
                    )
                rows = cur.fetchall()

        return [
            {
                'id': row[0],
                'title': row[1],
                'content_length': row[2],
                'created_at': row[3],
                'updated_at': row[4]
            }
            for row in rows
        ]
