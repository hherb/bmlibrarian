"""Tests for the PMC Cloud Service client/downloader (bmlibrarian.discovery.pmc_cloud).

The PMC FTP packages and OA Web Service were retired in August 2026; PDF
discovery now uses the pmc-oa-opendata S3 bucket over HTTPS.
"""

import hashlib
import io
from pathlib import Path
from typing import Callable, Dict, List, Optional
from unittest.mock import patch

import pytest
import requests

from bmlibrarian.discovery.data_types import (
    AccessType,
    DocumentIdentifiers,
    PDFSource,
    ResolutionStatus,
    SourceType,
)
from bmlibrarian.discovery.full_text_finder import FullTextFinder
from bmlibrarian.discovery.pmc_cloud import (
    PMC_CLOUD_HTTPS_BASE,
    PMCArticleVersion,
    PMCCloudClient,
    PMCCloudDownloader,
    metadata_url,
    ncbi_ftp_to_https,
    normalize_pmcid,
    parse_version_listing,
    parse_version_metadata,
    s3_url_to_https,
    select_preferred_version,
)
from bmlibrarian.discovery.resolvers import PMCResolver

PDF_BYTES = b"%PDF-1.7\n" + b"x" * 100
XML_BYTES = (
    b'<?xml version="1.0"?><article><front><article-meta><title-group>'
    b"<article-title>Cloud Article</article-title></title-group></article-meta>"
    b"</front><body><sec><title>Intro</title><p>Hello PMC cloud.</p></sec></body></article>"
)


def md5(data: bytes) -> str:
    """Hex MD5 of ``data``."""
    return hashlib.md5(data).hexdigest()


def listing_xml(*prefixes: str) -> str:
    """S3 ListObjectsV2 response with the given common prefixes."""
    common = "".join(f"<CommonPrefixes><Prefix>{p}/</Prefix></CommonPrefixes>" for p in prefixes)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">'
        f"<Name>pmc-oa-opendata</Name>{common}</ListBucketResult>"
    )


def metadata_json(pmcid: str = "PMC5334499", version: int = 1, pdf: bool = True,
                  manuscript: bool = False, retracted: bool = False) -> Dict:
    """Metadata object in the bucket's documented format."""
    prefix = f"{pmcid}.{version}"
    data = {
        "pmcid": pmcid, "version": version, "pmid": 28298962,
        "doi": "10.4329/wjr.v9.i2.27", "is_pmc_openaccess": True,
        "is_manuscript": manuscript, "is_retracted": retracted,
        "license_code": "CC BY-NC",
        "xml_url": f"s3://pmc-oa-opendata/{prefix}/{prefix}.xml?md5={md5(XML_BYTES)}",
        "text_url": f"s3://pmc-oa-opendata/{prefix}/{prefix}.txt?md5={'0' * 32}",
    }
    if pdf:
        data["pdf_url"] = f"s3://pmc-oa-opendata/{prefix}/{prefix}.pdf?md5={md5(PDF_BYTES)}"
    return data


def make_response(status: int = 200, body: bytes = b"", url: str = "") -> requests.Response:
    """A real requests.Response with a body that supports streaming."""
    response = requests.Response()
    response.status_code = status
    response.raw = io.BytesIO(body)
    response.url = url
    response.encoding = "utf-8"
    return response


class FakeBucket:
    """Routes session GETs to canned bucket responses and counts requests."""

    def __init__(self, routes: Dict[str, Callable[[], requests.Response]]) -> None:
        """Map URL (without query) to a response factory."""
        self.routes = routes
        self.calls: List[str] = []

    def get(self, url: str, params: Optional[Dict] = None, **kwargs) -> requests.Response:
        """Serve a canned response or 404."""
        key = url + ("?prefix=" + params["prefix"] if params else "")
        self.calls.append(key)
        factory = self.routes.get(key)
        return factory() if factory else make_response(404, b"", url)


# --- pure helpers -----------------------------------------------------------


