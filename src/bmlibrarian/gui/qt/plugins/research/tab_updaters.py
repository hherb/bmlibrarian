"""
Tab updater functions for the Research Tab.

This module contains pure functions that update tab content with data.
These functions handle populating tabs with documents, citations, and
analysis results.
"""

import logging
from typing import Optional, Any, List, Tuple, Protocol, Union

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QFrame,
    QLayout,
)
from PySide6.QtCore import Qt

from .constants import UIConstants, StyleSheets
from bmlibrarian.gui.document_card_factory_base import DocumentCardData, CardContext


class CardFactoryProtocol(Protocol):
    """Protocol defining the interface for document card factories."""

    def create_card(self, card_data: DocumentCardData) -> QWidget:
        """Create a document card from card data."""
        ...


def clear_layout_widgets(layout: Union[QVBoxLayout, QHBoxLayout, QLayout]) -> None:
    """
    Safely clear all widgets from a layout with proper cleanup.

    This function properly cleans up widgets by removing them from the layout
    and scheduling them for deletion. PySide6 will automatically handle
    signal disconnection when widgets are deleted.

    Args:
        layout: The layout to clear (QVBoxLayout, QHBoxLayout, or QLayout)
    """
    while layout.count():
        child = layout.takeAt(0)
        if child.widget():
            widget = child.widget()
            if widget:  # Type guard for None check
                # Set parent to None to ensure immediate cleanup
                widget.setParent(None)
                # Schedule deletion (PySide6 handles signal disconnection automatically)
                widget.deleteLater()
        elif child.layout():
            # Recursively clear nested layouts
            nested_layout = child.layout()
            if nested_layout:  # Type guard for None check
                clear_layout_widgets(nested_layout)


def _extract_year_from_document(doc: dict) -> Optional[int]:
    """
    Extract year from document dictionary.

    Args:
        doc: Document dictionary with publication_date or year field

    Returns:
        Year as integer, or None if not available
    """
    publication_date = doc.get('publication_date', '')
    year = doc.get('year', '')

    if publication_date and publication_date != 'Unknown':
        try:
            return int(str(publication_date)[:4]) if len(str(publication_date)) >= 4 else None
        except (ValueError, TypeError):
            pass

    if year:
        try:
            return int(year)
        except (ValueError, TypeError):
            pass

    return None


def create_document_card_data(
    doc: dict,
    context: CardContext,
    relevance_score: Optional[float] = None,
    show_abstract: bool = True,
    show_metadata: bool = True,
    show_pdf_button: bool = True,
    expanded_by_default: bool = False
) -> DocumentCardData:
    """
    Create DocumentCardData from a document dictionary.

    Args:
        doc: Document dictionary with metadata
        context: Card context (LITERATURE, COUNTERFACTUAL, etc.)
        relevance_score: Optional relevance score
        show_abstract: Whether to show abstract
        show_metadata: Whether to show metadata
        show_pdf_button: Whether to show PDF button
        expanded_by_default: Whether card is expanded by default

    Returns:
        DocumentCardData instance
    """
    return DocumentCardData(
        doc_id=doc.get('id', 0),
        title=doc.get('title', 'Untitled Document'),
        abstract=doc.get('abstract', ''),
        authors=doc.get('authors', []),
        year=_extract_year_from_document(doc),
        journal=doc.get('publication', ''),
        pmid=doc.get('pmid'),
        doi=doc.get('doi'),
        source=doc.get('source'),
        relevance_score=relevance_score,
        pdf_url=doc.get('pdf_url'),
        context=context,
        show_abstract=show_abstract,
        show_metadata=show_metadata,
        show_pdf_button=show_pdf_button,
        expanded_by_default=expanded_by_default
    )


def add_reasoning_section(
    card: QWidget,
    reasoning: str,
    ui: UIConstants
) -> None:
    """
    Add AI reasoning section to a document card.

    Args:
        card: Document card widget (must have details_layout attribute)
        reasoning: AI reasoning text
        ui: UI constants for styling
    """
    if not reasoning or not hasattr(card, 'details_layout'):
        return

    reasoning_container = QFrame()
    reasoning_container.setStyleSheet(StyleSheets.reasoning_box(ui))
    reasoning_layout = QVBoxLayout(reasoning_container)
    reasoning_layout.setContentsMargins(
        ui.CARD_PADDING, ui.CARD_PADDING,
        ui.CARD_PADDING, ui.CARD_PADDING
    )
    reasoning_layout.setSpacing(ui.CARD_INTERNAL_SPACING)

    reasoning_title = QLabel("<b>AI Reasoning:</b>")
    reasoning_layout.addWidget(reasoning_title)

    reasoning_text = QLabel(reasoning)
    reasoning_text.setWordWrap(True)
    reasoning_text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    reasoning_layout.addWidget(reasoning_text)

    # Insert at the beginning of details_layout (before abstract)
    card.details_layout.insertWidget(0, reasoning_container)


