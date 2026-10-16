"""PubMed Central Cloud Service access (PDF + JATS XML over HTTPS).

Since August 2026 PMC distributes its article datasets only through the PMC
Cloud Service (AWS Open Data bucket ``pmc-oa-opendata``). The FTP service's
``oa_package``/``oa_pdf`` trees and the OA Web Service (``oa.fcgi``) that
pointed at them were removed. The bucket is world-readable over plain HTTPS
and is organised by *article version*::

    PMC10009416.1/PMC10009416.1.pdf     (when licensing permits)
    PMC10009416.1/PMC10009416.1.xml     (JATS full text)
    PMC10009416.1/PMC10009416.1.txt
    PMC10009416.1/PMC10009416.1.json    (metadata, incl. per-file MD5)
    metadata/PMC10009416.1.json         (same metadata object)

A PMCID can have several versions (e.g. author manuscript + published
version); version 1 need not exist. See the bucket's README.txt
(https://pmc-oa-opendata.s3.amazonaws.com/README.txt).

This module provides pure helpers for the bucket layout, :class:`PMCCloudClient`
to find the preferred article version for a PMCID, and
:class:`PMCCloudDownloader` to fetch its PDF (MD5-verified) plus the article
XML, which is parsed into Markdown full text.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple
from urllib.parse import parse_qs, urlparse

import requests

from ..utils.download_utils import (
    discard_partial_download,
    partial_download_path,
    promote_partial_download,
)
from ..utils.pdf_validation import PDF_HEADER_READ_SIZE, is_pdf_content
from ..utils.rate_limit import (
    HostRateLimiter,
    RateLimitedSession,
    backoff_delay,
    throttle_delay,
)
from .data_types import DownloadResult, PDFSource
from .nxml_parser import NXMLParser

logger = logging.getLogger(__name__)

PMC_CLOUD_BUCKET = "pmc-oa-opendata"
PMC_CLOUD_HTTPS_BASE = f"https://{PMC_CLOUD_BUCKET}.s3.amazonaws.com"
# Prefix (within the bucket) holding a copy of every version's metadata JSON
PMC_CLOUD_METADATA_PREFIX = "metadata"

# Host that used to serve PMC/PubMed over FTP; it serves the same tree over HTTPS.
NCBI_FTP_HOST = "ftp.ncbi.nlm.nih.gov"

DEFAULT_TIMEOUT = 30
# Attempts per file (PDF / XML) for transient failures and MD5 mismatches.
DEFAULT_MAX_ATTEMPTS = 3
RETRY_BASE_SECONDS = 2.0
DOWNLOAD_CHUNK_SIZE = 64 * 1024

# HTTP statuses for which retrying the same URL cannot help.
PERMANENT_HTTP_STATUSES = frozenset({400, 401, 403, 404, 410})

PMCID_PATTERN = re.compile(r"^PMC\d+$")
# An article-version prefix as listed by S3, e.g. "PMC5334499.1/"
VERSION_PREFIX_PATTERN = re.compile(r"<Prefix>(PMC\d+\.\d+)/</Prefix>")
# Object key of a file inside one article version, e.g. "PMC5334499.1/PMC5334499.1.pdf"
OBJECT_KEY_PATTERN = re.compile(r"^PMC\d+\.\d+/[A-Za-z0-9][A-Za-z0-9._-]*$")
MD5_PATTERN = re.compile(r"^[0-9a-f]{32}$")

# File extension of the article XML saved next to the PDFs' fulltext dir
FULLTEXT_XML_SUFFIX = ".nxml"


class PMCCloudError(Exception):
    """A PMC Cloud Service request failed.

    Attributes:
        retryable: Whether another attempt at the same URL might succeed.
        attempts: How many attempts were made before giving up.
    """

    def __init__(self, message: str, retryable: bool, attempts: int = 1) -> None:
        """Initialize the error.

        Args:
            message: Human-readable description of the failure.
            retryable: Whether another attempt might succeed.
            attempts: Attempts made so far.
        """
        super().__init__(message)
        self.retryable = retryable
        self.attempts = attempts


@dataclass
class PMCArticleVersion:
    """One article version in the PMC Cloud Service (parsed metadata JSON)."""

    pmcid: str
    version: int
    xml_url: Optional[str] = None  # HTTPS URL
    xml_md5: Optional[str] = None
    pdf_url: Optional[str] = None  # HTTPS URL, None if the license forbids it
    pdf_md5: Optional[str] = None
    pmid: Optional[str] = None
    doi: Optional[str] = None
    license_code: Optional[str] = None
    is_manuscript: bool = False
    is_retracted: bool = False
    is_openaccess: bool = False
    extra: Dict[str, Any] = field(default_factory=dict)

    @property
    def prefix(self) -> str:
        """Bucket prefix of this version, e.g. ``PMC5334499.1``."""
        return f"{self.pmcid}.{self.version}"


# --- pure helpers -----------------------------------------------------------


def normalize_pmcid(value: str) -> Optional[str]:
    """Normalise a PMCID to ``PMC<digits>``.

    Args:
        value: PMCID with or without the ``PMC`` prefix (e.g. ``"123"``,
            ``"pmc123"``, ``"PMC123"``).

    Returns:
        The canonical PMCID, or None if ``value`` isn't a valid PMCID.
    """
    text = (value or "").strip().upper()
    if text.isdigit():
        text = f"PMC{text}"
    return text if PMCID_PATTERN.match(text) else None


def version_listing_params(pmcid: str) -> Dict[str, str]:
    """Query parameters for an S3 ListObjectsV2 call listing a PMCID's versions.

    Args:
        pmcid: Canonical PMCID.

    Returns:
        Parameters for a GET on :data:`PMC_CLOUD_HTTPS_BASE`.
    """
    return {"list-type": "2", "prefix": f"{pmcid}.", "delimiter": "/"}


def parse_version_listing(xml_text: str, pmcid: str) -> List[str]:
    """Extract the article-version prefixes for ``pmcid`` from an S3 listing.

    Args:
        xml_text: ListObjectsV2 XML response body.
        pmcid: Canonical PMCID the listing was made for.

    Returns:
        Version prefixes such as ``["PMC5334499.1"]``, in listing order,
        restricted to ``pmcid`` (anything else in the response is ignored).
    """
    wanted = f"{pmcid}."
    return [p for p in VERSION_PREFIX_PATTERN.findall(xml_text or "") if p.startswith(wanted)]


def metadata_url(version_prefix: str) -> str:
    """HTTPS URL of the metadata JSON for an article version.

    Args:
        version_prefix: e.g. ``PMC5334499.1``.

    Returns:
        URL under the bucket's ``metadata/`` prefix.
    """
    return f"{PMC_CLOUD_HTTPS_BASE}/{PMC_CLOUD_METADATA_PREFIX}/{version_prefix}.json"


def s3_url_to_https(url: str) -> Tuple[str, Optional[str]]:
    """Convert a metadata ``s3://`` file URL into an HTTPS URL plus its MD5.

    Metadata URLs look like
    ``s3://pmc-oa-opendata/PMC5334499.1/PMC5334499.1.pdf?md5=9c91…``.

    Args:
        url: URL from a metadata JSON object (untrusted).

    Returns:
        ``(https_url, md5)``; md5 is None if absent or malformed.

    Raises:
        ValueError: If the URL is not a file of an article version in the
            PMC bucket (wrong scheme/bucket, or a key that could escape the
            version prefix).
    """
    parsed = urlparse(url)
    if parsed.scheme != "s3" or parsed.netloc != PMC_CLOUD_BUCKET:
        raise ValueError(f"Not a PMC Cloud Service URL: {url!r}")
    key = parsed.path.lstrip("/")
    if ".." in key or not OBJECT_KEY_PATTERN.match(key):
        raise ValueError(f"Unexpected PMC Cloud Service object key: {key!r}")
    md5_values = parse_qs(parsed.query).get("md5", [])
    md5 = md5_values[0].lower() if md5_values else None
    if md5 is not None and not MD5_PATTERN.match(md5):
        md5 = None
    return f"{PMC_CLOUD_HTTPS_BASE}/{key}", md5


def ncbi_ftp_to_https(url: str) -> Optional[str]:
    """Rewrite an ``ftp://ftp.ncbi.nlm.nih.gov/...`` URL to its HTTPS equivalent.

    NCBI serves the same tree over HTTPS, which is far more reliable than
    its FTP service.

    Args:
        url: Any URL.

    Returns:
        The HTTPS URL, or None if ``url`` is not an NCBI FTP URL.
    """
    parsed = urlparse(url)
    if parsed.scheme.lower() != "ftp" or (parsed.hostname or "").lower() != NCBI_FTP_HOST:
        return None
    return f"https://{NCBI_FTP_HOST}{parsed.path}"


def _optional_str(value: Any) -> Optional[str]:
    """Return ``str(value)`` for non-empty scalars, else None."""
    if value is None or isinstance(value, (dict, list)):
        return None
    text = str(value).strip()
    return text or None


def parse_version_metadata(data: Mapping[str, Any]) -> PMCArticleVersion:
    """Parse and validate a PMC Cloud Service metadata JSON object.

    Args:
        data: Decoded JSON (untrusted).

    Returns:
        The parsed article version. File URLs that fail validation are
        dropped (logged) rather than trusted.

    Raises:
        ValueError: If the PMCID or version is missing or malformed.
    """
    pmcid = normalize_pmcid(str(data.get("pmcid", "")))
    if pmcid is None:
        raise ValueError(f"Invalid pmcid in metadata: {data.get('pmcid')!r}")
    version = data.get("version")
    if isinstance(version, bool) or not isinstance(version, int) or version < 1:
        raise ValueError(f"Invalid version in metadata for {pmcid}: {version!r}")

    urls: Dict[str, Tuple[Optional[str], Optional[str]]] = {}
    for kind in ("pdf_url", "xml_url"):
        raw = data.get(kind)
        if not raw:
            urls[kind] = (None, None)
            continue
        try:
            urls[kind] = s3_url_to_https(str(raw))
        except ValueError as e:
            logger.warning(f"Ignoring {kind} for {pmcid}.{version}: {e}")
            urls[kind] = (None, None)

    return PMCArticleVersion(
        pmcid=pmcid,
        version=version,
        pdf_url=urls["pdf_url"][0],
        pdf_md5=urls["pdf_url"][1],
        xml_url=urls["xml_url"][0],
        xml_md5=urls["xml_url"][1],
        pmid=_optional_str(data.get("pmid")),
        doi=_optional_str(data.get("doi")),
        license_code=_optional_str(data.get("license_code")),
        is_manuscript=data.get("is_manuscript") is True,
        is_retracted=data.get("is_retracted") is True,
        is_openaccess=data.get("is_pmc_openaccess") is True,
    )


def select_preferred_version(
    versions: List[PMCArticleVersion],
) -> Optional[PMCArticleVersion]:
    """Pick the version whose PDF discovery should download.

    Only versions with a PDF qualify. Preference order: not retracted, then
    the published version over an author manuscript, then the highest
    version number (PMC numbers versions in processing order, so this only
    breaks remaining ties).

    Args:
        versions: Parsed versions of one PMCID.

    Returns:
        The preferred version, or None if no version has a PDF.
    """
    with_pdf = [v for v in versions if v.pdf_url]
    if not with_pdf:
        return None
    return max(with_pdf, key=lambda v: (not v.is_retracted, not v.is_manuscript, v.version))


def classify_http_error(status_code: int, response: Optional[requests.Response]) -> bool:
    """Return True if an HTTP error status is worth retrying.

    Args:
        status_code: HTTP status of the failed response.
        response: The response, used to recognise throttling that the
            rate-limited session has already retried.

    Returns:
        False for permanent errors and already-retried throttling.
    """
    if status_code in PERMANENT_HTTP_STATUSES:
        return False
    if response is not None and throttle_delay(response, 0) is not None:
        return False  # RateLimitedSession already honoured Retry-After
    return status_code >= 500


# --- network ----------------------------------------------------------------


class PMCCloudClient:
    """Look up article versions in the PMC Cloud Service."""

    def __init__(
        self,
        session: Optional[requests.Session] = None,
        timeout: int = DEFAULT_TIMEOUT,
        rate_limiter: Optional[HostRateLimiter] = None,
    ) -> None:
        """Initialize the client.

        Args:
            session: HTTP session to use; defaults to a rate-limited session.
            timeout: Request timeout in seconds.
            rate_limiter: Limiter for the default session (shared by default).
        """
        self.session = session or RateLimitedSession(rate_limiter)
        self.timeout = timeout

    def list_versions(self, pmcid: str) -> List[str]:
        """List the article-version prefixes stored for ``pmcid``.

        Args:
            pmcid: Canonical PMCID.

        Returns:
            Version prefixes (empty if the article isn't in the datasets).

        Raises:
            requests.RequestException: On network errors or a non-200 response.
        """
        response = self.session.get(
            f"{PMC_CLOUD_HTTPS_BASE}/",
            params=version_listing_params(pmcid),
            timeout=self.timeout,
        )
        response.raise_for_status()
        return parse_version_listing(response.text, pmcid)

    def get_version(self, version_prefix: str) -> PMCArticleVersion:
        """Fetch and parse one version's metadata JSON.

        Args:
            version_prefix: e.g. ``PMC5334499.1``.

        Returns:
            The parsed version.

        Raises:
            requests.RequestException: On network errors or a non-200 response.
            ValueError: If the JSON is malformed or fails validation.
        """
        response = self.session.get(metadata_url(version_prefix), timeout=self.timeout)
        response.raise_for_status()
        try:
            data = response.json()
        except json.JSONDecodeError as e:
            raise ValueError(f"Malformed metadata JSON for {version_prefix}: {e}") from e
        if not isinstance(data, dict):
            raise ValueError(f"Metadata for {version_prefix} is not a JSON object")
        return parse_version_metadata(data)

    def find_article(self, pmcid: str) -> Optional[PMCArticleVersion]:
        """Return the preferred downloadable version of ``pmcid``.

        Versions whose metadata can't be read are skipped (and logged).

        Args:
            pmcid: PMCID in any form accepted by :func:`normalize_pmcid`.

        Returns:
            The preferred version with a PDF, or None if there is none.

        Raises:
            ValueError: If ``pmcid`` is not a valid PMCID.
            requests.RequestException: If the version listing fails.
        """
        canonical = normalize_pmcid(pmcid)
        if canonical is None:
            raise ValueError(f"Invalid PMCID: {pmcid!r}")
        versions: List[PMCArticleVersion] = []
        for prefix in self.list_versions(canonical):
            try:
                versions.append(self.get_version(prefix))
            except (requests.RequestException, ValueError) as e:
                logger.warning(f"Skipping PMC Cloud version {prefix}: {e}")
        return select_preferred_version(versions)


class PMCCloudDownloader:
    """Download an article's PDF and JATS XML from the PMC Cloud Service.

    The PDF is required; the XML is best-effort and, when available, saved
    as ``<fulltext_dir>/<stem>.nxml`` and parsed into Markdown full text.
    Each file is fetched with one retry loop (transient errors and MD5
    mismatches), streamed to a ``.part`` file and only promoted after its
    MD5 (from the metadata) and, for the PDF, its magic bytes check out.
    """

    def __init__(
        self,
        timeout: int = DEFAULT_TIMEOUT,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
        session: Optional[requests.Session] = None,
        rate_limiter: Optional[HostRateLimiter] = None,
    ) -> None:
        """Initialize the downloader.

        Args:
            timeout: Request timeout in seconds.
            max_attempts: Attempts per file.
            session: HTTP session; defaults to a rate-limited session.
            rate_limiter: Limiter for the default session (shared by default).
        """
        self.timeout = timeout
        self.max_attempts = max(1, max_attempts)
        self.session = session or RateLimitedSession(rate_limiter)
        self.nxml_parser = NXMLParser()

    def download(
        self,
        source: PDFSource,
        pdf_output_path: Path,
        fulltext_output_dir: Path,
    ) -> DownloadResult:
        """Download the PDF (and XML full text) described by a PMC Cloud source.

        Args:
            source: Source from :class:`~.resolvers.PMCResolver` (HTTPS PDF
                URL; ``metadata`` carries ``pdf_md5``, ``xml_url``, ``xml_md5``).
            pdf_output_path: Final path of the PDF.
            fulltext_output_dir: Directory for the ``.nxml`` file.

        Returns:
            DownloadResult with the PDF path and, if the XML could be fetched
            and parsed, ``full_text`` / ``full_text_path``.
        """
        start_time = time.time()
        meta = source.metadata or {}

        try:
            pdf_size, attempts = self._fetch_with_retries(
                source.url, pdf_output_path, meta.get("pdf_md5"), require_pdf=True
            )
        except PMCCloudError as e:
            return DownloadResult(
                success=False,
                source=source,
                error_message=f"PMC Cloud PDF download failed: {e}",
                duration_ms=(time.time() - start_time) * 1000,
                attempts=e.attempts,
            )

        result = DownloadResult(
            success=True,
            source=source,
            file_path=str(pdf_output_path),
            file_size=pdf_size,
            attempts=attempts,
        )

        xml_url = meta.get("xml_url")
        if xml_url:
            xml_path = fulltext_output_dir / f"{pdf_output_path.stem}{FULLTEXT_XML_SUFFIX}"
            try:
                self._fetch_with_retries(xml_url, xml_path, meta.get("xml_md5"), require_pdf=False)
                result.full_text_path = str(xml_path)
                result.full_text = self._parse_xml(xml_path)
            except PMCCloudError as e:
                # The PDF is the deliverable; missing full text is reported, not fatal.
                logger.warning(f"PMC Cloud XML download failed for {source.url}: {e}")

        result.duration_ms = (time.time() - start_time) * 1000
        return result

    def _parse_xml(self, xml_path: Path) -> Optional[str]:
        """Parse a downloaded JATS XML file into Markdown full text.

        Args:
            xml_path: Path of the saved XML.

        Returns:
            Full text, or None if it couldn't be decoded or parsed.
        """
        try:
            text = self.nxml_parser.parse(xml_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError) as e:
            logger.warning(f"Could not read PMC XML {xml_path}: {e}")
            return None
        if text:
            logger.info(f"Extracted {len(text)} chars of full text from {xml_path.name}")
        return text or None

    def _fetch_with_retries(
        self,
        url: str,
        dest: Path,
        expected_md5: Optional[str],
        require_pdf: bool,
    ) -> Tuple[int, int]:
        """Fetch ``url`` to ``dest`` with one bounded retry loop.

        Args:
            url: HTTPS URL to download.
            dest: Final destination path.
            expected_md5: MD5 from the metadata (verified when given).
            require_pdf: Reject content without PDF magic bytes.

        Returns:
            ``(bytes_written, attempts_used)``.

        Raises:
            PMCCloudError: When all attempts failed or a permanent error
                occurred; its ``attempts`` attribute holds the attempt count.
        """
        attempt = 1
        while True:
            try:
                return self._fetch_once(url, dest, expected_md5, require_pdf), attempt
            except PMCCloudError as e:
                logger.warning(f"PMC Cloud attempt {attempt}/{self.max_attempts} for {url}: {e}")
                if not e.retryable or attempt >= self.max_attempts:
                    e.attempts = attempt
                    raise
            time.sleep(backoff_delay(attempt - 1, base=RETRY_BASE_SECONDS))
            attempt += 1

    def _fetch_once(
        self,
        url: str,
        dest: Path,
        expected_md5: Optional[str],
        require_pdf: bool,
    ) -> int:
        """Single attempt: stream ``url`` into ``dest`` via a ``.part`` file.

        Args:
            url: HTTPS URL to download.
            dest: Final destination path (left untouched on failure).
            expected_md5: MD5 to verify, if known.
            require_pdf: Reject content without PDF magic bytes.

        Returns:
            Number of bytes written.

        Raises:
            PMCCloudError: On any failure, classified as retryable or not.
        """
        part = partial_download_path(dest)
        digest = hashlib.md5(usedforsecurity=False)
        total = 0
        head = b""
        try:
            response = self.session.get(url, timeout=self.timeout, stream=True)
            try:
                response.raise_for_status()
                dest.parent.mkdir(parents=True, exist_ok=True)
                with open(part, "wb") as f:
                    for chunk in response.iter_content(chunk_size=DOWNLOAD_CHUNK_SIZE):
                        if not chunk:
                            continue
                        if len(head) < PDF_HEADER_READ_SIZE:
                            head += chunk[: PDF_HEADER_READ_SIZE - len(head)]
                        f.write(chunk)
                        digest.update(chunk)
                        total += len(chunk)
            finally:
                response.close()
        except requests.HTTPError as e:
            discard_partial_download(part)
            status = e.response.status_code if e.response is not None else 0
            raise PMCCloudError(
                f"HTTP {status}", retryable=classify_http_error(status, e.response)
            ) from e
        except (requests.ConnectionError, requests.Timeout) as e:
            discard_partial_download(part)
            raise PMCCloudError(f"Network error: {e}", retryable=True) from e
        except requests.RequestException as e:
            discard_partial_download(part)
            raise PMCCloudError(f"Request error: {e}", retryable=False) from e
        except OSError as e:
            discard_partial_download(part)
            raise PMCCloudError(f"Could not write {dest}: {e}", retryable=False) from e

        if total == 0:
            discard_partial_download(part)
            raise PMCCloudError("Downloaded file is empty", retryable=True)
        if expected_md5 and digest.hexdigest() != expected_md5:
            discard_partial_download(part)
            raise PMCCloudError("MD5 mismatch (corrupt or truncated download)", retryable=True)
        if require_pdf and not is_pdf_content(head):
            discard_partial_download(part)
            raise PMCCloudError("Downloaded file is not a PDF", retryable=False)

        promote_partial_download(part, dest)
        logger.info(f"Downloaded {total} bytes from {url}")
        return total