class TestPureHelpers:
    """Bucket-layout helpers."""

    @pytest.mark.parametrize("value,expected", [
        ("PMC123", "PMC123"), ("pmc123", "PMC123"), (" 123 ", "PMC123"),
        ("PMC12x", None), ("", None), ("PMC", None), ("../PMC1", None),
    ])
    def test_normalize_pmcid(self, value: str, expected: Optional[str]) -> None:
        """PMCIDs are canonicalised; anything else is rejected."""
        assert normalize_pmcid(value) == expected

    def test_parse_version_listing_filters_to_pmcid(self) -> None:
        """Only this PMCID's version prefixes are returned."""
        xml = listing_xml("PMC5.1", "PMC5.2", "PMC55.1", "metadata")
        assert parse_version_listing(xml, "PMC5") == ["PMC5.1", "PMC5.2"]

    def test_parse_version_listing_empty(self) -> None:
        """Unknown articles (or junk) give no versions."""
        assert parse_version_listing(listing_xml(), "PMC5") == []
        assert parse_version_listing("<html>error</html>", "PMC5") == []

    def test_metadata_url(self) -> None:
        """Metadata lives under the metadata/ prefix."""
        assert metadata_url("PMC5.1") == f"{PMC_CLOUD_HTTPS_BASE}/metadata/PMC5.1.json"

    def test_s3_url_to_https(self) -> None:
        """s3:// URLs become HTTPS with the MD5 split off."""
        url, digest = s3_url_to_https(f"s3://pmc-oa-opendata/PMC5.1/PMC5.1.pdf?md5={'a' * 32}")
        assert url == f"{PMC_CLOUD_HTTPS_BASE}/PMC5.1/PMC5.1.pdf"
        assert digest == "a" * 32

    def test_s3_url_bad_md5_dropped(self) -> None:
        """A malformed md5 parameter is ignored, not trusted."""
        assert s3_url_to_https("s3://pmc-oa-opendata/PMC5.1/PMC5.1.pdf?md5=zz")[1] is None

    @pytest.mark.parametrize("url", [
        "s3://other-bucket/PMC5.1/PMC5.1.pdf",
        "https://pmc-oa-opendata.s3.amazonaws.com/PMC5.1/PMC5.1.pdf",
        "s3://pmc-oa-opendata/PMC5.1/../../etc/passwd",
        "s3://pmc-oa-opendata/metadata/PMC5.1.json",
        "s3://pmc-oa-opendata/PMC5.1/sub/dir.pdf",
    ])
    def test_s3_url_rejects_foreign_or_escaping_keys(self, url: str) -> None:
        """Only files directly inside an article version of the PMC bucket pass."""
        with pytest.raises(ValueError):
            s3_url_to_https(url)

    def test_ncbi_ftp_to_https(self) -> None:
        """NCBI FTP URLs map to the same path over HTTPS; others don't."""
        assert ncbi_ftp_to_https("ftp://ftp.ncbi.nlm.nih.gov/pub/x/y.pdf") == \
            "https://ftp.ncbi.nlm.nih.gov/pub/x/y.pdf"
        assert ncbi_ftp_to_https("ftp://ftp.example.org/x.pdf") is None
        assert ncbi_ftp_to_https("https://ftp.ncbi.nlm.nih.gov/x.pdf") is None


class TestParseVersionMetadata:
    """Validation of untrusted metadata JSON."""

    def test_valid(self) -> None:
        """Documented fields are parsed and URLs converted."""
        version = parse_version_metadata(metadata_json())
        assert version.prefix == "PMC5334499.1"
        assert version.pdf_url == f"{PMC_CLOUD_HTTPS_BASE}/PMC5334499.1/PMC5334499.1.pdf"
        assert version.pdf_md5 == md5(PDF_BYTES)
        assert version.xml_md5 == md5(XML_BYTES)
        assert version.pmid == "28298962"
        assert version.license_code == "CC BY-NC"
        assert version.is_openaccess and not version.is_manuscript

    def test_no_pdf(self) -> None:
        """Articles whose license forbids the PDF have no pdf_url."""
        assert parse_version_metadata(metadata_json(pdf=False)).pdf_url is None

    def test_foreign_pdf_url_dropped(self) -> None:
        """A pdf_url outside the bucket is discarded."""
        data = metadata_json()
        data["pdf_url"] = "s3://evil-bucket/PMC5334499.1/x.pdf"
        assert parse_version_metadata(data).pdf_url is None

    @pytest.mark.parametrize("bad", [{"pmcid": "nope", "version": 1},
                                     {"pmcid": "PMC1", "version": 0},
                                     {"pmcid": "PMC1", "version": "1"},
                                     {"pmcid": "PMC1", "version": True}])
    def test_invalid_identity_rejected(self, bad: Dict) -> None:
        """Missing/invalid pmcid or version raises ValueError."""
        with pytest.raises(ValueError):
            parse_version_metadata(bad)


