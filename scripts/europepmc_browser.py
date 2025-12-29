#!/usr/bin/env python3
"""Europe PMC Package Browser.

A minimal GUI for browsing articles in Europe PMC XML packages,
displaying the generated Markdown content.

Usage:
    uv run python scripts/europepmc_browser.py
"""

import gzip
import hashlib
import logging
import re
import sys
import urllib.request
from pathlib import Path
from typing import Optional, List, Dict
from concurrent.futures import ThreadPoolExecutor

from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLabel,
    QTextBrowser,
    QFileDialog,
    QMessageBox,
)
from PySide6.QtCore import Qt, QThread, Signal, QObject
from PySide6.QtGui import QDesktopServices
from PySide6.QtCore import QUrl

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

logger = logging.getLogger(__name__)

# Image cache directory
IMAGE_CACHE_DIR = Path.home() / ".cache" / "europepmc_images"
IMAGE_EXTENSIONS = [".jpg", ".jpeg", ".png", ".gif", ".tif", ".tiff"]
PMC_IMAGE_BASE_URL = "https://www.ncbi.nlm.nih.gov/pmc/articles"
REQUEST_TIMEOUT = 10  # seconds

from bmlibrarian.importers.europe_pmc_importer import (
    EuropePMCXMLParser,
    ArticleMetadata,
)


class ImageFetcher(QObject):
    """Background worker for fetching images from PMC."""

    images_ready = Signal(dict)  # Emits {graphic_ref: local_path}

    def __init__(self, parent: Optional[QObject] = None) -> None:
        """Initialize the image fetcher."""
        super().__init__(parent)
        self._cache_dir = IMAGE_CACHE_DIR
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._executor = ThreadPoolExecutor(max_workers=4)

    def fetch_images(self, pmcid: str, graphic_refs: List[str]) -> None:
        """Fetch images in background and emit when ready.

        Args:
            pmcid: PMC ID (e.g., "PMC12345678")
            graphic_refs: List of graphic reference IDs from the XML
        """
        # Submit all fetches to thread pool
        self._executor.submit(self._fetch_all, pmcid, graphic_refs)

    def _fetch_all(self, pmcid: str, graphic_refs: List[str]) -> None:
        """Fetch all images and emit result.

        Args:
            pmcid: PMC ID
            graphic_refs: List of graphic references
        """
        results: Dict[str, str] = {}
        pmc_num = pmcid.replace("PMC", "")

        for ref in graphic_refs:
            local_path = self._get_cached_path(pmcid, ref)

            # Check if already cached
            if local_path and local_path.exists():
                results[ref] = str(local_path)
                continue

            # Try to fetch from PMC
            fetched_path = self._fetch_image(pmc_num, ref)
            if fetched_path:
                results[ref] = str(fetched_path)

        # Emit results on main thread
        self.images_ready.emit(results)

    def _get_cached_path(self, pmcid: str, graphic_ref: str) -> Optional[Path]:
        """Get cached image path if it exists.

        Args:
            pmcid: PMC ID
            graphic_ref: Graphic reference ID

        Returns:
            Path to cached file if exists, None otherwise
        """
        # Check for any extension
        base_name = f"{pmcid}_{graphic_ref}"
        for ext in IMAGE_EXTENSIONS:
            cached = self._cache_dir / f"{base_name}{ext}"
            if cached.exists():
                return cached
        return None

    def _fetch_image(self, pmc_num: str, graphic_ref: str) -> Optional[Path]:
        """Fetch a single image from PMC.

        Args:
            pmc_num: PMC number without prefix (e.g., "12345678")
            graphic_ref: Graphic reference ID

        Returns:
            Path to downloaded file, or None if failed
        """
        # Try different extensions
        for ext in IMAGE_EXTENSIONS:
            url = f"{PMC_IMAGE_BASE_URL}/PMC{pmc_num}/bin/{graphic_ref}{ext}"
            try:
                req = urllib.request.Request(
                    url,
                    headers={"User-Agent": "BMLibrarian/1.0 (europepmc_browser)"}
                )
                with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as response:
                    if response.status == 200:
                        # Save to cache
                        cache_path = self._cache_dir / f"PMC{pmc_num}_{graphic_ref}{ext}"
                        with open(cache_path, "wb") as f:
                            f.write(response.read())
                        return cache_path
            except Exception as e:
                # Try next extension
                continue

        return None

    def get_cached_image(self, pmcid: str, graphic_ref: str) -> Optional[str]:
        """Get path to cached image if available.

        Args:
            pmcid: PMC ID
            graphic_ref: Graphic reference

        Returns:
            Path string if cached, None otherwise
        """
        path = self._get_cached_path(pmcid, graphic_ref)
        return str(path) if path else None


