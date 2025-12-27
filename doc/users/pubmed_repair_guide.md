# PubMed Download Repair Guide

This guide explains how to use the `pubmed_repair_cli.py` tool to detect and fix corrupted PubMed download files.

## Overview

When downloading large datasets from PubMed FTP servers, files can occasionally become corrupted due to:
- Network interruptions during download
- Disk write errors
- Incomplete transfers
- FTP connection timeouts

The repair CLI scans all downloaded `.xml.gz` files for corruption and automatically re-downloads any damaged files.

## Quick Start

```bash
# Scan for corrupted files (read-only, no changes)
uv run python pubmed_repair_cli.py scan

# Repair corrupted files (re-download)
uv run python pubmed_repair_cli.py repair -y

# Repair and re-import into database
uv run python pubmed_repair_cli.py repair --reimport -y
```

## Commands

### scan

Scans all downloaded PubMed files for corruption without making any changes.

```bash
# Scan all files (baseline + updates)
uv run python pubmed_repair_cli.py scan

# Scan only baseline files
uv run python pubmed_repair_cli.py scan --type baseline

# Scan only update files
uv run python pubmed_repair_cli.py scan --type update

# Verbose output (show each file being checked)
uv run python pubmed_repair_cli.py scan -v
```

**Output example:**
```
======================================================================
PubMed Download Integrity Scan
======================================================================
Data directory: /Users/user/knowledgebase/pubmed_data
======================================================================

Scanning update files...
  Scanning 399 update files...
    CORRUPTED: pubmed25n1581.xml.gz - Error: invalid stored block lengths
    CORRUPTED: pubmed25n1673.xml.gz - Error: invalid block type
  Completed: 399 files scanned, 2 corrupted

======================================================================
Scan Complete
======================================================================

Found 2 corrupted file(s):
  - pubmed25n1581.xml.gz
  - pubmed25n1673.xml.gz

Run 'pubmed_repair_cli.py repair' to fix these files.
```

### repair

Re-downloads corrupted files and optionally re-imports them into the database.

```bash
# Repair all corrupted files
uv run python pubmed_repair_cli.py repair -y

# Repair and re-import into database
uv run python pubmed_repair_cli.py repair --reimport -y

# Repair only baseline files
uv run python pubmed_repair_cli.py repair --type baseline -y

# Repair only update files
uv run python pubmed_repair_cli.py repair --type update -y

# Interactive mode (prompts for confirmation)
uv run python pubmed_repair_cli.py repair
```

**What repair does:**
1. Scans all files for corruption
2. Deletes corrupted files from disk
3. Resets tracking status in database
4. Re-downloads files from PubMed FTP
5. Verifies new downloads are intact
6. (Optional) Re-imports into database

## Options

| Option | Description |
|--------|-------------|
| `-v, --verbose` | Show detailed progress for each file |
| `--data-dir PATH` | Custom data directory (default: `~/knowledgebase/pubmed_data`) |
| `--type {baseline,update}` | Process only specific file type |
| `--reimport` | Re-import files after re-downloading (repair only) |
| `-y, --yes` | Skip confirmation prompts |

## How Corruption Detection Works

The tool verifies gzip file integrity by:
1. Reading the entire compressed file in 64KB chunks
2. Decompressing all data blocks
3. Verifying the CRC32 checksum at the end of the gzip stream

This catches corruption anywhere in the file, not just in the header.

## Common Error Messages

| Error | Meaning |
|-------|---------|
| `invalid stored block lengths` | File was truncated during download |
| `invalid block type` | Data corruption in compressed stream |
| `invalid literal/length/distance code` | Compressed data is damaged |
| `Truncated file` | Download was interrupted before completion |
| `Bad gzip file` | File header is corrupted or not a valid gzip |

## Recommended Workflow

### After Initial Download

Run a scan after downloading the baseline or updates to catch any corruption early:

```bash
# After downloading baseline
uv run python pubmed_bulk_cli.py download-baseline -y
uv run python pubmed_repair_cli.py scan --type baseline

# After downloading updates
uv run python pubmed_bulk_cli.py download-updates
uv run python pubmed_repair_cli.py scan --type update
```

### Regular Maintenance

Periodically scan your data directory to ensure integrity:

```bash
# Weekly integrity check
uv run python pubmed_repair_cli.py scan
```

### Before Major Imports

Always verify file integrity before importing:

```bash
# Verify and repair before import
uv run python pubmed_repair_cli.py repair --reimport -y
```

## Troubleshooting

### Files keep getting corrupted after re-download

This could indicate:
- Unstable network connection
- Issues with the PubMed FTP server
- Disk problems

Try:
1. Wait and retry later
2. Check your network connection
3. Verify disk health with `fsck` or similar tools

### Repair fails to re-download

The PubMed FTP server may be temporarily unavailable. Check:
- https://www.ncbi.nlm.nih.gov/home/about/policies/ for maintenance notices
- Your firewall/proxy settings for FTP access

### Database tracking is out of sync

If the tracking database doesn't reflect actual file state:

```bash
# Reset tracking and re-scan
uv run python pubmed_bulk_cli.py status
```

## See Also

- [PubMed Bulk Import Guide](pubmed_bulk_import_guide.md) - Complete PubMed mirroring documentation
- `pubmed_bulk_cli.py` - Main PubMed download and import CLI