class TestSelectPreferredVersion:
    """Choosing which article version to download."""

    def v(self, version: int, pdf: bool = True, manuscript: bool = False,
          retracted: bool = False) -> PMCArticleVersion:
        """Shorthand version factory."""
        return PMCArticleVersion(pmcid="PMC1", version=version,
                                 pdf_url="https://x/y.pdf" if pdf else None,
                                 is_manuscript=manuscript, is_retracted=retracted)

    def test_none_without_pdf(self) -> None:
        """No PDF in any version -> nothing to download."""
        assert select_preferred_version([self.v(1, pdf=False)]) is None
        assert select_preferred_version([]) is None

    def test_published_over_manuscript(self) -> None:
        """The published version wins even if the manuscript is numbered higher."""
        chosen = select_preferred_version([self.v(1), self.v(2, manuscript=True)])
        assert chosen is not None and chosen.version == 1

    def test_not_retracted_preferred(self) -> None:
        """A non-retracted version wins over a retracted one."""
        chosen = select_preferred_version([self.v(1), self.v(2, retracted=True)])
        assert chosen is not None and chosen.version == 1

    def test_highest_version_breaks_ties(self) -> None:
        """Otherwise the highest version number is used."""
        chosen = select_preferred_version([self.v(1), self.v(3), self.v(2)])
        assert chosen is not None and chosen.version == 3


# --- client -----------------------------------------------------------------


class TestPMCCloudClient:
    """Version lookup over HTTPS."""

    def test_find_article(self) -> None:
        """Listing + metadata lead to the preferred version with a PDF."""
        import json
        bucket = FakeBucket({
            f"{PMC_CLOUD_HTTPS_BASE}/?prefix=PMC5334499.":
                lambda: make_response(200, listing_xml("PMC5334499.1", "PMC5334499.2").encode()),
            metadata_url("PMC5334499.1"):
                lambda: make_response(200, json.dumps(metadata_json(version=1)).encode()),
            metadata_url("PMC5334499.2"):
                lambda: make_response(200, json.dumps(metadata_json(version=2, manuscript=True)).encode()),
        })
        client = PMCCloudClient(session=bucket)  # type: ignore[arg-type]
        article = client.find_article("5334499")
        assert article is not None and article.version == 1
        assert len(bucket.calls) == 3

    def test_bad_version_metadata_skipped(self) -> None:
        """A version with unreadable metadata doesn't sink the lookup."""
        import json
        bucket = FakeBucket({
            f"{PMC_CLOUD_HTTPS_BASE}/?prefix=PMC1.":
                lambda: make_response(200, listing_xml("PMC1.1", "PMC1.2").encode()),
            metadata_url("PMC1.1"): lambda: make_response(200, b"{not json"),
            metadata_url("PMC1.2"):
                lambda: make_response(200, json.dumps(metadata_json("PMC1", 2)).encode()),
        })
        article = PMCCloudClient(session=bucket).find_article("PMC1")  # type: ignore[arg-type]
        assert article is not None and article.version == 2

    def test_unknown_article(self) -> None:
        """An empty listing means no article (no metadata requests)."""
        bucket = FakeBucket({
            f"{PMC_CLOUD_HTTPS_BASE}/?prefix=PMC9.": lambda: make_response(200, listing_xml().encode()),
        })
        assert PMCCloudClient(session=bucket).find_article("PMC9") is None  # type: ignore[arg-type]
        assert len(bucket.calls) == 1

    def test_invalid_pmcid(self) -> None:
        """Invalid input is rejected before any request."""
        with pytest.raises(ValueError):
            PMCCloudClient(session=FakeBucket({})).find_article("abc")  # type: ignore[arg-type]


# --- downloader -------------------------------------------------------------


def cloud_source(pdf_md5: Optional[str] = None, xml: bool = True) -> PDFSource:
    """PMC_CLOUD source as PMCResolver produces it."""
    return PDFSource(
        url=f"{PMC_CLOUD_HTTPS_BASE}/PMC1.1/PMC1.1.pdf",
        source_type=SourceType.PMC_CLOUD,
        access_type=AccessType.OPEN,
        priority=5,
        metadata={
            "pmcid": "PMC1",
            "pdf_md5": pdf_md5 if pdf_md5 is not None else md5(PDF_BYTES),
            "xml_url": f"{PMC_CLOUD_HTTPS_BASE}/PMC1.1/PMC1.1.xml" if xml else None,
            "xml_md5": md5(XML_BYTES),
        },
    )


