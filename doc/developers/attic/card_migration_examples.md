# Migration Examples: Converting to Unified Document Cards

This guide shows step-by-step examples of migrating existing tabs to use the new unified document card component.

## Example 1: Simple Literature Search Tab

### Before (Old Code)

```python
import flet as ft
from bmlibrarian.gui.document_card_utils import create_document_card

class LiteratureTab:
    def __init__(self, page: ft.Page):
        self.page = page
        self.documents = []

    def display_documents(self, documents: list):
        """Display search results."""
        self.documents = documents

        # Create cards
        cards = [
            create_document_card(i, doc)
            for i, doc in enumerate(documents)
        ]

        # Add to UI
        results_column = ft.Column(cards, scroll="auto")
        self.page.add(results_column)
        self.page.update()
```

### After (New Unified Cards)

```python
import flet as ft
from bmlibrarian.gui.card_factory import CardFactory

class LiteratureTab:
    def __init__(self, page: ft.Page):
        self.page = page
        self.documents = []
        # Create card factory once
        self.card_factory = CardFactory(page)

    def display_documents(self, documents: list):
        """Display search results."""
        self.documents = documents

        # Create unified cards - same interface!
        cards = self.card_factory.create_search_results_cards(documents)

        # Add to UI (no changes)
        results_column = ft.Column(cards, scroll="auto")
        self.page.add(results_column)
        self.page.update()
```

**Changes Made:**
1. Import `CardFactory` instead of old utilities
2. Create `CardFactory` instance in `__init__`
3. Use `create_search_results_cards()` method
4. Full-text buttons automatically included!

---

## Example 2: Document Scoring Tab with Human Controls

### Before (Old Code)

```python
import flet as ft
from bmlibrarian.gui.document_cards import create_document_scoring_card

class ScoringTab:
    def __init__(self, page: ft.Page):
        self.page = page
        self.scored_documents = []

    def display_scored_documents(self, scored_docs: list):
        """Display documents with AI scores."""
        self.scored_documents = scored_docs

        cards = []
        for i, (doc, scoring_result) in enumerate(scored_docs):
            card = create_document_scoring_card(
                index=i,
                doc=doc,
                scoring_result=scoring_result,
                on_score_override=self.handle_score_override,
                on_score_approval=self.handle_score_approval
            )
            cards.append(card)

        results_column = ft.Column(cards, scroll="auto")
        self.page.add(results_column)
        self.page.update()

    def handle_score_override(self, index: int, score: str):
        """Handle human score override."""
        try:
            score_val = float(score)
            print(f"Score overridden: {index} -> {score_val}")
        except ValueError:
            print(f"Invalid score: {score}")

    def handle_score_approval(self, index: int, approved: bool):
        """Handle AI score approval."""
        if approved:
            print(f"AI score approved for document {index}")
```

### After (New Unified Cards)

```python
import flet as ft
from bmlibrarian.gui.card_factory import CardFactory

class ScoringTab:
    def __init__(self, page: ft.Page):
        self.page = page
        self.scored_documents = []
        # Create card factory
        self.card_factory = CardFactory(page)

    def display_scored_documents(self, scored_docs: list):
        """Display documents with AI scores."""
        self.scored_documents = scored_docs

        # One line instead of loop!
        cards = self.card_factory.create_scoring_cards(
            scored_documents=scored_docs,
            show_controls=True,
            on_score_change=self.handle_score_change,
            on_score_approve=self.handle_score_approval
        )

        results_column = ft.Column(cards, scroll="auto")
        self.page.add(results_column)
        self.page.update()

    def handle_score_change(self, index: int, score: str, score_type: str):
        """Handle score changes (unified callback)."""
        try:
            score_val = float(score)
            print(f"Score changed: {index} -> {score_val} ({score_type})")
        except ValueError:
            print(f"Invalid score: {score}")

    def handle_score_approval(self, index: int):
        """Handle AI score approval."""
        print(f"AI score approved for document {index}")
```

