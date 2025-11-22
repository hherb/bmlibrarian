"""
Importer Test Laboratory for BMLibrarian.

This module provides a PySide6-based GUI for testing and validating
importer functionality without affecting the production database.

Features:
- Fetch articles from medRxiv/PubMed without storing in database
- View raw and formatted abstracts side-by-side
- Export test results to JSON or SQLite for visual verification
- Test abstract formatting transformations
"""

import json
import logging
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any

from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QTextBrowser,
    QSpinBox,
    QComboBox,
    QGroupBox,
    QSplitter,
    QTabWidget,
    QFileDialog,
    QMessageBox,
    QProgressBar,
    QListWidget,
    QListWidgetItem,
)
from PySide6.QtCore import Qt, Signal, QThread

logger = logging.getLogger(__name__)


# =============================================================================
# Worker Thread for Fetching
# =============================================================================


class FetchWorker(QThread):
    """Worker thread for fetching articles without database storage."""

    progress = Signal(str)
    article_fetched = Signal(dict)  # Emits each article as it's fetched
    finished = Signal(bool, str, list)  # success, message, all_articles

    def __init__(
        self,
        source: str,
        days: int = 7,
        query: str = "",
        max_results: int = 100,
        parent: Optional[QWidget] = None,
    ):
        """
        Initialize fetch worker.

        Args:
            source: 'medrxiv' or 'pubmed'
            days: Number of days to fetch (medRxiv)
            query: Search query (PubMed)
            max_results: Maximum results to fetch
            parent: Parent widget
        """
        super().__init__(parent)
        self.source = source
        self.days = days
        self.query = query
        self.max_results = max_results
        self._cancelled = False
        self._articles: List[Dict[str, Any]] = []

    def cancel(self) -> None:
        """Cancel the fetch operation."""
        self._cancelled = True

    def run(self) -> None:
        """Execute the fetch operation."""
        try:
            if self.source == "medrxiv":
                self._fetch_medrxiv()
            elif self.source == "pubmed":
                self._fetch_pubmed()
            else:
                self.finished.emit(False, f"Unknown source: {self.source}", [])
                return

            if self._cancelled:
                self.finished.emit(False, "Fetch cancelled", self._articles)
            else:
                self.finished.emit(
                    True,
                    f"Fetched {len(self._articles)} articles",
                    self._articles,
                )
        except Exception as e:
            logger.error(f"Fetch failed: {e}", exc_info=True)
            self.finished.emit(False, f"Fetch failed: {e}", self._articles)

    def _fetch_medrxiv(self) -> None:
        """Fetch articles from medRxiv API."""
        import requests

        self.progress.emit("Connecting to medRxiv API...")

        # Calculate date range
        end_date = datetime.now()
        start_date = end_date - timedelta(days=self.days)

        # Create a temporary importer instance just for formatting
        from bmlibrarian.importers.medrxiv_importer import MedRxivImporter

        # Use __new__ to avoid database connection in __init__
        temp_importer = MedRxivImporter.__new__(MedRxivImporter)

        # Fetch from API
        base_url = "https://api.medrxiv.org/details/medrxiv"
        url = f"{base_url}/{start_date.strftime('%Y-%m-%d')}/{end_date.strftime('%Y-%m-%d')}/0"

        self.progress.emit(f"Fetching from {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}...")

        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            data = response.json()
        except Exception as e:
            self.progress.emit(f"API error: {e}")
            return

        papers = data.get("collection", [])
        total = min(len(papers), self.max_results)
        self.progress.emit(f"Found {len(papers)} papers, processing {total}...")

        for i, paper in enumerate(papers[:total]):
            if self._cancelled:
                break

            # Store both raw and formatted abstract
            raw_abstract = paper.get("abstract", "")
            formatted_abstract = temp_importer._format_abstract_markdown(raw_abstract)

            article = {
                "source": "medrxiv",
                "doi": paper.get("doi", ""),
                "title": paper.get("title", ""),
                "authors": paper.get("authors", ""),
                "date": paper.get("date", ""),
                "category": paper.get("category", ""),
                "abstract_raw": raw_abstract,
                "abstract_formatted": formatted_abstract,
                "pdf_url": f"https://www.medrxiv.org/content/{paper.get('doi', '')}.full.pdf",
            }

            self._articles.append(article)
            self.article_fetched.emit(article)

            if (i + 1) % 10 == 0:
                self.progress.emit(f"Processed {i + 1}/{total} articles...")

    def _fetch_pubmed(self) -> None:
        """Fetch articles from PubMed API."""
        import requests
        import xml.etree.ElementTree as ET

        self.progress.emit(f"Searching PubMed for: {self.query}...")

        # Search for PMIDs
        search_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
        search_params = {
            "db": "pubmed",
            "term": self.query,
            "retmax": self.max_results,
            "retmode": "json",
        }

        try:
            response = requests.get(search_url, params=search_params, timeout=30)
            response.raise_for_status()
            data = response.json()
            pmids = data.get("esearchresult", {}).get("idlist", [])
        except Exception as e:
            self.progress.emit(f"Search error: {e}")
            return

        if not pmids:
            self.progress.emit("No articles found")
            return

        self.progress.emit(f"Found {len(pmids)} articles, fetching details...")

        # Fetch article details
        fetch_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
        fetch_params = {
            "db": "pubmed",
            "id": ",".join(pmids),
            "rettype": "xml",
            "retmode": "xml",
        }

        try:
            response = requests.get(fetch_url, params=fetch_params, timeout=60)
            response.raise_for_status()
            root = ET.fromstring(response.content)
        except Exception as e:
            self.progress.emit(f"Fetch error: {e}")
            return

        # Parse articles
        from bmlibrarian.importers.pubmed_importer import PubMedImporter

        temp_importer = PubMedImporter.__new__(PubMedImporter)

        for i, article_elem in enumerate(root.findall(".//PubmedArticle")):
            if self._cancelled:
                break

            try:
                # Extract basic info
                medline = article_elem.find(".//MedlineCitation")
                if medline is None:
                    continue

                pmid_elem = medline.find(".//PMID")
                pmid = pmid_elem.text if pmid_elem is not None else ""

                article_node = medline.find(".//Article")
                if article_node is None:
                    continue

                title_elem = article_node.find(".//ArticleTitle")
                title = title_elem.text if title_elem is not None else ""

                # Get abstract
                abstract_elem = article_node.find(".//Abstract")
                abstract_raw = ""
                if abstract_elem is not None:
                    abstract_parts = []
                    for text_elem in abstract_elem.findall(".//AbstractText"):
                        label = text_elem.get("Label", "")
                        text = "".join(text_elem.itertext())
                        if label:
                            abstract_parts.append(f"{label}: {text}")
                        else:
                            abstract_parts.append(text)
                    abstract_raw = " ".join(abstract_parts)

                # Get authors
                authors = []
                for author in article_node.findall(".//Author"):
                    lastname = author.find(".//LastName")
                    forename = author.find(".//ForeName")
                    if lastname is not None and forename is not None:
                        authors.append(f"{lastname.text} {forename.text}")
                    elif lastname is not None:
                        authors.append(lastname.text)

                # Get date
                pub_date = article_node.find(".//PubDate")
                date_str = ""
                if pub_date is not None:
                    year = pub_date.find(".//Year")
                    month = pub_date.find(".//Month")
                    day = pub_date.find(".//Day")
                    parts = []
                    if year is not None:
                        parts.append(year.text)
                    if month is not None:
                        parts.append(month.text)
                    if day is not None:
                        parts.append(day.text)
                    date_str = "-".join(parts)

                # Get journal
                journal_elem = article_node.find(".//Journal/Title")
                journal = journal_elem.text if journal_elem is not None else ""

                article = {
                    "source": "pubmed",
                    "pmid": pmid,
                    "title": title,
                    "authors": ", ".join(authors),
                    "date": date_str,
                    "journal": journal,
                    "abstract_raw": abstract_raw,
                    "abstract_formatted": abstract_raw,  # PubMed already structured
                }

                self._articles.append(article)
                self.article_fetched.emit(article)

            except Exception as e:
                logger.warning(f"Error parsing article: {e}")
                continue

            if (i + 1) % 10 == 0:
                self.progress.emit(f"Processed {i + 1}/{len(pmids)} articles...")


