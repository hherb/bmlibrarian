"""Tests for the Europe PMC importer's ID parsing and duplicate matching (#444)."""

import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, List, Optional, Tuple

from bmlibrarian.importers.europe_pmc_importer import (
    ArticleMetadata,
    EuropePMCImporter,
    EuropePMCXMLParser,
)

ELIFE_ARTICLE = """
<article>
  <front>
    <article-meta>
      <article-id pub-id-type="pmcid">PMC111</article-id>
      <article-id pub-id-type="pmid">222</article-id>
      <article-id pub-id-type="doi">10.7554/eLife.12345</article-id>
      <title-group><article-title>Main title</article-title></title-group>
    </article-meta>
  </front>
  <body><p>Body text.</p></body>
  <sub-article>
    <front-stub>
      <article-id pub-id-type="doi">10.7554/eLife.12345.sa1</article-id>
    </front-stub>
  </sub-article>
</article>
"""


class FakeCursor:
    """Records queries and answers them from a queue of fetchone() results."""

    def __init__(self, results: List[Optional[Tuple[Any, ...]]], rowcount: int = 1) -> None:
        """Store the queued results and the rowcount reported for updates."""
        self.results = list(results)
        self.queries: List[Tuple[str, Tuple[Any, ...]]] = []
        self.rowcount = rowcount

    def execute(self, sql: str, params: Tuple[Any, ...]) -> None:
        """Record one query."""
        self.queries.append((sql, params))

    def fetchone(self) -> Optional[Tuple[Any, ...]]:
        """Return the next queued result."""
        return self.results.pop(0) if self.results else None


def _importer(tmp_path: Path) -> EuropePMCImporter:
    """Build an importer whose state file lives in a temp folder."""
    return EuropePMCImporter(packages_dir=tmp_path / "packages")


def test_sub_article_doi_does_not_replace_article_doi() -> None:
    """The article's own DOI wins over a decision-letter sub-article DOI."""
    meta = EuropePMCXMLParser()._parse_article(ET.fromstring(ELIFE_ARTICLE))
    assert meta is not None
    assert meta.pmcid == "PMC111"
    assert meta.pmid == "222"
    assert meta.doi == "10.7554/eLife.12345"


def test_doi_match_is_case_insensitive() -> None:
    """The DOI is compared with LOWER() on both sides (DOIs ignore case)."""
    cursor = FakeCursor([(42,)])
    article = ArticleMetadata(pmcid="PMC1", doi=" 10.1016/S0140-6736(20)30001-X ")
    assert EuropePMCImporter._find_cross_source_match(cursor, article, 9) == 42
    sql, params = cursor.queries[0]
    assert "LOWER(doi) = LOWER(%s)" in sql
    assert params == ("10.1016/S0140-6736(20)30001-X", 9)


def test_pmid_match_when_doi_misses() -> None:
    """No DOI match falls back to the PubMed record with the same PMID."""
    cursor = FakeCursor([None, (77,)])
    article = ArticleMetadata(pmcid="PMC1", doi="10.1/x", pmid="222")
    assert EuropePMCImporter._find_cross_source_match(cursor, article, 9) == 77
    sql, params = cursor.queries[1]
    assert "external_id = %s" in sql and "pubmed" in sql
    assert params == ("222",)


def test_no_match_without_ids() -> None:
    """Without a DOI or a numeric PMID nothing is queried."""
    cursor = FakeCursor([])
    article = ArticleMetadata(pmcid="PMC1", pmid="not-a-pmid")
    assert EuropePMCImporter._find_cross_source_match(cursor, article, 9) is None
    assert cursor.queries == []


def test_upsert_attaches_full_text_to_pubmed_record(tmp_path: Path) -> None:
    """A DOI-less article with a PubMed twin updates it instead of inserting."""
    importer = _importer(tmp_path)
    # Not in Europe PMC yet, no DOI, PMID matches document 77.
    cursor = FakeCursor([None, (77,)])
    article = ArticleMetadata(pmcid="PMC1", pmid="222", full_text="# Full text")
    assert importer._upsert_article(cursor, article, 9) == "updated"
    assert not any("INSERT" in sql for sql, _ in cursor.queries)
    assert cursor.queries[-1][1] == ("# Full text", 77)


def test_upsert_reports_skipped_when_twin_already_has_full_text(tmp_path: Path) -> None:
    """The guarded UPDATE changing no row is reported as skipped."""
    importer = _importer(tmp_path)
    cursor = FakeCursor([None, (77,)], rowcount=0)
    article = ArticleMetadata(pmcid="PMC1", pmid="222", full_text="# Full text")
    assert importer._upsert_article(cursor, article, 9) == "skipped"


def test_upsert_inserts_when_no_twin(tmp_path: Path) -> None:
    """With no match anywhere the article is inserted."""
    importer = _importer(tmp_path)
    cursor = FakeCursor([None, None, None])
    article = ArticleMetadata(pmcid="PMC1", pmid="222", doi="10.1/x")
    assert importer._upsert_article(cursor, article, 9) == "inserted"
    assert "INSERT INTO document" in cursor.queries[-1][0]


def test_ids_fall_back_to_whole_article_without_front_matter() -> None:
    """An article with no front-matter IDs still gets its PMCID."""
    article = ET.fromstring(
        '<article><article-id pub-id-type="pmcid">PMC9</article-id></article>'
    )
    ids = EuropePMCXMLParser._front_article_ids(article)
    assert [e.text for e in ids] == ["PMC9"]


def test_upsert_skips_twin_when_updates_disabled(tmp_path: Path) -> None:
    """With updates disabled a matched twin is left alone and nothing is written."""
    importer = _importer(tmp_path)
    importer.update_existing = False
    cursor = FakeCursor([None, (77,)])
    article = ArticleMetadata(pmcid="PMC1", pmid="222", full_text="# Full text")
    assert importer._upsert_article(cursor, article, 9) == "skipped"
    assert not any("UPDATE" in sql or "INSERT" in sql for sql, _ in cursor.queries)
