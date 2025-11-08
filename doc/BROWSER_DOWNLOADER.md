# Browser-Based PDF Downloader

This module provides browser automation capabilities for downloading PDFs from URLs that have anti-bot protections like Cloudflare verification, CAPTCHAs, or other browser checks.

## Features

- **Cloudflare Bypass**: Automatically waits for Cloudflare "Checking your browser" verification
- **Stealth Mode**: Uses browser fingerprint evasion techniques to avoid detection
- **Automatic Fallback**: Integrated with PDFManager to automatically try browser download when regular HTTP download fails
- **Batch Processing**: Efficient batch downloading with persistent browser session
- **Multiple Detection Methods**: Finds PDFs via direct links, download buttons, or embedded content

## Installation

Install Playwright and browser drivers:

```bash
# Add playwright to dependencies
uv add playwright

# Install Chromium browser driver
uv run python -m playwright install chromium
```

## Usage

### Standalone Script

Download PDFs using browser automation for documents with Cloudflare-protected URLs:

```bash
# Download 20 documents in headless mode
uv run python download_pdfs_with_browser.py --batch-size 20

# Run with visible browser (for debugging)
uv run python download_pdfs_with_browser.py --visible --batch-size 10

# Process multiple batches
uv run python download_pdfs_with_browser.py --batch-size 50 --max-batches 5

# Adjust Cloudflare wait time
uv run python download_pdfs_with_browser.py --cloudflare-wait 60

# Show successful downloads in output
uv run python download_pdfs_with_browser.py --show-success
```

### Programmatic Usage

#### Async API (Recommended for batch operations)

```python
from bmlibrarian.utils.browser_downloader import BrowserDownloader
from pathlib import Path
import asyncio

async def download_multiple():
    # Start browser once for multiple downloads
    async with BrowserDownloader(headless=True) as downloader:
        urls = [
            "https://example.com/paper1.pdf",
            "https://example.com/paper2.pdf",
            "https://example.com/paper3.pdf"
        ]

        for i, url in enumerate(urls):
            result = await downloader.download_pdf(
                url=url,
                save_path=Path(f"/tmp/paper{i}.pdf"),
                wait_for_cloudflare=True,
                max_wait=30
            )

            if result['status'] == 'success':
                print(f"Downloaded: {result['path']} ({result['size']} bytes)")
            else:
                print(f"Failed: {result['error']}")

asyncio.run(download_multiple())
```

#### Synchronous API (Simple single downloads)

```python
from bmlibrarian.utils.browser_downloader import download_pdf_with_browser
from pathlib import Path

result = download_pdf_with_browser(
    url="https://example.com/paper.pdf",
    save_path=Path("/tmp/paper.pdf"),
    headless=True,
    timeout=60000  # milliseconds
)

if result['status'] == 'success':
    print(f"Success: {result['path']} ({result['size']} bytes)")
else:
    print(f"Failed: {result['error']}")
```

#### Integration with PDFManager

The browser downloader is automatically integrated with PDFManager:

```python
from bmlibrarian.utils.pdf_manager import PDFManager

pdf_manager = PDFManager(base_dir=Path("~/pdfs"), db_conn=conn)

# Automatically tries browser download if regular download fails
pdf_path = pdf_manager.download_pdf(
    document={'id': 123, 'pdf_url': 'https://example.com/paper.pdf'},
    use_browser_fallback=True  # default: True
)
```

To disable browser fallback:

```python
pdf_path = pdf_manager.download_pdf(
    document=doc,
    use_browser_fallback=False  # only use regular HTTP download
)
```

## How It Works

### Stealth Techniques

The browser downloader uses multiple techniques to avoid detection:

1. **WebDriver Masking**: Removes `navigator.webdriver` flag
2. **Browser Fingerprinting**: Adds realistic plugins, mimeTypes, and chrome objects
3. **Realistic Headers**: Uses current browser User-Agent and headers
4. **Viewport Configuration**: Sets standard desktop resolution (1920x1080)
5. **Locale Settings**: Configures timezone, language, and permissions

### Cloudflare Detection

The downloader automatically detects Cloudflare verification by looking for:
- Page title containing "Just a moment" or "Checking your browser"
- Content containing "cloudflare", "cf-challenge", or "cf_chl_"

It waits up to 30 seconds (configurable) for the verification to complete before proceeding.

### PDF Detection Methods

The downloader tries multiple methods to find and download PDFs:

1. **Direct Response**: Checks if initial response is a PDF (Content-Type: application/pdf)
2. **URL Detection**: Checks if redirected URL ends with .pdf
3. **Link Scanning**: Searches page for `<a href="*.pdf">` links
4. **Download Buttons**: Looks for elements with `download` attribute or "Download" text
5. **Embedded Content**: Checks if page content starts with PDF magic bytes (%PDF)

## Limitations

### What It Can Handle

- ✅ Cloudflare "Checking your browser" verification
- ✅ JavaScript-based redirects
- ✅ Cookie-based access control
- ✅ Dynamic content loading
- ✅ Download buttons requiring clicks

### What It Cannot Handle

- ❌ Cloudflare Turnstile CAPTCHAs (requires manual solving)
- ❌ reCAPTCHA v2/v3 (requires CAPTCHA solving service)
- ❌ Login-protected content (requires authentication)
- ❌ Paywall-protected content (requires subscription)

For CAPTCHAs, you may need to:
1. Run in visible mode (`--visible`) to manually solve them
2. Integrate a CAPTCHA solving service (e.g., 2captcha, Anti-Captcha)
3. Use authenticated sessions if you have legitimate access

