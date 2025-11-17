# OpenAthens Proxy Authentication Guide

BMLibrarian supports OpenAthens proxy authentication for accessing paywalled journal articles through your institutional subscription. This guide explains how to set up and use OpenAthens authentication for PDF downloads.

## Table of Contents

- [Overview](#overview)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Configuration](#configuration)
- [Usage](#usage)
  - [Command Line](#command-line)
  - [Programmatic](#programmatic)
  - [With PDFManager](#with-pdfmanager)
- [Session Management](#session-management)
- [Troubleshooting](#troubleshooting)
- [Security Considerations](#security-considerations)

## Overview

OpenAthens is a widely-used authentication system that allows academic institutions to provide access to subscription-based resources. BMLibrarian's OpenAthens integration:

- **2FA Support**: Works with two-factor authentication
- **Session Persistence**: Maintains login for 24 hours (configurable)
- **Automatic Re-authentication**: Prompts for re-login when session expires
- **Seamless Integration**: Works transparently with PDF downloads
- **Secure Storage**: Encrypted session cookies stored locally

## Prerequisites

Before using OpenAthens authentication, you need:

1. **Institutional Access**: Valid credentials for an institution with OpenAthens subscription
2. **OpenAthens URL**: Your institution's OpenAthens proxy URL
   - Usually in format: `https://institution.openathens.net`
   - Contact your library or IT department if you don't know the URL
3. **Playwright**: Browser automation library for handling 2FA
   ```bash
   uv add playwright
   uv run python -m playwright install chromium
   ```

## Installation

OpenAthens support is built into BMLibrarian. Just ensure Playwright is installed:

```bash
# Install Playwright
uv add playwright

# Install Chromium browser driver
uv run python -m playwright install chromium
```

## Configuration

### Method 1: Configuration File (Recommended)

Edit `~/.bmlibrarian/config.json`:

```json
{
  "openathens": {
    "enabled": true,
    "institution_url": "https://yourinstitution.openathens.net",
    "session_timeout_hours": 24,
    "auto_login": true,
    "login_timeout": 300,
    "headless": false
  }
}
```

**Configuration Options:**

- `enabled` (bool): Enable OpenAthens proxy for PDF downloads
- `institution_url` (str): Your institution's OpenAthens URL
- `session_timeout_hours` (int): Hours before session expires (default: 24)
- `auto_login` (bool): Automatically login on startup if session expired (default: true)
- `login_timeout` (int): Maximum seconds to wait for login completion (default: 300)
- `headless` (bool): Run browser in headless mode for login (default: false for 2FA visibility)

### Method 2: Programmatic Configuration

```python
from bmlibrarian.utils.pdf_manager import PDFManager

openathens_config = {
    'enabled': True,
    'institution_url': 'https://yourinstitution.openathens.net',
    'session_timeout_hours': 24,
    'auto_login': True,
    'login_timeout': 300,
    'headless': False
}

pdf_manager = PDFManager(openathens_config=openathens_config)
```

## Usage

### Command Line

OpenAthens works automatically when configured. When you use any PDF download script:

```bash
# Download missing PDFs (will use OpenAthens if configured)
uv run python scripts/download_missing_pdfs.py --batch-size 20

# Import medRxiv with PDFs
uv run python medrxiv_import_cli.py update --download-pdfs
```

**First-time login:**
1. Browser window opens automatically
2. Log in to your institution's OpenAthens portal
3. Complete 2FA if required
4. Browser closes automatically when authentication succeeds
5. Session is saved for 24 hours

### Programmatic

#### Basic Authentication

```python
from bmlibrarian.utils.openathens_auth import OpenAthensAuth

# Create authenticator
auth = OpenAthensAuth(
    institution_url="https://yourinstitution.openathens.net",
    headless=False  # Show browser for 2FA
)

# Login (browser opens for user interaction)
if auth.login_sync(wait_for_login=300):
    print("Login successful!")
    print(f"Session info: {auth.get_session_info()}")
else:
    print("Login failed")

# Construct proxy URL
original_url = "https://www.nature.com/articles/s41586-024-12345.pdf"
proxy_url = auth.construct_proxy_url(original_url)
print(f"Proxy URL: {proxy_url}")
```

#### With PDFManager

```python
from bmlibrarian.utils.pdf_manager import PDFManager
from bmlibrarian.config import get_openathens_config

# Load from config file
openathens_config = get_openathens_config()

# Create PDF manager
pdf_manager = PDFManager(openathens_config=openathens_config)

# Check status
status = pdf_manager.get_openathens_status()
print(f"Authenticated: {status.get('authenticated')}")

# Download PDF (automatically uses OpenAthens proxy)
document = {
    'id': 12345,
    'title': 'Example Paper',
    'pdf_url': 'https://www.nature.com/articles/s41586-024-12345.pdf',
    'doi': '10.1038/s41586-024-12345',
    'publication_date': '2024-01-01'
}

pdf_path = pdf_manager.download_pdf(document)
if pdf_path:
    print(f"Downloaded to: {pdf_path}")
```

#### Manual Login

```python
from bmlibrarian.utils.pdf_manager import PDFManager

pdf_manager = PDFManager(openathens_config={'enabled': True, ...})

# Check if authentication needed
if not pdf_manager.get_openathens_status().get('authenticated'):
    # Manually trigger login
    pdf_manager.login_openathens(wait_for_login=300)
```

## Session Management

### Session Storage

OpenAthens sessions are stored at: `~/.bmlibrarian/openathens_session.pkl`

This file contains:
- Session cookies
- Creation timestamp
- Institution URL
- User agent

### Session Lifetime

- Default: 24 hours
- Configurable via `session_timeout_hours`
- Automatically refreshed if `auto_login` is enabled
- Can be manually refreshed

### Check Session Status

```python
from bmlibrarian.utils.pdf_manager import PDFManager

pdf_manager = PDFManager(openathens_config=...)

status = pdf_manager.get_openathens_status()
print(f"""
OpenAthens Status:
- Authenticated: {status.get('authenticated')}
- Created: {status.get('created_at')}
- Expires: {status.get('expires_at')}
- Time remaining: {status.get('time_remaining_hours'):.1f} hours
- Cookies: {status.get('cookie_count')}
""")
```

### Refresh Session

```python
# Automatically refresh if expired
pdf_manager.refresh_openathens_session()
```

### Clear Session

```python
# Clear session and require re-login
pdf_manager.clear_openathens_session()
```

## Troubleshooting

### Browser Not Opening

**Problem**: Browser doesn't open for login

**Solutions**:
1. Check Playwright installation:
   ```bash
   uv run python -m playwright install chromium
   ```
2. Try visible mode (set `headless: false`)
3. Check for error messages in logs

### Login Timeout

**Problem**: Login times out before completion

**Solutions**:
1. Increase `login_timeout` in config (default: 300 seconds)
2. Complete login faster
3. Check internet connection

### 2FA Issues

**Problem**: 2FA code not working

**Solutions**:
1. Ensure `headless: false` (can't complete 2FA in headless mode)
2. Use authenticator app instead of SMS if available
3. Check browser console for JavaScript errors

### Session Expired

**Problem**: Session expires too quickly

**Solutions**:
1. Increase `session_timeout_hours` (but institution may enforce limits)
2. Enable `auto_login` for automatic re-authentication
3. Check institution's session policies

### PDF Download Fails

**Problem**: PDF download fails even with valid session

**Solutions**:
1. Check if URL is actually behind paywall
2. Verify institution has access to the journal
3. Try manual download through browser to confirm access
4. Check logs for specific error messages
5. Some journals may block automated downloads

### Proxy URL Issues

**Problem**: Proxy URL not constructed correctly

**Solutions**:
1. Verify `institution_url` is correct
2. Check if institution uses custom proxy format
3. Contact library IT for correct OpenAthens URL

## Security Considerations

### Session File Security

- Session file stored at `~/.bmlibrarian/openathens_session.pkl`
- Contains authentication cookies
- **Protect this file** - anyone with access can use your session
- File permissions set to user-only (600)

### Best Practices

1. **Don't share session file**: Contains your authentication
2. **Use secure systems**: Only use on trusted computers
3. **Clear sessions**: Clear session when done on shared systems
4. **Monitor usage**: Check your institution's access logs periodically
5. **Report issues**: Report suspicious activity to your institution

### Privacy

- OpenAthens proxy logs your access
- Institution can see what resources you access
- Comply with your institution's acceptable use policy
- Don't share credentials or sessions

### Rate Limiting

- Respect journal rate limits
- Don't overwhelm servers with rapid requests
- Use reasonable batch sizes for downloads
- Add delays between requests if needed

## Examples

### Example 1: Simple Setup

```python
from bmlibrarian.utils.openathens_auth import create_openathens_auth

# One-liner setup with auto-login
auth = create_openathens_auth(
    institution_url="https://yourinstitution.openathens.net",
    auto_login=True
)

# Check if ready
if auth.is_authenticated():
    print("Ready to download!")
```

### Example 2: Batch Download with OpenAthens

```python
from bmlibrarian.utils.pdf_manager import PDFManager
import psycopg

# Setup
conn = psycopg.connect("dbname=knowledgebase")
pdf_manager = PDFManager(
    db_conn=conn,
    openathens_config={
        'enabled': True,
        'institution_url': 'https://yourinstitution.openathens.net',
        'auto_login': True
    }
)

# Download missing PDFs
stats = pdf_manager.download_missing_pdfs(
    batch_size=50,
    max_batches=10
)

print(f"Downloaded: {stats['downloaded']}")
print(f"Failed: {stats['failed']}")
```

### Example 3: Custom Session Handling

```python
from bmlibrarian.utils.openathens_auth import OpenAthensAuth

auth = OpenAthensAuth(
    institution_url="https://yourinstitution.openathens.net",
    session_timeout_hours=48,  # 2 days
    headless=False
)

# Manual login control
if not auth.is_authenticated():
    print("Please login...")
    auth.login_sync(wait_for_login=600)  # 10 minute timeout

# Use session for custom requests
import requests

url = "https://www.nature.com/articles/s41586-024-12345.pdf"
proxy_url = auth.construct_proxy_url(url)

response = requests.get(
    proxy_url,
    headers=auth.get_session_headers(),
    cookies=auth.get_cookies_dict()
)

if response.status_code == 200:
    with open('paper.pdf', 'wb') as f:
        f.write(response.content)
```

## Demo Script

Run the interactive demo to explore OpenAthens features:

```bash
uv run python examples/openathens_demo.py
```

The demo includes:
1. Basic authentication
2. PDFManager integration
3. Configuration file usage
4. Session management

## Support

If you encounter issues:

1. Check this guide's [Troubleshooting](#troubleshooting) section
2. Review logs for error messages
3. Verify institution credentials and URL
4. Contact your institution's library or IT support
5. Report bugs at: https://github.com/hherb/bmlibrarian/issues

## References

- [OpenAthens Documentation](https://docs.openathens.net/)
- [Playwright Documentation](https://playwright.dev/python/)
- BMLibrarian PDF Manager: `src/bmlibrarian/utils/pdf_manager.py`
- OpenAthens Auth Module: `src/bmlibrarian/utils/openathens_auth.py`
