# OpenAthens Authentication Guide

This guide explains how to use BMLibrarian's OpenAthens authentication module to access institutional journal subscriptions and paywalled content.

## Overview

OpenAthens is a widely-used federated authentication system that allows users to access institutional resources (journal articles, databases, etc.) using their institutional credentials. BMLibrarian's OpenAthens module enables:

- **Authenticated PDF downloads** from institutional subscriptions
- **Secure session management** with encrypted storage
- **Browser automation** for interactive institutional login
- **Cookie-based authentication** persistence across requests

## Installation

Install the required dependencies:

```bash
# Install Playwright for browser automation
uv add playwright

# Install Chromium browser driver
uv run python -m playwright install chromium
```

## Quick Start

### Basic Usage

```python
from bmlibrarian.utils.openathens_auth import OpenAthensConfig, OpenAthensAuth
from bmlibrarian.utils.pdf_manager import PDFManager

# 1. Configure OpenAthens
config = OpenAthensConfig(
    institution_url='https://your-institution.openathens.net/login'
)

# 2. Create authentication instance
auth = OpenAthensAuth(config)

# 3. Perform interactive login (opens browser)
# NOTE: This is an async function, use await or asyncio.run()
import asyncio
success = asyncio.run(auth.login_interactive())

if success:
    print("Login successful!")
else:
    print("Login failed")

# 4. Use with PDFManager for authenticated downloads
pdf_manager = PDFManager(openathens_auth=auth)

# Downloads will automatically use your authenticated session
document = {
    'id': 12345,
    'pdf_url': 'https://journal.example.com/article.pdf',
    'doi': '10.1234/example'
}

pdf_path = pdf_manager.download_pdf(document)
```

### Synchronous Login

For simpler use cases without async/await:

```python
from bmlibrarian.utils.openathens_auth import OpenAthensConfig, login_interactive_sync

config = OpenAthensConfig(
    institution_url='https://your-institution.openathens.net/login'
)

# This will block until login completes
auth = login_interactive_sync(config)

# Use auth with PDFManager as shown above
```

## Configuration

### OpenAthensConfig Parameters

```python
config = OpenAthensConfig(
    # Required: Your institution's OpenAthens login URL (HTTPS required)
    institution_url='https://institution.openathens.net/login',

    # Optional: Session expiration time in hours (default: 24)
    session_max_age_hours=24,

    # Optional: Polling interval for auth checks in seconds (default: 1.0)
    auth_check_interval=1.0,

    # Optional: Max seconds to wait for Cloudflare (default: 30)
    cloudflare_wait=30,

    # Optional: Page load timeout in milliseconds (default: 60000)
    page_timeout=60000,

    # Optional: Run browser in headless mode (default: True)
    headless=True,

    # Optional: Session validation cache TTL in seconds (default: 60)
    session_cache_ttl=60
)
```

### Configuration Validation

You can validate your OpenAthens configuration before use to prevent runtime errors:

```python
from bmlibrarian.config import (
    get_openathens_config,
    validate_openathens_config,
    validate_openathens_url
)

# Get config with validation (raises ValueError if invalid)
config = get_openathens_config(validate=True)

# Or validate manually for more control
config = get_openathens_config()
result = validate_openathens_config(config)
if not result.valid:
    print("Configuration errors:")
    for error in result.errors:
        print(f"  - {error}")
if result.warnings:
    print("Warnings:")
    for warning in result.warnings:
        print(f"  - {warning}")

# Validate just the URL
url_result = validate_openathens_url("https://institution.openathens.net")
if not url_result.valid:
    print(f"Invalid URL: {url_result.errors}")
```

**Validation checks include:**
- Institution URL uses HTTPS (required for security)
- Institution URL has a valid hostname
- `session_timeout_hours` is a positive number
- `login_timeout` is a positive number

### Finding Your Institution URL

1. **Via OpenAthens Search**:
   - Go to https://www.openathens.net/
   - Search for your institution
   - Copy the login URL

2. **Via Journal Access**:
   - Visit a journal your institution subscribes to
   - Click "Institutional Login" or "Access through your institution"
   - Select your institution
   - Copy the URL from the redirected login page

3. **Contact Your Library**:
   - Your institutional library can provide the correct OpenAthens URL

## Interactive Login Process

When you call `login_interactive()`, the following happens:

