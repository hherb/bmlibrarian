"""
Tests for bmlibrarian.importers.ncbi_https (verified, resumable HTTPS downloads).

NCBI's FTP service was observed to re-send earlier parts of a file mid-transfer
(the received stream rewinds, so the file comes out too large or silently
wrong). The HTTPS downloader therefore never trusts a transfer: every file is
written to ``<name>.part``, resumed with HTTP Range requests, verified against
NCBI's published MD5, and only then renamed to its final name.

The network is replaced by a fake session that serves bytes from memory and can
drop connections, ignore Range headers, or corrupt the stream.
"""

import hashlib
from pathlib import Path
from typing import Dict, List, Optional

import pytest
import requests

from bmlibrarian.importers import ncbi_https as nh

PAYLOAD = bytes(range(256)) * 400  # 102,400 bytes
PAYLOAD_MD5 = hashlib.md5(PAYLOAD).hexdigest()
URL = "https://ftp.ncbi.nlm.nih.gov/pubmed/baseline/pubmed26n0001.xml.gz"


class FakeResponse:
    """Minimal streaming response: status, headers and iter_content."""

    def __init__(self, status: int, body: bytes, headers: Dict[str, str],
                 fail_after: Optional[int] = None) -> None:
        self.status_code = status
        self.headers = headers
        self._body = body
        self._fail_after = fail_after
        self.text = body.decode("latin-1")

    def iter_content(self, chunk_size: int):
        """Yield the body in chunks, optionally dropping the connection part-way."""
        sent = 0
        for i in range(0, len(self._body), chunk_size):
            if self._fail_after is not None and sent >= self._fail_after:
                raise requests.ConnectionError("connection reset")
            chunk = self._body[i:i + chunk_size]
            sent += len(chunk)
            yield chunk

    def raise_for_status(self) -> None:
        """Raise for 4xx/5xx like requests does."""
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")

    def close(self) -> None:
        """Nothing to release."""

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *exc) -> None:
        self.close()


class FakeSession:
    """Serves PAYLOAD at URL, honouring Range unless told otherwise."""

    def __init__(self, payload: bytes = PAYLOAD, ignore_range: bool = False,
                 failures: Optional[List[int]] = None, corrupt_first: int = 0) -> None:
        self.payload = payload
        self.ignore_range = ignore_range
        self.failures = list(failures or [])  # bytes sent before each successive drop
        self.corrupt_first = corrupt_first   # number of initial requests that rewind the stream
        self.requests: List[Dict[str, str]] = []

    def get(self, url: str, headers: Optional[Dict[str, str]] = None, stream: bool = False,
            timeout: Optional[float] = None) -> FakeResponse:
        headers = headers or {}
        self.requests.append(dict(headers))
        body = self.payload
        if self.corrupt_first > 0:
            self.corrupt_first -= 1
            body = body[:60_000] + body[40_000:]  # the stream rewinds by 20 kB
        fail_after = self.failures.pop(0) if self.failures else None
        rng = headers.get("Range")
        if rng and not self.ignore_range:
            start = int(rng.split("=")[1].rstrip("-"))
            if start >= len(body):
                return FakeResponse(416, b"", {"Content-Range": f"bytes */{len(body)}"})
            part = body[start:]
            return FakeResponse(206, part, {
                "Content-Range": f"bytes {start}-{len(body) - 1}/{len(body)}",
                "Content-Length": str(len(part))}, fail_after)
        return FakeResponse(200, body, {"Content-Length": str(len(body))}, fail_after)


def make_downloader(session: FakeSession) -> nh.HttpsDownloader:
    return nh.HttpsDownloader(session=session, chunk_size=4096, max_retries=4, sleep=lambda s: None)


class TestPureHelpers:
    """Listing, checksum-file and Content-Range parsing."""

    def test_parse_listing_returns_sorted_unique_data_files(self) -> None:
        html = ('<a href="pubmed26n0002.xml.gz">x</a> <a href="pubmed26n0001.xml.gz">x</a>'
                '<a href="pubmed26n0001.xml.gz.md5">x</a><a href="README.txt">x</a>'
                '<a href="pubmed26n0001.xml.gz">dup</a><a href="../evil/pubmed26n9.xml.gz">x</a>')
        assert nh.parse_directory_listing(html) == ["pubmed26n0001.xml.gz", "pubmed26n0002.xml.gz"]

    def test_parse_md5_file(self) -> None:
        text = "MD5(pubmed26n0001.xml.gz)= fb7c05737f47f7e07245f0c064c6e00a\n"
        assert nh.parse_md5_file(text) == "fb7c05737f47f7e07245f0c064c6e00a"

    def test_parse_md5_file_rejects_garbage(self) -> None:
        with pytest.raises(ValueError):
            nh.parse_md5_file("<html>404</html>")

    def test_parse_content_range(self) -> None:
        assert nh.parse_content_range("bytes 100-199/1000") == (100, 1000)
        with pytest.raises(ValueError):
            nh.parse_content_range("bytes */1000")

    def test_part_path(self, tmp_path: Path) -> None:
        assert nh.part_path(tmp_path / "a.xml.gz") == tmp_path / "a.xml.gz.part"