def populate_unscored_documents(
    layout: QVBoxLayout,
    documents: List[dict],
    card_factory: CardFactoryProtocol,
    ui: UIConstants,
    logger: Optional[logging.Logger] = None
) -> int:
    """
    Populate a layout with unscored documents.

    This shows documents immediately after search, before scoring happens.
    Documents are displayed with basic metadata only (no scores).

    Args:
        layout: Layout to add cards to
        documents: List of document dictionaries
        card_factory: QtDocumentCardFactory instance
        ui: UI constants for styling
        logger: Optional logger for error reporting

    Returns:
        Number of cards successfully created
    """
    logger = logger or logging.getLogger(__name__)

    try:
        clear_layout_widgets(layout)
    except Exception as e:
        logger.warning(f"Error clearing layout (will continue): {e}")

    if not documents:
        # Show empty state
        empty_label = QLabel("No documents to display")
        empty_label.setStyleSheet(StyleSheets.empty_state_label(ui))
        empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(empty_label)
        layout.addStretch()
        return 0

    # Create simple document cards (without scores)
    cards_created = 0
    for i, doc in enumerate(documents):
        try:
            # Create fake score_result with "pending" status for display
            score_result = {
                'score': 0,
                'reasoning': 'Awaiting relevance scoring...',
                'confidence': 0,
                'pending': True
            }
            card = create_document_score_card(
                i + 1, doc, score_result, card_factory, ui, logger
            )
            layout.addWidget(card)
            cards_created += 1
        except Exception as e:
            logger.error(f"Error creating card for document {i+1}: {e}", exc_info=True)

    # Add stretch at the end
    layout.addStretch()

    logger.info(f"Literature tab populated with {cards_created}/{len(documents)} unscored documents")
    return cards_created


def update_literature_tab(
    layout: QVBoxLayout,
    scored_documents: List[Tuple[dict, dict]],
    card_factory: CardFactoryProtocol,
    ui: UIConstants,
    logger: Optional[logging.Logger] = None
) -> int:
    """
    Update a layout with scored documents.

    Args:
        layout: Layout to add cards to
        scored_documents: List of (document, score_result) tuples
        card_factory: QtDocumentCardFactory instance
        ui: UI constants for styling
        logger: Optional logger for error reporting

    Returns:
        Number of cards successfully created
    """
    logger = logger or logging.getLogger(__name__)

    try:
        clear_layout_widgets(layout)
    except Exception as e:
        logger.warning(f"Error clearing layout (will continue): {e}")

    if not scored_documents:
        # Show empty state
        empty_label = QLabel("No documents to display")
        empty_label.setStyleSheet(StyleSheets.empty_state_label(ui))
        empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(empty_label)
        layout.addStretch()
        return 0

    # Sort by score (highest first)
    sorted_docs = sorted(
        scored_documents,
        key=lambda x: x[1].get('score', 0),
        reverse=True
    )

    # Create document cards
    cards_created = 0
    for i, (doc, score_result) in enumerate(sorted_docs):
        try:
            card = create_document_score_card(
                i + 1, doc, score_result, card_factory, ui, logger
            )
            layout.addWidget(card)
            cards_created += 1
        except Exception as e:
            logger.error(f"Error creating card for document {i+1}: {e}", exc_info=True)

    # Add stretch at the end
    layout.addStretch()

    logger.info(f"Literature tab updated with {cards_created}/{len(scored_documents)} documents")
    return cards_created


