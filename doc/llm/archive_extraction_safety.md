# Safely extracting tar/zip archives

**Rule: never extract a tar or zip archive member without first validating
its path.** A malicious archive can carry members named `../../../etc/cron.d/x`
or `/etc/passwd` ("zip slip" / "tar slip") that escape the intended output
directory when extracted. `zipfile.extract` sanitizes such names by mangling
them (dropping leading slashes and `..`), but `tarfile.extract` on Python
< 3.14 follows them verbatim, and `ZipFile.extractall` / mangling can still
collide files — so we reject, not mangle.

## The one helper

Always gate extraction on
`bmlibrarian.utils.path_utils.is_safe_archive_member(member_name)`:

```python
from bmlibrarian.utils.path_utils import is_safe_archive_member

with zipfile.ZipFile(path) as zf:
    for member in zf.namelist():
        if not is_safe_archive_member(member):
            continue  # skip + log; never extractall()
        zf.extract(member, dest)
```

- Rejects absolute paths — POSIX (leading `/`, `PurePath.is_absolute`) *and*
  Windows drive-rooted (`C:\...` / `C:/...`, caught on POSIX via
  `PureWindowsPath.is_absolute`) — and any `..` path *component*. A literal
  `..` inside a filename (`PMC..123.pdf`) is fine.
- Normalizes `\` → `/` first, so Windows-style `..\..\x` traversal is caught
  on POSIX hosts (where `Path("..\\..\\x")` is otherwise a single component).
- Pure, no side effects beyond a WARNING log on rejection.

## Extra hardening for tar

On top of the guard, pass the stdlib data filter (Python ≥ 3.12, the project
minimum) — it independently blocks traversal and silences the 3.14 default-on
deprecation warning:

```python
tar.extract(member, dest, filter='data')
```

## Never use `extractall()`

`ZipFile.extractall()` / `TarFile.extractall()` extract every member with no
per-member veto. Loop and gate each member instead.

## Call sites (all routed through the helper)

- `importers/europe_pmc_pdf_downloader.py` — `_is_safe_zip_member` is a thin
  wrapper around `is_safe_archive_member` (kept for existing callers/tests).
- `importers/pmc_bulk_importer.py` — `_extract_package` (tar, + `filter='data'`).
- `importers/medrxiv_meca_importer.py` — `extract_package` (zip; replaced a
  blanket `extractall`).

Tests: `tests/test_path_utils.py` (the pure guard) and
`tests/test_importer_extraction_security.py` (both importers, real archives).
