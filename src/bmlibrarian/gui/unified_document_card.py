"""Unified Document Card Component

Provides a single, consistent card design for displaying documents across all tabs.
The card is collapsible with title and score visible when collapsed, and includes
context-specific features like scoring controls and full-text access buttons.
"""

import flet as ft
from typing import Dict, Optional, Callable, List, Any
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


class DocumentCardContext:
    """Enumeration of different contexts where document cards appear."""
    LITERATURE = "literature"  # Literature search results
    SCORING = "scoring"  # Document scoring view
    CITATIONS = "citations"  # Citations view
    COUNTERFACTUAL = "counterfactual"  # Counterfactual evidence
    REPORT = "report"  # Final report view


class UnifiedDocumentCard:
    """Creates unified document cards with consistent appearance across all contexts."""

    def __init__(
        self,
        page: ft.Page,
        pdf_manager=None,
        on_pdf_status_change: Optional[Callable[[int, str], None]] = None
    ):
        """Initialize unified document card creator.

        Args:
            page: Flet page instance for dialogs
            pdf_manager: PDFManager instance for handling PDF operations
            on_pdf_status_change: Callback when PDF status changes (doc_id, status)
        """
        self.page = page
        self.pdf_manager = pdf_manager
        self.on_pdf_status_change = on_pdf_status_change

    def create_card(
        self,
        index: int,
        doc: Dict[str, Any],
        context: str = DocumentCardContext.LITERATURE,
        ai_score: Optional[float] = None,
        human_score: Optional[float] = None,
        relevance_score: Optional[float] = None,
        citation_data: Optional[Dict] = None,
        scoring_reasoning: Optional[str] = None,
        on_score_change: Optional[Callable[[int, float, str], None]] = None,
        on_score_approve: Optional[Callable[[int], None]] = None,
        show_scoring_controls: bool = False
    ) -> ft.ExpansionTile:
        """Create a unified document card.

        Args:
            index: Document index in list
            doc: Document dictionary with metadata
            context: Display context (literature, scoring, citations, etc.)
            ai_score: AI-assigned relevance score (1-5 scale)
            human_score: Human-assigned override score (1-5 scale)
            relevance_score: Citation relevance score (0-1 scale)
            citation_data: Additional citation-specific data
            scoring_reasoning: AI scoring reasoning text
            on_score_change: Callback for score changes (index, score, type)
            on_score_approve: Callback for score approval (index)
            show_scoring_controls: Whether to show human scoring controls

        Returns:
            ExpansionTile widget for the document
        """
        # Extract document data
        title = doc.get('title', 'Untitled Document')
        authors = doc.get('authors', 'Unknown authors')
        publication = doc.get('publication', 'Unknown')
        year = self._extract_year(doc)
        abstract = doc.get('abstract', 'No abstract available')
        doc_id = doc.get('id') or doc.get('document_id', 'Unknown')
        pmid = doc.get('pmid')
        doi = doc.get('doi')

        # Determine which score badge to show
        display_score = None
        score_label = None
        if human_score is not None:
            display_score = human_score
            score_label = "Human"
        elif ai_score is not None:
            display_score = ai_score
            score_label = "AI"
        elif relevance_score is not None:
            display_score = relevance_score
            score_label = "Rel"

        # Create collapsed title row with badges
        title_row = self._create_title_row(
            index, title, display_score, score_label
        )

        # Create subtitle with authors and publication info
        subtitle_text = self._create_subtitle(authors, publication, year)

        # Create expanded content sections
        content_sections = self._create_content_sections(
            doc=doc,
            title=title,
            authors=authors,
            publication=publication,
            year=year,
            abstract=abstract,
            doc_id=doc_id,
            pmid=pmid,
            doi=doi,
            context=context,
            ai_score=ai_score,
            human_score=human_score,
            relevance_score=relevance_score,
            scoring_reasoning=scoring_reasoning,
            citation_data=citation_data,
            on_score_change=on_score_change,
            on_score_approve=on_score_approve,
            show_scoring_controls=show_scoring_controls,
            index=index
        )

        # Create expansion tile
        return ft.ExpansionTile(
            title=title_row,
            subtitle=ft.Text(
                subtitle_text,
                size=11,
                color=ft.Colors.GREY_600
            ),
            controls=[
                ft.Container(
                    content=ft.Column(content_sections, spacing=8),
                    padding=ft.padding.all(10)
                )
            ],
            initially_expanded=False
        )

    def _create_title_row(
        self,
        index: int,
        title: str,
        score: Optional[float],
        score_label: Optional[str]
    ) -> ft.Row:
        """Create title row with truncated title and score badge."""
        # Truncate title for collapsed view
        display_title = self._truncate_text(title, 80)
        title_text = f"{index + 1}. {display_title}"

        title_widgets = [
            ft.Text(
                title_text,
                size=12,
                weight=ft.FontWeight.W_500,
                color=ft.Colors.BLUE_800,
                expand=True
            )
        ]

        # Add score badge if available
        if score is not None and score_label:
            score_badge = self._create_score_badge(score, score_label)
            title_widgets.append(score_badge)

        return ft.Row(
            title_widgets,
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN
        )

    def _create_score_badge(self, score: float, label: str) -> ft.Container:
        """Create colored score badge based on score value."""
        # Determine if this is 0-1 scale (relevance) or 1-5 scale (AI/human)
        if score <= 1.0:
            # 0-1 relevance score
            color = self._get_relevance_color(score)
            text = f"{score:.2f}"
        else:
            # 1-5 AI/human score
            color = self._get_score_color(score)
            text = f"{score:.1f}"

        return ft.Container(
            content=ft.Text(
                text,
                size=12,
                weight=ft.FontWeight.BOLD,
                color=ft.Colors.WHITE
            ),
            bgcolor=color,
            padding=ft.padding.symmetric(horizontal=10, vertical=5),
            border_radius=15,
            margin=ft.margin.only(left=10)
        )

    def _get_score_color(self, score: float) -> str:
        """Get color for 1-5 scale score."""
        if score >= 4.5:
            return ft.Colors.GREEN_700
        elif score >= 3.5:
            return ft.Colors.BLUE_700
        elif score >= 2.5:
            return ft.Colors.ORANGE_700
        else:
            return ft.Colors.RED_700

    def _get_relevance_color(self, score: float) -> str:
        """Get color for 0-1 scale relevance score."""
        if score >= 0.8:
            return ft.Colors.GREEN_700
        elif score >= 0.6:
            return ft.Colors.BLUE_700
        elif score >= 0.4:
            return ft.Colors.ORANGE_700
        else:
            return ft.Colors.RED_700

    def _create_subtitle(
        self,
        authors: str,
        publication: str,
        year: str
    ) -> str:
        """Create subtitle text with authors and publication info."""
        # Truncate authors if too long
        if isinstance(authors, list):
            authors_str = ', '.join(authors[:3])
            if len(authors) > 3:
                authors_str += '...'
        else:
            authors_str = str(authors)[:100]
            if len(str(authors)) > 100:
                authors_str += '...'

        # Build publication info
        pub_parts = []
        if publication and str(publication).strip() not in ['Unknown', 'None', '']:
            pub_parts.append(str(publication))
        if year and str(year) not in ['Unknown', 'Unknown year', 'None', '']:
            pub_parts.append(str(year))

        pub_info = ' • '.join(pub_parts) if pub_parts else 'Unknown publication'

        return f"{authors_str} | {pub_info}"

    def _create_content_sections(
        self,
        doc: Dict,
        title: str,
        authors: str,
        publication: str,
        year: str,
        abstract: str,
        doc_id: Any,
        pmid: Optional[str],
        doi: Optional[str],
        context: str,
        ai_score: Optional[float],
        human_score: Optional[float],
        relevance_score: Optional[float],
        scoring_reasoning: Optional[str],
        citation_data: Optional[Dict],
        on_score_change: Optional[Callable],
        on_score_approve: Optional[Callable],
        show_scoring_controls: bool,
        index: int
    ) -> List[ft.Control]:
        """Create all content sections for expanded card."""
        sections = []

        # Full title section
        sections.append(self._create_title_section(title))

        # Authors section
        sections.append(self._create_authors_section(authors))

        # Metadata section
        sections.append(self._create_metadata_section(
            publication, year, doc_id, pmid, doi, relevance_score
        ))

        # Scoring section (if applicable)
        if ai_score is not None or human_score is not None:
            sections.append(self._create_scoring_section(
                ai_score=ai_score,
                human_score=human_score,
                reasoning=scoring_reasoning,
                show_controls=show_scoring_controls,
                on_score_change=on_score_change,
                on_approve=on_score_approve,
                index=index
            ))

        # Citation-specific sections
        if citation_data:
            sections.append(self._create_citation_sections(citation_data))

        # Abstract section
        sections.append(self._create_abstract_section(abstract, citation_data))

        # Full-text access button
        sections.append(self._create_fulltext_button(doc))

        return sections

    def _create_title_section(self, title: str) -> ft.Container:
        """Create full title section."""
        return ft.Container(
            content=ft.Text(
                f"Title: {title}",
                size=11,
                weight=ft.FontWeight.BOLD,
                color=ft.Colors.BLUE_900
            ),
            padding=ft.padding.only(bottom=8)
        )

    def _create_authors_section(self, authors: str) -> ft.Container:
        """Create authors section."""
        if isinstance(authors, list):
            authors_str = ', '.join(authors)
        else:
            authors_str = str(authors)

        return ft.Container(
            content=ft.Text(
                f"Authors: {authors_str}",
                size=10,
                color=ft.Colors.GREY_700
            ),
            padding=ft.padding.only(bottom=8)
        )

    def _create_metadata_section(
        self,
        publication: str,
        year: str,
        doc_id: Any,
        pmid: Optional[str],
        doi: Optional[str],
        relevance_score: Optional[float]
    ) -> ft.Container:
        """Create metadata section with key-value pairs."""
        metadata_items = []

        if relevance_score is not None:
            metadata_items.append(
                ft.Text(f"Relevance Score: {relevance_score:.3f}", size=10, color=ft.Colors.GREY_600)
            )

        if publication and str(publication).strip() not in ['Unknown', 'None', '']:
            metadata_items.append(
                ft.Text(f"Publication: {publication}", size=10, color=ft.Colors.GREY_600)
            )

        if year and str(year) not in ['Unknown', 'Unknown year', 'None', '']:
            metadata_items.append(
                ft.Text(f"Year: {year}", size=10, color=ft.Colors.GREY_600)
            )

        metadata_items.append(
            ft.Text(f"Document ID: {doc_id}", size=10, color=ft.Colors.GREY_600)
        )

        if pmid:
            metadata_items.append(
                ft.Text(f"PMID: {pmid}", size=10, color=ft.Colors.GREY_600)
            )

        if doi:
            metadata_items.append(
                ft.Text(f"DOI: {doi}", size=10, color=ft.Colors.GREY_600)
            )

        return ft.Container(
            content=ft.Column(metadata_items, spacing=4),
            padding=ft.padding.all(8),
            bgcolor=ft.Colors.GREY_50,
            border_radius=5
        )

    def _create_scoring_section(
        self,
        ai_score: Optional[float],
        human_score: Optional[float],
        reasoning: Optional[str],
        show_controls: bool,
        on_score_change: Optional[Callable],
        on_approve: Optional[Callable],
        index: int
    ) -> ft.Container:
        """Create scoring information and controls section."""
        scoring_content = []

        # Display scores
        score_row_items = []

        if ai_score is not None:
            score_row_items.append(
                ft.Container(
                    content=ft.Column([
                        ft.Text("AI Score", size=11, weight=ft.FontWeight.BOLD),
                        ft.Text(
                            f"{ai_score:.1f}/5.0",
                            size=16,
                            weight=ft.FontWeight.BOLD,
                            color=self._get_score_color(ai_score)
                        )
                    ], spacing=2),
                    padding=ft.padding.all(8),
                    bgcolor=ft.Colors.WHITE,
                    border=ft.border.all(1, ft.Colors.GREY_300),
                    border_radius=5,
                    width=90
                )
            )

        if human_score is not None:
            score_row_items.append(
                ft.Container(
                    content=ft.Column([
                        ft.Text("Human Score", size=11, weight=ft.FontWeight.BOLD),
                        ft.Text(
                            f"{human_score:.1f}/5.0",
                            size=16,
                            weight=ft.FontWeight.BOLD,
                            color=self._get_score_color(human_score)
                        )
                    ], spacing=2),
                    padding=ft.padding.all(8),
                    bgcolor=ft.Colors.GREEN_50,
                    border=ft.border.all(1, ft.Colors.GREEN_300),
                    border_radius=5,
                    width=90
                )
            )

        if score_row_items:
            scoring_content.append(ft.Row(score_row_items, spacing=10))

        # Human scoring controls (if enabled)
        if show_controls and on_score_change:
            controls_row = self._create_scoring_controls(
                index, on_score_change, on_approve
            )
            scoring_content.append(controls_row)

        # Reasoning
        if reasoning:
            scoring_content.append(
                ft.Container(
                    content=ft.Column([
                        ft.Text("AI Reasoning:", size=10, weight=ft.FontWeight.BOLD),
                        ft.Text(reasoning, size=10, color=ft.Colors.GREY_700)
                    ], spacing=4),
                    padding=ft.padding.all(8),
                    bgcolor=ft.Colors.BLUE_50,
                    border_radius=5
                )
            )

        return ft.Container(
            content=ft.Column(scoring_content, spacing=8),
            padding=ft.padding.only(bottom=8)
        )

    def _create_scoring_controls(
        self,
        index: int,
        on_score_change: Callable,
        on_approve: Optional[Callable]
    ) -> ft.Row:
        """Create human scoring control widgets."""
        score_field = ft.TextField(
            label="Override Score (1-5)",
            hint_text="e.g., 4.5",
            width=150,
            height=50,
            keyboard_type=ft.KeyboardType.NUMBER,
            on_change=lambda e: on_score_change(index, e.control.value, "human") if e.control.value else None
        )

        controls = [score_field]

        if on_approve:
            approve_btn = ft.ElevatedButton(
                "Approve AI Score",
                icon=ft.Icons.CHECK_CIRCLE,
                on_click=lambda e: on_approve(index),
                height=40,
                style=ft.ButtonStyle(
                    bgcolor=ft.Colors.GREEN_600,
                    color=ft.Colors.WHITE
                )
            )
            controls.append(approve_btn)

        return ft.Row(controls, spacing=10)

    def _create_citation_sections(self, citation_data: Dict) -> ft.Container:
        """Create citation-specific sections (summary, passage, etc.)."""
        sections = []

        # Summary
        if citation_data.get('summary'):
            sections.append(
                ft.Container(
                    content=ft.Column([
                        ft.Text("Summary:", size=10, weight=ft.FontWeight.BOLD),
                        ft.Text(citation_data['summary'], size=10, color=ft.Colors.GREY_800)
                    ], spacing=4),
                    padding=ft.padding.all(8),
                    bgcolor=ft.Colors.GREEN_50,
                    border_radius=5
                )
            )

        # Cited passage (highlighted)
        if citation_data.get('passage'):
            sections.append(
                ft.Container(
                    content=ft.Column([
                        ft.Text(
                            "📌 Cited Passage:",
                            size=10,
                            weight=ft.FontWeight.BOLD
                        ),
                        ft.Text(
                            citation_data['passage'],
                            size=10,
                            color=ft.Colors.BLACK,
                            italic=True,
                            selectable=True
                        )
                    ], spacing=4),
                    padding=ft.padding.all(10),
                    bgcolor=ft.Colors.YELLOW_50,
                    border=ft.border.all(2, ft.Colors.YELLOW_600),
                    border_radius=5
                )
            )

        return ft.Container(
            content=ft.Column(sections, spacing=8),
            padding=ft.padding.only(bottom=8)
        ) if sections else ft.Container()

    def _create_abstract_section(
        self,
        abstract: str,
        citation_data: Optional[Dict]
    ) -> ft.Container:
        """Create abstract section, with highlighting if citation passage exists."""
        # If we have citation data with a passage, try to highlight it
        if citation_data and citation_data.get('passage'):
            abstract_widget = self._create_highlighted_abstract(
                abstract, citation_data['passage']
            )
            title = "Abstract with Highlighted Citation:"
        else:
            abstract_widget = ft.Text(
                abstract,
                size=10,
                color=ft.Colors.GREY_800,
                selectable=True
            )
            title = "Abstract:"

        return ft.Container(
            content=ft.Column([
                ft.Text(title, size=10, weight=ft.FontWeight.BOLD),
                abstract_widget
            ], spacing=4),
            padding=ft.padding.all(10),
            bgcolor=ft.Colors.GREY_50,
            border_radius=5
        )

    def _create_highlighted_abstract(
        self,
        abstract: str,
        passage: str
    ) -> ft.Text:
        """Create abstract text with highlighted passage."""
        # Simple highlighting: find passage in abstract and mark it
        passage_lower = passage.lower().strip()
        abstract_lower = abstract.lower()

        # Try to find exact match first
        passage_index = abstract_lower.find(passage_lower)

        if passage_index >= 0:
            # Found exact match - create rich text with highlighting
            before = abstract[:passage_index]
            highlighted = abstract[passage_index:passage_index + len(passage)]
            after = abstract[passage_index + len(passage):]

            return ft.Text(
                spans=[
                    ft.TextSpan(before, style=ft.TextStyle(size=10, color=ft.Colors.GREY_800)),
                    ft.TextSpan(
                        highlighted,
                        style=ft.TextStyle(
                            size=10,
                            color=ft.Colors.BLACK,
                            weight=ft.FontWeight.BOLD,
                            bgcolor=ft.Colors.YELLOW_200
                        )
                    ),
                    ft.TextSpan(after, style=ft.TextStyle(size=10, color=ft.Colors.GREY_800))
                ],
                selectable=True
            )
        else:
            # No exact match - just show abstract normally
            return ft.Text(
                abstract,
                size=10,
                color=ft.Colors.GREY_800,
                selectable=True
            )

    def _create_fulltext_button(self, doc: Dict) -> ft.Container:
        """Create full-text access button based on PDF availability."""
        from ..utils.pdf_manager import PDFManager
        from ..app import get_database_connection

        pdf_path = doc.get('pdf_path')
        pdf_url = doc.get('pdf_url')

        # If we have pdf_filename but no pdf_path, try to resolve it
        if not pdf_path and doc.get('pdf_filename'):
            try:
                db_conn = get_database_connection()
                pdf_manager = PDFManager(db_conn=db_conn)
                resolved_path = pdf_manager.get_pdf_path(doc, create_dirs=False)
                if db_conn:
                    db_conn.close()
                if resolved_path and resolved_path.exists():
                    pdf_path = str(resolved_path)
                    doc['pdf_path'] = pdf_path  # Update doc dict for next time
            except Exception as e:
                logger.warning(f"Failed to resolve PDF path: {e}")

        # Determine button type
        if pdf_path and Path(pdf_path).exists():
            # Full text available locally
            button = ft.ElevatedButton(
                "📄 View Full Text",
                icon=ft.Icons.PICTURE_AS_PDF,
                on_click=lambda e: self._view_pdf(doc),
                style=ft.ButtonStyle(
                    bgcolor=ft.Colors.BLUE_600,
                    color=ft.Colors.WHITE
                ),
                height=40
            )
        elif pdf_url:
            # URL available - can fetch
            button = ft.ElevatedButton(
                "⬇️ Fetch Full Text",
                icon=ft.Icons.DOWNLOAD,
                on_click=lambda e: self._fetch_pdf(doc, button),
                style=ft.ButtonStyle(
                    bgcolor=ft.Colors.ORANGE_600,
                    color=ft.Colors.WHITE
                ),
                height=40
            )
        else:
            # No PDF - allow manual upload
            button = ft.ElevatedButton(
                "📤 Upload Full Text",
                icon=ft.Icons.UPLOAD_FILE,
                on_click=lambda e: self._upload_pdf(doc, button),
                style=ft.ButtonStyle(
                    bgcolor=ft.Colors.GREEN_600,
                    color=ft.Colors.WHITE
                ),
                height=40
            )

        return ft.Container(
            content=ft.Row([button], alignment=ft.MainAxisAlignment.START),
            padding=ft.padding.only(top=8)
        )

    def _view_pdf(self, doc: Dict):
        """Open existing PDF in system viewer."""
        from .pdf_viewer_dialog import PDFViewerDialog

        pdf_path = Path(doc.get('pdf_path', ''))
        if pdf_path.exists():
            viewer = PDFViewerDialog(self.page)
            viewer.show_pdf(pdf_path, doc)
        else:
            self._show_error("PDF file not found at expected location")

    def _fetch_pdf(self, doc: Dict, button: ft.ElevatedButton):
        """Download PDF from URL."""
        from .pdf_viewer_dialog import PDFViewerDialog

        viewer = PDFViewerDialog(self.page)
        viewer.download_and_show_pdf(
            doc,
            on_success=lambda path: self._on_pdf_downloaded(doc, path, button),
            on_error=lambda msg: self._show_error(msg)
        )

    def _upload_pdf(self, doc: Dict, button: ft.ElevatedButton):
        """Show file picker to upload PDF manually."""
        from .pdf_viewer_dialog import PDFViewerDialog

        viewer = PDFViewerDialog(self.page)
        viewer.import_pdf(
            doc,
            on_success=lambda path: self._on_pdf_uploaded(doc, path, button),
            on_error=lambda msg: self._show_error(msg)
        )

    def _on_pdf_downloaded(self, doc: Dict, pdf_path: Path, button: ft.ElevatedButton):
        """Handle successful PDF download."""
        logger.info(f"PDF downloaded successfully for document {doc.get('id')}: {pdf_path}")

        # Update document dict with pdf_path so UI can show view button
        doc['pdf_path'] = str(pdf_path)

        # Update the button to show "View Full Text"
        button.text = "📄 View Full Text"
        button.icon = ft.Icons.PICTURE_AS_PDF
        button.on_click = lambda _: self._view_pdf(doc)
        button.style = ft.ButtonStyle(
            bgcolor=ft.Colors.BLUE_600,
            color=ft.Colors.WHITE
        )

        # Update the UI
        if self.page:
            self.page.update()

        # Show success snackbar
        if self.page:
            snack_bar = ft.SnackBar(
                content=ft.Text("✅ PDF downloaded! Click 'View Full Text' to open it."),
                bgcolor=ft.Colors.GREEN_700,
                duration=5000
            )
            self.page.open(snack_bar)

        if self.on_pdf_status_change:
            self.on_pdf_status_change(doc.get('id'), "downloaded")

    def _on_pdf_uploaded(self, doc: Dict, pdf_path: Path, button: ft.ElevatedButton):
        """Handle successful PDF upload."""
        logger.info(f"PDF uploaded successfully for document {doc.get('id')}: {pdf_path}")

        # Update document dict with pdf_path so UI can show view button
        doc['pdf_path'] = str(pdf_path)

        # Update the button to show "View Full Text"
        button.text = "📄 View Full Text"
        button.icon = ft.Icons.PICTURE_AS_PDF
        button.on_click = lambda _: self._view_pdf(doc)
        button.style = ft.ButtonStyle(
            bgcolor=ft.Colors.BLUE_600,
            color=ft.Colors.WHITE
        )

        # Update the UI
        if self.page:
            self.page.update()

        # Show success snackbar
        if self.page:
            snack_bar = ft.SnackBar(
                content=ft.Text("✅ PDF imported! Click 'View Full Text' to open it."),
                bgcolor=ft.Colors.GREEN_700,
                duration=5000
            )
            self.page.open(snack_bar)

        if self.on_pdf_status_change:
            self.on_pdf_status_change(doc.get('id'), "uploaded")

    def _show_error(self, message: str):
        """Show error dialog."""
        error_dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("Error", size=18, weight=ft.FontWeight.BOLD, color=ft.Colors.RED_700),
            content=ft.Text(message, size=14),
            actions=[
                ft.TextButton("OK", on_click=lambda e: self._close_dialog(error_dialog))
            ]
        )

        self.page.overlay.append(error_dialog)
        error_dialog.open = True
        self.page.update()

    def _close_dialog(self, dialog: ft.AlertDialog):
        """Close a dialog."""
        dialog.open = False
        self.page.update()

    def _extract_year(self, doc: Dict) -> str:
        """Extract year from document publication date or year field."""
        publication_date = doc.get('publication_date')
        if publication_date and str(publication_date).strip() not in ['', 'Unknown', 'None']:
            date_str = str(publication_date).strip()
            if '-' in date_str:
                return date_str.split('-')[0]
            return date_str

        year = doc.get('year', 'Unknown year')
        return str(year) if year else 'Unknown year'

    def _truncate_text(self, text: str, max_length: int) -> str:
        """Truncate text to max length with ellipsis."""
        if len(text) <= max_length:
            return text
        return text[:max_length] + "..."


