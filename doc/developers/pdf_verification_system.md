# PDF Verification System - Developer Documentation

This document describes the architecture and implementation of the PDF verification dialog system used when downloaded PDFs don't match expected document metadata.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                        PDF Download Flow                             │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  PDFManager.download_pdf_with_discovery()                           │
│       │                                                              │
│       ▼                                                              │
│  FullTextFinder.discover_and_download()                             │
│       │                                                              │
│       ▼                                                              │
│  PDFVerifier.verify_downloaded_pdf()                                │
│       │                                                              │
│       ▼                                                              │
│  ┌────────────────┐                                                 │
│  │ Verified?      │──Yes──▶ Return PDF path                         │
│  └────────────────┘                                                 │
│       │ No                                                           │
│       ▼                                                              │
│  ┌────────────────────────────────────────┐                         │
│  │ prompt_on_mismatch?                    │──No──▶ Handle silently  │
│  └────────────────────────────────────────┘                         │
│       │ Yes                                                          │
│       ▼                                                              │
│  ┌────────────────────────────────────────┐                         │
│  │ GUI or CLI?                            │                         │
│  └────────────────────────────────────────┘                         │
│       │                    │                                         │
│       ▼ GUI                ▼ CLI                                     │
│  PDFVerificationDialog  prompt_cli_verification()                   │
│       │                    │                                         │
│       └────────┬───────────┘                                        │
│                ▼                                                     │
│  VerificationDecision (ACCEPT/REJECT/RETRY/etc.)                    │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

## Key Components

### 1. Data Types (`discovery/verification_prompt.py`)

#### VerificationDecision Enum
```python
class VerificationDecision(Enum):
    ACCEPT = "accept"           # Accept and ingest the PDF
    SAVE_AS = "save_as"         # Save PDF to custom location
    RETRY = "retry"             # Reject and try searching again
    REJECT = "reject"           # Reject completely
    REASSIGN = "reassign"       # Assign to different document
    MANUAL_UPLOAD = "manual_upload"  # User selected a different PDF
```

#### VerificationPromptData Dataclass
```python
@dataclass
class VerificationPromptData:
    pdf_path: Path                              # Downloaded PDF location
    expected_doi: Optional[str]                 # DOI from database
    extracted_doi: Optional[str]                # DOI from PDF
    expected_title: Optional[str]               # Title from database
    extracted_title: Optional[str]              # Title from PDF
    expected_pmid: Optional[str] = None
    extracted_pmid: Optional[str] = None
    title_similarity: Optional[float] = None    # 0.0 to 1.0
    verification_warnings: Optional[list] = None
    doc_id: Optional[int] = None                # Original document ID
    alternative_document: Optional[AlternativeDocument] = None
    source_url: Optional[str] = None            # URL for "Open in Browser"
    manual_upload_path: Optional[Path] = None   # Set by dialog
```

#### AlternativeDocument Dataclass
```python
@dataclass
class AlternativeDocument:
    doc_id: int          # Database ID
    title: str
    doi: str
    has_pdf: bool        # Whether already has a PDF
    authors: Optional[str] = None
    year: Optional[int] = None
```

### 2. GUI Dialog (`discovery/verification_dialog.py`)

#### PDFVerificationDialog Class

A PySide6 QDialog with:
- PDF viewer panel (left, 60%)
- Information panel (right, 40%) with:
  - Expected document section (blue)
  - Downloaded PDF section (red)
  - Mismatch analysis section (amber)
  - Alternative document section (green, conditional)
- Button panel with two rows

**Key attributes:**
```python
self.decision: VerificationDecision  # Final decision
self.save_path: Optional[Path]       # Path if user saved copy
self.reassign_doc_id: Optional[int]  # Doc ID if reassigned
self._pdf_saved: bool                # Track if saved
self._pdf_reassigned: bool           # Track if reassigned
```

**Non-terminating actions** (dialog stays open):
- `_on_open_browser()` - Opens URL, no return
- `_on_save_as()` - Saves copy, disables button
- `_on_reassign()` - Updates database, disables button

**Terminating actions** (dialog closes):
- `_on_accept()` - Returns ACCEPT
- `_on_manual_upload()` - Returns MANUAL_UPLOAD with path
- `_on_retry()` - Returns RETRY
- `_on_reject()` - Returns REJECT

### 3. CLI Prompt (`discovery/verification_prompt.py`)

#### prompt_cli_verification()
```python
def prompt_cli_verification(
    data: VerificationPromptData,
    show_pdf_callback: Optional[Callable[[Path], None]] = None
) -> tuple[VerificationDecision, Optional[Path], Optional[int]]:
```

