"""
Evaluator Manager for creating and managing evaluators in public.evaluators table.

Provides helpers for agents to get or create evaluators based on model/parameters,
enabling proper audit tracking.
"""

import json
import logging
from typing import Optional, Dict, Any
import psycopg
from psycopg.rows import dict_row

logger = logging.getLogger(__name__)


class EvaluatorManager:
    """
    Manages evaluator records in public.evaluators table.

    Evaluators represent unique combinations of:
    - user_id (for human evaluators)
    - model_id (for AI evaluators)
    - parameters (JSONB with temperature, top_p, etc.)
    - prompt (optional system prompt)

    This enables tracking WHO (user/model/params) performed each action.
    """

    def __init__(self, conn: psycopg.Connection):
        """
        Initialize evaluator manager.

        Args:
            conn: Active psycopg connection to PostgreSQL database
        """
        self.conn = conn

    def get_or_create_evaluator(
        self,
        name: str,
        user_id: Optional[int] = None,
        model_id: Optional[str] = None,
        parameters: Optional[Dict[str, Any]] = None,
        prompt: Optional[str] = None
    ) -> int:
        """
        Get existing or create new evaluator.

        Matches on (user_id, model_id, parameters) to avoid duplicates.

        Args:
            name: Human-readable name for the evaluator
            user_id: User ID (for human evaluators, typically 1)
            model_id: Model identifier (e.g., 'medgemma-27b-text-it-Q8_0:latest')
            parameters: Model parameters (temperature, top_p, etc.)
            prompt: Optional system prompt

        Returns:
            evaluator_id (INTEGER)

        Example:
            >>> evaluator_id = manager.get_or_create_evaluator(
            ...     name="MedGemma 27B Scoring",
            ...     model_id="medgemma-27b-text-it-Q8_0:latest",
            ...     parameters={"temperature": 0.1, "top_p": 0.9}
            ... )
        """
        # Try to find existing evaluator with same model/params
        with self.conn.cursor() as cur:
            if user_id is not None and model_id is None:
                # Human evaluator - match on user_id only
                cur.execute("""
                    SELECT id FROM public.evaluators
                    WHERE user_id = %s AND model_id IS NULL
                    LIMIT 1
                """, (user_id,))
            elif model_id is not None:
                # AI evaluator - match on model_id and parameters
                if parameters:
                    params_json = json.dumps(parameters)
                    cur.execute("""
                        SELECT id FROM public.evaluators
                        WHERE model_id = %s
                          AND parameters::text = %s::text
                        LIMIT 1
                    """, (model_id, params_json))
                else:
                    cur.execute("""
                        SELECT id FROM public.evaluators
                        WHERE model_id = %s
                          AND parameters IS NULL
                        LIMIT 1
                    """, (model_id,))
            else:
                # Neither user nor model specified - error
                raise ValueError("Must specify either user_id or model_id")

            result = cur.fetchone()
            if result:
                evaluator_id = result[0]
                logger.debug(f"Found existing evaluator {evaluator_id}: {name}")
                return evaluator_id

            # Not found - create new evaluator
            params_jsonb = json.dumps(parameters) if parameters else None
            cur.execute("""
                INSERT INTO public.evaluators (name, user_id, model_id, parameters, prompt)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id
            """, (name, user_id, model_id, params_jsonb, prompt))

            evaluator_id = cur.fetchone()[0]
            self.conn.commit()

            logger.info(f"Created new evaluator {evaluator_id}: {name}")
            return evaluator_id

    def get_evaluator_for_agent(
        self,
        agent_type: str,
        model_name: str,
        temperature: float,
        top_p: float,
        user_id: Optional[int] = None
    ) -> int:
        """
        Get or create evaluator for a specific agent configuration.

        Helper method that creates descriptive name and packages parameters.

        Args:
            agent_type: Type of agent (e.g., 'query', 'scoring', 'citation', 'reporting')
            model_name: Model identifier
            temperature: Model temperature
            top_p: Model top_p
            user_id: Optional user ID for human-in-the-loop

        Returns:
            evaluator_id (INTEGER)

        Example:
            >>> evaluator_id = manager.get_evaluator_for_agent(
            ...     agent_type='scoring',
            ...     model_name='medgemma-27b-text-it-Q8_0:latest',
            ...     temperature=0.1,
            ...     top_p=0.9
            ... )
        """
        # Create descriptive name
        name = f"{agent_type.capitalize()} - {model_name} (T={temperature}, p={top_p})"

        # Package parameters
        parameters = {
            "type": f"{agent_type}_agent",
            "temperature": temperature,
            "top_p": top_p
        }

        return self.get_or_create_evaluator(
            name=name,
            user_id=user_id,
            model_id=model_name,
            parameters=parameters
        )

    def get_human_evaluator(
        self,
        user_id: int = 1,
        name: Optional[str] = None
    ) -> int:
        """
        Get or create evaluator for human reviewer.

        Args:
            user_id: User ID (default: 1)
            name: Optional custom name (default: "Human Evaluator (user_{user_id})")

        Returns:
            evaluator_id (INTEGER)
        """
        if name is None:
            name = f"Human Evaluator (user_{user_id})"

        return self.get_or_create_evaluator(
            name=name,
            user_id=user_id,
            model_id=None,
            parameters=None
        )

    def get_evaluator_info(
        self,
        evaluator_id: int
    ) -> Optional[Dict[str, Any]]:
        """
        Get full information about an evaluator.

        Args:
            evaluator_id: ID of the evaluator

        Returns:
            Dictionary with evaluator data, or None if not found
        """
        with self.conn.cursor(row_factory=dict_row) as cur:
            cur.execute("""
                SELECT * FROM public.evaluators
                WHERE id = %s
            """, (evaluator_id,))
            return cur.fetchone()

    def list_evaluators(
        self,
        model_id: Optional[str] = None,
        user_id: Optional[int] = None
    ) -> list[Dict[str, Any]]:
        """
        List evaluators, optionally filtered by model or user.

        Args:
            model_id: Filter by model ID (optional)
            user_id: Filter by user ID (optional)

        Returns:
            List of dictionaries with evaluator data
        """
        with self.conn.cursor(row_factory=dict_row) as cur:
            if model_id is not None:
                cur.execute("""
                    SELECT * FROM public.evaluators
                    WHERE model_id = %s
                    ORDER BY created_at DESC
                """, (model_id,))
            elif user_id is not None:
                cur.execute("""
                    SELECT * FROM public.evaluators
                    WHERE user_id = %s
                    ORDER BY created_at DESC
                """, (user_id,))
            else:
                cur.execute("""
                    SELECT * FROM public.evaluators
                    ORDER BY created_at DESC
                """)

            return cur.fetchall()

    def update_evaluator_prompt(
        self,
        evaluator_id: int,
        prompt: str
    ) -> None:
        """
        Update the prompt for an evaluator.

        Args:
            evaluator_id: ID of the evaluator
            prompt: New system prompt
        """
        with self.conn.cursor() as cur:
            cur.execute("""
                UPDATE public.evaluators
                SET prompt = %s,
                    updated_at = NOW()
                WHERE id = %s
            """, (prompt, evaluator_id))
            self.conn.commit()

            logger.info(f"Updated prompt for evaluator {evaluator_id}")