def create_document_score_card(
    index: int,
    doc: dict,
    score_result: dict,
    card_factory: CardFactoryProtocol,
    ui: UIConstants,
    logger: Optional[logging.Logger] = None
) -> QWidget:
    """
    Create a collapsible document card showing score and metadata using the factory.

    Args:
        index: Document number (for display)
        doc: Document dictionary
        score_result: Scoring result dictionary
        card_factory: QtDocumentCardFactory instance
        ui: UI constants for styling
        logger: Optional logger for error reporting

    Returns:
        QWidget containing the collapsible document card
    """
    logger = logger or logging.getLogger(__name__)

    try:
        # Extract score information
        score = score_result.get('score', 0)
        reasoning = score_result.get('reasoning', '')
        is_pending = score_result.get('pending', False)

        # Create DocumentCardData
        card_data = create_document_card_data(
            doc,
            context=CardContext.LITERATURE,
            relevance_score=score if not is_pending else None,
            show_abstract=True,
            show_metadata=True,
            show_pdf_button=True,
            expanded_by_default=False
        )

        # Create card using factory
        card = card_factory.create_card(card_data)

        # Add AI reasoning section if available (prepend to details_layout)
        if reasoning and not is_pending:
            add_reasoning_section(card, reasoning, ui)

        return card

    except Exception as e:
        logger.error(f"Error creating document card using factory: {e}", exc_info=True)
        # Fallback to a simple error card
        error_widget = QLabel(f"Error displaying document: {str(e)}")
        error_widget.setStyleSheet(StyleSheets.error_label())
        return error_widget


def update_citations_tab(
    layout: QVBoxLayout,
    citations: List[Any],
    ui: UIConstants,
    logger: Optional[logging.Logger] = None
) -> int:
    """
    Update the Citations tab with extracted citations using CitationCard widget.

    Args:
        layout: Layout to add cards to
        citations: List of citation dictionaries or citation objects
        ui: UI constants for styling
        logger: Optional logger for error reporting

    Returns:
        Number of cards successfully created
    """
    logger = logger or logging.getLogger(__name__)

    try:
        clear_layout_widgets(layout)
    except Exception as e:
        logger.warning(f"Error clearing layout (will continue): {e}")

    if not citations:
        # Show empty state
        empty_label = QLabel("No citations to display")
        empty_label.setStyleSheet(StyleSheets.empty_state_label(ui))
        empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(empty_label)
        layout.addStretch()
        return 0

    # Import CitationCard widget
    from ...widgets.citation_card import CitationCard

    # Create citation cards using the CitationCard widget
    cards_created = 0
    for i, citation in enumerate(citations):
        try:
            card = CitationCard(citation_data=citation, index=i + 1)
            layout.addWidget(card)
            cards_created += 1
        except Exception as e:
            logger.error(f"Error creating citation card {i+1}: {e}", exc_info=True)

    # Add stretch at the end
    layout.addStretch()

    logger.info(f"Citations tab updated with {cards_created}/{len(citations)} citations using CitationCard widget")
    return cards_created


def update_counterfactual_tab(
    layout: QVBoxLayout,
    summary_label: QLabel,
    results: dict,
    card_factory: CardFactoryProtocol,
    ui: UIConstants,
    logger: Optional[logging.Logger] = None
) -> None:
    """
    Update the Counterfactual tab with analysis results.

    Args:
        layout: Layout to add content to
        summary_label: Summary label to update
        results: Dictionary containing counterfactual analysis results
        card_factory: QtDocumentCardFactory instance
        ui: UI constants for styling
        logger: Optional logger for error reporting
    """
    logger = logger or logging.getLogger(__name__)

    try:
        # Clear existing widgets
        clear_layout_widgets(layout)

        # Update summary label
        question_count = results.get('question_count', 0)
        doc_count = results.get('document_count', 0)
        summary_label.setText(
            f"Analysis complete | {question_count} counterfactual questions | "
            f"{doc_count} potentially contradictory documents found"
        )

        if question_count == 0:
            # Show message if no questions generated
            no_questions_label = QLabel("No counterfactual questions were generated.")
            no_questions_label.setStyleSheet(StyleSheets.empty_state_label(ui))
            no_questions_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(no_questions_label)
            layout.addStretch()
            return

        # Display counterfactual questions
        questions = results.get('questions', [])
        for i, question in enumerate(questions, 1):
            card = _create_counterfactual_question_card(i, question, ui)
            layout.addWidget(card)

        # Display contradictory documents using document card factory
        contradictory_docs = results.get('contradictory_documents', [])
        if contradictory_docs:
            _add_contradictory_documents_section(
                layout, contradictory_docs, card_factory, ui, logger
            )

        # Display contradictory citations
        contradictory_citations = results.get('contradictory_citations', [])
        if contradictory_citations:
            _add_contradictory_citations_section(
                layout, contradictory_citations, ui, logger
            )

        layout.addStretch()

    except Exception as e:
        logger.error(f"Error updating counterfactual tab: {e}", exc_info=True)