## Troubleshooting

### Playwright Not Installed

```
ImportError: No module named 'playwright'
```

**Solution**: Install playwright
```bash
uv add playwright
uv run python -m playwright install chromium
```

### Browser Driver Missing

```
playwright._impl._errors.Error: Executable doesn't exist
```

**Solution**: Install browser drivers
```bash
uv run python -m playwright install chromium
```

### Cloudflare Verification Timeout

```
Cloudflare verification timeout after 30s
```

**Solution**: Increase wait time
```bash
uv run python download_pdfs_with_browser.py --cloudflare-wait 60
```

Or run in visible mode to see what's happening:
```bash
uv run python download_pdfs_with_browser.py --visible
```

### Download Failed: Could not find PDF content

**Possible causes**:
1. Page requires login/authentication
2. CAPTCHA challenge present
3. Paywall or subscription required
4. PDF not actually available at URL

**Debug steps**:
```bash
# Run in visible mode to see the page
uv run python download_pdfs_with_browser.py --visible --batch-size 1
```

## Performance Considerations

### Memory Usage

Browser automation uses more memory than regular HTTP requests:
- **HTTP download**: ~10-20 MB per process
- **Browser download**: ~200-400 MB per browser instance

### Speed

- **HTTP download**: 1-5 seconds per PDF
- **Browser download**: 10-30 seconds per PDF (including Cloudflare wait)

### Best Practices

1. **Use batch processing**: Start browser once for multiple downloads
2. **Filter candidates**: Only use browser download for known problematic URLs
3. **Set reasonable timeouts**: Don't wait too long for verification
4. **Monitor resources**: Watch memory usage with large batches

## Configuration Options

### BrowserDownloader Parameters

- `headless` (bool): Run browser in headless mode (default: True)
- `timeout` (int): Timeout for page operations in milliseconds (default: 60000)

### download_pdf Parameters

- `url` (str): URL to download from
- `save_path` (Path): Path to save the PDF
- `wait_for_cloudflare` (bool): Wait for Cloudflare verification (default: True)
- `max_wait` (int): Maximum seconds to wait for verification (default: 30)

## Security Notes

### Privacy

Browser automation makes real browser requests that:
- Use your IP address
- Execute JavaScript (sandboxed by Playwright)
- May set cookies and tracking data

For privacy-sensitive operations, consider:
- Using a VPN or proxy
- Clearing browser data between sessions
- Using Tor or privacy-focused browsers

### Rate Limiting

Respect website rate limits:
- Add delays between requests
- Don't overwhelm servers with parallel requests
- Honor robots.txt and terms of service

### Legal Considerations

This tool should only be used:
- For content you have legitimate access to
- In compliance with website terms of service
- For research and personal use within fair use guidelines

Do NOT use this tool to:
- Bypass paywalls for copyrighted content
- Download content you don't have rights to access
- Violate computer fraud or abuse laws
- Circumvent DRM or access controls

## Examples

### Example 1: Download with Retry Logic

```python
from bmlibrarian.utils.browser_downloader import download_pdf_with_browser
from pathlib import Path
import time

def download_with_retry(url, save_path, max_retries=3):
    for attempt in range(max_retries):
        result = download_pdf_with_browser(url, save_path, headless=True)

        if result['status'] == 'success':
            return result

        print(f"Attempt {attempt + 1} failed: {result['error']}")
        if attempt < max_retries - 1:
            time.sleep(5)  # Wait before retry

    return result
```

### Example 2: Batch Download with Progress

```python
import asyncio
from bmlibrarian.utils.browser_downloader import BrowserDownloader
from pathlib import Path

async def batch_download_with_progress(urls):
    results = []

    async with BrowserDownloader(headless=True) as downloader:
        for i, url in enumerate(urls, 1):
            print(f"Downloading {i}/{len(urls)}: {url}")

            save_path = Path(f"/tmp/paper_{i}.pdf")
            result = await downloader.download_pdf(url, save_path)

            results.append(result)

            if result['status'] == 'success':
                print(f"  ✓ Success ({result['size']} bytes)")
            else:
                print(f"  ✗ Failed: {result['error']}")

    return results
```

### Example 3: Filter URLs for Browser Download

```python
from bmlibrarian.utils.pdf_manager import PDFManager

def smart_download(document, pdf_manager):
    """Try regular download first, browser download if needed."""

    # Known problematic domains that need browser
    browser_needed_domains = [
        'journals.aps.org',
        'www.nature.com',
        'science.org',
        # Add more as needed
    ]

    pdf_url = document.get('pdf_url', '')
    needs_browser = any(domain in pdf_url for domain in browser_needed_domains)

    if needs_browser:
        # Use browser directly
        return pdf_manager.download_pdf(document, use_browser_fallback=True)
    else:
        # Try regular download first
        path = pdf_manager.download_pdf(document, use_browser_fallback=False)
        if not path:
            # Fallback to browser if regular fails
            path = pdf_manager.download_pdf(document, use_browser_fallback=True)
        return path
```

## Contributing

To improve the browser downloader:

1. **Add more stealth techniques**: Research latest detection methods
2. **Improve PDF detection**: Add more ways to find download links
3. **Add CAPTCHA integration**: Integrate solving services
4. **Add authentication support**: Handle login-protected content
5. **Optimize performance**: Reduce memory usage and download time

Report issues with specific URLs that fail to download, including:
- URL (if shareable)
- Error message
- Website domain
- Whether visible mode works