1. **Browser Launch**: A browser window opens (or runs headless)
2. **Navigation**: Browser navigates to your institution's login page
3. **User Authentication**: You log in with your institutional credentials
4. **Cookie Detection**: System monitors for authentication cookies
5. **Session Capture**: Upon successful login, cookies are saved securely
6. **Browser Cleanup**: Browser closes automatically

### What You Need to Do

During interactive login:

1. **Enter your credentials** on your institution's login page
2. **Complete any 2FA** (if required by your institution)
3. **Wait for confirmation** - system will detect successful authentication
4. **Browser closes automatically** when login is complete

### Troubleshooting Login

**Browser doesn't open (headless mode)**:
```python
# Use visible browser for debugging
config = OpenAthensConfig(
    institution_url='https://institution.openathens.net/login',
    headless=False  # Show browser window
)
```

**Login times out**:
```python
# Increase timeout for slow networks
config = OpenAthensConfig(
    institution_url='https://institution.openathens.net/login',
    page_timeout=120000  # 2 minutes
)
```

**Authentication not detected**:
- Check that you completed the entire login process
- Verify you reached the post-login landing page
- Some institutions have multi-step authentication
- Run with `headless=False` to see what's happening

## Session Management

### Session Storage

Sessions are stored securely in:
```
~/.bmlibrarian/openathens_session.json
```

**Security Features**:
- **File Permissions**: 600 (owner read/write only)
- **JSON Format**: Safe serialization (not pickle)
- **Parent Directory**: 700 permissions (owner access only)

### Session Validation

```python
auth = OpenAthensAuth(config)

# Check if session is valid (not expired)
if auth.is_session_valid():
    print("Session is valid")
else:
    print("Session expired or not found")

# Check authentication with caching
if auth.is_authenticated():
    print("Authenticated")

    # Get cookies for manual use
    cookies = auth.get_cookies()

    # Get user agent from session
    user_agent = auth.get_user_agent()
```

### Session Expiration

Sessions expire after `session_max_age_hours` (default: 24 hours).

To use a different expiration:
```python
config = OpenAthensConfig(
    institution_url='https://institution.openathens.net/login',
    session_max_age_hours=12  # 12 hours
)
```

### Clearing Sessions

```python
auth = OpenAthensAuth(config)

# Clear current session and delete session file
auth.clear_session()
```

## Integration with PDFManager

### Automatic Authentication

PDFManager automatically uses OpenAthens authentication when available:

```python
from bmlibrarian.utils.openathens_auth import OpenAthensConfig, OpenAthensAuth
from bmlibrarian.utils.pdf_manager import PDFManager

# Setup authentication
config = OpenAthensConfig(institution_url='https://institution.openathens.net/login')
auth = OpenAthensAuth(config)

# If session exists and is valid, load it
# Otherwise, perform interactive login
if not auth.is_authenticated():
    import asyncio
    asyncio.run(auth.login_interactive())

# Create PDFManager with authentication
pdf_manager = PDFManager(openathens_auth=auth)

# Downloads will include authentication cookies
document = {'id': 123, 'pdf_url': 'https://paywalled-journal.com/article.pdf'}
pdf_path = pdf_manager.download_pdf(document)
```

### Checking Session Before Download

```python
# Check authentication status before bulk downloads
if not pdf_manager.openathens_auth or not pdf_manager.openathens_auth.is_authenticated():
    print("Warning: Not authenticated. Downloads may fail for paywalled content.")

    # Re-authenticate if needed
    if pdf_manager.openathens_auth:
        import asyncio
        asyncio.run(pdf_manager.openathens_auth.login_interactive())
```

## Security Considerations

### Best Practices

1. **HTTPS Only**: URLs must use HTTPS for secure transmission
2. **Session Files**: Stored with 600 permissions (owner only)
3. **Credential Privacy**: Never log or print session cookies
4. **Network Security**: Use on trusted networks only
5. **Regular Re-authentication**: Don't rely on expired sessions

### Session File Security

Session files contain sensitive authentication cookies:

```json
{
  "created_at": "2025-01-15T10:30:00",
  "cookies": [
    {"name": "openathens_session", "value": "sensitive_value"}
  ],
  "institution_url": "https://institution.openathens.net/login",
  "user_agent": "Mozilla/5.0..."
}
```

**Protection Mechanisms**:
- **File permissions**: 600 (owner read/write only)
- **Directory permissions**: 700 (owner access only)
- **JSON format**: Safe deserialization (no code execution risk)
- **No plaintext credentials**: Only session cookies stored