def _create_counterfactual_question_card(
    index: int,
    question: Any,
    ui: UIConstants
) -> QFrame:
    """
    Create a card displaying a counterfactual question.

    Args:
        index: Question number
        question: Question object with question, reasoning, etc. attributes
        ui: UI constants for styling

    Returns:
        QFrame containing the question card
    """
    card = QFrame()
    card.setFrameShape(QFrame.Shape.StyledPanel)
    card.setStyleSheet(StyleSheets.counterfactual_card(ui))

    card_layout = QVBoxLayout(card)
    card_layout.setSpacing(ui.CARD_SPACING)

    # Question number and priority
    header_layout = QHBoxLayout()
    question_number = QLabel(f"Question {index}")
    header_layout.addWidget(question_number)

    priority = getattr(question, 'priority', 'MEDIUM')
    priority_label = QLabel(f"Priority: {priority}")
    priority_color = ui.PRIORITY_COLORS.get(priority, ui.PRIORITY_COLORS['LOW'])
    priority_label.setStyleSheet(f"color: {priority_color}; font-weight: bold;")
    header_layout.addWidget(priority_label)
    header_layout.addStretch()

    card_layout.addLayout(header_layout)

    # Research question
    question_text = getattr(question, 'question', 'No question text')
    question_label = QLabel(f"<b>Research Question:</b><br>{question_text}")
    question_label.setWordWrap(True)
    question_label.setStyleSheet(StyleSheets.card_label_padding(ui))
    card_layout.addWidget(question_label)

    # Counterfactual statement
    cf_statement = getattr(question, 'counterfactual_statement', '')
    if cf_statement:
        statement_label = QLabel(f"<b>Counterfactual Statement:</b><br>{cf_statement}")
        statement_label.setWordWrap(True)
        statement_label.setStyleSheet(
            f"{StyleSheets.card_label_padding(ui)} color: {ui.COLOR_TEXT_GREY};"
        )
        card_layout.addWidget(statement_label)

    # Reasoning
    reasoning = getattr(question, 'reasoning', '')
    if reasoning:
        reasoning_label = QLabel(f"<b>Reasoning:</b><br>{reasoning}")
        reasoning_label.setWordWrap(True)
        reasoning_label.setStyleSheet(f"{StyleSheets.card_label_padding(ui)} font-style: italic;")
        card_layout.addWidget(reasoning_label)

    # Search keywords
    keywords = getattr(question, 'search_keywords', [])
    if keywords:
        keywords_text = ", ".join(keywords[:ui.MAX_KEYWORDS_DISPLAY])
        keywords_label = QLabel(f"<b>Search Keywords:</b> {keywords_text}")
        keywords_label.setWordWrap(True)
        card_layout.addWidget(keywords_label)

    return card


def _add_contradictory_documents_section(
    layout: QVBoxLayout,
    documents: List[dict],
    card_factory: CardFactoryProtocol,
    ui: UIConstants,
    logger: logging.Logger
) -> int:
    """
    Add contradictory documents section to counterfactual tab.

    Args:
        layout: Layout to add cards to
        documents: List of contradictory documents
        card_factory: QtDocumentCardFactory instance
        ui: UI constants for styling
        logger: Logger for error reporting

    Returns:
        Number of cards created
    """
    # Add section header
    doc_header = QLabel(f"\nPotentially Contradictory Documents ({len(documents)})")
    layout.addWidget(doc_header)

    # Create document cards using factory
    cards_created = 0
    for i, doc in enumerate(documents):
        try:
            # Create DocumentCardData for counterfactual context
            card_data = create_document_card_data(
                doc,
                context=CardContext.COUNTERFACTUAL,
                show_abstract=True,
                show_metadata=True,
                show_pdf_button=True,
                expanded_by_default=False
            )

            # Create card using factory
            card = card_factory.create_card(card_data)

            # Add counterfactual question tag if available
            cf_question = doc.get('_counterfactual_question')
            cf_priority = doc.get('_counterfactual_priority')
            if cf_question and hasattr(card, 'details_layout'):
                _add_counterfactual_info_to_card(card, cf_question, cf_priority, ui)

            layout.addWidget(card)
            cards_created += 1
        except Exception as e:
            logger.error(f"Error creating counterfactual document card {i+1}: {e}", exc_info=True)

    logger.info(f"Counterfactual tab updated with {cards_created}/{len(documents)} document cards")
    return cards_created


