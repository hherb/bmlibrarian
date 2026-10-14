"""
Unit tests for PubMedBulkImporter._parse_article field extraction.

Each test pins one defect found while porting the parser to Rust (Phase 0 of
doc/planning/rust/implementation_plan.md): elements were searched under the
wrong parent, so author keywords and retraction cross-references were never
read, and the DOI lookup could return a cited reference's DOI. The record below
follows the PubMed DTD layout (KeywordList and CommentsCorrectionsList are
children of MedlineCitation; ReferenceList lives in PubmedData).
"""

import xml.etree.ElementTree as ET
from typing import Optional
from unittest.mock import MagicMock, patch

import pytest

from src.bmlibrarian.importers.pubmed_bulk_importer import PubMedBulkImporter


def make_record(
    own_doi: Optional[str] = "10.1000/own",
    reference_doi: str = "10.1000/cited",
    keywords: tuple = ("Aspirin", "Myocardial infarction"),
    comments_corrections: str = "",
    date_revised: Optional[tuple] = ("2024", "03", "15"),
) -> ET.Element:
    """Build one PubmedArticle element in the PubMed DTD layout."""
    own_ids = '<ArticleId IdType="pubmed">12345</ArticleId>'
    if own_doi:
        own_ids += f'<ArticleId IdType="doi">{own_doi}</ArticleId>'
    keyword_xml = ""
    if keywords:
        keyword_xml = ('<KeywordList Owner="NOTNLM">'
                       + "".join(f'<Keyword MajorTopicYN="N">{k}</Keyword>' for k in keywords)
                       + "</KeywordList>")
    revised_xml = ""
    if date_revised:
        y, m, d = date_revised
        revised_xml = f"<DateRevised><Year>{y}</Year><Month>{m}</Month><Day>{d}</Day></DateRevised>"
    xml = f"""
    <PubmedArticle>
      <MedlineCitation Status="MEDLINE" Owner="NLM">
        <PMID Version="1">12345</PMID>
        {revised_xml}
        <Article PubModel="Print">
          <Journal><JournalIssue><PubDate><Year>2020</Year><Month>Mar</Month></PubDate></JournalIssue>
            <Title>Journal of Tests</Title></Journal>
          <ArticleTitle>Aspirin and the heart</ArticleTitle>
          <Abstract><AbstractText>Aspirin lowers risk.</AbstractText></Abstract>
          <AuthorList><Author><LastName>Smith</LastName><ForeName>Jane</ForeName></Author></AuthorList>
          <PublicationTypeList><PublicationType>Journal Article</PublicationType></PublicationTypeList>
        </Article>
        {comments_corrections}
        {keyword_xml}
      </MedlineCitation>
      <PubmedData>
        <ArticleIdList>{own_ids}</ArticleIdList>
        <ReferenceList><Reference><Citation>Cited work.</Citation>
          <ArticleIdList><ArticleId IdType="doi">{reference_doi}</ArticleId></ArticleIdList>
        </Reference></ReferenceList>
      </PubmedData>
    </PubmedArticle>"""
    return ET.fromstring(xml)


@pytest.fixture
def importer(tmp_path) -> PubMedBulkImporter:
    """PubMedBulkImporter with the database lookup mocked out."""
    with patch("src.bmlibrarian.importers.pubmed_bulk_importer.get_db_manager") as mock_db:
        mock_db.return_value = MagicMock()
        cursor = mock_db.return_value.get_connection.return_value.__enter__.return_value.cursor
        cursor.return_value.__enter__.return_value.fetchone.return_value = [1]
        return PubMedBulkImporter(data_dir=str(tmp_path), use_tracking=False)


class TestKeywords:
    """Author keywords live in MedlineCitation/KeywordList."""

    def test_keywords_are_extracted_from_medline_citation(self, importer) -> None:
        article = importer._parse_article(make_record())
        assert article["keywords"] == ["Aspirin", "Myocardial infarction"]

    def test_no_keyword_list_gives_empty_list(self, importer) -> None:
        article = importer._parse_article(make_record(keywords=()))
        assert article["keywords"] == []


