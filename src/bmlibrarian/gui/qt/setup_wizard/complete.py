"""
Completion page for the Setup Wizard.

Contains the final page showing setup completion summary.
"""

from typing import Optional, TYPE_CHECKING

from PySide6.QtWidgets import (
    QWizardPage,
    QVBoxLayout,
    QLabel,
    QGroupBox,
)

from ..resources.styles.dpi_scale import get_font_scale

if TYPE_CHECKING:
    from .wizard import SetupWizard


class CompletePage(QWizardPage):
    """
    Final page showing setup completion summary.

    Displays summary of what was configured and next steps.
    """

    def __init__(self, parent: Optional["SetupWizard"] = None):
        """Initialize complete page."""
        super().__init__(parent)
        self._wizard = parent
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the complete page UI."""
        scale = get_font_scale()

        self.setTitle("Setup Complete!")
        self.setSubTitle("BMLibrarian has been configured successfully.")

        layout = QVBoxLayout(self)
        layout.setSpacing(scale["spacing_large"])

        # Summary
        self.summary_label = QLabel()
        self.summary_label.setWordWrap(True)
        layout.addWidget(self.summary_label)

        # Next steps
        next_steps_group = QGroupBox("Next Steps")
        next_steps_layout = QVBoxLayout(next_steps_group)

        next_steps_text = QLabel(
            "You can now:\n\n"
            "  1. Run the BMLibrarian CLI:\n"
            "     uv run python bmlibrarian_cli.py\n\n"
            "  2. Run the Research GUI:\n"
            "     uv run python bmlibrarian_research_gui.py\n\n"
            "  3. Configure additional settings:\n"
            "     uv run python bmlibrarian_config_gui.py\n\n"
            "  4. Import more data:\n"
            "     uv run python medrxiv_import_cli.py update\n"
            "     uv run python pubmed_import_cli.py search \"your query\""
        )
        next_steps_text.setWordWrap(True)
        next_steps_layout.addWidget(next_steps_text)

        layout.addWidget(next_steps_group)

        layout.addStretch()

    def initializePage(self) -> None:
        """Initialize the page when it becomes visible."""
        if self._wizard:
            config = self._wizard.get_config()
            import_results = self._wizard.get_import_results()

            summary = self._build_summary(config, import_results)
            self.summary_label.setText(summary)

    def _build_summary(self, config: dict, import_results: dict) -> str:
        """
        Build the summary text from config and import results.

        Args:
            config: Wizard configuration dictionary
            import_results: Import results dictionary

        Returns:
            Formatted summary string
        """
        summary = (
            f"Configuration Summary:\n\n"
            f"  Database: {config.get('postgres_db', 'N/A')}@"
            f"{config.get('postgres_host', 'localhost')}:"
            f"{config.get('postgres_port', '5432')}\n"
            f"  User: {config.get('postgres_user', 'N/A')}\n"
            f"  PDF Directory: {config.get('pdf_base_dir', 'N/A')}\n"
        )

        # Add API key status
        anthropic_key = config.get('anthropic_api_key', '')
        openai_key = config.get('openai_api_key', '')
        if anthropic_key or openai_key:
            summary += "\nAPI Keys:\n"
            if anthropic_key:
                # Show only last 4 characters for security
                masked_key = f"sk-ant-...{anthropic_key[-4:]}" if len(anthropic_key) > 4 else "****"
                summary += f"  Anthropic: Configured ({masked_key})\n"
            if openai_key:
                masked_key = f"sk-...{openai_key[-4:]}" if len(openai_key) > 4 else "****"
                summary += f"  OpenAI: Configured ({masked_key})\n"

        summary += "\nImport Results:\n"

        # Add import results
        if import_results.get("medrxiv_success"):
            stats = import_results.get("medrxiv_stats", {})
            summary += f"  medRxiv: {stats.get('total_processed', 0)} papers imported\n"
        elif import_results.get("medrxiv_stats"):
            summary += "  medRxiv: Import skipped or failed\n"

        if import_results.get("pubmed_success"):
            stats = import_results.get("pubmed_stats", {})
            summary += f"  PubMed: {stats.get('imported', 0)} articles imported\n"
        elif import_results.get("pubmed_stats"):
            summary += "  PubMed: Import skipped or failed\n"

        if import_results.get("mesh_success"):
            stats = import_results.get("mesh_stats", {})
            summary += (
                f"  MeSH: {stats.get('descriptors', 0):,} descriptors, "
                f"{stats.get('terms', 0):,} terms imported\n"
            )
        elif import_results.get("mesh_stats"):
            summary += "  MeSH: Import skipped or failed\n"

        return summary
