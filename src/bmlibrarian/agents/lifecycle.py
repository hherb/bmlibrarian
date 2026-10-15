"""
Agent lifecycle helpers for GUI applications.

Creates the full set of BMLibrarian agents (with audit tracking when the
``audit`` schema exists) and releases their resources on shutdown. Framework
neutral; used by the Qt main window. Moved here from the retired Flet GUI's
``gui/flet/workflow.py`` (October 2026).
"""

import logging
from typing import Any, Dict, Optional

from .factory import AgentFactory

logger = logging.getLogger(__name__)


def cleanup_agents(agents: Optional[Dict[str, Any]]) -> None:
    """Release agent resources, returning the audit connection to the pool.

    Args:
        agents: Dictionary from ``initialize_agents_in_main_thread()``
    """
    if not agents:
        return

    audit_conn = agents.get('_audit_conn')
    db_manager = agents.get('_db_manager')
    if audit_conn and db_manager:
        try:
            db_manager._pool.putconn(audit_conn)
            logger.info("Audit connection returned to DatabaseManager pool")
        except Exception as e:
            logger.error(f"Error returning audit connection to pool: {e}", exc_info=True)


def _acquire_audit_connection(db_manager: Any) -> Optional[Any]:
    """Borrow a pooled connection for audit tracking if the audit schema exists.

    Args:
        db_manager: The DatabaseManager

    Returns:
        A pooled connection (caller must return it via ``cleanup_agents``), or
        None when the audit schema is missing or the check fails
    """
    with db_manager.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT EXISTS (
                    SELECT FROM information_schema.schemata
                    WHERE schema_name = 'audit'
                )
                """
            )
            audit_exists = cur.fetchone()[0]

    if not audit_exists:
        logger.warning(
            "Audit schema not found - audit tracking disabled. Run migrations "
            "to enable it: uv run python -m bmlibrarian.migrations run"
        )
        return None

    logger.info("Audit schema found - enabling audit tracking")
    # Long-lived connection, returned to the pool on GUI shutdown
    return db_manager._pool.getconn()


def initialize_agents_in_main_thread() -> Optional[Dict[str, Any]]:
    """Create all agents (call from the GUI main thread to avoid signal issues).

    Returns:
        Dictionary of agents keyed by name, plus ``_db_manager`` and
        ``_audit_conn`` entries for ``cleanup_agents``; None if creation failed
    """
    try:
        logger.info("Initializing BMLibrarian agents with config.json settings...")

        from ..database import get_db_manager

        audit_conn = None
        db_manager = None
        try:
            db_manager = get_db_manager()
            audit_conn = _acquire_audit_connection(db_manager)
        except Exception as e:
            logger.warning(f"Could not initialize audit tracking, continuing without it: {e}")
            audit_conn = None

        agents = AgentFactory.create_all_agents(auto_register=True, audit_conn=audit_conn)

        # Keep the pool handle for cleanup on shutdown
        if db_manager:
            agents['_db_manager'] = db_manager
            agents['_audit_conn'] = audit_conn

        for agent_name, agent in agents.items():
            if hasattr(agent, 'model') and agent_name != 'orchestrator':
                logger.info(f"{agent_name} using model: {agent.model}")

        logger.info(
            "Agents initialized"
            + (" with audit tracking" if audit_conn else " (audit tracking not enabled)")
        )
        return agents

    except Exception as e:
        logger.error(f"Failed to initialize agents in main thread: {e}", exc_info=True)
        return None
