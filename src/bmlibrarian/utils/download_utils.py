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


def unused_download_path(path: Path) -> Path:
    """Reserve and return ``path``, or the first free ``<stem>_<n><suffix>``.

    A download must not replace a file that may be another document's PDF
    (#319), so it goes to a fresh name instead. The name is reserved by
    atomically creating an empty file there (``O_CREAT | O_EXCL``), so two
    concurrent downloads can never pick the same name (#322). The caller
    writes over the placeholder, or removes it with
    :func:`discard_empty_reservation` if nothing was written.

    Args:
        path: The preferred destination (its directory must exist).

    Returns:
        ``path`` if nothing was there, else the first ``<stem>_<n><suffix>``
        (n = 1, 2, ...) that did not exist; either way now an empty file.

    Raises:
        OSError: If the placeholder cannot be created (e.g. missing directory).
    """
    candidate = path
    n = 1
    while True:
        try:
            os.close(os.open(candidate, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
            return candidate
        except FileExistsError:
            candidate = path.with_name(f"{path.stem}_{n}{path.suffix}")
            n += 1


def discard_empty_reservation(path: Path) -> None:
    """Remove the placeholder from :func:`unused_download_path` if still empty.

    A non-empty file is a completed download and is kept. Filesystem errors
    are logged, never raised, so cleanup cannot mask a download failure.

    Args:
        path: The path :func:`unused_download_path` returned.
    """
    try:
        if path.stat().st_size == 0:
            path.unlink()
    except FileNotFoundError:
        pass
    except OSError as e:
        logger.warning("Failed to remove unused download placeholder %s: %s", path, e)


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