class TestDoi:
    """The DOI must be the article's own, never a cited reference's."""

    def test_own_doi_is_used(self, importer) -> None:
        article = importer._parse_article(make_record(own_doi="10.1000/own"))
        assert article["doi"] == "10.1000/own"

    def test_reference_doi_is_not_used_when_article_has_none(self, importer) -> None:
        article = importer._parse_article(make_record(own_doi=None, reference_doi="10.1000/cited"))
        assert article["doi"] is None


class TestRetraction:
    """Retraction cross-references live in MedlineCitation/CommentsCorrectionsList."""

    RETRACTION_IN = ('<CommentsCorrectionsList><CommentsCorrections RefType="RetractionIn">'
                     "<RefSource>J Tests. 2021</RefSource><PMID Version=\"1\">99999</PMID>"
                     "</CommentsCorrections></CommentsCorrectionsList>")
    ERRATUM_IN = ('<CommentsCorrectionsList><CommentsCorrections RefType="ErratumIn">'
                  "<RefSource>J Tests. 2021</RefSource></CommentsCorrections></CommentsCorrectionsList>")

    def test_retraction_in_marks_article_retracted(self, importer) -> None:
        article = importer._parse_article(make_record(comments_corrections=self.RETRACTION_IN))
        assert article["transparency_metadata"]["is_retracted"] is True

    def test_erratum_does_not_mark_article_retracted(self, importer) -> None:
        article = importer._parse_article(make_record(comments_corrections=self.ERRATUM_IN))
        assert article["transparency_metadata"]["is_retracted"] is False


class TestDateRevised:
    """DateRevised orders revisions of the same PMID (newest wins on merge)."""

    def test_date_revised_is_extracted(self, importer) -> None:
        article = importer._parse_article(make_record(date_revised=("2024", "03", "15")))
        assert article["date_revised"] == "2024-03-15"

    def test_missing_date_revised_is_none(self, importer) -> None:
        article = importer._parse_article(make_record(date_revised=None))
        assert article["date_revised"] is None


class TestDeleteCitation:
    """Update files list withdrawn PMIDs in DeleteCitation; they are collected, never stored as articles."""

    def test_deleted_pmids_are_extracted(self) -> None:
        from src.bmlibrarian.importers.pubmed_bulk_importer import parse_deleted_pmids
        elem = ET.fromstring('<DeleteCitation><PMID Version="1">111</PMID>'
                             '<PMID Version="1"> 222 </PMID></DeleteCitation>')
        assert parse_deleted_pmids(elem) == ["111", "222"]

    def test_invalid_pmids_are_dropped(self) -> None:
        from src.bmlibrarian.importers.pubmed_bulk_importer import parse_deleted_pmids
        elem = ET.fromstring("<DeleteCitation><PMID>12a</PMID><PMID></PMID><PMID>7</PMID></DeleteCitation>")
        assert parse_deleted_pmids(elem) == ["7"]

    def test_import_file_passes_deletions_to_store(self, importer, tmp_path) -> None:
        import gzip
        path = tmp_path / "pubmed26n9999.xml.gz"
        record = ET.tostring(make_record()).decode()
        with gzip.open(path, "wt", encoding="utf-8") as fh:
            fh.write("<PubmedArticleSet>" + record +
                     '<DeleteCitation><PMID Version="1">777</PMID></DeleteCitation></PubmedArticleSet>')
        captured = {}

        def fake_store(articles, filename, sha256, started, withdrawn_pmids=()):
            captured["pmids"] = [a["pmid"] for a in articles]
            captured["withdrawn"] = list(withdrawn_pmids)
            return len(articles)

        importer._is_file_committed = lambda name: False
        importer._store_file = fake_store
        stats = importer.import_file(path)
        assert captured == {"pmids": ["12345"], "withdrawn": ["777"]}
        assert stats["articles_withdrawn"] == 1
