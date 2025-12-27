# PubMed Download Repair System

Technical documentation for the PubMed download repair system, which detects and fixes corrupted gzip files.

## Architecture Overview

The repair system consists of:

1. **pubmed_repair_cli.py** - Command-line interface for scanning and repairing
2. **Gzip integrity verification** - Full-file CRC32 validation
3. **Integration with PubMedBulkImporter** - Leverages existing download/import infrastructure

## The Corruption Problem

### Root Cause

The original gzip verification in `pubmed_bulk_importer.py` only checked the first byte:

```python
# INSUFFICIENT - only verifies header
with gzip.open(dest_path, 'rb') as gz:
    gz.read(1)  # Only reads first byte
```

This passed files with valid headers but corrupted data streams.

### The Fix

Full-file verification reads the entire compressed stream:

```python
# CORRECT - verifies entire file including CRC32
with gzip.open(dest_path, 'rb') as gz:
    while gz.read(65536):  # Read in 64KB chunks
        pass
```

This triggers gzip's internal CRC32 verification at the end of the stream.

## Implementation Details

### verify_gzip_integrity()

```python
def verify_gzip_integrity(filepath: Path) -> tuple[bool, Optional[str]]:
    """
    Verify gzip file integrity by reading entire file.

    The gzip format includes a CRC32 checksum at the end of the stream.
    By reading the entire file, we force decompression of all blocks
    and verification of the checksum.

    Returns:
        Tuple of (is_valid, error_message)
    """
    try:
        with gzip.open(filepath, 'rb') as gz:
            while gz.read(65536):  # 64KB chunks for memory efficiency
                pass
        return True, None
    except gzip.BadGzipFile as e:
        return False, f"Bad gzip file: {e}"
    except EOFError as e:
        return False, f"Truncated file: {e}"
    except Exception as e:
        return False, f"Error: {e}"
```

### Database Tracking Reset

When a file needs re-downloading, we reset its tracking status:

```python
def reset_file_for_redownload(tracker: DownloadTracker, filename: str) -> None:
    """Reset a file's tracking status so it will be re-downloaded."""
    with db_manager.get_connection() as conn:
        with conn.cursor() as cur:
            # Delete record so download logic sees it as missing
            cur.execute(
                "DELETE FROM pubmed_download_log WHERE file_name = %s",
                (filename,)
            )
            conn.commit()
```

For re-import, we mark the file as unprocessed:

```python
def reset_file_for_reimport(tracker: DownloadTracker, filename: str) -> None:
    """Reset a file's processed status so it will be re-imported."""
    with db_manager.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE pubmed_download_log
                SET processed = FALSE,
                    process_date = NULL,
                    status = 'downloaded'
                WHERE file_name = %s
            """, (filename,))
            conn.commit()
```

## Workflow

### Scan Operation

```
1. List all *.xml.gz files in baseline_dir and update_dir
2. For each file:
   a. Open with gzip.open()
   b. Read entire file in 64KB chunks
   c. If exception raised, mark as corrupted
3. Report all corrupted files
```

### Repair Operation

```
1. Scan for corrupted files (as above)
2. For each corrupted file:
   a. Delete the file from disk
   b. Delete tracking record from pubmed_download_log
3. Call importer.download_baseline() / download_updates()
   - These will re-download missing files
   - New download verification will validate CRC32
4. Verify re-downloaded files are intact
5. If --reimport:
   a. Reset processed=FALSE for repaired files
   b. Call importer.import_all_files()
```

## Error Types

| Exception | Cause | Recovery |
|-----------|-------|----------|
| `gzip.BadGzipFile` | Invalid gzip header or structure | Re-download |
| `EOFError` | Truncated file (incomplete download) | Re-download |
| `zlib.error` | Corrupted compressed data | Re-download |
| `OSError` | File system error | Check disk, re-download |

## Integration Points

### With PubMedBulkImporter

The repair CLI uses the same `PubMedBulkImporter` class for downloads:

```python
importer = PubMedBulkImporter(
    data_dir=args.data_dir,
    use_tracking=True
)

# Re-download will use existing retry logic, FTP handling, etc.
importer.download_baseline(skip_existing=True)
importer.download_updates(skip_existing=True)
```

### With DownloadTracker

The repair system manipulates the `pubmed_download_log` table:

- **DELETE** - Removes record so file appears "missing" to downloader
- **UPDATE** - Resets `processed=FALSE` so file will be re-imported

## Performance Considerations

### Scan Performance

- Reading a 50MB compressed file takes ~1-2 seconds
- Full baseline scan (~1200 files) takes ~20-40 minutes
- Updates scan (~400 files) takes ~5-10 minutes

### Memory Usage

The 64KB chunk size keeps memory usage constant regardless of file size:

```python
while gz.read(65536):  # Never loads entire file into memory
    pass
```

### Parallelization

Current implementation is sequential. Parallel scanning could be added:

```python
from concurrent.futures import ThreadPoolExecutor

with ThreadPoolExecutor(max_workers=4) as executor:
    results = executor.map(verify_gzip_integrity, files)
```

However, sequential is usually sufficient and avoids I/O contention.

## Testing

### Unit Test for Verification

```python
def test_verify_gzip_integrity():
    # Create valid gzip file
    valid_path = Path("/tmp/valid.gz")
    with gzip.open(valid_path, 'wb') as f:
        f.write(b"test data")

    is_valid, error = verify_gzip_integrity(valid_path)
    assert is_valid is True
    assert error is None

    # Create corrupted file
    corrupt_path = Path("/tmp/corrupt.gz")
    with open(corrupt_path, 'wb') as f:
        f.write(b"not a gzip file")

    is_valid, error = verify_gzip_integrity(corrupt_path)
    assert is_valid is False
    assert "Bad gzip file" in error
```

### Integration Test

```bash
# Create a corrupted file manually
dd if=/dev/urandom of=~/knowledgebase/pubmed_data/updatefiles/test_corrupt.xml.gz bs=1024 count=100

# Scan should detect it
uv run python pubmed_repair_cli.py scan --type update

# Clean up
rm ~/knowledgebase/pubmed_data/updatefiles/test_corrupt.xml.gz
```

## Future Improvements

1. **Parallel scanning** - Use thread pool for faster scans
2. **Checksum verification** - Compare against MD5 files from PubMed FTP
3. **Incremental scans** - Only scan files modified since last scan
4. **Automatic scheduling** - Run scans after each download automatically

## Related Files

- `src/bmlibrarian/importers/pubmed_bulk_importer.py` - Main importer with fixed verification
- `pubmed_bulk_cli.py` - Download and import CLI
- `pubmed_repair_cli.py` - Repair CLI (this system)
- `doc/users/pubmed_repair_guide.md` - User documentation