**Changes Made:**
1. Use `CardFactory` instead of individual card functions
2. Single method call `create_scoring_cards()` instead of loop
3. Updated callback signature: `on_score_change(index, score, type)` instead of `on_score_override(index, score)`
4. Simplified `on_score_approve` - just takes index now
5. Full-text buttons automatically included!

---

## Example 3: Citations Tab

### Before (Old Code)

```python
import flet as ft
from bmlibrarian.gui.citation_card_utils import CitationCardCreator

class CitationsTab:
    def __init__(self, page: ft.Page):
        self.page = page
        self.citations = []
        self.card_creator = CitationCardCreator()

    def display_citations(self, citations: list):
        """Display extracted citations."""
        self.citations = citations

        cards = self.card_creator.create_citation_cards_list(citations)

        results_column = ft.Column(cards, scroll="auto")
        self.page.add(results_column)
        self.page.update()
```

### After (New Unified Cards)

```python
import flet as ft
from bmlibrarian.gui.card_factory import CardFactory

class CitationsTab:
    def __init__(self, page: ft.Page):
        self.page = page
        self.citations = []
        # Use unified card factory
        self.card_factory = CardFactory(page)

    def display_citations(self, citations: list):
        """Display extracted citations."""
        self.citations = citations

        # Same method call!
        cards = self.card_factory.create_citation_cards(citations)

        results_column = ft.Column(cards, scroll="auto")
        self.page.add(results_column)
        self.page.update()
```

**Changes Made:**
1. Import `CardFactory` instead of `CitationCardCreator`
2. Use `CardFactory.create_citation_cards()` method
3. Citation highlighting and all features preserved!
4. Full-text buttons automatically included!

---

## Example 4: Mixed Context Tab (Counterfactual Evidence)

### Before (Old Code - may not exist yet)

```python
import flet as ft
from bmlibrarian.gui.document_card_utils import create_document_card

class CounterfactualTab:
    def __init__(self, page: ft.Page):
        self.page = page
        self.evidence = []

    def display_counterfactual_evidence(self, documents: list, scores: list):
        """Display contradictory evidence."""
        self.evidence = documents

        cards = []
        for i, doc in enumerate(documents):
            card = create_document_card(i, doc, show_score=True,
                                       scoring_result={'score': scores[i]})
            cards.append(card)

        results_column = ft.Column(cards, scroll="auto")
        self.page.add(results_column)
        self.page.update()
```

### After (New Unified Cards)

```python
import flet as ft
from bmlibrarian.gui.card_factory import CardFactory

class CounterfactualTab:
    def __init__(self, page: ft.Page):
        self.page = page
        self.evidence = []
        self.card_factory = CardFactory(page)

    def display_counterfactual_evidence(self, documents: list, scores: list):
        """Display contradictory evidence."""
        self.evidence = documents

        # Clean, simple call
        cards = self.card_factory.create_counterfactual_cards(
            documents=documents,
            scores=scores
        )

        results_column = ft.Column(cards, scroll="auto")
        self.page.add(results_column)
        self.page.update()
```

**Changes Made:**
1. Use dedicated `create_counterfactual_cards()` method
2. Cleaner parameter passing
3. Full-text buttons automatically included!

---

## Example 5: Dynamic Single Card Update

### Before (Old Code)

```python
def update_document_card(self, index: int, doc: dict):
    """Update a single document card."""
    from bmlibrarian.gui.document_card_utils import create_document_card

    new_card = create_document_card(index, doc)

    # Replace card in UI
    self.cards_container.controls[index] = new_card
    self.page.update()
```

### After (New Unified Cards)

```python
def update_document_card(self, index: int, doc: dict, ai_score: float = None):
    """Update a single document card."""
    from bmlibrarian.gui.unified_document_card import DocumentCardContext

    new_card = self.card_factory.create_single_document_card(
        index=index,
        doc=doc,
        context=DocumentCardContext.LITERATURE,
        ai_score=ai_score  # Optional - can include scores
    )

    # Replace card in UI (same)
    self.cards_container.controls[index] = new_card
    self.page.update()
```