### What's NOT Stored

- ❌ Your institutional username/password
- ❌ 2FA codes or recovery keys
- ❌ Any personal identification information
- ✅ Only authentication cookies (like browser cookies)

### Network Connectivity

Authentication requires:
- Access to your institution's OpenAthens server
- Access to journal/publisher websites
- Stable internet connection during login

The module performs connectivity checks before attempting login.

## Advanced Usage

### Custom Cookie Patterns

If your institution uses non-standard authentication cookies:

```python
config = OpenAthensConfig(
    institution_url='https://institution.openathens.net/login'
)

# Add custom cookie patterns
config.auth_cookie_patterns.append(r'custom_auth_.*')
config.auth_cookie_patterns.append(r'institution_session')
```

### Session Validation Caching

To reduce overhead, session validation is cached:

```python
config = OpenAthensConfig(
    institution_url='https://institution.openathens.net/login',
    session_cache_ttl=120  # Cache validation for 2 minutes
)
```

This prevents redundant validation checks when downloading multiple PDFs.

### Manual Cookie Management

For advanced use cases:

```python
auth = OpenAthensAuth(config)

# Get cookies as list of dicts
cookies = auth.get_cookies()

# Use with requests library
import requests
cookie_dict = {c['name']: c['value'] for c in cookies}

response = requests.get(
    'https://journal.example.com/article.pdf',
    cookies=cookie_dict,
    headers={'User-Agent': auth.get_user_agent()}
)
```

## Common Issues

### Issue: "Institution URL must use HTTPS"

**Cause**: Attempted to use HTTP URL instead of HTTPS.

**Solution**: Use HTTPS URL from your institution:
```python
# ❌ Wrong
config = OpenAthensConfig(institution_url='http://institution.edu/login')

# ✅ Correct
config = OpenAthensConfig(institution_url='https://institution.openathens.net/login')
```

### Issue: "Playwright not installed"

**Cause**: Missing Playwright dependency.

**Solution**:
```bash
uv add playwright
uv run python -m playwright install chromium
```

### Issue: "Network connectivity check failed"

**Cause**: Cannot reach institution URL.

**Solutions**:
- Check your internet connection
- Verify the institution URL is correct
- Check if VPN is required for institutional access
- Ensure firewall allows connections

### Issue: "Authentication timeout or failed"

**Causes**:
- Incomplete login process
- Incorrect credentials
- Multi-step authentication not completed
- Cookie patterns not matching

**Solutions**:
```python
# Run with visible browser to debug
config = OpenAthensConfig(
    institution_url='https://institution.openathens.net/login',
    headless=False  # See what's happening
)

# Increase timeout for slow processes
config = OpenAthensConfig(
    institution_url='https://institution.openathens.net/login',
    page_timeout=120000  # 2 minutes
)
```

### Issue: Downloads fail despite authentication

**Possible causes**:
- Session expired (check `is_authenticated()`)
- Institution doesn't subscribe to that journal
- Journal requires additional authentication
- Network issues

**Solutions**:
```python
# Check session status
if not auth.is_authenticated():
    # Re-authenticate
    import asyncio
    asyncio.run(auth.login_interactive())

# Check session age
if auth.session_data:
    from datetime import datetime
    age = datetime.now() - auth.session_data['created_at']
    print(f"Session age: {age}")
```

## Example Workflows

### Single PDF Download

```python
from bmlibrarian.utils.openathens_auth import OpenAthensConfig, OpenAthensAuth
from bmlibrarian.utils.pdf_manager import PDFManager
import asyncio

# Configure and authenticate
config = OpenAthensConfig(institution_url='https://institution.openathens.net/login')
auth = OpenAthensAuth(config)

# Login if needed
if not auth.is_authenticated():
    success = asyncio.run(auth.login_interactive())
    if not success:
        raise RuntimeError("Login failed")

# Download PDF
pdf_manager = PDFManager(openathens_auth=auth)
document = {
    'id': 12345,
    'pdf_url': 'https://journal.example.com/article.pdf',
    'doi': '10.1234/example'
}

pdf_path = pdf_manager.download_pdf(document)
if pdf_path:
    print(f"Downloaded: {pdf_path}")
else:
    print("Download failed")
```

### Batch PDF Downloads

