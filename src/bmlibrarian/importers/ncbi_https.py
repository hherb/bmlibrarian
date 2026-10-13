"""
Verified, resumable HTTPS downloads from the NCBI file server.

NCBI serves the same tree over FTP and HTTPS (``ftp.ncbi.nlm.nih.gov``). The
FTP service was observed (October 2026) to re-send earlier parts of a file
mid-transfer: the received stream rewinds, so files come out too large or,
after an interrupted transfer, silently wrong. This module therefore downloads
over HTTPS and never trusts a transfer:

1. data is written to ``<name>.part``; an interrupted transfer resumes with an
   HTTP ``Range`` request (a server that ignores it restarts the file);
2. the finished ``.part`` must match NCBI's published MD5 (``<name>.md5``);
3. only then is it renamed to its final name (atomic ``os.replace``).

A file at its final name is therefore always complete and verified, so readers
(the importer) may run while a download is in progress.
"""

import hashlib
import logging
import os
import re
import time
from pathlib import Path
from typing import Callable, List, Optional, Tuple

import requests

logger = logging.getLogger(__name__)

NCBI_HTTPS_BASE_URL = "https://ftp.ncbi.nlm.nih.gov"
PART_SUFFIX = ".part"
MD5_SUFFIX = ".md5"
DEFAULT_CHUNK_SIZE = 1024 * 1024
DEFAULT_MAX_RETRIES = 5
RETRY_BASE_DELAY_SECONDS = 10
CONNECT_TIMEOUT_SECONDS = 30
READ_TIMEOUT_SECONDS = 120
HTTP_PARTIAL_CONTENT = 206
HTTP_RANGE_NOT_SATISFIABLE = 416
USER_AGENT = "bmlibrarian-pubmed-mirror (+https://github.com/hherb/bmlibrarian)"

# Only plain data file names are accepted from a listing (no paths, no ..).
LISTING_FILE_PATTERN = re.compile(r'href="(pubmed\d+n\d+\.xml\.gz)"')
MD5_HEX_PATTERN = re.compile(r"^[0-9a-f]{32}$")
MD5_FILE_PATTERN = re.compile(r"=\s*([0-9a-fA-F]{32})\s*$")
CONTENT_RANGE_PATTERN = re.compile(r"^bytes (\d+)-(\d+)/(\d+)$")

ProgressCallback = Callable[[str], None]


def parse_directory_listing(html: str) -> List[str]:
    """
    Extract the PubMed data file names from an NCBI HTTPS directory listing.

    Args:
        html: The listing page.

    Returns:
        Sorted, de-duplicated ``pubmedNNnNNNN.xml.gz`` names (checksum files and
        anything that is not a bare data file name are ignored).
    """
    return sorted(set(LISTING_FILE_PATTERN.findall(html)))


def parse_md5_file(text: str) -> str:
    """
    Parse an NCBI checksum file (``MD5(name)= <hex>``).

    Args:
        text: Contents of the ``.md5`` file.

    Returns:
        The lower-case hex digest.

    Raises:
        ValueError: If the text does not contain a digest.
    """
    match = MD5_FILE_PATTERN.search(text.strip())
    if not match:
        raise ValueError(f"not an MD5 checksum file: {text[:80]!r}")
    return match.group(1).lower()


def parse_content_range(header: str) -> Tuple[int, int]:
    """
    Parse a ``Content-Range: bytes start-end/total`` header.

    Args:
        header: The header value.

    Returns:
        (start offset, total size).

    Raises:
        ValueError: If the header is not a satisfied byte range.
    """
    match = CONTENT_RANGE_PATTERN.match(header.strip())
    if not match:
        raise ValueError(f"unexpected Content-Range: {header!r}")
    return int(match.group(1)), int(match.group(3))


def part_path(dest: Path) -> Path:
    """Path of the in-progress download for ``dest``."""
    return dest.with_name(dest.name + PART_SUFFIX)


def file_md5(path: Path, chunk_size: int = DEFAULT_CHUNK_SIZE) -> str:
    """MD5 hex digest of a file."""
    md5 = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            md5.update(chunk)
    return md5.hexdigest()


def _default_session() -> requests.Session:
    """A requests session identifying the mirror client."""
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    return session


