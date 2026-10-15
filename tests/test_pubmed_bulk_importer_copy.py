"""
Tests for the COPY-based, revision-aware, resumable PubMed bulk write path.

Unit tests cover the pure staging-row conversion. Integration tests are opt-in
(BMLIBRARIAN_TEST_DB_ENV = env file of a *development* database with the
BMLibrarian schema, e.g. ~/.bmlibrarian/.env_pg18_dev) and refuse the
production database. They write gzip'd PubMed files to a temp directory, import
them, and delete their own rows afterwards.
"""

import gzip
import os
from pathlib import Path
from typing import Iterator, List, Optional

import pytest
from dotenv import dotenv_values

from src.bmlibrarian.db_test_guard import is_protected_database
from src.bmlibrarian.importers import pubmed_bulk_importer as pbi

TEST_DB_ENV_VARIABLE = "BMLIBRARIAN_TEST_DB_ENV"
TEST_PMIDS = ("990000001", "990000002")


def record_xml(pmid: str, title: str, date_revised: Optional[str], keywords: tuple = ("Aspirin",)) -> str:
    """One PubmedArticle in the PubMed DTD layout."""
    revised = ""
    if date_revised:
        y, m, d = date_revised.split("-")
        revised = f"<DateRevised><Year>{y}</Year><Month>{m}</Month><Day>{d}</Day></DateRevised>"
    kw = "".join(f"<Keyword>{k}</Keyword>" for k in keywords)
    return f"""<PubmedArticle><MedlineCitation><PMID Version="1">{pmid}</PMID>{revised}
      <Article><Journal><JournalIssue><PubDate><Year>2020</Year><Month>Mar</Month></PubDate></JournalIssue>
      <Title>J Tests</Title></Journal><ArticleTitle>{title}</ArticleTitle>
      <Abstract><AbstractText>Abstract of {pmid}.</AbstractText></Abstract>
      <PublicationTypeList><PublicationType>Journal Article</PublicationType></PublicationTypeList>
      </Article><KeywordList>{kw}</KeywordList></MedlineCitation>
      <PubmedData><ArticleIdList><ArticleId IdType="pubmed">{pmid}</ArticleId>
      <ArticleId IdType="doi">10.9999/{pmid}</ArticleId></ArticleIdList></PubmedData></PubmedArticle>"""


def write_file(directory: Path, name: str, records: List[str], deleted: tuple = ()) -> Path:
    """Write a gzip'd PubmedArticleSet file, optionally with a DeleteCitation block."""
    path = directory / name
    delete = ""
    if deleted:
        delete = "<DeleteCitation>" + "".join(f'<PMID Version="1">{p}</PMID>' for p in deleted) + "</DeleteCitation>"
    with gzip.open(path, "wt", encoding="utf-8") as fh:
        fh.write("<?xml version='1.0'?><PubmedArticleSet>" + "".join(records) + delete + "</PubmedArticleSet>")
    return path


# --------------------------------------------------------------------------- unit


class TestStagingRows:
    """Conversion of parsed articles into COPY rows."""

    def article(self, **overrides) -> dict:
        base = {"pmid": "1", "doi": "", "title": "T", "abstract": "", "authors": ["A B"],
                "publication": "", "publication_date": "2020-03-01", "url": "u", "mesh_terms": [],
                "keywords": ["k"], "date_revised": "2024-01-02",
                "transparency_metadata": {"is_retracted": False}}
        base.update(overrides)
        return base

    def test_empty_strings_become_null(self) -> None:
        docs, _ = pbi.to_staging_rows([self.article()])
        row = dict(zip(pbi.STAGE_DOCUMENT_COLUMNS, docs[0]))
        assert row["doi"] is None and row["abstract"] is None and row["publication"] is None

    def test_invalid_publication_date_becomes_null(self) -> None:
        docs, _ = pbi.to_staging_rows([self.article(publication_date="2020-Sum-01")])
        assert dict(zip(pbi.STAGE_DOCUMENT_COLUMNS, docs[0]))["publication_date"] is None

    def test_date_revised_is_carried(self) -> None:
        docs, _ = pbi.to_staging_rows([self.article()])
        assert dict(zip(pbi.STAGE_DOCUMENT_COLUMNS, docs[0]))["date_revised"] == "2024-01-02"

    def test_metadata_row_only_when_meaningful(self) -> None:
        _, metas = pbi.to_staging_rows([self.article()])
        assert metas == []
        _, metas = pbi.to_staging_rows([self.article(transparency_metadata={
            "is_retracted": False, "publication_types": ["Journal Article"]})])
        assert len(metas) == 1