# Convenience functions for backward compatibility and easy use

def create_literature_card(page: ft.Page, index: int, doc: Dict, **kwargs) -> ft.ExpansionTile:
    """Create a document card for literature search results."""
    card_creator = UnifiedDocumentCard(page, **kwargs)
    return card_creator.create_card(index, doc, context=DocumentCardContext.LITERATURE)


def create_scored_card(
    page: ft.Page,
    index: int,
    doc: Dict,
    ai_score: float,
    reasoning: str = None,
    show_controls: bool = False,
    **kwargs
) -> ft.ExpansionTile:
    """Create a document card with AI scoring."""
    card_creator = UnifiedDocumentCard(page, **kwargs)
    return card_creator.create_card(
        index, doc,
        context=DocumentCardContext.SCORING,
        ai_score=ai_score,
        scoring_reasoning=reasoning,
        show_scoring_controls=show_controls
    )


def create_citation_card(
    page: ft.Page,
    index: int,
    doc: Dict,
    citation_data: Dict,
    **kwargs
) -> ft.ExpansionTile:
    """Create a document card for citations view."""
    card_creator = UnifiedDocumentCard(page, **kwargs)
    return card_creator.create_card(
        index, doc,
        context=DocumentCardContext.CITATIONS,
        citation_data=citation_data,
        relevance_score=citation_data.get('relevance_score')
    )
