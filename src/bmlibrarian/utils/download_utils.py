"""Atomic download helpers shared by BMLibrarian's PDF download paths.

Downloading directly to the final output path has two failure modes:

1. A mid-stream failure (timeout, dropped connection) leaves a truncated
   file at the final path, which later code mistakes for a completed
   download and never retries.
2. Cleaning that up with an unconditional ``unlink(final_path)`` in the
   error handler introduces the opposite bug: when the failure occurs
   *before* any bytes are written (e.g. a connect timeout), the file at
   the final path is a previous successful download — and the cleanup
   deletes it.

The safe pattern is to stream into a temporary sibling file (the final
path plus :data:`PARTIAL_DOWNLOAD_SUFFIX`) and atomically promote it into
place only after the content has been fully written and validated. Error
handlers then discard the partial file only, and can never touch a good
file at the final path.

These are small pure helpers (golden rule 11) with no dependency on any
network library, so every download call site (HTTP, FTP, browser) can
share them and they can be unit tested in isolation.
"""

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

# Suffix appended to the final filename while a download is in flight.
# The partial file lives in the same directory as the final path so that
# the promoting rename is atomic (same filesystem).
PARTIAL_DOWNLOAD_SUFFIX = ".part"


def partial_download_path(final_path: Path) -> Path:
    """Return the temporary sibling path used while downloading ``final_path``.

    Args:
        final_path: The path the completed download will occupy.

    Returns:
        ``final_path`` with :data:`PARTIAL_DOWNLOAD_SUFFIX` appended to its
        name (same directory, so promotion via rename is atomic).
    """
    return final_path.with_name(final_path.name + PARTIAL_DOWNLOAD_SUFFIX)


def promote_partial_download(partial_path: Path, final_path: Path) -> None:
    """Atomically move a completed, validated partial download into place.

    Overwrites any existing file at ``final_path`` (a fresh successful
    download supersedes a previous one).

    Args:
        partial_path: The fully-written temporary file.
        final_path: The destination path for the completed download.

    Raises:
        OSError: If the rename fails (propagated so the caller's retry
            logic treats the attempt as failed).
    """
    os.replace(partial_path, final_path)


def discard_partial_download(partial_path: Path) -> None:
    """Remove a partial download file if present.

    Safe to call from error handlers: it never touches the final path,
    only the temporary partial file, and swallows (but logs) filesystem
    errors so cleanup can never mask the original download failure.

    Args:
        partial_path: The temporary partial file to remove.
    """
    try:
        partial_path.unlink(missing_ok=True)
    except OSError as e:
        logger.warning("Failed to remove partial download %s: %s", partial_path, e)