# --------------------------------------------------------------------------- integration


@pytest.fixture
def dev_importer(tmp_path: Path, monkeypatch) -> Iterator[pbi.PubMedBulkImporter]:
    """Importer bound to the opt-in development database; cleans up its rows."""
    env_file = os.environ.get(TEST_DB_ENV_VARIABLE)
    if not env_file:
        pytest.skip(f"{TEST_DB_ENV_VARIABLE} not set")
    cfg = dotenv_values(Path(env_file).expanduser())
    if is_protected_database(cfg.get("POSTGRES_DB")):
        pytest.fail(f"refusing to run against {cfg.get('POSTGRES_DB')!r}")
    for key in ("POSTGRES_HOST", "POSTGRES_PORT", "POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD"):
        monkeypatch.setenv(key, cfg[key])
    from src.bmlibrarian.database import DatabaseManager

    db = DatabaseManager(auto_migrate=True)
    with db.get_connection() as conn:
        assert conn.execute("SELECT current_database()").fetchone()[0] == cfg["POSTGRES_DB"]
        # Scalar subquery: an aggregate in the outer SELECT would always yield a row.
        conn.execute("INSERT INTO sources (id, name) SELECT (SELECT coalesce(max(id), 0) + 1 FROM sources), "
                     "'pubmed' WHERE NOT EXISTS (SELECT 1 FROM sources WHERE lower(name) LIKE '%pubmed%')")
    importer = pbi.PubMedBulkImporter(data_dir=str(tmp_path / "data"), use_tracking=False, db_manager=db)

    def cleanup() -> None:
        with db.get_connection() as conn:
            conn.execute("DELETE FROM transparency.document_metadata WHERE document_id IN "
                         "(SELECT id FROM document WHERE external_id = ANY(%s))", (list(TEST_PMIDS),))
            conn.execute("DELETE FROM document WHERE external_id = ANY(%s)", (list(TEST_PMIDS),))
            conn.execute("DELETE FROM ingest.ledger WHERE file LIKE 'pbi-test-%%'")
            conn.execute("DELETE FROM ingest.withdrawn_pmid WHERE pmid = ANY(%s)", (list(TEST_PMIDS),))

    cleanup()
    yield importer
    cleanup()


def fetch(importer: pbi.PubMedBulkImporter, pmid: str) -> Optional[tuple]:
    """(title, keywords, date_revised::text) of a PMID, or None."""
    with importer.db_manager.get_connection() as conn:
        return conn.execute("SELECT title, keywords, date_revised::text FROM document WHERE external_id = %s",
                            (pmid,)).fetchone()


def ledger_files(importer: pbi.PubMedBulkImporter) -> List[str]:
    """Test files recorded in the ledger."""
    with importer.db_manager.get_connection() as conn:
        return [r[0] for r in conn.execute(
            "SELECT file FROM ingest.ledger WHERE file LIKE 'pbi-test-%%' ORDER BY file").fetchall()]