def _add_counterfactual_info_to_card(
    card: QWidget,
    cf_question: str,
    cf_priority: Optional[str],
    ui: UIConstants
) -> None:
    """
    Add counterfactual question info to a document card.

    Args:
        card: Document card widget (must have details_layout attribute)
        cf_question: Counterfactual question text
        cf_priority: Optional priority level (HIGH, MEDIUM, LOW)
        ui: UI constants for styling
    """
    cf_info_container = QFrame()
    cf_info_container.setStyleSheet(StyleSheets.counterfactual_info_box(ui))
    cf_info_layout = QVBoxLayout(cf_info_container)
    cf_info_layout.setContentsMargins(
        ui.CARD_PADDING, ui.CARD_PADDING,
        ui.CARD_PADDING, ui.CARD_PADDING
    )
    cf_info_layout.setSpacing(ui.CARD_INTERNAL_SPACING)

    cf_title = QLabel("<b>Related Counterfactual Question:</b>")
    if cf_priority:
        priority_color = ui.PRIORITY_COLORS.get(cf_priority, ui.PRIORITY_COLORS['LOW'])
        cf_title.setText(
            f"<b>Related Counterfactual Question</b> "
            f"<span style='color: {priority_color};'>[{cf_priority} Priority]</span>"
        )
    cf_info_layout.addWidget(cf_title)

    cf_question_text = QLabel(cf_question)
    cf_question_text.setWordWrap(True)
    cf_question_text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    cf_info_layout.addWidget(cf_question_text)

    # Insert at the beginning of details_layout (before abstract)
    card.details_layout.insertWidget(0, cf_info_container)


def _add_contradictory_citations_section(
    layout: QVBoxLayout,
    citations: List[Any],
    ui: UIConstants,
    logger: logging.Logger
) -> int:
    """
    Add contradictory citations section to counterfactual tab.

    Args:
        layout: Layout to add cards to
        citations: List of contradictory citations
        ui: UI constants for styling
        logger: Logger for error reporting

    Returns:
        Number of cards created
    """
    # Add section header for citations
    citations_header = QLabel(f"\nContradictory Citations ({len(citations)})")
    layout.addWidget(citations_header)

    citations_desc = QLabel(
        "Specific passages extracted from contradictory documents that challenge the original claims:"
    )
    citations_desc.setWordWrap(True)
    layout.addWidget(citations_desc)

    # Import CitationCard widget
    from ...widgets.citation_card import CitationCard

    # Create citation cards
    cards_created = 0
    for i, citation_info in enumerate(citations, 1):
        try:
            # Extract citation object (may be wrapped in dict)
            if isinstance(citation_info, dict) and 'citation' in citation_info:
                citation = citation_info['citation']
                original_claim = citation_info.get('original_claim', '')
                cf_question = citation_info.get('counterfactual_question', '')
            else:
                citation = citation_info
                original_claim = ''
                cf_question = ''

            # Create citation card using the existing widget
            citation_card = CitationCard(citation, index=i)

            # Add context information if available
            if (original_claim or cf_question) and hasattr(citation_card, 'main_layout'):
                _add_citation_context(citation_card, original_claim, cf_question, ui)

            layout.addWidget(citation_card)
            cards_created += 1

        except Exception as e:
            logger.error(f"Error creating counterfactual citation card {i}: {e}", exc_info=True)

    logger.info(f"Counterfactual tab updated with {cards_created} citation cards")
    return cards_created


def _add_citation_context(
    citation_card: QWidget,
    original_claim: str,
    cf_question: str,
    ui: UIConstants
) -> None:
    """
    Add context information to a citation card.

    Args:
        citation_card: Citation card widget (must have main_layout attribute)
        original_claim: Original claim being challenged
        cf_question: Counterfactual research question
        ui: UI constants for styling
    """
    context_frame = QFrame()
    context_frame.setStyleSheet(StyleSheets.counterfactual_info_box(ui))
    context_layout = QVBoxLayout(context_frame)
    context_layout.setContentsMargins(
        ui.CARD_PADDING, ui.CARD_PADDING,
        ui.CARD_PADDING, ui.CARD_PADDING
    )
    context_layout.setSpacing(ui.CARD_INTERNAL_SPACING)

    if original_claim:
        claim_label = QLabel(f"<b>Challenges Claim:</b> {original_claim}")
        claim_label.setWordWrap(True)
        claim_label.setStyleSheet("background-color: transparent; border: none;")
        context_layout.addWidget(claim_label)

    if cf_question:
        question_label = QLabel(f"<b>Research Question:</b> {cf_question}")
        question_label.setWordWrap(True)
        question_label.setStyleSheet("background-color: transparent; border: none;")
        context_layout.addWidget(question_label)

    # Insert context at the top of the citation card
    citation_card.main_layout.insertWidget(0, context_frame)