**Changes Made:**
1. Use `create_single_document_card()` for individual cards
2. Can specify context and optional parameters
3. More flexible than old approach

---

## Example 6: Adding PDF Manager Integration

### Enhanced Version with PDF Manager

```python
import flet as ft
from bmlibrarian.gui.card_factory import CardFactory
from bmlibrarian.utils.pdf_manager import PDFManager

class LiteratureTab:
    def __init__(self, page: ft.Page):
        self.page = page
        self.documents = []

        # Initialize PDF manager
        self.pdf_manager = PDFManager()

        # Pass PDF manager to card factory
        self.card_factory = CardFactory(
            page,
            pdf_manager=self.pdf_manager
        )

    def display_documents(self, documents: list):
        """Display search results with full PDF support."""
        self.documents = documents

        # Cards now have full PDF download/upload/view functionality!
        cards = self.card_factory.create_search_results_cards(documents)

        results_column = ft.Column(cards, scroll="auto")
        self.page.add(results_column)
        self.page.update()
```

**New Features Enabled:**
- Automatic PDF download from URLs
- PDF upload via file picker
- PDF viewing in system viewer
- All handled automatically by the cards!

---

## Quick Reference: Method Mapping

| Old Method | New Method | Context |
|------------|------------|---------|
| `create_document_card()` | `factory.create_search_results_cards()` | Literature |
| `create_document_scoring_card()` | `factory.create_scoring_cards()` | Scoring |
| `create_citation_card()` | `factory.create_citation_cards()` | Citations |
| `create_scored_document_cards_list()` | `factory.create_scoring_cards()` | Scoring |
| N/A | `factory.create_counterfactual_cards()` | Counterfactual |
| N/A | `factory.create_single_document_card()` | Any |

---

## Testing Your Migration

After migrating, verify:

1. **Visual Appearance**: Cards should look like the unified design
2. **Collapsible Behavior**: Title and score visible when collapsed
3. **Full-Text Buttons**: Correct button appears based on PDF availability
4. **Score Badges**: Color-coded and positioned correctly
5. **Citations**: Passages highlighted in yellow
6. **Callbacks**: All interactive features work as expected

Run the demo to see expected behavior:
```bash
uv run python examples/unified_card_demo.py
```

---

## Common Migration Issues

### Issue 1: Callback Signature Changed

**Old:**
```python
def on_score_override(self, index: int, score: str):
    ...

def on_score_approval(self, index: int, approved: bool):
    ...
```

**New:**
```python
def on_score_change(self, index: int, score: str, score_type: str):
    # score_type is either "ai" or "human"
    ...

def on_score_approve(self, index: int):
    # No approved boolean - approval is implicit
    ...
```

### Issue 2: Document Format

Ensure your documents have the expected fields:
```python
{
    'id': <int>,              # Required
    'title': <str>,           # Required
    'authors': <list|str>,    # Optional
    'publication': <str>,     # Optional
    'year': <str>,            # Optional
    'abstract': <str>,        # Optional but recommended
    'pdf_path': <str>,        # Optional
    'pdf_url': <str>,         # Optional
    'pmid': <str>,            # Optional
    'doi': <str>              # Optional
}
```

### Issue 3: Factory vs Direct Creation

For most cases, use `CardFactory`. Only use `UnifiedDocumentCard` directly if you need very custom behavior.

**Recommended:**
```python
factory = CardFactory(page)
cards = factory.create_search_results_cards(documents)
```

**Advanced/Custom:**
```python
card_creator = UnifiedDocumentCard(page, pdf_manager=my_manager)
card = card_creator.create_card(0, doc, context="custom", ...)
```

---

## Next Steps

1. Start with your simplest tab (usually Literature)
2. Test thoroughly before moving to next tab
3. Update one tab at a time
4. Keep old code commented out until verified
5. Run full integration tests after migration

For questions or issues, refer to:
- [doc/developers/unified_document_card.md](unified_document_card.md) - Complete API documentation
- [examples/unified_card_demo.py](../../examples/unified_card_demo.py) - Working examples