def test_file_is_stored_with_its_ledger_row(dev_importer, tmp_path) -> None:
    f = write_file(tmp_path, "pbi-test-0001.xml.gz",
                   [record_xml(TEST_PMIDS[0], "First", "2024-01-01", ("Aspirin", "Heart"))])
    stats = dev_importer.import_file(f)
    assert stats["articles_imported"] == 1
    assert fetch(dev_importer, TEST_PMIDS[0]) == ("First", ["Aspirin", "Heart"], "2024-01-01")
    assert ledger_files(dev_importer) == ["pbi-test-0001.xml.gz"]


def test_reimporting_a_file_is_idempotent(dev_importer, tmp_path) -> None:
    f = write_file(tmp_path, "pbi-test-0001.xml.gz", [record_xml(TEST_PMIDS[0], "First", "2024-01-01")])
    dev_importer.import_file(f)
    dev_importer.import_file(f, force=True)
    with dev_importer.db_manager.get_connection() as conn:
        n = conn.execute("SELECT count(*) FROM document WHERE external_id = %s", (TEST_PMIDS[0],)).fetchone()[0]
    assert n == 1


def test_newer_revision_wins_regardless_of_order(dev_importer, tmp_path) -> None:
    newer = write_file(tmp_path, "pbi-test-0002.xml.gz", [record_xml(TEST_PMIDS[0], "Newer", "2025-06-01")])
    older = write_file(tmp_path, "pbi-test-0003.xml.gz", [record_xml(TEST_PMIDS[0], "Older", "2023-01-01")])
    dev_importer.import_file(newer)
    dev_importer.import_file(older)
    assert fetch(dev_importer, TEST_PMIDS[0])[0] == "Newer"


def test_newest_revision_wins_within_one_file(dev_importer, tmp_path) -> None:
    f = write_file(tmp_path, "pbi-test-0004.xml.gz", [
        record_xml(TEST_PMIDS[1], "Newest", "2025-06-01"),
        record_xml(TEST_PMIDS[1], "Stale", "2020-01-01"),
    ])
    dev_importer.import_file(f)
    assert fetch(dev_importer, TEST_PMIDS[1])[0] == "Newest"


def test_committed_file_is_skipped_on_resume(dev_importer, tmp_path) -> None:
    f = write_file(tmp_path, "pbi-test-0005.xml.gz", [record_xml(TEST_PMIDS[0], "First", "2024-01-01")])
    dev_importer.import_file(f)
    stats = dev_importer.import_file(f)
    assert stats.get("skipped") is True and stats["articles_imported"] == 0


def test_failure_mid_store_leaves_nothing_and_resume_retries(dev_importer, tmp_path, monkeypatch) -> None:
    """Atomicity: a failure after the document merge rolls back rows and ledger row."""
    f = write_file(tmp_path, "pbi-test-0006.xml.gz", [record_xml(TEST_PMIDS[0], "First", "2024-01-01")])
    monkeypatch.setattr(pbi, "MERGE_METADATA_SQL", "SELECT 1/0")
    stats = dev_importer.import_file(f)
    assert stats["errors"] == 1
    assert fetch(dev_importer, TEST_PMIDS[0]) is None
    assert ledger_files(dev_importer) == []
    monkeypatch.undo()
    stats = dev_importer.import_file(f)
    assert stats["articles_imported"] == 1 and ledger_files(dev_importer) == ["pbi-test-0006.xml.gz"]


def test_parallel_workers_store_all_files_and_newest_revision_wins(dev_importer, tmp_path) -> None:
    """Two worker processes; the same PMID in two files must still resolve to the newest revision."""
    baseline = dev_importer.baseline_dir
    write_file(baseline, "pbi-test-0101.xml.gz", [record_xml(TEST_PMIDS[0], "Newest", "2025-06-01")])
    write_file(baseline, "pbi-test-0102.xml.gz", [record_xml(TEST_PMIDS[1], "Other", "2024-01-01")])
    write_file(baseline, "pbi-test-0103.xml.gz", [record_xml(TEST_PMIDS[0], "Stale", "2020-01-01")])
    stats = dev_importer.import_all_files(file_type="baseline", workers=2)
    assert stats["files_processed"] == 3
    assert ledger_files(dev_importer) == ["pbi-test-0101.xml.gz", "pbi-test-0102.xml.gz", "pbi-test-0103.xml.gz"]
    assert fetch(dev_importer, TEST_PMIDS[0])[0] == "Newest"
    assert fetch(dev_importer, TEST_PMIDS[1])[0] == "Other"