@pytest.fixture(autouse=True)
def no_backoff_sleep():
    """Skip real retry backoff sleeps."""
    with patch("bmlibrarian.discovery.pmc_cloud.time.sleep"):
        yield


class TestPMCCloudDownloader:
    """PDF + XML download with MD5 verification."""

    def downloader(self, routes: Dict[str, Callable[[], requests.Response]]
                   ) -> "tuple[PMCCloudDownloader, FakeBucket]":
        """Downloader wired to a fake bucket."""
        bucket = FakeBucket(routes)
        return PMCCloudDownloader(session=bucket, max_attempts=3), bucket  # type: ignore[arg-type]

    def test_pdf_and_full_text(self, tmp_path: Path) -> None:
        """PDF is saved, XML saved as .nxml and parsed into full text."""
        dl, _ = self.downloader({
            f"{PMC_CLOUD_HTTPS_BASE}/PMC1.1/PMC1.1.pdf": lambda: make_response(200, PDF_BYTES),
            f"{PMC_CLOUD_HTTPS_BASE}/PMC1.1/PMC1.1.xml": lambda: make_response(200, XML_BYTES),
        })
        pdf_path = tmp_path / "pdf" / "2017" / "doc.pdf"
        result = dl.download(cloud_source(), pdf_path, tmp_path / "fulltext" / "2017")

        assert result.success is True
        assert pdf_path.read_bytes() == PDF_BYTES
        assert result.full_text_path == str(tmp_path / "fulltext" / "2017" / "doc.nxml")
        assert result.full_text and "Hello PMC cloud" in result.full_text

    def test_md5_mismatch_retried_then_succeeds(self, tmp_path: Path) -> None:
        """A corrupt body is discarded and re-fetched."""
        bodies = iter([PDF_BYTES[:-5] + b"#####", PDF_BYTES])
        dl, bucket = self.downloader({
            f"{PMC_CLOUD_HTTPS_BASE}/PMC1.1/PMC1.1.pdf": lambda: make_response(200, next(bodies)),
        })
        result = dl.download(cloud_source(xml=False), tmp_path / "a.pdf", tmp_path)
        assert result.success is True
        assert result.attempts == 2
        assert (tmp_path / "a.pdf").read_bytes() == PDF_BYTES

    def test_persistent_md5_mismatch_fails_without_file(self, tmp_path: Path) -> None:
        """After max attempts the download fails and no file is left behind."""
        dl, bucket = self.downloader({
            f"{PMC_CLOUD_HTTPS_BASE}/PMC1.1/PMC1.1.pdf": lambda: make_response(200, PDF_BYTES),
        })
        result = dl.download(cloud_source(pdf_md5="0" * 32, xml=False), tmp_path / "a.pdf", tmp_path)
        assert result.success is False
        assert "MD5 mismatch" in result.error_message
        assert result.attempts == 3
        assert len(bucket.calls) == 3
        assert list(tmp_path.iterdir()) == []

    def test_404_not_retried(self, tmp_path: Path) -> None:
        """Permanent HTTP errors stop immediately."""
        dl, bucket = self.downloader({})
        result = dl.download(cloud_source(), tmp_path / "a.pdf", tmp_path)
        assert result.success is False
        assert "HTTP 404" in result.error_message
        assert len(bucket.calls) == 1

    def test_5xx_retried(self, tmp_path: Path) -> None:
        """Server errors are transient."""
        responses = iter([make_response(500), make_response(200, PDF_BYTES)])
        dl, _ = self.downloader({
            f"{PMC_CLOUD_HTTPS_BASE}/PMC1.1/PMC1.1.pdf": lambda: next(responses),
        })
        assert dl.download(cloud_source(xml=False), tmp_path / "a.pdf", tmp_path).success

    def test_non_pdf_rejected(self, tmp_path: Path) -> None:
        """Content without PDF magic (MD5 unknown) is not saved as a PDF."""
        dl, bucket = self.downloader({
            f"{PMC_CLOUD_HTTPS_BASE}/PMC1.1/PMC1.1.pdf": lambda: make_response(200, b"<html>x</html>"),
        })
        source = cloud_source(xml=False)
        source.metadata["pdf_md5"] = None
        result = dl.download(source, tmp_path / "a.pdf", tmp_path)
        assert result.success is False
        assert len(bucket.calls) == 1
        assert not (tmp_path / "a.pdf").exists()

    def test_xml_failure_keeps_pdf(self, tmp_path: Path) -> None:
        """Missing full text doesn't fail the PDF download."""
        dl, _ = self.downloader({
            f"{PMC_CLOUD_HTTPS_BASE}/PMC1.1/PMC1.1.pdf": lambda: make_response(200, PDF_BYTES),
        })
        result = dl.download(cloud_source(), tmp_path / "a.pdf", tmp_path / "ft")
        assert result.success is True
        assert result.full_text is None and result.full_text_path is None

    def test_existing_file_untouched_on_failure(self, tmp_path: Path) -> None:
        """A failed re-download never clobbers a previous good PDF."""
        target = tmp_path / "a.pdf"
        target.write_bytes(b"%PDF-old")
        dl, _ = self.downloader({})
        assert dl.download(cloud_source(xml=False), target, tmp_path).success is False
        assert target.read_bytes() == b"%PDF-old"


