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
    QSizePolicy,
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
        file_path: str = "",
        max_results: int = 100,
        parent: Optional[QWidget] = None,
    ):
        """
        Initialize fetch worker.

        Args:
            source: 'medrxiv' or 'pubmed'
            days: Number of days to fetch (medRxiv)
            file_path: Path to local PubMed XML file (.xml.gz)
            max_results: Maximum results to fetch
            parent: Parent widget
        """
        super().__init__(parent)
        self.source = source
        self.days = days
        self.query = file_path  # Keep as self.query for compatibility with _fetch_pubmed
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
        """Parse articles from local PubMed XML file."""
        import gzip
        import xml.etree.ElementTree as ET

        # Use the file path from query field (which is now a file path)
        file_path = Path(self.query)

        if not file_path.exists():
            self.progress.emit(f"File not found: {file_path}")
            return

        self.progress.emit(f"Parsing PubMed XML file: {file_path.name}...")

        # Create a temporary bulk importer to use its parsing methods
        from bmlibrarian.importers.pubmed_bulk_importer import PubMedBulkImporter

        # Use __new__ to avoid database connection
        temp_importer = PubMedBulkImporter.__new__(PubMedBulkImporter)

        try:
            # Open file (gzip or plain XML)
            if file_path.suffix == '.gz':
                file_handle = gzip.open(file_path, 'rb')
            else:
                file_handle = open(file_path, 'rb')

            with file_handle:
                # Use iterparse for memory efficiency
                context = ET.iterparse(file_handle, events=('end',))
                count = 0

                for event, elem in context:
                    if self._cancelled:
                        break

                    if elem.tag == 'PubmedArticle':
                        count += 1
                        if count > self.max_results:
                            break

                        # Use the bulk importer's parsing method
                        parsed = temp_importer._parse_article(elem)

                        if parsed:
                            # Get raw abstract for comparison
                            abstract_elem = elem.find('.//Abstract')
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

                            article = {
                                "source": "pubmed",
                                "pmid": parsed.get("pmid", ""),
                                "doi": parsed.get("doi", ""),
                                "title": parsed.get("title", ""),
                                "authors": ", ".join(parsed.get("authors", [])),
                                "date": parsed.get("publication_date", ""),
                                "journal": parsed.get("publication", ""),
                                "abstract_raw": abstract_raw,
                                "abstract_formatted": parsed.get("abstract", ""),
                            }

                            self._articles.append(article)
                            self.article_fetched.emit(article)

                        # Clear element to save memory
                        elem.clear()

                        if count % 100 == 0:
                            self.progress.emit(f"Processed {count} articles...")

        except gzip.BadGzipFile as e:
            self.progress.emit(f"Invalid gzip file: {e}")
            return
        except ET.ParseError as e:
            self.progress.emit(f"XML parse error: {e}")
            return
        except Exception as e:
            self.progress.emit(f"Error parsing file: {e}")
            return

        self.progress.emit(f"Parsed {len(self._articles)} articles from {file_path.name}")


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

        # File path (for PubMed local XML)
        params_layout.addWidget(QLabel("XML File:"))
        self.file_edit = QLineEdit()
        self.file_edit.setPlaceholderText("Path to PubMed XML file (.xml.gz)...")
        self.file_edit.setEnabled(False)
        params_layout.addWidget(self.file_edit)

        # Browse button for file selection
        self.browse_btn = QPushButton("Browse...")
        self.browse_btn.clicked.connect(self._browse_file)
        self.browse_btn.setEnabled(False)
        params_layout.addWidget(self.browse_btn)

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

        # Fixed height for params group
        params_group.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        layout.addWidget(params_group)

        # Progress - fixed height
        self.progress_label = QLabel("Ready")
        self.progress_label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        layout.addWidget(self.progress_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)  # Indeterminate
        self.progress_bar.setVisible(False)
        self.progress_bar.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        layout.addWidget(self.progress_bar)

        # Main content area: article list + preview - EXPANDS
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

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

        # Title - use QTextBrowser for text selection
        self.title_label = QTextBrowser()
        self.title_label.setOpenExternalLinks(True)
        self.title_label.setStyleSheet(
            "font-weight: bold; font-size: 14px; background: transparent; border: none;"
        )
        self.title_label.setMaximumHeight(60)
        self.title_label.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        preview_layout.addWidget(self.title_label)

        # Metadata - use QTextBrowser for text selection (allows copy DOI, PMID, etc.)
        self.meta_label = QTextBrowser()
        self.meta_label.setOpenExternalLinks(True)
        self.meta_label.setStyleSheet("color: #666; background: transparent; border: none;")
        self.meta_label.setMaximumHeight(40)
        self.meta_label.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
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
        self.file_edit.setEnabled(is_pubmed)
        self.browse_btn.setEnabled(is_pubmed)
        self.days_spin.setEnabled(not is_pubmed)

    def _browse_file(self) -> None:
        """Open file browser for PubMed XML file selection."""
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select PubMed XML File",
            str(Path.home()),
            "PubMed XML files (*.xml.gz *.xml);;All files (*.*)",
        )
        if path:
            self.file_edit.setText(path)

    def _start_fetch(self) -> None:
        """Start fetching articles."""
        source = self.source_combo.currentText().lower()
        days = self.days_spin.value()
        file_path = self.file_edit.text()  # Now used for PubMed XML file path
        max_results = self.max_spin.value()

        if source == "pubmed" and not file_path:
            QMessageBox.warning(self, "Warning", "Please select a PubMed XML file")
            return

        if source == "pubmed" and not Path(file_path).exists():
            QMessageBox.warning(self, "Warning", f"File not found: {file_path}")
            return

        # Clear previous results
        self._articles = []
        self.article_list.clear()
        self.title_label.setPlainText("")
        self.meta_label.setPlainText("")
        self.raw_text.clear()
        self.formatted_browser.clear()

        # Update UI
        self.fetch_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.progress_bar.setVisible(True)

        # Start worker
        self._worker = FetchWorker(source, days, file_path, max_results, self)
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
        self.title_label.setPlainText(article.get("title", ""))

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
        self.meta_label.setPlainText(" | ".join(meta_parts))

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