def withdrawn(importer: pbi.PubMedBulkImporter, pmid: str) -> Optional[bool]:
    """Whether the PMID's document is marked withdrawn (None if absent)."""
    with importer.db_manager.get_connection() as conn:
        row = conn.execute("SELECT withdrawn_date IS NOT NULL FROM document WHERE external_id = %s",
                           (pmid,)).fetchone()
    return row[0] if row else None


def withdrawn_mark(importer: pbi.PubMedBulkImporter, pmid: str) -> Optional[tuple]:
    """(withdrawn_date::text, withdrawn_reason) of a PMID's document, or None."""
    with importer.db_manager.get_connection() as conn:
        return conn.execute("SELECT withdrawn_date::text, withdrawn_reason FROM document WHERE external_id = %s",
                            (pmid,)).fetchone()


def test_deletion_after_insert_marks_document_withdrawn(dev_importer, tmp_path) -> None:
    """A deletion in a later file marks the existing document, and only that one."""
    dev_importer.import_file(write_file(tmp_path, "pbi-test-0201.xml.gz",
                                        [record_xml(TEST_PMIDS[0], "First", "2024-01-01"),
                                         record_xml(TEST_PMIDS[1], "Other", "2024-01-01")]))
    stats = dev_importer.import_file(write_file(tmp_path, "pbi-test-0202.xml.gz", [], deleted=(TEST_PMIDS[0],)))
    assert stats["withdrawals_listed"] == 1 and stats["documents_withdrawn"] == 1
    assert withdrawn(dev_importer, TEST_PMIDS[0]) is True
    assert withdrawn_mark(dev_importer, TEST_PMIDS[0])[1] == pbi.WITHDRAWN_REASON
    assert withdrawn(dev_importer, TEST_PMIDS[1]) is False
    assert ledger_files(dev_importer) == ["pbi-test-0201.xml.gz", "pbi-test-0202.xml.gz"]


def test_deletion_before_insert_still_marks_document(dev_importer, tmp_path) -> None:
    """Files may be imported in any order: a deletion seen first applies when the record arrives."""
    dev_importer.import_file(write_file(tmp_path, "pbi-test-0203.xml.gz", [], deleted=(TEST_PMIDS[0],)))
    dev_importer.import_file(write_file(tmp_path, "pbi-test-0204.xml.gz",
                                        [record_xml(TEST_PMIDS[0], "Late", "2024-01-01")]))
    assert withdrawn(dev_importer, TEST_PMIDS[0]) is True


def test_later_revision_does_not_clear_withdrawal(dev_importer, tmp_path) -> None:
    """Withdrawals are permanent: a newer revision of the record keeps the mark."""
    dev_importer.import_file(write_file(tmp_path, "pbi-test-0205.xml.gz",
                                        [record_xml(TEST_PMIDS[0], "First", "2024-01-01")], deleted=(TEST_PMIDS[0],)))
    dev_importer.import_file(write_file(tmp_path, "pbi-test-0206.xml.gz",
                                        [record_xml(TEST_PMIDS[0], "Revised", "2025-01-01")]))
    assert fetch(dev_importer, TEST_PMIDS[0])[0] == "Revised"
    assert withdrawn(dev_importer, TEST_PMIDS[0]) is True


