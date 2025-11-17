"""
Search Settings Tab for BMLibrarian Qt GUI.
Mirrors functionality from bmlibrarian/gui/tabs/search_tab.py

Provides configuration for literature search strategies including:
- Keyword fulltext search
- BM25 ranking
- Semantic search
- Semantic search with HyDE (Hypothetical Document Embeddings)
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QCheckBox,
    QComboBox, QGroupBox, QScrollArea, QFrame
)
from PySide6.QtCore import Qt, Slot
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..plugins.settings.plugin import SettingsPlugin


class SearchSettingsTab:
    """Search strategy configuration tab for Qt GUI."""

    def __init__(self, settings_plugin: "SettingsPlugin"):
        """Initialize search settings tab.

        Args:
            settings_plugin: Parent settings plugin instance
        """
        self.settings_plugin = settings_plugin
        self.config = settings_plugin.config
        self.controls = {}

    def build(self) -> QWidget:
        """Build the search settings tab content.

        Returns:
            QWidget containing all search strategy controls
        """
        # Main widget with scroll area
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)

        # Create scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)
        scroll_layout.setSpacing(15)
        scroll_layout.setContentsMargins(15, 15, 15, 15)

        # Header
        header_label = QLabel("Literature Search Strategy")
        header_label.setStyleSheet("font-size: 14pt; font-weight: bold; color: #1976D2;")
        scroll_layout.addWidget(header_label)

        desc_label = QLabel(
            "Configure search methods for literature retrieval. "
            "Enable multiple strategies for hybrid search."
        )
        desc_label.setWordWrap(True)
        desc_label.setStyleSheet("color: #666666; font-style: italic;")
        scroll_layout.addWidget(desc_label)

        scroll_layout.addSpacing(10)

        # Build sections
        scroll_layout.addWidget(self._build_keyword_search_section())
        scroll_layout.addWidget(self._create_divider())
        scroll_layout.addWidget(self._build_bm25_section())
        scroll_layout.addWidget(self._create_divider())
        scroll_layout.addWidget(self._build_semantic_section())
        scroll_layout.addWidget(self._create_divider())
        scroll_layout.addWidget(self._build_hyde_section())
        scroll_layout.addStretch()

        scroll.setWidget(scroll_widget)
        layout.addWidget(scroll)

        return widget

    def _create_divider(self) -> QFrame:
        """Create a horizontal divider line."""
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        return line

    def _build_keyword_search_section(self) -> QGroupBox:
        """Build keyword fulltext search configuration."""
        group = QGroupBox("🔍 Keyword Fulltext Search")
        group.setStyleSheet("""
            QGroupBox {
                font-size: 12pt;
                font-weight: bold;
                border: 2px solid #CCCCCC;
                border-radius: 5px;
                margin-top: 10px;
                padding-top: 10px;
                background-color: #FAFAFA;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
        """)

        layout = QVBoxLayout()
        layout.setSpacing(10)

        search_config = self.config._config.get('search_strategy', {})
        keyword_config = search_config.get('keyword', {})

        # Enable checkbox
        self.controls['keyword_enabled'] = QCheckBox("Enable Keyword Fulltext Search")
        self.controls['keyword_enabled'].setChecked(keyword_config.get('enabled', True))
        self.controls['keyword_enabled'].setToolTip("PostgreSQL fulltext search using keywords")
        self.controls['keyword_enabled'].stateChanged.connect(self._on_keyword_toggle)
        layout.addWidget(self.controls['keyword_enabled'])

        # Parameters
        params_layout = QHBoxLayout()

        # Max results
        max_label = QLabel("Max Results:")
        max_label.setFixedWidth(100)
        params_layout.addWidget(max_label)

        self.controls['keyword_max_results'] = QLineEdit()
        self.controls['keyword_max_results'].setText(str(keyword_config.get('max_results', 100)))
        self.controls['keyword_max_results'].setFixedWidth(100)
        self.controls['keyword_max_results'].setToolTip("Maximum documents to retrieve")
        self.controls['keyword_max_results'].setEnabled(keyword_config.get('enabled', True))
        params_layout.addWidget(self.controls['keyword_max_results'])

        params_layout.addSpacing(30)

        # Operator
        op_label = QLabel("Operator:")
        op_label.setFixedWidth(80)
        params_layout.addWidget(op_label)

        self.controls['keyword_operator'] = QComboBox()
        self.controls['keyword_operator'].addItems(['AND', 'OR'])
        self.controls['keyword_operator'].setCurrentText(keyword_config.get('operator', 'AND'))
        self.controls['keyword_operator'].setFixedWidth(100)
        self.controls['keyword_operator'].setToolTip("How to combine search terms")
        self.controls['keyword_operator'].setEnabled(keyword_config.get('enabled', True))
        params_layout.addWidget(self.controls['keyword_operator'])

        params_layout.addStretch()
        layout.addLayout(params_layout)

        # Case sensitive
        self.controls['keyword_case_sensitive'] = QCheckBox("Case sensitive")
        self.controls['keyword_case_sensitive'].setChecked(keyword_config.get('case_sensitive', False))
        self.controls['keyword_case_sensitive'].setToolTip("Perform case-sensitive matching")
        self.controls['keyword_case_sensitive'].setEnabled(keyword_config.get('enabled', True))
        layout.addWidget(self.controls['keyword_case_sensitive'])

        group.setLayout(layout)
        return group

    def _build_bm25_section(self) -> QGroupBox:
        """Build BM25 ranking configuration."""
        group = QGroupBox("📊 BM25 Ranking")
        group.setStyleSheet("""
            QGroupBox {
                font-size: 12pt;
                font-weight: bold;
                border: 2px solid #CCCCCC;
                border-radius: 5px;
                margin-top: 10px;
                padding-top: 10px;
                background-color: #FAFAFA;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
        """)

        layout = QVBoxLayout()
        layout.setSpacing(10)

        search_config = self.config._config.get('search_strategy', {})
        bm25_config = search_config.get('bm25', {})

        # Enable checkbox
        self.controls['bm25_enabled'] = QCheckBox("Enable BM25 Ranking")
        self.controls['bm25_enabled'].setChecked(bm25_config.get('enabled', False))
        self.controls['bm25_enabled'].setToolTip("Best Match 25 probabilistic ranking algorithm")
        self.controls['bm25_enabled'].stateChanged.connect(self._on_bm25_toggle)
        layout.addWidget(self.controls['bm25_enabled'])

        # Max results
        max_layout = QHBoxLayout()
        max_label = QLabel("Max Results:")
        max_label.setFixedWidth(100)
        max_layout.addWidget(max_label)

        self.controls['bm25_max_results'] = QLineEdit()
        self.controls['bm25_max_results'].setText(str(bm25_config.get('max_results', 100)))
        self.controls['bm25_max_results'].setFixedWidth(100)
        self.controls['bm25_max_results'].setEnabled(bm25_config.get('enabled', False))
        max_layout.addWidget(self.controls['bm25_max_results'])
        max_layout.addStretch()
        layout.addLayout(max_layout)

        group.setLayout(layout)
        return group

    def _build_semantic_section(self) -> QGroupBox:
        """Build semantic search configuration."""
        group = QGroupBox("🧠 Semantic Search")
        group.setStyleSheet("""
            QGroupBox {
                font-size: 12pt;
                font-weight: bold;
                border: 2px solid #CCCCCC;
                border-radius: 5px;
                margin-top: 10px;
                padding-top: 10px;
                background-color: #FAFAFA;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
        """)

        layout = QVBoxLayout()
        layout.setSpacing(10)

        search_config = self.config._config.get('search_strategy', {})
        semantic_config = search_config.get('semantic', {})

        # Enable checkbox
        self.controls['semantic_enabled'] = QCheckBox("Enable Semantic Search")
        self.controls['semantic_enabled'].setChecked(semantic_config.get('enabled', False))
        self.controls['semantic_enabled'].setToolTip("Vector similarity search using embeddings")
        self.controls['semantic_enabled'].stateChanged.connect(self._on_semantic_toggle)
        layout.addWidget(self.controls['semantic_enabled'])

        # Parameters
        params_layout = QHBoxLayout()

        # Max results
        max_label = QLabel("Max Results:")
        max_label.setFixedWidth(100)
        params_layout.addWidget(max_label)

        self.controls['semantic_max_results'] = QLineEdit()
        self.controls['semantic_max_results'].setText(str(semantic_config.get('max_results', 50)))
        self.controls['semantic_max_results'].setFixedWidth(100)
        self.controls['semantic_max_results'].setEnabled(semantic_config.get('enabled', False))
        params_layout.addWidget(self.controls['semantic_max_results'])

        params_layout.addSpacing(30)

        # Similarity threshold
        thresh_label = QLabel("Threshold:")
        thresh_label.setFixedWidth(80)
        params_layout.addWidget(thresh_label)

        self.controls['semantic_threshold'] = QLineEdit()
        self.controls['semantic_threshold'].setText(str(semantic_config.get('similarity_threshold', 0.7)))
        self.controls['semantic_threshold'].setFixedWidth(100)
        self.controls['semantic_threshold'].setToolTip("Minimum similarity score (0.0-1.0)")
        self.controls['semantic_threshold'].setEnabled(semantic_config.get('enabled', False))
        params_layout.addWidget(self.controls['semantic_threshold'])

        params_layout.addStretch()
        layout.addLayout(params_layout)

        group.setLayout(layout)
        return group

    def _build_hyde_section(self) -> QGroupBox:
        """Build HyDE (Hypothetical Document Embeddings) configuration."""
        group = QGroupBox("🔮 HyDE (Hypothetical Document Embeddings)")
        group.setStyleSheet("""
            QGroupBox {
                font-size: 12pt;
                font-weight: bold;
                border: 2px solid #CCCCCC;
                border-radius: 5px;
                margin-top: 10px;
                padding-top: 10px;
                background-color: #FAFAFA;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
        """)

        layout = QVBoxLayout()
        layout.setSpacing(10)

        search_config = self.config._config.get('search_strategy', {})
        hyde_config = search_config.get('hyde', {})

        # Enable checkbox
        self.controls['hyde_enabled'] = QCheckBox("Enable HyDE Search")
        self.controls['hyde_enabled'].setChecked(hyde_config.get('enabled', False))
        self.controls['hyde_enabled'].setToolTip("Generate hypothetical documents and search by their embeddings")
        self.controls['hyde_enabled'].stateChanged.connect(self._on_hyde_toggle)
        layout.addWidget(self.controls['hyde_enabled'])

        # Parameters
        params_layout = QHBoxLayout()

        # Max results
        max_label = QLabel("Max Results:")
        max_label.setFixedWidth(100)
        params_layout.addWidget(max_label)

        self.controls['hyde_max_results'] = QLineEdit()
        self.controls['hyde_max_results'].setText(str(hyde_config.get('max_results', 50)))
        self.controls['hyde_max_results'].setFixedWidth(100)
        self.controls['hyde_max_results'].setEnabled(hyde_config.get('enabled', False))
        params_layout.addWidget(self.controls['hyde_max_results'])

        params_layout.addSpacing(30)

        # Similarity threshold
        thresh_label = QLabel("Threshold:")
        thresh_label.setFixedWidth(80)
        params_layout.addWidget(thresh_label)

        self.controls['hyde_threshold'] = QLineEdit()
        self.controls['hyde_threshold'].setText(str(hyde_config.get('similarity_threshold', 0.7)))
        self.controls['hyde_threshold'].setFixedWidth(100)
        self.controls['hyde_threshold'].setToolTip("Minimum similarity score (0.0-1.0)")
        self.controls['hyde_threshold'].setEnabled(hyde_config.get('enabled', False))
        params_layout.addWidget(self.controls['hyde_threshold'])

        params_layout.addStretch()
        layout.addLayout(params_layout)

        group.setLayout(layout)
        return group

    @Slot(int)
    def _on_keyword_toggle(self, state: int):
        """Handle keyword search toggle."""
        enabled = state == Qt.CheckState.Checked.value
        self.controls['keyword_max_results'].setEnabled(enabled)
        self.controls['keyword_operator'].setEnabled(enabled)
        self.controls['keyword_case_sensitive'].setEnabled(enabled)

    @Slot(int)
    def _on_bm25_toggle(self, state: int):
        """Handle BM25 toggle."""
        enabled = state == Qt.CheckState.Checked.value
        self.controls['bm25_max_results'].setEnabled(enabled)

    @Slot(int)
    def _on_semantic_toggle(self, state: int):
        """Handle semantic search toggle."""
        enabled = state == Qt.CheckState.Checked.value
        self.controls['semantic_max_results'].setEnabled(enabled)
        self.controls['semantic_threshold'].setEnabled(enabled)

    @Slot(int)
    def _on_hyde_toggle(self, state: int):
        """Handle HyDE toggle."""
        enabled = state == Qt.CheckState.Checked.value
        self.controls['hyde_max_results'].setEnabled(enabled)
        self.controls['hyde_threshold'].setEnabled(enabled)

    def update_config(self):
        """Update configuration from UI controls."""
        try:
            # Ensure search_strategy section exists
            if 'search_strategy' not in self.config._config:
                self.config._config['search_strategy'] = {}

            search_config = self.config._config['search_strategy']

            # Update keyword config
            if 'keyword' not in search_config:
                search_config['keyword'] = {}
            search_config['keyword']['enabled'] = self.controls['keyword_enabled'].isChecked()
            search_config['keyword']['max_results'] = int(self.controls['keyword_max_results'].text())
            search_config['keyword']['operator'] = self.controls['keyword_operator'].currentText()
            search_config['keyword']['case_sensitive'] = self.controls['keyword_case_sensitive'].isChecked()

            # Update BM25 config
            if 'bm25' not in search_config:
                search_config['bm25'] = {}
            search_config['bm25']['enabled'] = self.controls['bm25_enabled'].isChecked()
            search_config['bm25']['max_results'] = int(self.controls['bm25_max_results'].text())

            # Update semantic config
            if 'semantic' not in search_config:
                search_config['semantic'] = {}
            search_config['semantic']['enabled'] = self.controls['semantic_enabled'].isChecked()
            search_config['semantic']['max_results'] = int(self.controls['semantic_max_results'].text())
            search_config['semantic']['similarity_threshold'] = float(self.controls['semantic_threshold'].text())

            # Update HyDE config
            if 'hyde' not in search_config:
                search_config['hyde'] = {}
            search_config['hyde']['enabled'] = self.controls['hyde_enabled'].isChecked()
            search_config['hyde']['max_results'] = int(self.controls['hyde_max_results'].text())
            search_config['hyde']['similarity_threshold'] = float(self.controls['hyde_threshold'].text())

        except (ValueError, KeyError) as e:
            print(f"Error updating config from search tab: {e}")

    def refresh(self):
        """Refresh UI controls with current configuration values."""
        search_config = self.config._config.get('search_strategy', {})

        # Keyword
        keyword_config = search_config.get('keyword', {})
        self.controls['keyword_enabled'].setChecked(keyword_config.get('enabled', True))
        self.controls['keyword_max_results'].setText(str(keyword_config.get('max_results', 100)))
        self.controls['keyword_operator'].setCurrentText(keyword_config.get('operator', 'AND'))
        self.controls['keyword_case_sensitive'].setChecked(keyword_config.get('case_sensitive', False))

        # BM25
        bm25_config = search_config.get('bm25', {})
        self.controls['bm25_enabled'].setChecked(bm25_config.get('enabled', False))
        self.controls['bm25_max_results'].setText(str(bm25_config.get('max_results', 100)))

        # Semantic
        semantic_config = search_config.get('semantic', {})
        self.controls['semantic_enabled'].setChecked(semantic_config.get('enabled', False))
        self.controls['semantic_max_results'].setText(str(semantic_config.get('max_results', 50)))
        self.controls['semantic_threshold'].setText(str(semantic_config.get('similarity_threshold', 0.7)))

        # HyDE
        hyde_config = search_config.get('hyde', {})
        self.controls['hyde_enabled'].setChecked(hyde_config.get('enabled', False))
        self.controls['hyde_max_results'].setText(str(hyde_config.get('max_results', 50)))
        self.controls['hyde_threshold'].setText(str(hyde_config.get('similarity_threshold', 0.7)))