class HttpsDownloader:
    """
    Downloads NCBI files over HTTPS with resume and MD5 verification.

    The session and sleep function are injectable so the retry logic can be
    tested without a network.
    """

    def __init__(
        self,
        session: Optional[requests.Session] = None,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        max_retries: int = DEFAULT_MAX_RETRIES,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        """
        Args:
            session: HTTP session (default: a new requests session).
            chunk_size: Bytes per streamed chunk.
            max_retries: Attempts per file before giving up.
            sleep: Delay function used between attempts.
        """
        self.session = session if session is not None else _default_session()
        self.chunk_size = chunk_size
        self.max_retries = max_retries
        self.sleep = sleep
        self.timeout = (CONNECT_TIMEOUT_SECONDS, READ_TIMEOUT_SECONDS)

    def list_files(self, directory_url: str) -> List[str]:
        """
        List the data files in a remote directory.

        Args:
            directory_url: Directory URL ending in ``/``.

        Returns:
            Sorted data file names.
        """
        return parse_directory_listing(self._get_text(directory_url))

    def fetch_md5(self, file_url: str) -> str:
        """
        Fetch NCBI's published MD5 for a file.

        Args:
            file_url: URL of the data file (the ``.md5`` suffix is added).

        Returns:
            The expected hex digest.
        """
        return parse_md5_file(self._get_text(file_url + MD5_SUFFIX))

    def _get_text(self, url: str) -> str:
        """
        GET a small text resource, retrying transient connection/HTTP errors.

        Raises:
            requests.RequestException: The last error once all attempts fail.
        """
        for attempt in range(1, self.max_retries + 1):
            try:
                with self.session.get(url, timeout=self.timeout) as resp:
                    resp.raise_for_status()
                    return resp.text
            except requests.RequestException as e:
                logger.warning(f"GET {url} failed (attempt {attempt}/{self.max_retries}): {e}")
                if attempt == self.max_retries:
                    raise
                self.sleep(RETRY_BASE_DELAY_SECONDS * attempt)
        raise AssertionError("unreachable")

    def download(
        self,
        url: str,
        dest: Path,
        expected_md5: str,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> bool:
        """
        Download ``url`` to ``dest``; ``dest`` appears only once its MD5 matches.

        An existing ``dest`` with the right MD5 is kept; one with the wrong MD5
        (e.g. a failed legacy FTP download) is replaced. An interrupted
        transfer is resumed from ``<dest>.part``, also across runs.

        Args:
            url: Source URL.
            dest: Final destination path.
            expected_md5: Expected lower-case hex MD5.
            progress_callback: Optional callback for progress messages.

        Returns:
            True if ``dest`` now holds the verified file, False after all retries.

        Raises:
            ValueError: If ``expected_md5`` is not a hex MD5 digest.
        """
        if not MD5_HEX_PATTERN.match(expected_md5):
            raise ValueError(f"invalid expected MD5: {expected_md5!r}")
        name = dest.name
        if dest.exists():
            if file_md5(dest, self.chunk_size) == expected_md5:
                logger.info(f"{name}: already downloaded and verified")
                return True
            logger.warning(f"{name}: existing file fails MD5 check, downloading again")
            dest.unlink()

        part = part_path(dest)
        for attempt in range(1, self.max_retries + 1):
            try:
                self._transfer(url, part, name, progress_callback)
                if file_md5(part, self.chunk_size) == expected_md5:
                    os.replace(part, dest)
                    logger.info(f"{name}: download complete, MD5 verified")
                    return True
                logger.error(f"{name}: MD5 mismatch after transfer (attempt {attempt}/{self.max_retries})")
                part.unlink()
            except (requests.RequestException, OSError, ValueError) as e:
                logger.error(f"{name}: transfer error (attempt {attempt}/{self.max_retries}): {e}")
                if progress_callback:
                    progress_callback(f"[DOWNLOAD ERROR] {name}: {e} (attempt {attempt}/{self.max_retries})")
            if attempt < self.max_retries:
                self.sleep(RETRY_BASE_DELAY_SECONDS * attempt)
        logger.error(f"{name}: download failed after {self.max_retries} attempts")
        return False

    def _transfer(self, url: str, part: Path, name: str,
                  progress_callback: Optional[ProgressCallback]) -> None:
        """
        Fetch the remainder of ``url`` into ``part`` (resuming if it exists).

        Raises:
            requests.RequestException: On HTTP or connection errors.
            ValueError: If the server answers a Range request with a wrong offset.
        """
        offset = part.stat().st_size if part.exists() else 0
        headers = {"Range": f"bytes={offset}-"} if offset else {}
        with self.session.get(url, headers=headers, stream=True, timeout=self.timeout) as resp:
            if offset and resp.status_code == HTTP_RANGE_NOT_SATISFIABLE:
                return  # nothing left to fetch; the MD5 check decides
            resp.raise_for_status()
            if resp.status_code == HTTP_PARTIAL_CONTENT:
                start, _total = parse_content_range(resp.headers.get("Content-Range", ""))
                if start != offset:
                    part.unlink()
                    raise ValueError(f"server resumed at {start}, expected {offset}")
                mode = "ab"
                msg = f"{name}: resuming at {offset / (1024 * 1024):.1f} MB"
            else:
                mode = "wb"  # full body: the server ignored Range (or none was sent)
                msg = f"{name}: downloading"
            logger.info(msg)
            if progress_callback:
                progress_callback(f"[DOWNLOAD] {msg}")
            with open(part, mode) as f:
                for chunk in resp.iter_content(self.chunk_size):
                    if chunk:
                        f.write(chunk)
                f.flush()
                os.fsync(f.fileno())
