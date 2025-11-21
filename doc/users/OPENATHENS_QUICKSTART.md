# OpenAthens Quick Start Guide

Get started with OpenAthens proxy authentication in 5 minutes.

## Prerequisites

```bash
# Install Playwright
uv add playwright
uv run python -m playwright install chromium
```

## Configuration

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

**Replace** `yourinstitution.openathens.net` with your actual institution's OpenAthens URL.

## First Time Setup

1. **Find Your OpenAthens URL**
   - Check your library website
   - Contact IT/library support
   - Usually: `https://[institution].openathens.net`

2. **Initial Login**
   ```bash
   # Run any PDF download command
   uv run python scripts/download_missing_pdfs.py --batch-size 1
   ```

3. **Complete Authentication**
   - Browser opens automatically
   - Log in with institutional credentials
   - Complete 2FA if required
   - Browser closes when authenticated
   - Session saved for 24 hours

## Usage

### Command Line

```bash
# Download PDFs (automatically uses OpenAthens)
uv run python scripts/download_missing_pdfs.py --batch-size 20

# Import medRxiv with PDFs
uv run python medrxiv_import_cli.py update --download-pdfs
```

### Python Code

```python
from bmlibrarian.utils.pdf_manager import PDFManager
from bmlibrarian.config import get_openathens_config

# Load config and create PDF manager
pdf_manager = PDFManager(openathens_config=get_openathens_config())

# Download PDF
document = {
    'id': 12345,
    'pdf_url': 'https://www.nature.com/articles/s41586-024-12345.pdf',
    'title': 'Example Paper'
}

pdf_path = pdf_manager.download_pdf(document)
```

## Session Management

```python
# Check status
status = pdf_manager.get_openathens_status()
print(f"Authenticated: {status['authenticated']}")
print(f"Time remaining: {status['time_remaining_hours']:.1f} hours")

# Manually login
pdf_manager.login_openathens()

# Refresh expired session
pdf_manager.refresh_openathens_session()

# Clear session
pdf_manager.clear_openathens_session()
```

## Troubleshooting

### Browser Doesn't Open
```bash
# Reinstall Playwright
uv run python -m playwright install chromium
```

### Login Timeout
- Increase `login_timeout` in config (seconds)
- Default: 300 (5 minutes)

### Session Expires Too Fast
- Increase `session_timeout_hours`
- Enable `auto_login` for automatic re-authentication

### 2FA Issues
- Set `headless: false` (required for 2FA)
- Use authenticator app instead of SMS

## Examples

### Run Demo

```bash
uv run python examples/openathens_demo.py
```

### Quick Test

```python
from bmlibrarian.utils.openathens_auth import create_openathens_auth

auth = create_openathens_auth(
    institution_url="https://yourinstitution.openathens.net",
    auto_login=True
)

if auth.is_authenticated():
    print("✅ Ready!")
    print(auth.get_session_info())
```

## Security

- Session stored at: `~/.bmlibrarian/openathens_session.pkl`
- **Don't share this file** - contains authentication
- Clear session on shared computers: `pdf_manager.clear_openathens_session()`

## Help

- Full Guide: `doc/users/openathens_guide.md`
- Demo: `examples/openathens_demo.py`
- Issues: https://github.com/hherb/bmlibrarian/issues

## Session File Location

```
~/.bmlibrarian/
├── config.json              # Your configuration
└── openathens_session.pkl   # Session cookies (auto-created)
```

## Common URLs

Find your institution's OpenAthens URL:

- Check library website for "Remote Access" or "Off-Campus Access"
- Search: "[your university] openathens"
- Contact library IT support
- Format usually: `https://[institution].openathens.net`

## Next Steps

1. ✅ Configure `~/.bmlibrarian/config.json`
2. ✅ Complete first-time login
3. ✅ Download PDFs through OpenAthens proxy
4. 📚 Read full guide: `doc/users/openathens_guide.md`
