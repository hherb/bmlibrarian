"""Unified Document Card Demo

Demonstrates the unified document card component across different contexts:
- Literature search results
- Document scoring interface
- Citations view
- Counterfactual evidence

The cards maintain consistent appearance while showing context-specific features.
"""

import flet as ft
from pathlib import Path
import sys

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.bmlibrarian.gui.unified_document_card import (
    UnifiedDocumentCard,
    DocumentCardContext,
    create_literature_card,
    create_scored_card,
    create_citation_card
)


def main(page: ft.Page):
    """Demo application showing unified document cards in different contexts."""
    page.title = "Unified Document Card Demo"
    page.padding = 20
    page.scroll = "auto"

    # Sample document data
    sample_doc = {
        'id': 64396205,
        'title': 'Utility of Bedside Ultrasound Measurement of Optic Nerve Sheath Diameter as a Screening Tool for raised Intracranial Pressure in Neurocritical Care',
        'authors': ['Gurav Sushma', 'Zirpe Kapil', 'Bhoyar Abhaya', 'Deshmukh Abhijeet', 'Pote Prajakta'],
        'publication': 'The Journal of the Association of Physicians of India',
        'year': '2023',
        'publication_date': '2023-01-01',
        'abstract': 'Intracranial pressure (ICP) needs to be monitored in neurocritical patients. There is a need for portable bedside optic nerve ultrasound (ONUS) for early diagnosis to initiate the measures to reduce ICP to find out utility of bedside ONUS to diagnose raised ICP in neurocritical care. Materials and methods: After obtaining the ethical committee, a prospective observational study was conducted. Optic nerve sheath diameter (ONSD) was measured in two groups: control group patients with neurological symptoms but computed tomography (CT)/magnetic resonance imaging (MRI) not suggestive of raised ICP, and second was study group patients with neurological symptoms and CT/MRI suggestive of elevated ICP Result: In patients with normal ICP, the mean ONSD in females was 4.47mm, and in males was 4.66mm. In patients with raised ICP, the mean ONSD in females was 6.45 ± 0.78 mm, and in males was 6.33 ± 0.70 mm. At a cut-off value of >4.8 mm, the sensitivity and specificity are 100% to diagnose raised ICP.',
        'pmid': '37449686',
        'doi': '10.59556/japi.71.0287',
        'pdf_path': None,  # No PDF available
        'pdf_url': 'https://example.com/paper.pdf'  # URL available for download
    }

    # Create card creator instance
    card_creator = UnifiedDocumentCard(page)

    def on_score_change(index: int, score: str, score_type: str):
        """Handle score change."""
        try:
            score_val = float(score)
            print(f"Score changed for doc {index}: {score_val} ({score_type})")
        except ValueError:
            print(f"Invalid score: {score}")

    def on_score_approve(index: int):
        """Handle score approval."""
        print(f"AI score approved for doc {index}")

    # Header
    page.add(
        ft.Text(
            "Unified Document Card Demo",
            size=28,
            weight=ft.FontWeight.BOLD,
            color=ft.Colors.BLUE_700
        ),
        ft.Text(
            "Consistent document cards across all contexts",
            size=14,
            color=ft.Colors.GREY_600
        ),
        ft.Divider(height=20)
    )

    # Demo 1: Literature Search Card
    page.add(
        ft.Text(
            "1. Literature Search Results",
            size=20,
            weight=ft.FontWeight.BOLD,
            color=ft.Colors.BLUE_600
        ),
        ft.Text(
            "Basic document card with full-text access button",
            size=12,
            color=ft.Colors.GREY_600
        )
    )

    literature_card = card_creator.create_card(
        index=0,
        doc=sample_doc,
        context=DocumentCardContext.LITERATURE
    )
    page.add(literature_card, ft.Divider(height=20))

    # Demo 2: Document Scoring Card
    page.add(
        ft.Text(
            "2. Document Scoring Interface",
            size=20,
            weight=ft.FontWeight.BOLD,
            color=ft.Colors.BLUE_600
        ),
        ft.Text(
            "Card with AI score, reasoning, and human override controls",
            size=12,
            color=ft.Colors.GREY_600
        )
    )

    scoring_card = card_creator.create_card(
        index=1,
        doc=sample_doc,
        context=DocumentCardContext.SCORING,
        ai_score=4.5,
        scoring_reasoning="This passage directly provides the cutoff ONSD measurement of greater than 4.8mm that indicates raised intracranial pressure with perfect sensitivity and specificity based on this study's findings.",
        show_scoring_controls=True,
        on_score_change=on_score_change,
        on_score_approve=on_score_approve
    )
    page.add(scoring_card, ft.Divider(height=20))

    # Demo 3: Citation Card
    page.add(
        ft.Text(
            "3. Citations View",
            size=20,
            weight=ft.FontWeight.BOLD,
            color=ft.Colors.BLUE_600
        ),
        ft.Text(
            "Card with citation summary, passage, and relevance score",
            size=12,
            color=ft.Colors.GREY_600
        )
    )

    citation_data = {
        'summary': 'This passage directly provides the cutoff value for raised ICP based on optic nerve sheath diameter (ONSD) measurements using ultrasound, which is what the user asked about.',
        'passage': 'At a cut-off value of >4.8 mm, the sensitivity and specificity are 100% to diagnose raised ICP.',
        'relevance_score': 0.95
    }

    citation_card = card_creator.create_card(
        index=2,
        doc=sample_doc,
        context=DocumentCardContext.CITATIONS,
        citation_data=citation_data,
        relevance_score=0.95
    )
    page.add(citation_card, ft.Divider(height=20))

    # Demo 4: Card with Human Score Override
    page.add(
        ft.Text(
            "4. Human-Scored Document",
            size=20,
            weight=ft.FontWeight.BOLD,
            color=ft.Colors.BLUE_600
        ),
        ft.Text(
            "Card showing both AI and human scores",
            size=12,
            color=ft.Colors.GREY_600
        )
    )

    human_scored_card = card_creator.create_card(
        index=3,
        doc=sample_doc,
        context=DocumentCardContext.SCORING,
        ai_score=4.5,
        human_score=5.0,
        scoring_reasoning="Original AI assessment was high quality.",
        show_scoring_controls=False
    )
    page.add(human_scored_card, ft.Divider(height=20))

    # Demo 5: Document with Local PDF
    page.add(
        ft.Text(
            "5. Document with Local PDF",
            size=20,
            weight=ft.FontWeight.BOLD,
            color=ft.Colors.BLUE_600
        ),
        ft.Text(
            "Card with 'View Full Text' button for locally available PDF",
            size=12,
            color=ft.Colors.GREY_600
        )
    )

    doc_with_pdf = sample_doc.copy()
    doc_with_pdf['pdf_path'] = '/path/to/existing/document.pdf'

    pdf_card = card_creator.create_card(
        index=4,
        doc=doc_with_pdf,
        context=DocumentCardContext.LITERATURE
    )
    page.add(pdf_card, ft.Divider(height=20))

    # Demo 6: Document with No PDF Source
    page.add(
        ft.Text(
            "6. Document Requiring Manual Upload",
            size=20,
            weight=ft.FontWeight.BOLD,
            color=ft.Colors.BLUE_600
        ),
        ft.Text(
            "Card with 'Upload Full Text' button when no URL is available",
            size=12,
            color=ft.Colors.GREY_600
        )
    )

    doc_no_pdf = sample_doc.copy()
    doc_no_pdf['pdf_path'] = None
    doc_no_pdf['pdf_url'] = None

    upload_card = card_creator.create_card(
        index=5,
        doc=doc_no_pdf,
        context=DocumentCardContext.LITERATURE
    )
    page.add(upload_card)

    # Instructions
    page.add(
        ft.Divider(height=30),
        ft.Container(
            content=ft.Column([
                ft.Text(
                    "Key Features:",
                    size=16,
                    weight=ft.FontWeight.BOLD,
                    color=ft.Colors.BLUE_700
                ),
                ft.Text("• Collapsible cards with title and score visible when collapsed", size=12),
                ft.Text("• Consistent appearance across all contexts (literature, scoring, citations, etc.)", size=12),
                ft.Text("• Context-specific features appear only when relevant", size=12),
                ft.Text("• Smart full-text access buttons:", size=12),
                ft.Text("  - 'View Full Text' if PDF exists locally", size=11, color=ft.Colors.GREY_700),
                ft.Text("  - 'Fetch Full Text' if URL is available", size=11, color=ft.Colors.GREY_700),
                ft.Text("  - 'Upload Full Text' if no source is available", size=11, color=ft.Colors.GREY_700),
                ft.Text("• AI and human scores with color-coded badges", size=12),
                ft.Text("• Relevance scores for citations (0-1 scale)", size=12),
                ft.Text("• Citation highlighting in abstracts", size=12),
                ft.Text("• Human-in-the-loop scoring controls when needed", size=12),
            ], spacing=8),
            padding=ft.padding.all(15),
            bgcolor=ft.Colors.BLUE_50,
            border_radius=10
        )
    )


if __name__ == "__main__":
    ft.app(target=main)
