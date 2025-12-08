"""
Evaluator Registry for consistent evaluator_id management.

This module provides a centralized way to manage evaluator records in the
public.evaluators table, ensuring consistent attribution across all agents.

Key features:
- Get-or-create pattern to avoid duplicate evaluators
- Caching to minimize database lookups
- Support for both AI model evaluators and human evaluators
- Consistent parameter normalization

Author: BMLibrarian
Date: 2025-12-07
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional, Dict, Any, Tuple, TYPE_CHECKING
from datetime import datetime

from .schemas import PARAMETER_DECIMAL_PRECISION

if TYPE_CHECKING:
    from bmlibrarian.database import DatabaseManager

logger = logging.getLogger(__name__)


@dataclass
class EvaluatorInfo:
    """Information about an evaluator."""
    id: int
    name: str
    user_id: Optional[int]
    model_id: Optional[str]
    parameters: Optional[Dict[str, Any]]
    prompt: Optional[str]
    created_at: datetime
    updated_at: datetime

    @property
    def is_human(self) -> bool:
        """Check if this is a human evaluator."""
        return self.user_id is not None and self.model_id is None

    @property
    def is_model(self) -> bool:
        """Check if this is an AI model evaluator."""
        return self.model_id is not None

    def get_temperature(self) -> float:
        """Get temperature parameter, defaulting to 0.0."""
        if self.parameters and "temperature" in self.parameters:
            return float(self.parameters["temperature"])
        return 0.0

    def get_top_p(self) -> float:
        """Get top_p parameter, defaulting to 1.0."""
        if self.parameters and "top_p" in self.parameters:
            return float(self.parameters["top_p"])
        return 1.0


class EvaluatorRegistry:
    """
    Manages evaluator registration and lookup.

    Ensures consistent evaluator_id usage across all agents by providing
    a centralized get-or-create pattern with caching.

    Usage:
        registry = EvaluatorRegistry(db_manager)

        # For AI model evaluators
        evaluator_id = registry.get_or_create_model_evaluator(
            model_name="gpt-oss:20b",
            temperature=0.1,
            top_p=0.9
        )

        # For human evaluators
        evaluator_id = registry.get_or_create_human_evaluator(
            user_id=123,
            name="Dr. Smith"
        )

        # Get evaluator info
        info = registry.get_evaluator_info(evaluator_id)
    """

    def __init__(self, db_manager: "DatabaseManager"):
        """
        Initialize the evaluator registry.

        Args:
            db_manager: DatabaseManager instance for database access
        """
        self.db = db_manager
        self._cache: Dict[Tuple[Any, ...], int] = {}
        self._info_cache: Dict[int, EvaluatorInfo] = {}

    def _normalize_parameters(
        self,
        temperature: float,
        top_p: float,
        extra_params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Normalize parameters to a consistent format.

        Args:
            temperature: Model temperature
            top_p: Model top_p (nucleus sampling)
            extra_params: Additional parameters

        Returns:
            Normalized parameters dict
        """
        params = {
            "temperature": round(temperature, PARAMETER_DECIMAL_PRECISION),
            "top_p": round(top_p, PARAMETER_DECIMAL_PRECISION),
        }
        if extra_params:
            # Filter out temperature and top_p from extra_params to avoid duplicates
            for key, value in extra_params.items():
                if key not in ("temperature", "top_p"):
                    params[key] = value
        return params

    def _generate_name(
        self,
        model_name: Optional[str] = None,
        user_name: Optional[str] = None,
        temperature: Optional[float] = None,
        top_p: Optional[float] = None
    ) -> str:
        """
        Generate a descriptive name for an evaluator.

        Args:
            model_name: AI model name
            user_name: Human evaluator name
            temperature: Model temperature
            top_p: Model top_p

        Returns:
            Descriptive evaluator name
        """
        if model_name:
            # Model evaluator
            parts = [model_name]
            if temperature is not None and temperature != 0.0:
                parts.append(f"t={temperature}")
            if top_p is not None and top_p != 1.0:
                parts.append(f"p={top_p}")
            return " ".join(parts)
        elif user_name:
            return f"Human: {user_name}"
        else:
            return "Unknown Evaluator"

    def get_or_create_model_evaluator(
        self,
        model_name: str,
        temperature: float = 0.0,
        top_p: float = 1.0,
        prompt: Optional[str] = None,
        extra_params: Optional[Dict[str, Any]] = None
    ) -> int:
        """
        Get existing evaluator_id or create new one for an AI model.

        Uses caching to avoid repeated database lookups.

        Args:
            model_name: Ollama model name (e.g., "gpt-oss:20b")
            temperature: Model temperature parameter
            top_p: Model top_p (nucleus sampling) parameter
            prompt: Optional system prompt
            extra_params: Additional model parameters

        Returns:
            Evaluator ID from public.evaluators
        """
        # Normalize for consistent cache keys
        temperature = round(temperature, PARAMETER_DECIMAL_PRECISION)
        top_p = round(top_p, PARAMETER_DECIMAL_PRECISION)
        cache_key = ("model", model_name, temperature, top_p, prompt)

        if cache_key in self._cache:
            return self._cache[cache_key]

        # Check database
        evaluator_id = self._find_model_evaluator(
            model_name, temperature, top_p, prompt
        )

        if evaluator_id is None:
            # Create new evaluator
            evaluator_id = self._create_evaluator(
                name=self._generate_name(model_name, temperature=temperature, top_p=top_p),
                model_id=model_name,
                parameters=self._normalize_parameters(temperature, top_p, extra_params),
                prompt=prompt
            )
            logger.info(
                f"Created new model evaluator: id={evaluator_id}, model={model_name}, "
                f"temp={temperature}, top_p={top_p}"
            )

        self._cache[cache_key] = evaluator_id
        return evaluator_id

    def get_or_create_human_evaluator(
        self,
        user_id: int,
        name: Optional[str] = None
    ) -> int:
        """
        Get existing evaluator_id or create new one for a human evaluator.

        Args:
            user_id: User ID from public.users
            name: Optional display name (defaults to username lookup)

        Returns:
            Evaluator ID from public.evaluators
        """
        cache_key = ("human", user_id)

        if cache_key in self._cache:
            return self._cache[cache_key]

        # Check database
        evaluator_id = self._find_human_evaluator(user_id)

        if evaluator_id is None:
            # Look up username if name not provided
            if name is None:
                name = self._lookup_username(user_id) or f"User {user_id}"

            evaluator_id = self._create_evaluator(
                name=self._generate_name(user_name=name),
                user_id=user_id
            )
            logger.info(f"Created new human evaluator: id={evaluator_id}, user_id={user_id}")

        self._cache[cache_key] = evaluator_id
        return evaluator_id

    def get_evaluator_info(self, evaluator_id: int) -> Optional[EvaluatorInfo]:
        """
        Get full evaluator details.

        Args:
            evaluator_id: Evaluator ID to look up

        Returns:
            EvaluatorInfo or None if not found

        Raises:
            RuntimeError: If database operation fails
        """
        if evaluator_id in self._info_cache:
            return self._info_cache[evaluator_id]

        query = """
            SELECT id, name, user_id, model_id, parameters, prompt,
                   created_at, updated_at
            FROM public.evaluators
            WHERE id = %s
        """

        try:
            with self.db.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, (evaluator_id,))
                    row = cur.fetchone()
        except Exception as e:
            logger.error(f"Failed to get evaluator info for id={evaluator_id}: {e}")
            raise RuntimeError(f"Database error getting evaluator info: {e}") from e

        if row is None:
            return None

        info = EvaluatorInfo(
            id=row[0],
            name=row[1],
            user_id=row[2],
            model_id=row[3],
            parameters=row[4],
            prompt=row[5],
            created_at=row[6],
            updated_at=row[7]
        )

        self._info_cache[evaluator_id] = info
        return info

    def _find_model_evaluator(
        self,
        model_name: str,
        temperature: float,
        top_p: float,
        prompt: Optional[str]
    ) -> Optional[int]:
        """
        Find existing model evaluator with matching parameters.

        Args:
            model_name: Model name
            temperature: Temperature parameter
            top_p: Top_p parameter
            prompt: Optional system prompt

        Returns:
            Evaluator ID if found, None otherwise

        Raises:
            RuntimeError: If database operation fails
        """
        # Build query to match parameters within JSONB
        if prompt is None:
            query = """
                SELECT id FROM public.evaluators
                WHERE model_id = %s
                  AND (parameters->>'temperature')::NUMERIC = %s
                  AND (parameters->>'top_p')::NUMERIC = %s
                  AND prompt IS NULL
                LIMIT 1
            """
            params = (model_name, temperature, top_p)
        else:
            query = """
                SELECT id FROM public.evaluators
                WHERE model_id = %s
                  AND (parameters->>'temperature')::NUMERIC = %s
                  AND (parameters->>'top_p')::NUMERIC = %s
                  AND prompt = %s
                LIMIT 1
            """
            params = (model_name, temperature, top_p, prompt)

        try:
            with self.db.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, params)
                    row = cur.fetchone()
        except Exception as e:
            logger.error(f"Failed to find model evaluator for {model_name}: {e}")
            raise RuntimeError(f"Database error finding model evaluator: {e}") from e

        return row[0] if row else None

    def _find_human_evaluator(self, user_id: int) -> Optional[int]:
        """
        Find existing human evaluator for a user.

        Args:
            user_id: User ID

        Returns:
            Evaluator ID if found, None otherwise

        Raises:
            RuntimeError: If database operation fails
        """
        query = """
            SELECT id FROM public.evaluators
            WHERE user_id = %s AND model_id IS NULL
            LIMIT 1
        """

        try:
            with self.db.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, (user_id,))
                    row = cur.fetchone()
        except Exception as e:
            logger.error(f"Failed to find human evaluator for user_id={user_id}: {e}")
            raise RuntimeError(f"Database error finding human evaluator: {e}") from e

        return row[0] if row else None

    def _create_evaluator(
        self,
        name: str,
        user_id: Optional[int] = None,
        model_id: Optional[str] = None,
        parameters: Optional[Dict[str, Any]] = None,
        prompt: Optional[str] = None
    ) -> int:
        """
        Create a new evaluator record.

        Args:
            name: Display name
            user_id: User ID for human evaluators
            model_id: Model name for AI evaluators
            parameters: Model parameters (JSONB)
            prompt: Optional system prompt

        Returns:
            New evaluator ID

        Raises:
            RuntimeError: If database operation fails
        """
        import json

        query = """
            INSERT INTO public.evaluators (name, user_id, model_id, parameters, prompt)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
        """

        params_json = json.dumps(parameters) if parameters else None

        try:
            with self.db.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, (name, user_id, model_id, params_json, prompt))
                    evaluator_id = cur.fetchone()[0]
                conn.commit()
        except Exception as e:
            logger.error(f"Failed to create evaluator '{name}': {e}")
            raise RuntimeError(f"Database error creating evaluator: {e}") from e

        return evaluator_id

    def _lookup_username(self, user_id: int) -> Optional[str]:
        """
        Look up username from public.users table.

        Args:
            user_id: User ID

        Returns:
            Username or None if not found

        Raises:
            RuntimeError: If database operation fails
        """
        query = "SELECT username FROM public.users WHERE id = %s"

        try:
            with self.db.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, (user_id,))
                    row = cur.fetchone()
        except Exception as e:
            logger.error(f"Failed to lookup username for user_id={user_id}: {e}")
            raise RuntimeError(f"Database error looking up username: {e}") from e

        return row[0] if row else None

    def clear_cache(self) -> None:
        """Clear all caches. Useful for testing or after bulk operations."""
        self._cache.clear()
        self._info_cache.clear()

    def preload_cache(self) -> int:
        """
        Preload cache with all existing evaluators.

        Useful at startup to minimize database round-trips.

        Returns:
            Number of evaluators loaded

        Raises:
            RuntimeError: If database operation fails
        """
        query = """
            SELECT id, name, user_id, model_id, parameters, prompt,
                   created_at, updated_at
            FROM public.evaluators
        """

        count = 0
        try:
            with self.db.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(query)
                    for row in cur:
                        info = EvaluatorInfo(
                            id=row[0],
                            name=row[1],
                            user_id=row[2],
                            model_id=row[3],
                            parameters=row[4],
                            prompt=row[5],
                            created_at=row[6],
                            updated_at=row[7]
                        )
                        self._info_cache[info.id] = info

                        # Also populate the lookup cache
                        if info.is_model and info.parameters:
                            temp = info.get_temperature()
                            top_p = info.get_top_p()
                            cache_key = ("model", info.model_id, temp, top_p, info.prompt)
                            self._cache[cache_key] = info.id
                        elif info.is_human:
                            cache_key = ("human", info.user_id)
                            self._cache[cache_key] = info.id

                        count += 1
        except Exception as e:
            logger.error(f"Failed to preload evaluator cache: {e}")
            raise RuntimeError(f"Database error preloading evaluator cache: {e}") from e

        logger.debug(f"Preloaded {count} evaluators into cache")
        return count
