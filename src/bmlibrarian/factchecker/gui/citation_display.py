"""
Citation display components for Fact Checker Review GUI.

Leverages BMLibrarian GUI utilities for citation cards and text highlighting.
"""

from typing import Dict, List, Optional, Any
import flet as ft

# Import BMLibrarian GUI utilities
try:
    from bmlibrarian.gui.citation_card_utils import extract_citation_data, create_citation_metadata
    from bmlibrarian.gui.text_highlighting import create_highlighted_abstract
    from bmlibrarian.gui.ui_builder import (
        create_expandable_card,
        create_relevance_badge,
        create_metadata_section,
        create_text_content_section,
        truncate_text
    )
    GUI_UTILS_AVAILABLE = True
except ImportError:
    GUI_UTILS_AVAILABLE = False


# Import PostgreSQL database manager for fetching abstracts
try:
    from bmlibrarian.database import get_db_manager
    DB_AVAILABLE = True
except ImportError:
    DB_AVAILABLE = False


class CitationDisplay:
    """Manages citation display with abstract fetching and highlighting."""

    def __init__(self):
        """Initialize citation display."""
        self.db_manager = None

        # Initialize database manager if available
        if DB_AVAILABLE:
            try:
                self.db_manager = get_db_manager()
                print("✓ PostgreSQL database manager initialized successfully")
            except Exception as e:
                print(f"Warning: Could not initialize PostgreSQL database manager: {e}")
                self.db_manager = None

    def _fetch_abstract_by_pmid(self, pmid: str) -> Optional[str]:
        """Fetch full abstract from database using PMID."""
        if not self.db_manager or not pmid:
            return None

        clean_pmid = pmid.replace('PMID:', '').replace('pmid:', '').strip()

        try:
            with self.db_manager.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        "SELECT abstract FROM document WHERE external_id = %s",
                        (clean_pmid,)
                    )
                    result = cursor.fetchone()
                    return result[0] if result else None
        except Exception as e:
            print(f"Error fetching abstract for PMID {pmid}: {e}")
            return None

    def _fetch_abstract_by_doi(self, doi: str) -> Optional[str]:
        """Fetch full abstract from database using DOI."""
        if not self.db_manager or not doi:
            return None

        clean_doi = doi.replace('DOI:', '').replace('doi:', '').strip()

        try:
            with self.db_manager.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        "SELECT abstract FROM document WHERE doi = %s",
                        (clean_doi,)
                    )
                    result = cursor.fetchone()
                    return result[0] if result else None
        except Exception as e:
            print(f"Error fetching abstract for DOI {doi}: {e}")
            return None

    def _fetch_document_abstract(self, document_id: str) -> Optional[str]:
        """Fetch full abstract from database by document ID."""
        if not self.db_manager or not document_id:
            return None

        try:
            with self.db_manager.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        "SELECT abstract FROM document WHERE id = %s",
                        (document_id,)
                    )
                    result = cursor.fetchone()
                    return result[0] if result else None
        except Exception as e:
            print(f"Error fetching abstract for document {document_id}: {e}")
            return None

    def _enrich_evidence_with_identifiers(self, evidence: Dict[str, Any]) -> Dict[str, Any]:
        """Enrich evidence with missing identifiers by looking up in database."""
        if not self.db_manager:
            return evidence

        # If we already have document_id and pmid, no need to enrich
        if evidence.get('document_id') and evidence.get('pmid'):
            return evidence

        # Try to enrich using DOI
        doi = evidence.get('doi', '')
        if doi:
            clean_doi = doi.replace('DOI:', '').replace('doi:', '').strip()
            try:
                with self.db_manager.get_connection() as conn:
                    with conn.cursor() as cursor:
                        cursor.execute(
                            "SELECT id, external_id FROM document WHERE doi = %s",
                            (clean_doi,)
                        )
                        result = cursor.fetchone()
                        if result:
                            if not evidence.get('document_id'):
                                evidence['document_id'] = str(result[0])
                            if not evidence.get('pmid') and result[1]:
                                evidence['pmid'] = f"PMID:{result[1]}"
            except Exception as e:
                print(f"Warning: Could not enrich evidence with identifiers: {e}")

        return evidence

    def create_citation_card(self, index: int, evidence: Dict[str, Any]) -> ft.Control:
        """
        Create an expandable citation card.

        Args:
            index: Citation index
            evidence: Evidence dictionary

        Returns:
            Flet control for citation card
        """
        # Enrich evidence with missing identifiers
        enriched_evidence = self._enrich_evidence_with_identifiers(evidence)

        if GUI_UTILS_AVAILABLE:
            return self._create_expandable_citation_card(index, enriched_evidence)
        else:
            return self._create_simple_citation_card(index + 1, enriched_evidence)

    def _create_expandable_citation_card(self, index: int, evidence: Dict[str, Any]) -> ft.ExpansionTile:
        """Create an expandable card with full abstract and highlighting."""
        citation_text = evidence.get('citation', 'No citation text available')
        pmid = evidence.get('pmid', '')
        doi = evidence.get('doi', '')
        document_id = evidence.get('document_id', '')
        relevance_score = evidence.get('relevance_score', 0)
        stance = evidence.get('stance', 'neutral')

        # Fetch full abstract from database
        abstract = None
        if self.db_manager:
            if document_id:
                abstract = self._fetch_document_abstract(document_id)
            elif pmid:
                abstract = self._fetch_abstract_by_pmid(pmid)
            elif doi:
                abstract = self._fetch_abstract_by_doi(doi)

        # Determine stance styling
        if stance == 'supports':
            stance_badge_color = ft.Colors.GREEN_700
            stance_icon = "✓"
            stance_display = "SUPPORTS"
        elif stance == 'contradicts':
            stance_badge_color = ft.Colors.RED_700
            stance_icon = "✗"
            stance_display = "CONTRADICTS"
        else:
            stance_badge_color = ft.Colors.GREY_600
            stance_icon = "?"
            stance_display = "NEUTRAL" if stance else "UNKNOWN"

        # Create title
        truncated_citation = truncate_text(citation_text, 80)
        title_text = f"{index + 1}. {truncated_citation}"

        # Create stance badge
        stance_badge = ft.Container(
            content=ft.Text(
                f"{stance_icon} {stance_display}",
                size=10,
                weight=ft.FontWeight.BOLD,
                color=ft.Colors.WHITE,
                selectable=True
            ),
            bgcolor=stance_badge_color,
            padding=ft.padding.symmetric(horizontal=8, vertical=4),
            border_radius=12
        )

        # Create relevance badge
        relevance_badge = create_relevance_badge(relevance_score)

        # Create subtitle
        identifier_parts = []
        if pmid:
            identifier_parts.append(pmid)
        if doi:
            identifier_parts.append(doi)
        if document_id:
            identifier_parts.append(f"Doc: {document_id}")
        subtitle_text = " | ".join(identifier_parts) if identifier_parts else "No identifier"

        # Create content sections
        content_sections = []

        # Metadata section
        metadata_items = [
            ("Stance", stance_display),
            ("Relevance Score", f"{relevance_score:.3f}" if relevance_score else "N/A"),
        ]
        if pmid:
            metadata_items.append(("PMID", pmid))
        if doi:
            metadata_items.append(("DOI", doi))
        if document_id:
            metadata_items.append(("Document ID", document_id))

        content_sections.append(create_metadata_section(metadata_items, ft.Colors.BLUE_50))

        # Citation passage section
        content_sections.append(create_text_content_section(
            "Extracted Citation:",
            citation_text,
            ft.Colors.YELLOW_100
        ))

        # Abstract with highlighting if available
        if abstract:
            content_sections.append(
                ft.Container(
                    content=ft.Column([
                        ft.Text("Full Abstract with Highlighted Citation:",
                               size=10, weight=ft.FontWeight.BOLD),
                        create_highlighted_abstract(abstract, citation_text)
                    ], spacing=5),
                    padding=ft.padding.all(10),
                    bgcolor=ft.Colors.GREY_50,
                    border_radius=5,
                    border=ft.border.all(1, ft.Colors.GREY_300)
                )
            )
        else:
            content_sections.append(
                ft.Container(
                    content=ft.Text(
                        "ℹ️ Full abstract not available" + (" (database not connected)" if not self.db_manager else ""),
                        size=10,
                        color=ft.Colors.GREY_600,
                        italic=True
                    ),
                    padding=ft.padding.all(10)
                )
            )

        return create_expandable_card(
            title_text,
            subtitle_text,
            content_sections,
            [stance_badge, relevance_badge]
        )

    def _create_simple_citation_card(self, index: int, evidence: Dict[str, Any]) -> ft.Container:
        """Create a simple citation card fallback."""
        stance = evidence.get('stance', 'neutral')
        if stance == 'supports':
            stance_color = ft.Colors.GREEN_100
            stance_border = ft.Colors.GREEN_500
            stance_display = "SUPPORTS"
        elif stance == 'contradicts':
            stance_color = ft.Colors.RED_100
            stance_border = ft.Colors.RED_500
            stance_display = "CONTRADICTS"
        else:
            stance_color = ft.Colors.GREY_100
            stance_border = ft.Colors.GREY_400
            stance_display = "NEUTRAL" if stance else "UNKNOWN"

        return ft.Container(
            content=ft.Column([
                ft.Text(
                    f"Citation {index}: {stance_display}",
                    size=13,
                    weight=ft.FontWeight.BOLD
                ),
                ft.Text(
                    evidence.get('citation', 'No citation text'),
                    size=12,
                    selectable=True
                )
            ], spacing=5),
            padding=ft.padding.all(12),
            bgcolor=stance_color,
            border_radius=8,
            border=ft.border.all(1, stance_border)
        )

    def create_citations_list(self, evidence_list: List[Dict[str, Any]]) -> ft.Column:
        """
        Create scrollable list of citation cards.

        Args:
            evidence_list: List of evidence dictionaries

        Returns:
            Column containing citation cards
        """
        citations_column = ft.Column(
            controls=[],
            spacing=10,
            scroll=ft.ScrollMode.AUTO
        )

        if not evidence_list:
            citations_column.controls.append(
                ft.Text("No citations available", size=12, color=ft.Colors.GREY_500, italic=True)
            )
            return citations_column

        for i, evidence in enumerate(evidence_list):
            citation_card = self.create_citation_card(i, evidence)
            citations_column.controls.append(citation_card)

        return citations_column
