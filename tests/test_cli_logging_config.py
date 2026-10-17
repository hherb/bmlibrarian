"""Tests for the CLI session logger's routing of bmlib records."""

import logging
from pathlib import Path

from bmlibrarian.cli.logging_config import BMLIB_LOGGER_NAME, WorkflowLogger


def _cli_handlers(logger: logging.Logger) -> list:
    """Handlers the CLI attached to *logger*."""
    return [h for h in logger.handlers if getattr(h, '_bmlibrarian_cli_handler', False)]


def test_bmlib_warnings_reach_session_log_file(tmp_path: Path) -> None:
    """A bmlib warning is written to the session log; bmlib info is not."""
    log_file = tmp_path / "session.log"
    workflow_logger = WorkflowLogger(str(log_file))
    bmlib_logger = logging.getLogger(f"{BMLIB_LOGGER_NAME}.llm.json_repair")
    try:
        bmlib_logger.warning("JSON repair failed after 3 attempts")
        bmlib_logger.info("routine bmlib detail")
        for handler in workflow_logger.logger.handlers:
            handler.flush()

        content = log_file.read_text(encoding="utf-8")
        assert "JSON repair failed after 3 attempts" in content
        assert "[bmlib.llm.json_repair]" in content
        assert "routine bmlib detail" not in content
    finally:
        root_bmlib = logging.getLogger(BMLIB_LOGGER_NAME)
        for handler in _cli_handlers(root_bmlib):
            root_bmlib.removeHandler(handler)
        for handler in list(workflow_logger.logger.handlers):
            workflow_logger.logger.removeHandler(handler)
            handler.close()


def test_recreating_session_logger_does_not_stack_bmlib_handlers(tmp_path: Path) -> None:
    """Each WorkflowLogger replaces the previous session's bmlib handlers."""
    first = WorkflowLogger(str(tmp_path / "a.log"))
    second = WorkflowLogger(str(tmp_path / "b.log"))
    root_bmlib = logging.getLogger(BMLIB_LOGGER_NAME)
    try:
        assert len(_cli_handlers(root_bmlib)) == 2  # file + console
    finally:
        for handler in _cli_handlers(root_bmlib):
            root_bmlib.removeHandler(handler)
        for wl in (first, second):
            for handler in list(wl.logger.handlers):
                wl.logger.removeHandler(handler)
                handler.close()
