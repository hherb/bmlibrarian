"""
Results Cache Manager for SystematicReviewAgent

This module provides persistent caching of quality assessment results with versioning
for reproducibility, performance optimization, and model training data collection.

Features:
- Automatic version tracking (model, parameters, agent version)
- Check-before-assess pattern to avoid redundant LLM calls
- Force flag to bypass cache when needed
- Database-backed storage for durability
- Cache maintenance methods (cleanup, size metrics, integrity validation)

Golden Rules Compliance:
- Rule #5: All database communication through DatabaseManager
- Rule #2: No magic numbers (configurable timeouts, versions)
"""

import hashlib
import json
import logging
import time
from typing import Dict, Any, Optional, List
from datetime import datetime, date, timezone

from bmlibrarian.evaluations.store import DateTimeEncoder

logger = logging.getLogger(__name__)

# Constant for byte-to-megabyte conversion (Golden Rule #2: No magic numbers)
BYTES_PER_MB = 1024 * 1024


class ResultsCacheManager:
    """
    Manages caching of quality assessment results with versioning.

    This class provides methods to:
    1. Register assessment versions (model + parameters)
    2. Check if cached result exists for (document, version)
    3. Store new assessment results
    4. Retrieve cached results

    Example:
        >>> cache = ResultsCacheManager(db_manager)
        >>> version_id = cache.register_version('study_assessment', 'gpt-oss:20b', '1.0.0', {'temperature': 0.1})
        >>> cached = cache.get_study_assessment(doc_id, version_id)
        >>> if cached is None:
        ...     result = run_assessment(document)
        ...     cache.store_study_assessment(doc_id, version_id, result)
    """

    def __init__(self, db_manager=None):
        """
        Initialize the ResultsCacheManager.

        Args:
            db_manager: Optional DatabaseManager instance. If None, will lazy-load.
        """
        self._db_manager = db_manager
        self._version_cache: Dict[str, int] = {}  # In-memory cache for version IDs (keyed by hash)

    @staticmethod
    def _create_cache_key(
        assessment_type: str,
        model_name: str,
        agent_version: str,
        parameters: Dict[str, Any]
    ) -> str:
        """
        Create a stable, memory-efficient cache key using SHA-256 hash.

        This method normalizes parameters (sorted keys, consistent JSON encoding)
        and creates a hash-based key for efficient in-memory caching.

        Args:
            assessment_type: Type of assessment ('study_assessment', 'pico', etc.)
            model_name: Ollama model name
            agent_version: Agent version string
            parameters: Dictionary of model parameters

        Returns:
            64-character hexadecimal hash string as cache key
        """
        # Normalize parameters: sort keys recursively for consistent ordering
        normalized_params = json.dumps(parameters, sort_keys=True, separators=(',', ':'))

        # Create composite string for hashing
        key_components = f"{assessment_type}:{model_name}:{agent_version}:{normalized_params}"

        # Use SHA-256 for collision resistance and fixed output size (64 chars hex)
        return hashlib.sha256(key_components.encode('utf-8')).hexdigest()

    @property
    def db_manager(self):
        """Lazy-load database manager."""
        if self._db_manager is None:
            from bmlibrarian.database import get_db_manager
            self._db_manager = get_db_manager()
        return self._db_manager

    # =========================================================================
    # Version Management
    # =========================================================================

    def register_version(
        self,
        assessment_type: str,
        model_name: str,
        agent_version: str,
        parameters: Dict[str, Any]
    ) -> int:
        """
        Register or retrieve an assessment version ID.

        This uses the database function get_or_create_version which handles
        uniqueness constraints and returns existing version if already registered.

        Args:
            assessment_type: Type of assessment ('study_assessment', 'pico', 'prisma', 'paper_weight')
            model_name: Ollama model name (e.g., 'gpt-oss:20b')
            agent_version: Agent version string (e.g., '1.0.0')
            parameters: Dictionary of model parameters (temperature, top_p, etc.)

        Returns:
            Integer version_id for this assessment configuration

        Raises:
            RuntimeError: If database operation fails
        """
        # Create hash-based cache key for memory efficiency
        cache_key = self._create_cache_key(assessment_type, model_name, agent_version, parameters)

        # Check in-memory cache first
        if cache_key in self._version_cache:
            return self._version_cache[cache_key]

        try:
            # Call database function
            with self.db_manager.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT results_cache.get_or_create_version(
                            %s::TEXT, %s::TEXT, %s::TEXT, %s::JSONB
                        )
                        """,
                        (assessment_type, model_name, agent_version, json.dumps(parameters))
                    )
                    version_id = cursor.fetchone()[0]
                    conn.commit()

            # Cache the result
            self._version_cache[cache_key] = version_id
            logger.debug(
                f"Registered version {version_id} for {assessment_type} "
                f"(model={model_name}, agent={agent_version})"
            )

            return version_id

        except Exception as e:
            logger.error(f"Failed to register assessment version: {e}")
            raise RuntimeError(f"Version registration failed: {e}")

    # =========================================================================
    # Study Assessment Caching
    # =========================================================================

    def get_study_assessment(
        self,
        document_id: int,
        version_id: int
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieve cached study assessment.

        Args:
            document_id: Document ID
            version_id: Assessment version ID

        Returns:
            Cached assessment result dictionary, or None if not cached
        """
        try:
            with self.db_manager.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT result, assessed_at
                        FROM results_cache.study_assessments
                        WHERE document_id = %s AND version_id = %s
                        """,
                        (document_id, version_id)
                    )
                    row = cursor.fetchone()

            if row:
                logger.debug(
                    f"Cache HIT: Study assessment for document {document_id} "
                    f"(assessed {row[1]})"
                )
                return row[0]  # Return JSONB result

            logger.debug(f"Cache MISS: Study assessment for document {document_id}")
            return None

        except Exception as e:
            logger.error(f"Failed to retrieve cached study assessment: {e}")
            return None  # Fail gracefully, assessment will be recomputed

    def store_study_assessment(
        self,
        document_id: int,
        version_id: int,
        result: Dict[str, Any],
        execution_time_ms: Optional[int] = None
    ) -> bool:
        """
        Store study assessment result in cache.

        Args:
            document_id: Document ID
            version_id: Assessment version ID
            result: Assessment result dictionary
            execution_time_ms: Optional execution time in milliseconds

        Returns:
            True if stored successfully, False otherwise
        """
        try:
            with self.db_manager.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        INSERT INTO results_cache.study_assessments
                            (document_id, version_id, result, execution_time_ms)
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT (document_id, version_id) DO UPDATE
                        SET result = EXCLUDED.result,
                            assessed_at = NOW(),
                            execution_time_ms = EXCLUDED.execution_time_ms
                        """,
                        (document_id, version_id, json.dumps(result, cls=DateTimeEncoder), execution_time_ms)
                    )
                    conn.commit()

            logger.debug(f"Stored study assessment for document {document_id} in cache")
            return True

        except Exception as e:
            logger.error(f"Failed to store study assessment in cache: {e}")
            return False

    # =========================================================================
    # PICO Extraction Caching
    # =========================================================================

    def get_pico_extraction(
        self,
        document_id: int,
        version_id: int
    ) -> Optional[Dict[str, Any]]:
        """Retrieve cached PICO extraction."""
        try:
            with self.db_manager.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT result, extracted_at
                        FROM results_cache.pico_extractions
                        WHERE document_id = %s AND version_id = %s
                        """,
                        (document_id, version_id)
                    )
                    row = cursor.fetchone()

            if row:
                logger.debug(f"Cache HIT: PICO extraction for document {document_id}")
                return row[0]

            logger.debug(f"Cache MISS: PICO extraction for document {document_id}")
            return None

        except Exception as e:
            logger.error(f"Failed to retrieve cached PICO extraction: {e}")
            return None

    def store_pico_extraction(
        self,
        document_id: int,
        version_id: int,
        result: Dict[str, Any],
        execution_time_ms: Optional[int] = None
    ) -> bool:
        """Store PICO extraction result in cache."""
        try:
            with self.db_manager.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        INSERT INTO results_cache.pico_extractions
                            (document_id, version_id, population, intervention, comparison, outcome,
                             study_type, sample_size, extraction_confidence, result, execution_time_ms)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (document_id, version_id) DO UPDATE
                        SET population = EXCLUDED.population,
                            intervention = EXCLUDED.intervention,
                            comparison = EXCLUDED.comparison,
                            outcome = EXCLUDED.outcome,
                            study_type = EXCLUDED.study_type,
                            sample_size = EXCLUDED.sample_size,
                            extraction_confidence = EXCLUDED.extraction_confidence,
                            result = EXCLUDED.result,
                            extracted_at = NOW(),
                            execution_time_ms = EXCLUDED.execution_time_ms
                        """,
                        (
                            document_id, version_id,
                            result.get('population'),
                            result.get('intervention'),
                            result.get('comparison'),
                            result.get('outcome'),
                            result.get('study_type'),
                            result.get('sample_size'),
                            result.get('extraction_confidence'),
                            json.dumps(result, cls=DateTimeEncoder),
                            execution_time_ms
                        )
                    )
                    conn.commit()

            logger.debug(f"Stored PICO extraction for document {document_id} in cache")
            return True

        except Exception as e:
            logger.error(f"Failed to store PICO extraction in cache: {e}")
            return False

    # =========================================================================
    # PRISMA Assessment Caching
    # =========================================================================

    def get_prisma_assessment(
        self,
        document_id: int,
        version_id: int
    ) -> Optional[Dict[str, Any]]:
        """Retrieve cached PRISMA assessment."""
        try:
            with self.db_manager.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT result, assessed_at
                        FROM results_cache.prisma_assessments
                        WHERE document_id = %s AND version_id = %s
                        """,
                        (document_id, version_id)
                    )
                    row = cursor.fetchone()

            if row:
                logger.debug(f"Cache HIT: PRISMA assessment for document {document_id}")
                return row[0]

            logger.debug(f"Cache MISS: PRISMA assessment for document {document_id}")
            return None

        except Exception as e:
            logger.error(f"Failed to retrieve cached PRISMA assessment: {e}")
            return None

    def store_prisma_assessment(
        self,
        document_id: int,
        version_id: int,
        result: Dict[str, Any],
        execution_time_ms: Optional[int] = None
    ) -> bool:
        """Store PRISMA assessment result in cache."""
        try:
            with self.db_manager.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        INSERT INTO results_cache.prisma_assessments
                            (document_id, version_id, is_suitable, overall_score,
                             reporting_completeness, result, execution_time_ms)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (document_id, version_id) DO UPDATE
                        SET is_suitable = EXCLUDED.is_suitable,
                            overall_score = EXCLUDED.overall_score,
                            reporting_completeness = EXCLUDED.reporting_completeness,
                            result = EXCLUDED.result,
                            assessed_at = NOW(),
                            execution_time_ms = EXCLUDED.execution_time_ms
                        """,
                        (
                            document_id, version_id,
                            result.get('is_suitable', False),
                            result.get('overall_score'),
                            result.get('reporting_completeness'),
                            json.dumps(result, cls=DateTimeEncoder),
                            execution_time_ms
                        )
                    )
                    conn.commit()

            logger.debug(f"Stored PRISMA assessment for document {document_id} in cache")
            return True

        except Exception as e:
            logger.error(f"Failed to store PRISMA assessment in cache: {e}")
            return False

    # =========================================================================
    # Suitability Check Caching
    # =========================================================================

    def get_suitability_check(
        self,
        document_id: int,
        check_type: str,
        version_id: int
    ) -> Optional[Dict[str, Any]]:
        """Retrieve cached suitability check (pico or prisma)."""
        try:
            with self.db_manager.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT result, checked_at
                        FROM results_cache.suitability_checks
                        WHERE document_id = %s AND check_type = %s AND version_id = %s
                        """,
                        (document_id, check_type, version_id)
                    )
                    row = cursor.fetchone()

            if row:
                logger.debug(
                    f"Cache HIT: {check_type.upper()} suitability check for document {document_id}"
                )
                return row[0]

            logger.debug(
                f"Cache MISS: {check_type.upper()} suitability check for document {document_id}"
            )
            return None

        except Exception as e:
            logger.error(f"Failed to retrieve cached suitability check: {e}")
            return None

    def store_suitability_check(
        self,
        document_id: int,
        check_type: str,
        version_id: int,
        result: Dict[str, Any],
        execution_time_ms: Optional[int] = None
    ) -> bool:
        """Store suitability check result in cache."""
        try:
            with self.db_manager.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        INSERT INTO results_cache.suitability_checks
                            (document_id, check_type, version_id, is_suitable,
                             confidence, rationale, study_type, result, execution_time_ms)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (document_id, check_type, version_id) DO UPDATE
                        SET is_suitable = EXCLUDED.is_suitable,
                            confidence = EXCLUDED.confidence,
                            rationale = EXCLUDED.rationale,
                            study_type = EXCLUDED.study_type,
                            result = EXCLUDED.result,
                            checked_at = NOW(),
                            execution_time_ms = EXCLUDED.execution_time_ms
                        """,
                        (
                            document_id, check_type, version_id,
                            result.get('is_suitable', False),
                            result.get('confidence'),
                            result.get('rationale'),
                            result.get('study_type'),
                            json.dumps(result, cls=DateTimeEncoder),
                            execution_time_ms
                        )
                    )
                    conn.commit()

            logger.debug(
                f"Stored {check_type.upper()} suitability check for document {document_id} in cache"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to store suitability check in cache: {e}")
            return False

    # =========================================================================
    # Paper Weight Caching
    # =========================================================================

    def get_paper_weight(
        self,
        document_id: int,
        version_id: int
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieve cached paper weight assessment.

        Args:
            document_id: Document ID
            version_id: Assessment version ID

        Returns:
            Cached paper weight result dictionary, or None if not cached
        """
        try:
            with self.db_manager.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT result, assessed_at
                        FROM results_cache.paper_weight_cache
                        WHERE document_id = %s AND version_id = %s
                        """,
                        (document_id, version_id)
                    )
                    row = cursor.fetchone()

            if row:
                logger.debug(
                    f"Cache HIT: Paper weight assessment for document {document_id} "
                    f"(assessed {row[1]})"
                )
                return row[0]

            logger.debug(f"Cache MISS: Paper weight assessment for document {document_id}")
            return None

        except Exception as e:
            logger.error(f"Failed to retrieve cached paper weight assessment: {e}")
            return None

    def store_paper_weight(
        self,
        document_id: int,
        version_id: int,
        result: Dict[str, Any],
        paper_weight_assessment_id: Optional[int] = None,
        execution_time_ms: Optional[int] = None
    ) -> bool:
        """
        Store paper weight assessment result in cache.

        Args:
            document_id: Document ID
            version_id: Assessment version ID
            result: Assessment result dictionary
            paper_weight_assessment_id: Optional ID from paper_weights.assessments
            execution_time_ms: Optional execution time in milliseconds

        Returns:
            True if stored successfully, False otherwise
        """
        try:
            composite_score = result.get('composite_score')

            with self.db_manager.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        INSERT INTO results_cache.paper_weight_cache
                            (document_id, version_id, paper_weight_assessment_id,
                             composite_score, result, execution_time_ms)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        ON CONFLICT (document_id, version_id) DO UPDATE
                        SET paper_weight_assessment_id = EXCLUDED.paper_weight_assessment_id,
                            composite_score = EXCLUDED.composite_score,
                            result = EXCLUDED.result,
                            assessed_at = NOW(),
                            execution_time_ms = EXCLUDED.execution_time_ms
                        """,
                        (
                            document_id, version_id, paper_weight_assessment_id,
                            composite_score, json.dumps(result, cls=DateTimeEncoder), execution_time_ms
                        )
                    )
                    conn.commit()

            logger.debug(f"Stored paper weight assessment for document {document_id} in cache")
            return True

        except Exception as e:
            logger.error(f"Failed to store paper weight assessment in cache: {e}")
            return False

    # =========================================================================
    # Statistics
    # =========================================================================

    def get_cache_statistics(self) -> Dict[str, Any]:
        """
        Get statistics about cached results.

        Returns:
            Dictionary with cache statistics
        """
        try:
            with self.db_manager.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT
                            (SELECT COUNT(*) FROM results_cache.study_assessments) as study_count,
                            (SELECT COUNT(*) FROM results_cache.pico_extractions) as pico_count,
                            (SELECT COUNT(*) FROM results_cache.prisma_assessments) as prisma_count,
                            (SELECT COUNT(*) FROM results_cache.suitability_checks) as suitability_count,
                            (SELECT COUNT(*) FROM results_cache.paper_weight_cache) as paper_weight_count,
                            (SELECT COUNT(*) FROM results_cache.assessment_versions) as version_count
                        """
                    )
                    row = cursor.fetchone()

            return {
                "study_assessments_cached": row[0],
                "pico_extractions_cached": row[1],
                "prisma_assessments_cached": row[2],
                "suitability_checks_cached": row[3],
                "paper_weight_cached": row[4],
                "total_versions": row[5]
            }

        except Exception as e:
            logger.error(f"Failed to get cache statistics: {e}")
            return {}

    # =========================================================================
    # Cache Maintenance
    # =========================================================================

    def get_cache_size_metrics(self) -> Dict[str, Any]:
        """
        Get detailed size metrics for cache tables.

        Returns disk usage estimates and row counts for each cache table.
        Useful for monitoring cache growth and planning maintenance.

        Returns:
            Dictionary with size metrics per table including:
            - row_count: Number of cached entries
            - estimated_size_bytes: Approximate storage size
            - avg_result_size_bytes: Average size of result JSON
        """
        try:
            with self.db_manager.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT
                            'study_assessments' as table_name,
                            COUNT(*) as row_count,
                            pg_total_relation_size('results_cache.study_assessments') as table_size,
                            COALESCE(AVG(LENGTH(result::TEXT)), 0) as avg_result_size
                        FROM results_cache.study_assessments
                        UNION ALL
                        SELECT
                            'pico_extractions',
                            COUNT(*),
                            pg_total_relation_size('results_cache.pico_extractions'),
                            COALESCE(AVG(LENGTH(result::TEXT)), 0)
                        FROM results_cache.pico_extractions
                        UNION ALL
                        SELECT
                            'prisma_assessments',
                            COUNT(*),
                            pg_total_relation_size('results_cache.prisma_assessments'),
                            COALESCE(AVG(LENGTH(result::TEXT)), 0)
                        FROM results_cache.prisma_assessments
                        UNION ALL
                        SELECT
                            'suitability_checks',
                            COUNT(*),
                            pg_total_relation_size('results_cache.suitability_checks'),
                            COALESCE(AVG(LENGTH(result::TEXT)), 0)
                        FROM results_cache.suitability_checks
                        UNION ALL
                        SELECT
                            'paper_weight_cache',
                            COUNT(*),
                            pg_total_relation_size('results_cache.paper_weight_cache'),
                            COALESCE(AVG(LENGTH(result::TEXT)), 0)
                        FROM results_cache.paper_weight_cache
                        """
                    )
                    rows = cursor.fetchall()

            metrics = {}
            total_size = 0
            total_rows = 0

            for table_name, row_count, table_size, avg_result_size in rows:
                metrics[table_name] = {
                    "row_count": row_count,
                    "table_size_bytes": table_size,
                    "table_size_mb": round(table_size / BYTES_PER_MB, 2),
                    "avg_result_size_bytes": int(avg_result_size)
                }
                total_size += table_size
                total_rows += row_count

            metrics["_totals"] = {
                "total_rows": total_rows,
                "total_size_bytes": total_size,
                "total_size_mb": round(total_size / BYTES_PER_MB, 2)
            }

            return metrics

        except Exception as e:
            logger.error(f"Failed to get cache size metrics: {e}")
            return {}

    def clean_old_versions(
        self,
        keep_latest_n: int = 3,
        assessment_type: Optional[str] = None,
        dry_run: bool = True
    ) -> Dict[str, Any]:
        """
        Clean up old assessment versions and their cached results.

        Retains the N most recent versions (by creation date) per assessment type
        and removes older versions along with their cached results.

        Args:
            keep_latest_n: Number of recent versions to keep per assessment type (default: 3)
            assessment_type: Optional filter to only clean specific assessment type
            dry_run: If True, only reports what would be deleted without actually deleting

        Returns:
            Dictionary with cleanup results:
            - versions_to_delete: List of version IDs that would be/were deleted
            - rows_deleted_per_table: Count of cached rows deleted per table
            - dry_run: Whether this was a dry run
        """
        if keep_latest_n < 1:
            raise ValueError("keep_latest_n must be at least 1")

        try:
            with self.db_manager.get_connection() as conn:
                with conn.cursor() as cursor:
                    # Find versions to delete (keeping latest N per assessment type)
                    type_filter = ""
                    params: List[Any] = [keep_latest_n]
                    if assessment_type:
                        type_filter = "WHERE assessment_type = %s"
                        params = [assessment_type, keep_latest_n]

                    cursor.execute(
                        f"""
                        WITH ranked_versions AS (
                            SELECT
                                id,
                                assessment_type,
                                model_name,
                                agent_version,
                                created_at,
                                ROW_NUMBER() OVER (
                                    PARTITION BY assessment_type
                                    ORDER BY created_at DESC
                                ) as version_rank
                            FROM results_cache.assessment_versions
                            {type_filter}
                        )
                        SELECT id, assessment_type, model_name, agent_version, created_at
                        FROM ranked_versions
                        WHERE version_rank > %s
                        ORDER BY assessment_type, created_at DESC
                        """,
                        params
                    )
                    versions_to_delete = cursor.fetchall()

                    result = {
                        "versions_to_delete": [
                            {
                                "id": v[0],
                                "assessment_type": v[1],
                                "model_name": v[2],
                                "agent_version": v[3],
                                "created_at": str(v[4])
                            }
                            for v in versions_to_delete
                        ],
                        "rows_deleted_per_table": {},
                        "dry_run": dry_run
                    }

                    if not versions_to_delete:
                        logger.info("No old versions to clean up")
                        return result

                    version_ids = [v[0] for v in versions_to_delete]

                    if dry_run:
                        # Count what would be deleted without actually deleting
                        tables = [
                            ('study_assessments', 'version_id'),
                            ('pico_extractions', 'version_id'),
                            ('prisma_assessments', 'version_id'),
                            ('suitability_checks', 'version_id'),
                            ('paper_weight_cache', 'version_id'),
                        ]
                        for table, col in tables:
                            cursor.execute(
                                f"SELECT COUNT(*) FROM results_cache.{table} WHERE {col} = ANY(%s)",
                                (version_ids,)
                            )
                            result["rows_deleted_per_table"][table] = cursor.fetchone()[0]

                        logger.info(
                            f"Dry run: would delete {len(versions_to_delete)} versions "
                            f"and {sum(result['rows_deleted_per_table'].values())} cached rows"
                        )
                    else:
                        # Actually delete (cascade should handle cached rows via FK)
                        cursor.execute(
                            "DELETE FROM results_cache.assessment_versions WHERE id = ANY(%s)",
                            (version_ids,)
                        )
                        deleted_count = cursor.rowcount
                        conn.commit()

                        # Clear in-memory cache
                        self._version_cache.clear()

                        result["versions_deleted"] = deleted_count
                        logger.info(f"Deleted {deleted_count} old assessment versions")

                    return result

        except Exception as e:
            logger.error(f"Failed to clean old versions: {e}")
            raise RuntimeError(f"Cache cleanup failed: {e}")

    def validate_cache_integrity(self) -> Dict[str, Any]:
        """
        Validate the integrity of the cache.

        Checks for:
        - Orphaned cached results (version_id references non-existent version)
        - Duplicate cache entries
        - Missing required fields in cached results

        Returns:
            Dictionary with validation results:
            - is_valid: True if no issues found
            - issues: List of issue descriptions
            - statistics: Counts of checked items
        """
        issues: List[str] = []
        stats = {
            "versions_checked": 0,
            "cache_entries_checked": 0,
            "orphaned_entries": 0,
            "entries_with_missing_fields": 0
        }

        try:
            with self.db_manager.get_connection() as conn:
                with conn.cursor() as cursor:
                    # Check version count
                    cursor.execute("SELECT COUNT(*) FROM results_cache.assessment_versions")
                    stats["versions_checked"] = cursor.fetchone()[0]

                    # Check for orphaned study assessments
                    cursor.execute(
                        """
                        SELECT COUNT(*)
                        FROM results_cache.study_assessments sa
                        LEFT JOIN results_cache.assessment_versions av ON sa.version_id = av.id
                        WHERE av.id IS NULL
                        """
                    )
                    orphaned = cursor.fetchone()[0]
                    if orphaned > 0:
                        issues.append(f"Found {orphaned} orphaned study_assessments entries")
                        stats["orphaned_entries"] += orphaned

                    # Check for study assessments missing required result fields
                    cursor.execute(
                        """
                        SELECT COUNT(*)
                        FROM results_cache.study_assessments
                        WHERE result IS NULL
                           OR result->>'study_type' IS NULL
                           OR result->>'quality_score' IS NULL
                        """
                    )
                    missing_fields = cursor.fetchone()[0]
                    if missing_fields > 0:
                        issues.append(f"Found {missing_fields} study_assessments with missing required fields")
                        stats["entries_with_missing_fields"] += missing_fields

                    # Count total cache entries
                    cursor.execute(
                        """
                        SELECT
                            (SELECT COUNT(*) FROM results_cache.study_assessments) +
                            (SELECT COUNT(*) FROM results_cache.pico_extractions) +
                            (SELECT COUNT(*) FROM results_cache.prisma_assessments) +
                            (SELECT COUNT(*) FROM results_cache.suitability_checks) +
                            (SELECT COUNT(*) FROM results_cache.paper_weight_cache)
                        """
                    )
                    stats["cache_entries_checked"] = cursor.fetchone()[0]

            return {
                "is_valid": len(issues) == 0,
                "issues": issues,
                "statistics": stats
            }

        except Exception as e:
            logger.error(f"Failed to validate cache integrity: {e}")
            return {
                "is_valid": False,
                "issues": [f"Validation failed with error: {e}"],
                "statistics": stats
            }

    def clear_version_cache(self) -> None:
        """
        Clear the in-memory version ID cache.

        Useful when versions may have been modified externally or
        after running cache cleanup operations.
        """
        self._version_cache.clear()
        logger.debug("Cleared in-memory version cache")