Returns: `(decision, path, reassign_doc_id)`
- `path` is save_path for SAVE_AS, or upload_path for MANUAL_UPLOAD
- `reassign_doc_id` is only set for REASSIGN

### 4. Integration Points

#### PDFManager (`utils/pdf_manager.py`)

```python
def download_pdf_with_discovery(
    self,
    document: Dict[str, Any],
    verify_content: bool = True,
    prompt_on_mismatch: bool = False,
    verification_callback: Optional[Callable] = None,
    parent_widget=None,
    max_retries: int = 3
) -> Optional[Path]:
```

**Decision handling in `download_pdf_with_discovery()`:**

```python
if decision == 'accept':
    # Assign to original document
    return pdf_path

elif decision == 'manual_upload':
    # Copy user's file to correct location
    shutil.copy2(save_path, target_path)
    return target_path

elif decision == 'reassign':
    # Already handled by dialog (non-terminating)
    # No action needed here
    return None

elif decision == 'save_as':
    # User saved copy, delete temp
    pdf_path.unlink()
    return None

elif decision == 'retry':
    # Loop back and try again
    retry_count += 1
    continue

else:  # 'reject'
    pdf_path.unlink()
    return None
```

#### QtDocumentCardFactory (`gui/qt/qt_document_card_factory.py`)

Integrates with the FETCH button workflow in document cards:

```python
def _execute_pdf_discovery(self, card_data, progress_callback):
    # ... download and verify ...

    if result.verified is False:
        # Build VerificationPromptData with source_url
        source_url = result.source.url if result.source else None

        prompt_data = VerificationPromptData(
            pdf_path=pdf_path,
            source_url=source_url,
            # ... other fields ...
        )

        decision, save_path, reassign_doc_id = prompt_gui_verification(
            prompt_data, parent_widget
        )

        # Handle each decision type...
```

## Database Operations

### find_alternative_document()
Looks up documents by extracted DOI:
```python
def find_alternative_document(extracted_doi: str) -> Optional[AlternativeDocument]:
    """Find document matching extracted DOI that doesn't have a PDF."""
    # Query: SELECT ... FROM document WHERE LOWER(doi) = LOWER(%s)
```

### Reassignment (in dialog)
Direct database update when user clicks Reassign:
```python
with db_manager.get_connection() as conn:
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE document SET pdf_filename = %s WHERE id = %s",
            (relative_path, alt.doc_id)
        )
        conn.commit()
```

## Button Layout

### Row 1: Primary Actions
| Button | Color | Action | Terminates? |
|--------|-------|--------|-------------|
| Accept & Ingest | Green (#4CAF50) | Assign to original doc | Yes |
| Manual Upload | Teal (#009688) | File picker | Yes |

### Row 2: Secondary Actions
| Button | Color | Action | Terminates? |
|--------|-------|--------|-------------|
| Open in Browser | Cyan (#00BCD4) | Open URL | No |
| Save As | Blue (#2196F3) | Save copy | No |
| Retry Search | Orange (#FF9800) | Try again | Yes |
| Reject | Red (#f44336) | Discard | Yes |

### Alternative Document Section
| Button | Color | Action | Terminates? |
|--------|-------|--------|-------------|
| Assign to Doc X | Purple (#9C27B0) | Update DB | No |

## Extension Points

### Custom Verification Callback
```python
def my_verification_handler(data: VerificationPromptData) -> tuple:
    # Custom logic
    return VerificationDecision.ACCEPT, None, None

pdf_manager.download_pdf_with_discovery(
    document,
    verification_callback=my_verification_handler
)
```

### Adding New Decision Types
1. Add to `VerificationDecision` enum
2. Add button in `_create_button_panel()` or appropriate section
3. Add handler method `_on_new_action()`
4. Handle in `pdf_manager.py` and `qt_document_card_factory.py`

## Error Handling

- All button handlers wrapped in try/except
- Failed reassignment shows QMessageBox.critical
- Failed browser open shows QMessageBox.warning
- Database errors logged and reported to user

## Testing

### Manual Testing Scenarios
1. DOI mismatch with alternative document available
2. DOI mismatch without alternative document
3. Title-only mismatch (no DOI in PDF)
4. Manual upload with valid PDF
5. Manual upload with invalid file
6. Open browser then manual upload
7. Reassign then reject
8. Save as then accept

### Unit Test Considerations
- Mock database for `find_alternative_document()`
- Mock `webbrowser.open()` for browser tests
- Mock `QFileDialog` for upload tests
- Test each decision path independently