```python
from bmlibrarian.utils.openathens_auth import OpenAthensConfig, OpenAthensAuth
from bmlibrarian.utils.pdf_manager import PDFManager
import asyncio

# Setup
config = OpenAthensConfig(institution_url='https://institution.openathens.net/login')
auth = OpenAthensAuth(config)

if not auth.is_authenticated():
    asyncio.run(auth.login_interactive())

pdf_manager = PDFManager(openathens_auth=auth)

# Batch download
documents = [
    {'id': 1, 'pdf_url': 'https://journal.com/article1.pdf', 'doi': '10.1/a'},
    {'id': 2, 'pdf_url': 'https://journal.com/article2.pdf', 'doi': '10.1/b'},
    {'id': 3, 'pdf_url': 'https://journal.com/article3.pdf', 'doi': '10.1/c'},
]

for doc in documents:
    print(f"Downloading {doc['doi']}...")

    # Check session is still valid (cached check)
    if not auth.is_authenticated():
        print("Session expired, re-authenticating...")
        asyncio.run(auth.login_interactive())

    pdf_path = pdf_manager.download_pdf(doc)
    if pdf_path:
        print(f"  ✓ {pdf_path}")
    else:
        print(f"  ✗ Failed")
```

### Session Reuse

```python
from bmlibrarian.utils.openathens_auth import OpenAthensConfig, OpenAthensAuth

# Day 1: Login and download
config = OpenAthensConfig(institution_url='https://institution.openathens.net/login')
auth = OpenAthensAuth(config)
asyncio.run(auth.login_interactive())
# ... download PDFs ...

# Day 2: Reuse existing session (no login needed)
config = OpenAthensConfig(institution_url='https://institution.openathens.net/login')
auth = OpenAthensAuth(config)  # Automatically loads saved session

if auth.is_authenticated():
    print("Using existing session")
    # ... download more PDFs ...
else:
    print("Session expired, need to re-login")
    asyncio.run(auth.login_interactive())
```

## Limitations

### What OpenAthens Can Access

- ✅ Journals your institution subscribes to
- ✅ Databases with institutional access
- ✅ Resources configured in your institution's OpenAthens

### What OpenAthens Cannot Access

- ❌ Journals your institution doesn't subscribe to
- ❌ Resources not configured for OpenAthens
- ❌ Content requiring separate personal accounts
- ❌ Paywalled content without institutional access

### Technical Limitations

- **Browser dependency**: Requires Playwright and Chromium
- **Interactive login**: Initial authentication requires user interaction
- **Session persistence**: Sessions expire after configured time
- **Network dependency**: Requires internet access for authentication
- **Cookie-based**: Relies on cookie authentication (standard for OpenAthens)

## Compliance and Ethics

### Acceptable Use

✅ **Permitted**:
- Downloading articles for personal research
- Accessing content your institution subscribes to
- Automated downloading within reasonable limits
- Educational and academic use

❌ **Not Permitted**:
- Sharing session files with others
- Circumventing paywalls for non-subscribed content
- Mass downloading beyond institutional agreements
- Commercial redistribution of downloaded content

### Responsible Use

1. **Respect institutional policies**: Follow your library's acceptable use policy
2. **Rate limiting**: Don't overwhelm journal servers with requests
3. **Personal use**: Don't share authentication sessions
4. **License compliance**: Respect copyright and licensing terms

### Legal Considerations

- Only download content your institution has legitimate access to
- Comply with publisher terms of service
- Respect copyright laws in your jurisdiction
- Follow your institution's acceptable use policies

## Support

### Getting Help

1. **Check session status**: Use `is_authenticated()` to verify
2. **Run with visible browser**: Set `headless=False` to debug
3. **Check logs**: Enable logging to see detailed operations
4. **Contact your library**: Verify institutional access

### Reporting Issues

When reporting issues, include:
- Institution type (university, hospital, etc.)
- OpenAthens URL (if sharable)
- Error messages
- Browser behavior (if visible)
- Session validation status

**Do NOT include**:
- Session cookies or session file contents
- Your institutional credentials
- Any authentication tokens

## See Also

- [PDF Import Guide](pdf_import_guide.md) - Importing PDFs into BMLibrarian
- [Browser Downloader](../BROWSER_DOWNLOADER.md) - Browser-based PDF downloads
- [PDF Manager](../developers/pdf_manager.md) - PDF management system