# =============================================================================
# Main Window
# =============================================================================


class ImporterTestLab(QMainWindow):
    """Main window for importer testing laboratory."""

    def __init__(self):
        """Initialize the importer test lab."""
        super().__init__()

        self._worker: Optional[FetchWorker] = None
        self._articles: List[Dict[str, Any]] = []

        self._setup_ui()
        self.setWindowTitle("BMLibrarian Importer Test Lab")
        self.resize(1200, 800)

    def _setup_ui(self) -> None:
        """Set up the user interface."""
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        # Create tab widget
        tabs = QTabWidget()
        layout.addWidget(tabs)

        # Tab 1: Fetch & Test
        fetch_tab = self._create_fetch_tab()
        tabs.addTab(fetch_tab, "Fetch & Test")

        # Tab 2: Export
        export_tab = self._create_export_tab()
        tabs.addTab(export_tab, "Export Results")

    def _create_fetch_tab(self) -> QWidget:
        """Create the fetch and test tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Source selection and parameters
        params_group = QGroupBox("Fetch Parameters")
        params_layout = QHBoxLayout(params_group)

        # Source dropdown
        params_layout.addWidget(QLabel("Source:"))
        self.source_combo = QComboBox()
        self.source_combo.addItems(["medRxiv", "PubMed"])
        self.source_combo.currentTextChanged.connect(self._on_source_changed)
        params_layout.addWidget(self.source_combo)

        # Days (for medRxiv)
        params_layout.addWidget(QLabel("Days:"))
        self.days_spin = QSpinBox()
        self.days_spin.setRange(1, 365)
        self.days_spin.setValue(7)
        params_layout.addWidget(self.days_spin)

        # Query (for PubMed)
        params_layout.addWidget(QLabel("Query:"))
        self.query_edit = QLineEdit()
        self.query_edit.setPlaceholderText("PubMed search query...")
        self.query_edit.setEnabled(False)
        params_layout.addWidget(self.query_edit)

        # Max results
        params_layout.addWidget(QLabel("Max:"))
        self.max_spin = QSpinBox()
        self.max_spin.setRange(1, 1000)
        self.max_spin.setValue(50)
        params_layout.addWidget(self.max_spin)

        # Fetch button
        self.fetch_btn = QPushButton("Fetch Articles")
        self.fetch_btn.clicked.connect(self._start_fetch)
        params_layout.addWidget(self.fetch_btn)

        # Cancel button
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self._cancel_fetch)
        self.cancel_btn.setEnabled(False)
        params_layout.addWidget(self.cancel_btn)

        layout.addWidget(params_group)

        # Progress
        self.progress_label = QLabel("Ready")
        layout.addWidget(self.progress_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)  # Indeterminate
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        # Main content area: article list + preview
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Article list
        list_group = QGroupBox("Fetched Articles")
        list_layout = QVBoxLayout(list_group)
        self.article_list = QListWidget()
        self.article_list.currentItemChanged.connect(self._on_article_selected)
        list_layout.addWidget(self.article_list)
        splitter.addWidget(list_group)

        # Preview area
        preview_group = QGroupBox("Abstract Preview")
        preview_layout = QVBoxLayout(preview_group)

        # Title
        self.title_label = QLabel()
        self.title_label.setWordWrap(True)
        self.title_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        preview_layout.addWidget(self.title_label)

        # Metadata
        self.meta_label = QLabel()
        self.meta_label.setWordWrap(True)
        self.meta_label.setStyleSheet("color: #666;")
        preview_layout.addWidget(self.meta_label)

        # Raw vs Formatted comparison
        compare_splitter = QSplitter(Qt.Orientation.Horizontal)

        raw_group = QGroupBox("Raw Abstract")
        raw_layout = QVBoxLayout(raw_group)
        self.raw_text = QTextEdit()
        self.raw_text.setReadOnly(True)
        raw_layout.addWidget(self.raw_text)
        compare_splitter.addWidget(raw_group)

        formatted_group = QGroupBox("Formatted Abstract (Markdown)")
        formatted_layout = QVBoxLayout(formatted_group)
        self.formatted_browser = QTextBrowser()
        formatted_layout.addWidget(self.formatted_browser)
        compare_splitter.addWidget(formatted_group)

        preview_layout.addWidget(compare_splitter)
        splitter.addWidget(preview_group)

        # Set splitter proportions
        splitter.setSizes([300, 900])

        layout.addWidget(splitter)

        return widget

    def _create_export_tab(self) -> QWidget:
        """Create the export tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Export options
        options_group = QGroupBox("Export Options")
        options_layout = QHBoxLayout(options_group)

        # Format selection
        options_layout.addWidget(QLabel("Format:"))
        self.format_combo = QComboBox()
        self.format_combo.addItems(["JSON", "SQLite"])
        options_layout.addWidget(self.format_combo)

        options_layout.addStretch()

        # Export button
        export_btn = QPushButton("Export Fetched Articles")
        export_btn.clicked.connect(self._export_articles)
        options_layout.addWidget(export_btn)

        layout.addWidget(options_group)

        # Statistics
        stats_group = QGroupBox("Fetch Statistics")
        stats_layout = QVBoxLayout(stats_group)
        self.stats_label = QLabel("No articles fetched yet")
        stats_layout.addWidget(self.stats_label)
        layout.addWidget(stats_group)

        layout.addStretch()

        return widget

    def _on_source_changed(self, source: str) -> None:
        """Handle source selection change."""
        is_pubmed = source.lower() == "pubmed"
        self.query_edit.setEnabled(is_pubmed)
        self.days_spin.setEnabled(not is_pubmed)

    def _start_fetch(self) -> None:
        """Start fetching articles."""
        source = self.source_combo.currentText().lower()
        days = self.days_spin.value()
        query = self.query_edit.text()
        max_results = self.max_spin.value()

        if source == "pubmed" and not query:
            QMessageBox.warning(self, "Warning", "Please enter a PubMed search query")
            return

        # Clear previous results
        self._articles = []
        self.article_list.clear()
        self.title_label.clear()
        self.meta_label.clear()
        self.raw_text.clear()
        self.formatted_browser.clear()

        # Update UI
        self.fetch_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.progress_bar.setVisible(True)

        # Start worker
        self._worker = FetchWorker(source, days, query, max_results, self)
        self._worker.progress.connect(self._on_progress)
        self._worker.article_fetched.connect(self._on_article_fetched)
        self._worker.finished.connect(self._on_fetch_finished)
        self._worker.start()

    def _cancel_fetch(self) -> None:
        """Cancel the fetch operation."""
        if self._worker:
            self._worker.cancel()
            self.progress_label.setText("Cancelling...")

    def _on_progress(self, message: str) -> None:
        """Handle progress updates."""
        self.progress_label.setText(message)

    def _on_article_fetched(self, article: Dict[str, Any]) -> None:
        """Handle a single article being fetched."""
        self._articles.append(article)

        # Add to list
        title = article.get("title", "Untitled")[:80]
        if len(article.get("title", "")) > 80:
            title += "..."

        item = QListWidgetItem(title)
        item.setData(Qt.ItemDataRole.UserRole, len(self._articles) - 1)
        self.article_list.addItem(item)

    def _on_fetch_finished(
        self, success: bool, message: str, articles: List[Dict[str, Any]]
    ) -> None:
        """Handle fetch completion."""
        self.fetch_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.progress_bar.setVisible(False)
        self.progress_label.setText(message)

        # Update statistics
        self._update_stats()

        if not success:
            QMessageBox.warning(self, "Fetch Result", message)

    def _on_article_selected(
        self, current: QListWidgetItem, previous: QListWidgetItem
    ) -> None:
        """Handle article selection."""
        if current is None:
            return

        idx = current.data(Qt.ItemDataRole.UserRole)
        if idx is None or idx >= len(self._articles):
            return

        article = self._articles[idx]

        # Update title
        self.title_label.setText(article.get("title", ""))

        # Update metadata
        meta_parts = []
        if article.get("authors"):
            meta_parts.append(f"Authors: {article['authors']}")
        if article.get("date"):
            meta_parts.append(f"Date: {article['date']}")
        if article.get("doi"):
            meta_parts.append(f"DOI: {article['doi']}")
        if article.get("pmid"):
            meta_parts.append(f"PMID: {article['pmid']}")
        self.meta_label.setText(" | ".join(meta_parts))

        # Update raw abstract
        self.raw_text.setPlainText(article.get("abstract_raw", ""))

        # Update formatted abstract (render Markdown as HTML)
        formatted = article.get("abstract_formatted", "")
        # Convert Markdown to HTML for display
        html = self._markdown_to_html(formatted)
        self.formatted_browser.setHtml(html)

    def _markdown_to_html(self, text: str) -> str:
        """Convert simple Markdown to HTML."""
        import re

        if not text:
            return ""

        # Bold: **text** -> <b>text</b>
        html = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", text)
        # Paragraph breaks
        html = html.replace("\n\n", "</p><p>")
        return f"<p>{html}</p>"

    def _update_stats(self) -> None:
        """Update the statistics display."""
        if not self._articles:
            self.stats_label.setText("No articles fetched yet")
            return

        sources = {}
        for article in self._articles:
            src = article.get("source", "unknown")
            sources[src] = sources.get(src, 0) + 1

        stats_text = f"Total articles: {len(self._articles)}\n"
        for src, count in sources.items():
            stats_text += f"  {src}: {count}\n"

        self.stats_label.setText(stats_text)

    def _export_articles(self) -> None:
        """Export fetched articles to file."""
        if not self._articles:
            QMessageBox.warning(self, "Warning", "No articles to export")
            return

        fmt = self.format_combo.currentText()

        if fmt == "JSON":
            path, _ = QFileDialog.getSaveFileName(
                self, "Export to JSON", "", "JSON files (*.json)"
            )
            if path:
                self._export_json(path)
        else:
            path, _ = QFileDialog.getSaveFileName(
                self, "Export to SQLite", "", "SQLite databases (*.db *.sqlite)"
            )
            if path:
                self._export_sqlite(path)

    def _export_json(self, path: str) -> None:
        """Export articles to JSON file."""
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "exported_at": datetime.now().isoformat(),
                        "total_articles": len(self._articles),
                        "articles": self._articles,
                    },
                    f,
                    indent=2,
                    ensure_ascii=False,
                )
            QMessageBox.information(
                self, "Export Complete", f"Exported {len(self._articles)} articles to {path}"
            )
        except Exception as e:
            QMessageBox.critical(self, "Export Error", f"Failed to export: {e}")

    def _export_sqlite(self, path: str) -> None:
        """Export articles to SQLite database."""
        try:
            # Remove existing file if present
            if Path(path).exists():
                Path(path).unlink()

            conn = sqlite3.connect(path)
            cursor = conn.cursor()

            # Create table
            cursor.execute("""
                CREATE TABLE articles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source TEXT,
                    doi TEXT,
                    pmid TEXT,
                    title TEXT,
                    authors TEXT,
                    date TEXT,
                    category TEXT,
                    journal TEXT,
                    abstract_raw TEXT,
                    abstract_formatted TEXT,
                    pdf_url TEXT
                )
            """)

            # Insert articles
            for article in self._articles:
                cursor.execute(
                    """
                    INSERT INTO articles (
                        source, doi, pmid, title, authors, date,
                        category, journal, abstract_raw, abstract_formatted, pdf_url
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        article.get("source", ""),
                        article.get("doi", ""),
                        article.get("pmid", ""),
                        article.get("title", ""),
                        article.get("authors", ""),
                        article.get("date", ""),
                        article.get("category", ""),
                        article.get("journal", ""),
                        article.get("abstract_raw", ""),
                        article.get("abstract_formatted", ""),
                        article.get("pdf_url", ""),
                    ),
                )

            conn.commit()
            conn.close()

            QMessageBox.information(
                self, "Export Complete", f"Exported {len(self._articles)} articles to {path}"
            )
        except Exception as e:
            QMessageBox.critical(self, "Export Error", f"Failed to export: {e}")

    def closeEvent(self, event) -> None:
        """Handle window close."""
        if self._worker and self._worker.isRunning():
            self._worker.cancel()
            self._worker.wait(3000)
        super().closeEvent(event)


def main():
    """Main entry point."""
    import sys

    logging.basicConfig(level=logging.INFO)

    app = QApplication(sys.argv)
    window = ImporterTestLab()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