# --- integration with resolver / finder ------------------------------------


class TestPMCResolverCloud:
    """PMCResolver turns the preferred cloud version into a PMC_CLOUD source."""

    def test_resolve_by_pmcid(self) -> None:
        """The source carries HTTPS URL, MD5s and the XML URL."""
        resolver = PMCResolver()
        article = parse_version_metadata(metadata_json())
        with patch.object(resolver._cloud_client, "find_article", return_value=article):
            result = resolver.resolve(DocumentIdentifiers(pmcid="PMC5334499"))
        assert result.status == ResolutionStatus.SUCCESS
        source = result.sources[0]
        assert source.source_type == SourceType.PMC_CLOUD
        assert source.url.startswith("https://pmc-oa-opendata.s3.amazonaws.com/")
        assert source.metadata["pdf_md5"] == md5(PDF_BYTES)
        assert source.metadata["xml_url"].endswith("PMC5334499.1.xml")
        assert source.license == "CC BY-NC"

    def test_cloud_failure_falls_back_to_article_page(self) -> None:
        """A cloud outage falls through to the article-page scrape."""
        resolver = PMCResolver()
        with patch.object(resolver._cloud_client, "find_article",
                          side_effect=requests.ConnectionError("down")), \
                patch.object(resolver, "_get_pdf_url_from_article_page",
                             return_value="https://pmc.ncbi.nlm.nih.gov/articles/PMC1/pdf/x.pdf"):
            result = resolver.resolve(DocumentIdentifiers(pmcid="PMC1"))
        assert result.sources[0].source_type == SourceType.PMC


class TestFullTextFinderRouting:
    """FullTextFinder dispatch for PMC Cloud and NCBI FTP URLs."""

    def test_pmc_cloud_source_uses_cloud_downloader(self, tmp_path: Path) -> None:
        """PMC_CLOUD sources go to PMCCloudDownloader with the fulltext sibling dir."""
        finder = FullTextFinder()
        pdf_path = tmp_path / "pdf" / "2017" / "doc.pdf"
        with patch.object(finder._pmc_cloud_downloader, "download") as download:
            finder._download_from_source(cloud_source(), pdf_path, max_attempts=1)
        kwargs = download.call_args.kwargs
        assert kwargs["fulltext_output_dir"] == tmp_path / "fulltext" / "2017"

    def test_ncbi_ftp_url_downloaded_over_https(self, tmp_path: Path) -> None:
        """ftp://ftp.ncbi.nlm.nih.gov URLs never touch ftplib."""
        finder = FullTextFinder()
        source = PDFSource(url="ftp://ftp.ncbi.nlm.nih.gov/pub/x/paper.pdf",
                           source_type=SourceType.PMC, access_type=AccessType.OPEN)
        with patch.object(finder.session, "get",
                          return_value=make_response(200, PDF_BYTES)) as get, \
                patch("ftplib.FTP") as ftp:
            result = finder._download_from_source(source, tmp_path / "p.pdf", max_attempts=1)
        ftp.assert_not_called()
        assert get.call_args.args[0] == "https://ftp.ncbi.nlm.nih.gov/pub/x/paper.pdf"
        assert result.success is True
        assert result.source.url.startswith("https://")
