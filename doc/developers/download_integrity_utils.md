# Download Integrity Utilities

Modules: `bmlibrarian.utils.pdf_validation`, `bmlibrarian.utils.download_utils`

Small pure helpers (golden rule 11) shared by every PDF download path
(`utils/pdf_manager.py`, `discovery/full_text_finder.py`,
`importers/medrxiv_importer.py`), closing two silent-corruption bug classes
found in the July 2026 code review.

## `pdf_validation` — magic-byte content validation

Remote servers routinely return an HTML paywall/login page with HTTP 200
and a `.pdf`-looking URL. Trusting the status code (or the Content-Type
header, which servers also get wrong) silently poisons the PDF corpus:
the HTML page is saved as `<doi>.pdf` and recorded as a successful
download forever.

Per the PDF specification a conforming file must begin with the ASCII
header `%PDF-`. Checking those magic bytes is the authoritative,
network-independent test.

| Function | Purpose |
|----------|---------|
| `is_pdf_content(first_bytes)` | True if the leading bytes contain the `%PDF-` header (searched within the first `PDF_HEADER_READ_SIZE` bytes to tolerate BOM/whitespace prefixes). Non-bytes and empty input return False. |
| `is_pdf_file(file_path)` | Reads only the file's first `PDF_HEADER_READ_SIZE` bytes and applies `is_pdf_content`. I/O errors are logged and reported as "not a PDF", never raised. |

The module deliberately has no dependency on `requests` or any network
library, so it is reusable and unit-testable regardless of how the bytes
were obtained (HTTP, FTP, or browser automation).

## `download_utils` — atomic download-to-temp-then-rename

Downloading straight to the final output path has two failure modes:

1. A mid-stream failure leaves a truncated file at the final path, which
   later code mistakes for a completed download and never retries.
2. "Fixing" that with an unconditional `unlink(final_path)` in the error
   handler introduces the opposite bug: when the failure occurs *before*
   any bytes are written (e.g. a connect timeout), the file at the final
   path is a **previous successful download** — and the cleanup deletes it.

The safe pattern: stream into a temporary sibling file (final path +
`.part`), validate it (magic bytes / size), then atomically promote it
into place. Error handlers discard only the partial file and can never
touch a good file at the final path.

| Function | Purpose |
|----------|---------|
| `partial_download_path(final_path)` | Temporary sibling path (`paper.pdf` → `paper.pdf.part`, same directory so the promoting rename is atomic). |
| `promote_partial_download(partial_path, final_path)` | `os.replace` the validated partial file into place (overwrites an older download). |
| `discard_partial_download(partial_path)` | Remove the partial file if present; safe in error handlers (logs and swallows filesystem errors, never touches the final path). |

### Canonical usage

```python
from bmlibrarian.utils.download_utils import (
    partial_download_path, promote_partial_download, discard_partial_download,
)
from bmlibrarian.utils.pdf_validation import is_pdf_file

part_path = partial_download_path(output_path)
for attempt in range(max_attempts):
    try:
        stream_response_into(part_path)
        if not is_pdf_file(part_path):
            discard_partial_download(part_path)
            continue          # retry / try next source
        promote_partial_download(part_path, output_path)
        return output_path    # success
    except NetworkError:
        discard_partial_download(part_path)  # never unlink output_path
```

## Regression tests

`tests/test_pdf_download_integrity.py` covers both modules hermetically
(no network): HTML-paywall rejection, mid-stream partial-file cleanup,
pre-existing-file preservation on failed attempts, no leftover `.part`
artifacts, and magic-byte validation of browser-fallback output.