class TestDownload:
    """The final name only ever holds a file whose MD5 matched."""

    def test_clean_download_lands_at_final_name(self, tmp_path: Path) -> None:
        dest = tmp_path / "pubmed26n0001.xml.gz"
        assert make_downloader(FakeSession()).download(URL, dest, PAYLOAD_MD5)
        assert dest.read_bytes() == PAYLOAD
        assert not nh.part_path(dest).exists()

    def test_dropped_connection_resumes_with_range(self, tmp_path: Path) -> None:
        dest = tmp_path / "f.xml.gz"
        session = FakeSession(failures=[30_000])
        assert make_downloader(session).download(URL, dest, PAYLOAD_MD5)
        assert dest.read_bytes() == PAYLOAD
        assert session.requests[1].get("Range", "").startswith("bytes=")
        assert int(session.requests[1]["Range"][6:-1]) > 0

    def test_server_ignoring_range_restarts_from_zero(self, tmp_path: Path) -> None:
        dest = tmp_path / "f.xml.gz"
        nh.part_path(dest).write_bytes(PAYLOAD[:10_000])
        assert make_downloader(FakeSession(ignore_range=True)).download(URL, dest, PAYLOAD_MD5)
        assert dest.read_bytes() == PAYLOAD

    def test_corrupted_stream_is_rejected_and_retried(self, tmp_path: Path) -> None:
        dest = tmp_path / "f.xml.gz"
        session = FakeSession(corrupt_first=1)
        assert make_downloader(session).download(URL, dest, PAYLOAD_MD5)
        assert dest.read_bytes() == PAYLOAD
        assert len(session.requests) == 2

    def test_persistent_corruption_fails_without_final_file(self, tmp_path: Path) -> None:
        dest = tmp_path / "f.xml.gz"
        assert not make_downloader(FakeSession(corrupt_first=99)).download(URL, dest, PAYLOAD_MD5)
        assert not dest.exists()
        assert not nh.part_path(dest).exists()

    def test_existing_verified_file_is_not_downloaded_again(self, tmp_path: Path) -> None:
        dest = tmp_path / "f.xml.gz"
        dest.write_bytes(PAYLOAD)
        session = FakeSession()
        assert make_downloader(session).download(URL, dest, PAYLOAD_MD5)
        assert session.requests == []

    def test_existing_wrong_file_is_replaced(self, tmp_path: Path) -> None:
        dest = tmp_path / "f.xml.gz"
        dest.write_bytes(PAYLOAD[:5_000])  # e.g. a failed legacy FTP download
        assert make_downloader(FakeSession()).download(URL, dest, PAYLOAD_MD5)
        assert dest.read_bytes() == PAYLOAD

    def test_complete_part_file_is_verified_without_body(self, tmp_path: Path) -> None:
        dest = tmp_path / "f.xml.gz"
        nh.part_path(dest).write_bytes(PAYLOAD)
        assert make_downloader(FakeSession()).download(URL, dest, PAYLOAD_MD5)
        assert dest.read_bytes() == PAYLOAD

    def test_invalid_expected_md5_is_rejected(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError):
            make_downloader(FakeSession()).download(URL, tmp_path / "f.xml.gz", "not-a-hash")


class TestRemote:
    """Listing and checksum lookups go through the same session."""

    def test_list_files_and_fetch_md5(self) -> None:
        listing = b'<a href="pubmed26n0001.xml.gz">a</a><a href="pubmed26n0002.xml.gz">b</a>'
        md5_text = f"MD5(pubmed26n0001.xml.gz)= {PAYLOAD_MD5}\n".encode()

        class Router(FakeSession):
            def get(self, url, headers=None, stream=False, timeout=None):
                if url.endswith("/"):
                    return FakeResponse(200, listing, {})
                if url.endswith(".md5"):
                    return FakeResponse(200, md5_text, {})
                return super().get(url, headers, stream, timeout)

        dl = make_downloader(Router())
        base = "https://ftp.ncbi.nlm.nih.gov/pubmed/baseline/"
        assert dl.list_files(base) == ["pubmed26n0001.xml.gz", "pubmed26n0002.xml.gz"]
        assert dl.fetch_md5(base + "pubmed26n0001.xml.gz") == PAYLOAD_MD5


class TestMetadataRetries:
    """A dropped connection on the small listing/.md5 requests must not skip a file."""

    def test_fetch_md5_retries_after_disconnect(self) -> None:
        md5_text = f"MD5(pubmed26n0001.xml.gz)= {PAYLOAD_MD5}\n".encode()

        class Flaky(FakeSession):
            calls = 0

            def get(self, url, headers=None, stream=False, timeout=None):
                Flaky.calls += 1
                if Flaky.calls == 1:
                    raise requests.ConnectionError("Remote end closed connection without response")
                return FakeResponse(200, md5_text, {})

        assert make_downloader(Flaky()).fetch_md5(URL) == PAYLOAD_MD5
        assert Flaky.calls == 2

    def test_list_files_gives_up_after_max_retries(self) -> None:
        class Down(FakeSession):
            def get(self, url, headers=None, stream=False, timeout=None):
                raise requests.ConnectionError("down")

        with pytest.raises(requests.ConnectionError):
            make_downloader(Down()).list_files("https://ftp.ncbi.nlm.nih.gov/pubmed/baseline/")