def test_backfill_applies_deletions_of_already_imported_files(dev_importer, tmp_path) -> None:
    """The backfill marks documents and is idempotent (second run changes nothing)."""
    updates = dev_importer.update_dir
    dev_importer.import_file(write_file(tmp_path, "pbi-test-0207.xml.gz",
                                        [record_xml(TEST_PMIDS[0], "First", "2024-01-01")]))
    write_file(updates, "pbi-test-0208.xml.gz", [], deleted=(TEST_PMIDS[0],))
    result = dev_importer.backfill_withdrawals(file_type="update")
    assert result["files_scanned"] == 1 and result["pmids_recorded"] == 1 and result["documents_marked"] == 1
    assert result["files_failed"] == []
    first_mark = withdrawn_mark(dev_importer, TEST_PMIDS[0])
    assert first_mark[1] == pbi.WITHDRAWN_REASON
    again = dev_importer.backfill_withdrawals(file_type="update")  # idempotent
    assert again["pmids_recorded"] == 0 and again["documents_marked"] == 0
    assert withdrawn_mark(dev_importer, TEST_PMIDS[0]) == first_mark


def test_reconcile_marks_withdrawals_missed_by_concurrent_files(dev_importer: pbi.PubMedBulkImporter,
                                                                 tmp_path: Path) -> None:
    """A record and its deletion stored concurrently miss each other; the final pass marks it."""
    dev_importer.import_file(write_file(tmp_path, "pbi-test-0210.xml.gz",
                                        [record_xml(TEST_PMIDS[0], "First", "2024-01-01")]))
    with dev_importer.db_manager.get_connection() as conn:  # the concurrent file's committed deletion
        conn.execute("INSERT INTO ingest.withdrawn_pmid (pmid, file) VALUES (%s, 'pbi-test-0211.xml.gz')",
                     (TEST_PMIDS[0],))
    assert withdrawn(dev_importer, TEST_PMIDS[0]) is False
    assert dev_importer._reconcile_withdrawals() == 1
    assert withdrawn(dev_importer, TEST_PMIDS[0]) is True
    assert dev_importer._reconcile_withdrawals() == 0


def test_import_all_files_runs_final_withdrawal_pass(dev_importer: pbi.PubMedBulkImporter, tmp_path: Path) -> None:
    """Parallel import of a record and its deletion ends with the document marked."""
    write_file(dev_importer.update_dir, "pbi-test-0212.xml.gz", [record_xml(TEST_PMIDS[0], "First", "2024-01-01")])
    write_file(dev_importer.update_dir, "pbi-test-0213.xml.gz", [], deleted=(TEST_PMIDS[0],))
    stats = dev_importer.import_all_files(file_type="update", workers=2)
    assert withdrawn(dev_importer, TEST_PMIDS[0]) is True
    assert stats["total_documents_withdrawn"] == 1


def test_searches_exclude_withdrawn_documents(dev_importer, tmp_path) -> None:
    """find_abstract_ids must not return withdrawn records (checked on the dev database only)."""
    from src.bmlibrarian import database
    word = "zqxwithdrawntestword"
    rec = record_xml(TEST_PMIDS[0], f"Title {word}", "2024-01-01").replace("Abstract of", f"{word} abstract of")
    rec2 = record_xml(TEST_PMIDS[1], f"Title {word}", "2024-01-01")
    dev_importer.import_file(write_file(tmp_path, "pbi-test-0209.xml.gz", [rec, rec2], deleted=(TEST_PMIDS[0],)))
    database.close_database()
    try:
        db = database.get_db_manager()
        with db.get_connection() as conn:
            assert not is_protected_database(conn.execute("SELECT current_database()").fetchone()[0])
            ids = {r[0] for r in conn.execute("SELECT id, external_id FROM document WHERE external_id = ANY(%s)",
                                              (list(TEST_PMIDS),)).fetchall()}
        found = set(database.find_abstract_ids(word, max_rows=10))
        found_docs = {d["external_id"] for d in database.find_abstracts(word, max_rows=10)}
    finally:
        database.close_database()
    assert len(found & ids) == 1
    assert found_docs == {TEST_PMIDS[1]}
