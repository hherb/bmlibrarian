"""
Backwards compatibility wrapper for workflow.

This module has moved to bmlibrarian.gui.flet.workflow.
This file re-exports all symbols for backwards compatibility.
"""

from .flet.workflow import *  # noqa: F401, F403
from .flet.workflow import (
    WorkflowExecutor,
    initialize_agents_in_main_thread,
    cleanup_agents,
)