class EuropePMCBrowser(QMainWindow):
    """Main window for browsing Europe PMC packages."""

    # Window geometry constants
    WINDOW_WIDTH = 900
    WINDOW_HEIGHT = 700
    MIN_WIDTH = 600
    MIN_HEIGHT = 400

    def __init__(self) -> None:
        """Initialize the browser window."""
        super().__init__()
        self.setWindowTitle("Europe PMC Package Browser")
        self.setGeometry(100, 100, self.WINDOW_WIDTH, self.WINDOW_HEIGHT)
        self.setMinimumSize(self.MIN_WIDTH, self.MIN_HEIGHT)

        # Data storage
        self.articles: List[ArticleMetadata] = []
        self.current_index: int = 0
        self.current_file: Optional[Path] = None
        self._cached_images: Dict[str, str] = {}  # graphic_ref -> local_path
        self._current_pmcid: str = ""

        # Parser
        self.parser = EuropePMCXMLParser()

        # Image fetcher
        self.image_fetcher = ImageFetcher(self)
        self.image_fetcher.images_ready.connect(self._on_images_ready)

        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the user interface."""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        # Top bar with file button and info
        top_bar = QHBoxLayout()

        self.open_btn = QPushButton("Open Package...")
        self.open_btn.clicked.connect(self._open_file)
        top_bar.addWidget(self.open_btn)

        self.file_label = QLabel("No file loaded")
        self.file_label.setStyleSheet("color: gray;")
        top_bar.addWidget(self.file_label, 1)

        layout.addLayout(top_bar)

        # Navigation bar
        nav_bar = QHBoxLayout()

        self.prev_btn = QPushButton("◀ Previous")
        self.prev_btn.clicked.connect(self._prev_article)
        self.prev_btn.setEnabled(False)
        nav_bar.addWidget(self.prev_btn)

        self.position_label = QLabel("0 / 0")
        self.position_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        nav_bar.addWidget(self.position_label, 1)

        self.next_btn = QPushButton("Next ▶")
        self.next_btn.clicked.connect(self._next_article)
        self.next_btn.setEnabled(False)
        nav_bar.addWidget(self.next_btn)

        layout.addLayout(nav_bar)

        # Article info bar
        self.info_label = QLabel("")
        self.info_label.setStyleSheet("font-weight: bold; padding: 5px;")
        self.info_label.setWordWrap(True)
        layout.addWidget(self.info_label)

        # Markdown display
        self.text_browser = QTextBrowser()
        self.text_browser.setOpenExternalLinks(True)
        layout.addWidget(self.text_browser, 1)

    def _open_file(self) -> None:
        """Open a .xml.gz package file."""
        # Default to europepmc packages directory if it exists
        default_dir = Path.home() / "europepmc" / "packages"
        if not default_dir.exists():
            default_dir = Path.home()

        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Open Europe PMC Package",
            str(default_dir),
            "GZipped XML (*.xml.gz);;All Files (*)",
        )

        if not file_path:
            return

        self._load_package(Path(file_path))

    def _load_package(self, package_path: Path) -> None:
        """Load articles from a package file.

        Args:
            package_path: Path to the .xml.gz package
        """
        self.articles = []
        self.current_index = 0
        self.current_file = package_path

        self.file_label.setText(f"Loading {package_path.name}...")
        self.file_label.setStyleSheet("color: orange;")
        QApplication.processEvents()

        try:
            with gzip.open(package_path, "rb") as f:
                for article in self.parser.parse_package_streaming(f):
                    self.articles.append(article)

            self.file_label.setText(f"{package_path.name}")
            self.file_label.setStyleSheet("color: green;")

            if self.articles:
                self._update_display()
                self._update_nav_buttons()
            else:
                self.text_browser.setPlainText("No articles found in package.")
                self.info_label.setText("")
                self.position_label.setText("0 / 0")

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load package:\n{e}")
            self.file_label.setText("Error loading file")
            self.file_label.setStyleSheet("color: red;")

    def _update_display(self) -> None:
        """Update the display with the current article."""
        if not self.articles:
            return

        article = self.articles[self.current_index]
        self._current_pmcid = article.pmcid

        # Update position
        self.position_label.setText(f"{self.current_index + 1} / {len(self.articles)}")

        # Update info bar
        info_parts = [article.pmcid]
        if article.pmid:
            info_parts.append(f"PMID: {article.pmid}")
        if article.doi:
            info_parts.append(f"DOI: {article.doi}")
        if article.year:
            info_parts.append(f"({article.year})")
        self.info_label.setText(" | ".join(info_parts))

        # Display markdown content
        if article.full_text:
            # Extract graphic refs and start fetching images
            graphic_refs = self._extract_graphic_refs(article.full_text)
            if graphic_refs:
                self.image_fetcher.fetch_images(article.pmcid, graphic_refs)

            # Convert figures - use cached images if available
            content = self._convert_figures_to_images(
                article.full_text, article.pmcid, self._cached_images
            )
            self.text_browser.setMarkdown(content)
        else:
            # Fallback to basic info if no full text
            fallback = f"# {article.title or 'No Title'}\n\n"
            if article.abstract:
                fallback += f"## Abstract\n\n{article.abstract}\n"
            self.text_browser.setMarkdown(fallback)

    def _extract_graphic_refs(self, content: str) -> List[str]:
        """Extract all graphic references from markdown content.

        Args:
            content: Markdown content with figure syntax

        Returns:
            List of graphic reference IDs
        """
        pattern = r'!\[[^\]]*\]\(([^)]+)\)'
        return re.findall(pattern, content)

    def _on_images_ready(self, images: Dict[str, str]) -> None:
        """Handle images fetched from PMC.

        Args:
            images: Dict mapping graphic_ref to local file path
        """
        if not images:
            return

        # Update cache
        self._cached_images.update(images)

        # Refresh display if we're still on the same article
        if self.articles and self._current_pmcid == self.articles[self.current_index].pmcid:
            article = self.articles[self.current_index]
            if article.full_text:
                content = self._convert_figures_to_images(
                    article.full_text, article.pmcid, self._cached_images
                )
                # Preserve scroll position
                scrollbar = self.text_browser.verticalScrollBar()
                scroll_pos = scrollbar.value()
                self.text_browser.setMarkdown(content)
                scrollbar.setValue(scroll_pos)

    def _convert_figures_to_images(
        self, content: str, pmcid: str, cached_images: Dict[str, str]
    ) -> str:
        """Convert figure markdown to display cached images or placeholders.

        Args:
            content: Markdown content with figure syntax
            pmcid: PMC ID for constructing URLs
            cached_images: Dict mapping graphic_ref to local file path

        Returns:
            Modified content with images or placeholders
        """
        figure_pattern = r'!\[([^\]]*)\]\(([^)]+)\)'

        def replace_figure(match: re.Match) -> str:
            alt_text = match.group(1)
            graphic_ref = match.group(2)

            # Check if image is cached
            if graphic_ref in cached_images:
                local_path = cached_images[graphic_ref]
                # Use file:// URL for local images
                return f"![{alt_text}](file://{local_path})"

            # Extract figure label
            label_match = re.match(r'(Figure \d+[a-zA-Z]?)', alt_text)
            label = label_match.group(1) if label_match else "Figure"

            # PMC URL for fallback link
            pmc_url = f"https://europepmc.org/article/PMC/{pmcid.replace('PMC', '')}"

            # Placeholder with loading indicator
            placeholder = (
                f"\n\n> **🔄 {label}** *(loading...)*\n"
                f"> \n"
                f"> *{alt_text}*\n"
                f"> \n"
                f"> [View on Europe PMC]({pmc_url})\n\n"
            )
            return placeholder

        return re.sub(figure_pattern, replace_figure, content)

    def _update_nav_buttons(self) -> None:
        """Enable/disable navigation buttons based on position."""
        has_articles = len(self.articles) > 0
        self.prev_btn.setEnabled(has_articles and self.current_index > 0)
        self.next_btn.setEnabled(
            has_articles and self.current_index < len(self.articles) - 1
        )

    def _prev_article(self) -> None:
        """Navigate to the previous article."""
        if self.current_index > 0:
            self.current_index -= 1
            self._update_display()
            self._update_nav_buttons()

    def _next_article(self) -> None:
        """Navigate to the next article."""
        if self.current_index < len(self.articles) - 1:
            self.current_index += 1
            self._update_display()
            self._update_nav_buttons()

    def keyPressEvent(self, event) -> None:
        """Handle keyboard navigation.

        Args:
            event: Key press event
        """
        if event.key() == Qt.Key.Key_Left:
            self._prev_article()
        elif event.key() == Qt.Key.Key_Right:
            self._next_article()
        else:
            super().keyPressEvent(event)


def main() -> None:
    """Main entry point."""
    app = QApplication(sys.argv)
    window = EuropePMCBrowser()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
