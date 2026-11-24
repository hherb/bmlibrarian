"""OpenAthens cookies keep their domain, path and secure scope (#434).

Both HTTP download paths used to flatten the browser cookies into a
``{name: value}`` dict, which ``requests`` sends to whatever host the PDF
URL (taken from imported metadata) or a redirect names, over plain HTTP too.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import requests
from requests.cookies import RequestsCookieJar

from bmlibrarian.discovery.data_types import AccessType, PDFSource, SourceType
from bmlibrarian.discovery.full_text_finder import FullTextFinder
from bmlibrarian.utils.openathens_auth import cookie_jar_from_browser_cookies
from bmlibrarian.utils.pdf_manager import PDFManager

PDF_BYTES = b"%PDF-1.4\n1 0 obj\n<< >>\nendobj\n%%EOF"

BROWSER_COOKIES = [
    {"name": "oamps", "value": "s1", "domain": ".openathens.net", "path": "/", "secure": True},
    {"name": "pub", "value": "s2", "domain": "www.publisher.com", "path": "/", "secure": True},
]


def cookie_header(jar: RequestsCookieJar, url: str) -> str | None:
    """Return the Cookie header ``requests`` would send to ``url``."""
    return requests.Request("GET", url, cookies=jar).prepare().headers.get("Cookie")


def fake_auth() -> MagicMock:
    """An authenticated OpenAthensAuth stand-in holding BROWSER_COOKIES."""
    auth = MagicMock()
    auth.is_authenticated.return_value = True
    auth.get_user_agent.return_value = None
    auth.get_cookie_jar.side_effect = lambda: cookie_jar_from_browser_cookies(BROWSER_COOKIES)
    return auth


def pdf_response() -> MagicMock:
    """A 200 response streaming a valid PDF."""
    response = MagicMock()
    response.status_code = 200
    response.headers = {"content-type": "application/pdf"}
    response.raise_for_status.return_value = None
    response.iter_content.return_value = [PDF_BYTES]
    return response


class TestCookieJarFromBrowserCookies:
    """The converter keeps each cookie's scope and drops unscoped ones."""

    def test_cookies_go_only_to_their_own_host_over_https(self) -> None:
        jar = cookie_jar_from_browser_cookies(BROWSER_COOKIES)
        assert cookie_header(jar, "https://www.publisher.com/a.pdf") == "pub=s2"
        assert cookie_header(jar, "https://login.openathens.net/x") == "oamps=s1"
        assert cookie_header(jar, "https://some-mirror.example/a.pdf") is None
        assert cookie_header(jar, "http://www.publisher.com/a.pdf") is None

    def test_cookie_without_domain_is_dropped(self) -> None:
        """A domain-less cookie would be sent everywhere, so it is not kept."""
        jar = cookie_jar_from_browser_cookies([
            {"name": "nodomain", "value": "x"},
            {"name": "empty", "value": "x", "domain": ""},
            {"value": "x", "domain": "a.example"},
            "not-a-dict",
        ])
        assert len(jar) == 0

    def test_missing_path_and_secure_default_to_root_and_insecure(self) -> None:
        jar = cookie_jar_from_browser_cookies([{"name": "a", "value": "1", "domain": "a.example"}])
        assert cookie_header(jar, "http://a.example/deep/path") == "a=1"


class TestDownloadPathsSendScopedCookies:
    """Both HTTP download paths pass the jar, not a flat dict."""

    def test_pdf_manager_download_pdf(self, tmp_path: Path) -> None:
        manager = PDFManager(base_dir=str(tmp_path), openathens_auth=fake_auth())
        document = {"id": 1, "doi": "10.1/x", "pdf_url": "http://some-mirror.example/x.pdf"}
        with patch("bmlibrarian.utils.pdf_manager.requests.get", return_value=pdf_response()) as get:
            manager.download_pdf(document, max_retries=1, use_browser_fallback=False)
        jar = get.call_args.kwargs["cookies"]
        assert isinstance(jar, RequestsCookieJar)
        assert cookie_header(jar, document["pdf_url"]) is None

    def test_full_text_finder_institutional_source(self, tmp_path: Path) -> None:
        finder = FullTextFinder(unpaywall_email="test@example.com", openathens_auth=fake_auth())
        source = PDFSource(
            url="http://some-mirror.example/x.pdf",
            source_type=SourceType.OPENATHENS,
            access_type=AccessType.INSTITUTIONAL,
        )
        with patch.object(finder.session, "get", return_value=pdf_response()) as get:
            finder._download_from_source(source=source, output_path=tmp_path / "x.pdf", max_attempts=1)
        jar = get.call_args.kwargs["cookies"]
        assert isinstance(jar, RequestsCookieJar)
        assert cookie_header(jar, source.url) is None
        assert cookie_header(jar, "https://www.publisher.com/x.pdf") == "pub=s2"
