"""Browser-based PDF downloader for handling Cloudflare and anti-bot protections.

This module uses Playwright to download PDFs from URLs that have anti-bot protections
like Cloudflare verification, CAPTCHAs, or other browser checks.
"""

import logging
import time
from pathlib import Path
from typing import Optional, Dict, Any
import asyncio

logger = logging.getLogger(__name__)


class BrowserDownloader:
    """Download PDFs using browser automation to bypass anti-bot protections."""

    def __init__(self, headless: bool = True, timeout: int = 60000):
        """Initialize browser downloader.

        Args:
            headless: Run browser in headless mode (default: True)
            timeout: Timeout for page operations in milliseconds (default: 60000)
        """
        self.headless = headless
        self.timeout = timeout
        self.browser = None
        self.playwright = None

    async def __aenter__(self):
        """Async context manager entry."""
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.stop()

    async def start(self):
        """Start the browser instance."""
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            logger.error(
                "Playwright not installed. Install with: uv add playwright && "
                "uv run python -m playwright install chromium"
            )
            raise

        self.playwright = await async_playwright().start()

        # Launch Chromium with stealth settings
        self.browser = await self.playwright.chromium.launch(
            headless=self.headless,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--disable-dev-shm-usage',
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-web-security',
                '--disable-features=IsolateOrigins,site-per-process'
            ]
        )
        logger.info(f"Browser started (headless={self.headless})")

    async def stop(self):
        """Stop the browser instance."""
        if self.browser:
            await self.browser.close()
            logger.info("Browser stopped")
        if self.playwright:
            await self.playwright.stop()

    async def download_pdf(
        self,
        url: str,
        save_path: Path,
        wait_for_cloudflare: bool = True,
        max_wait: int = 30,
        expected_doi: Optional[str] = None
    ) -> Dict[str, Any]:
        """Download a PDF using browser automation.

        Args:
            url: URL to download from
            save_path: Path to save the PDF
            wait_for_cloudflare: Wait for Cloudflare verification to complete
            max_wait: Maximum seconds to wait for verification (default: 30)
            expected_doi: If provided, validate embedded PDF URLs contain this DOI
                         to prevent downloading wrong papers from related article sections

        Returns:
            Dictionary with download result:
                - status: 'success' or 'failed'
                - path: Path to downloaded file (if successful)
                - size: File size in bytes (if successful)
                - error: Error message (if failed)
        """
        if not self.browser:
            return {
                'status': 'failed',
                'error': 'Browser not started. Use async with or call start() first.'
            }

        context = None
        page = None

        try:
            # Create browser context with realistic settings
            context = await self.browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                          'AppleWebKit/537.36 (KHTML, like Gecko) '
                          'Chrome/131.0.0.0 Safari/537.36',
                locale='en-US',
                timezone_id='America/New_York',
                permissions=['notifications'],
                color_scheme='light',
                accept_downloads=True
            )

            # Add stealth scripts to context
            await context.add_init_script("""
                // Override navigator.webdriver
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });

                // Override plugins and mimeTypes
                Object.defineProperty(navigator, 'plugins', {
                    get: () => [1, 2, 3, 4, 5]
                });

                Object.defineProperty(navigator, 'languages', {
                    get: () => ['en-US', 'en']
                });

                // Override permissions
                const originalQuery = window.navigator.permissions.query;
                window.navigator.permissions.query = (parameters) => (
                    parameters.name === 'notifications' ?
                        Promise.resolve({ state: Notification.permission }) :
                        originalQuery(parameters)
                );

                // Add chrome object
                window.chrome = {
                    runtime: {}
                };
            """)

            page = await context.new_page()

            # Set download behavior
            save_path.parent.mkdir(parents=True, exist_ok=True)

            logger.info(f"Navigating to: {url}")

            # For URLs ending in .pdf, try direct fetch first (some sites like PMC
            # block navigation but allow fetch from a page context)
            if url.lower().endswith('.pdf'):
                result = await self._try_direct_fetch(page, url, save_path)
                if result:
                    return result

            # Navigate to URL - don't expect download by default (most sites use PDF viewers)
            response = None
            try:
                response = await page.goto(url, wait_until='domcontentloaded', timeout=self.timeout)
            except Exception as e:
                # If navigation fails because download started, handle it
                if 'Download is starting' in str(e):
                    logger.info("Direct download triggered, waiting for file...")
                    try:
                        async with page.expect_download(timeout=10000) as download_info:
                            download = await download_info.value
                            await download.save_as(save_path)
                            return {
                                'status': 'success',
                                'path': str(save_path),
                                'size': save_path.stat().st_size
                            }
                    except Exception as download_error:
                        return {
                            'status': 'failed',
                            'error': f'Download failed: {download_error}'
                        }
                else:
                    raise

            if not response:
                return {
                    'status': 'failed',
                    'error': 'No response received from URL'
                }

            # Check if we got a PDF directly
            content_type = response.headers.get('content-type', '').lower()
            if 'application/pdf' in content_type:
                logger.info("PDF received directly, downloading...")
                pdf_content = await response.body()

                # Verify it's actually a PDF
                if pdf_content and pdf_content[:4] == b'%PDF':
                    save_path.write_bytes(pdf_content)
                    return {
                        'status': 'success',
                        'path': str(save_path),
                        'size': len(pdf_content)
                    }
                else:
                    logger.warning("Content-Type is PDF but content is not a PDF file")

            # Wait for page to fully load (especially for PDFs that load in viewer)
            try:
                await page.wait_for_load_state('networkidle', timeout=10000)
            except Exception:
                pass  # Continue if timeout

            # Wait for Cloudflare verification if needed
            if wait_for_cloudflare:
                logger.info("Checking for Cloudflare verification...")
                await self._wait_for_cloudflare(page, max_wait)

            # Check for embedded PDF viewer (embed, object, or iframe)
            pdf_src = None

            # Try multiple selectors for embedded PDFs
            selectors = [
                'embed[type="application/pdf"]',
                'object[type="application/pdf"]',
                'iframe[src*=".pdf"]',
                'embed[src*=".pdf"]',
                'object[data*=".pdf"]'
            ]

            for selector in selectors:
                element = await page.query_selector(selector)
                if element:
                    # Try both 'src' and 'data' attributes
                    pdf_src = await element.get_attribute('src') or await element.get_attribute('data')
                    if pdf_src and pdf_src != 'about:blank':  # Skip useless about:blank
                        logger.info(f"Found embedded PDF via {selector}: {pdf_src}")
                        break
                    else:
                        pdf_src = None  # Reset if about:blank

            if pdf_src:
                # Make PDF URL absolute if relative
                from urllib.parse import urljoin
                pdf_url_abs = urljoin(url, pdf_src)

                # CRITICAL: Validate embedded PDF URL matches expected DOI
                # This prevents downloading wrong papers from "related articles" sections
                if expected_doi and not self._url_matches_doi(pdf_url_abs, expected_doi):
                    logger.warning(
                        f"Embedded PDF URL does not match expected DOI {expected_doi}: {pdf_url_abs}"
                    )
                    logger.info("Skipping embedded PDF to avoid downloading wrong document")
                    pdf_src = None  # Skip this embedded PDF
                else:
                    logger.info(f"Downloading from embedded viewer: {pdf_url_abs}")

                    try:
                        response = await page.goto(pdf_url_abs, timeout=self.timeout)
                        pdf_content = await response.body()

                        if pdf_content and pdf_content[:4] == b'%PDF':
                            save_path.write_bytes(pdf_content)
                            return {
                                'status': 'success',
                                'path': str(save_path),
                                'size': len(pdf_content)
                            }
                    except Exception as e:
                        logger.warning(f"Failed to download from embedded src: {e}")

            # Look for download link or button (common on journal sites)
            download_link = await self._find_download_link(page)
            if download_link:
                logger.info(f"Found download link: {download_link}")
                try:
                    # Try to download via the link
                    async with page.expect_download(timeout=15000) as download_info:
                        # Click the link or navigate to it
                        if download_link.startswith('http'):
                            await page.goto(download_link, timeout=self.timeout)
                        else:
                            button = await page.query_selector(f'a[href*="download"], button:has-text("Download")')
                            if button:
                                await button.click()

                    download = await download_info.value
                    await download.save_as(save_path)
                    return {
                        'status': 'success',
                        'path': str(save_path),
                        'size': save_path.stat().st_size
                    }
                except Exception as e:
                    logger.warning(f"Failed to download via link: {e}")

            # Check if page is now showing a PDF
            current_url = page.url
            if current_url.lower().endswith('.pdf'):
                logger.info("PDF URL detected, attempting download...")

                # Try to intercept the PDF download via CDP
                try:
                    client = await page.context.new_cdp_session(page)
                    await client.send('Page.setDownloadBehavior', {
                        'behavior': 'allow',
                        'downloadPath': str(save_path.parent)
                    })
                except Exception as e:
                    logger.debug(f"Could not set download behavior: {e}")

                # Wait a bit for PDF to load
                await asyncio.sleep(2)

                # Try to get the PDF content from the page
                pdf_content = await page.content()

                # Check if it's actually PDF content (binary)
                if pdf_content and pdf_content.strip().startswith('%PDF'):
                    logger.info("PDF content found in page source")
                    save_path.write_bytes(pdf_content.encode('latin-1'))
                    return {
                        'status': 'success',
                        'path': str(save_path),
                        'size': len(pdf_content)
                    }

                # Try fetching as binary
                response_binary = await page.evaluate('''async () => {
                    const response = await fetch(window.location.href);
                    const buffer = await response.arrayBuffer();
                    const bytes = new Uint8Array(buffer);
                    return Array.from(bytes);
                }''')

                if response_binary:
                    pdf_bytes = bytes(response_binary)
                    if pdf_bytes[:4] == b'%PDF':
                        logger.info("PDF retrieved via fetch API")
                        save_path.write_bytes(pdf_bytes)
                        return {
                            'status': 'success',
                            'path': str(save_path),
                            'size': len(pdf_bytes)
                        }

                logger.warning("URL ends with .pdf but could not retrieve PDF content")

            # Look for PDF download link
            pdf_link = await self._find_pdf_link(page)
            if pdf_link:
                logger.info(f"Found PDF link: {pdf_link}")

                # Set up download handler
                async with page.expect_download(timeout=self.timeout) as download_info:
                    await page.goto(pdf_link, timeout=self.timeout)

                download = await download_info.value
                await download.save_as(save_path)

                return {
                    'status': 'success',
                    'path': str(save_path),
                    'size': save_path.stat().st_size
                }

            # Try to get PDF from current page content
            content = await page.content()
            if content.startswith('%PDF'):
                logger.info("PDF content detected in page")
                save_path.write_text(content)
                return {
                    'status': 'success',
                    'path': str(save_path),
                    'size': len(content)
                }

            return {
                'status': 'failed',
                'error': 'Could not find PDF content on page'
            }

        except Exception as e:
            logger.error(f"Browser download failed: {e}")
            return {
                'status': 'failed',
                'error': str(e)
            }

        finally:
            if page:
                await page.close()
            if context:
                await context.close()

    async def _try_direct_fetch(
        self,
        page,
        url: str,
        save_path: Path
    ) -> Optional[Dict[str, Any]]:
        """Try to fetch PDF directly, handling PMC PoW challenges.

        PMC uses a Proof of Work (PoW) challenge that requires:
        1. First navigation to trigger the PoW JavaScript
        2. Waiting for the challenge to complete and set a cookie
        3. Second navigation to download the actual PDF

        This method handles both PMC-style PoW challenges and other sites
        that may serve PDFs directly.

        Args:
            page: Playwright page object
            url: PDF URL to fetch
            save_path: Path to save the PDF

        Returns:
            Success result dict if PDF downloaded, None to try other methods
        """
        import asyncio

        # Set up download handler to capture downloads
        download_captured = None

        def handle_download(download):
            nonlocal download_captured
            download_captured = download
            logger.info(f"Download event: {download.suggested_filename}")

        page.on('download', handle_download)

        try:
            logger.info(f"Trying direct fetch for PDF: {url}")

            # First navigation - may trigger PoW challenge for PMC
            try:
                response = await page.goto(url, wait_until='load', timeout=self.timeout)

                # Check if we got a PDF directly
                if response:
                    content_type = response.headers.get('content-type', '').lower()
                    if 'application/pdf' in content_type:
                        pdf_content = await response.body()
                        if pdf_content and pdf_content[:4] == b'%PDF':
                            save_path.write_bytes(pdf_content)
                            logger.info(f"PDF downloaded directly ({len(pdf_content)} bytes)")
                            return {
                                'status': 'success',
                                'path': str(save_path),
                                'size': len(pdf_content)
                            }
            except Exception as nav_error:
                if 'Download is starting' in str(nav_error):
                    # Download triggered during navigation, wait for it
                    await asyncio.sleep(2)
                    if download_captured:
                        await download_captured.save_as(save_path)
                        size = save_path.stat().st_size if save_path.exists() else 0
                        return {
                            'status': 'success',
                            'path': str(save_path),
                            'size': size
                        }
                else:
                    logger.debug(f"Navigation error: {nav_error}")

            # Wait for potential PoW challenge to complete
            await asyncio.sleep(3)

            # Check for PoW cookie (PMC uses 'cloudpmc-viewer-pow')
            context = page.context
            cookies = await context.cookies()
            has_pow_cookie = any('pow' in c.get('name', '').lower() for c in cookies)

            if has_pow_cookie:
                logger.info("PoW cookie found, attempting second navigation")

                # Second navigation should trigger the actual download
                try:
                    await page.goto(url, wait_until='commit', timeout=self.timeout)
                except Exception as e:
                    if 'Download is starting' not in str(e):
                        logger.debug(f"Second navigation error: {e}")

                # Wait for download handler to capture the file
                await asyncio.sleep(2)

                if download_captured:
                    await download_captured.save_as(save_path)
                    size = save_path.stat().st_size if save_path.exists() else 0

                    # Verify it's a PDF
                    if save_path.exists() and size > 0:
                        with open(save_path, 'rb') as f:
                            header = f.read(4)
                        if header == b'%PDF':
                            logger.info(f"PDF downloaded via PoW challenge ({size} bytes)")
                            return {
                                'status': 'success',
                                'path': str(save_path),
                                'size': size
                            }

        except Exception as e:
            logger.debug(f"Direct fetch exception: {e}")
        finally:
            # Remove the download handler
            page.remove_listener('download', handle_download)

        return None

    async def _wait_for_cloudflare(self, page, max_wait: int):
        """Wait for Cloudflare verification to complete.

        Args:
            page: Playwright page object
            max_wait: Maximum seconds to wait
        """
        start_time = time.time()

        while time.time() - start_time < max_wait:
            # Check for common Cloudflare indicators
            title = await page.title()
            content = await page.content()

            cloudflare_indicators = [
                'Just a moment',
                'Checking your browser',
                'cloudflare',
                'cf-challenge',
                'cf_chl_'
            ]

            has_cloudflare = any(
                indicator.lower() in title.lower() or
                indicator.lower() in content.lower()
                for indicator in cloudflare_indicators
            )

            if not has_cloudflare:
                logger.info("Cloudflare verification completed (or not present)")
                return

            logger.info(f"Waiting for Cloudflare verification... ({int(time.time() - start_time)}s)")
            await asyncio.sleep(1)

        logger.warning(f"Cloudflare verification timeout after {max_wait}s")

    def _url_matches_doi(self, url: str, expected_doi: str) -> bool:
        """Check if a URL contains or references the expected DOI.

        This helps prevent downloading wrong papers from "related articles"
        or "recommended reading" sections on publisher pages.

        Args:
            url: URL to check (e.g., embedded PDF URL)
            expected_doi: DOI we're looking for (e.g., "10.1234/xyz.123")

        Returns:
            True if URL appears to reference the expected DOI, False otherwise
        """
        from urllib.parse import unquote

        # Normalize for comparison
        url_lower = unquote(url).lower()
        doi_lower = expected_doi.lower()

        # Direct DOI match (URL contains the DOI)
        # DOI format: 10.prefix/suffix - check both with and without URL encoding
        if doi_lower in url_lower:
            return True

        # Check URL-encoded version (slashes become %2F)
        doi_encoded = doi_lower.replace('/', '%2f')
        if doi_encoded in url_lower:
            return True

        # Check with underscores (some sites use underscores instead of slashes)
        doi_underscore = doi_lower.replace('/', '_')
        if doi_underscore in url_lower:
            return True

        # Extract DOI suffix (part after the prefix) for partial matching
        # e.g., from "10.1038/nature12373" extract "nature12373"
        if '/' in expected_doi:
            doi_suffix = expected_doi.split('/', 1)[1].lower()
            # Only match if suffix is reasonably unique (>6 chars)
            if len(doi_suffix) > 6 and doi_suffix in url_lower:
                return True

        return False

    async def _find_download_link(self, page) -> Optional[str]:
        """Find download link on the page (more aggressive than _find_pdf_link).

        Args:
            page: Playwright page object

        Returns:
            Download URL if found, None otherwise
        """
        try:
            # Look for explicit download links
            download_links = await page.evaluate("""
                () => {
                    const links = Array.from(document.querySelectorAll('a[href]'));
                    const downloadLinks = links
                        .filter(a => {
                            const href = a.href.toLowerCase();
                            const text = a.textContent.toLowerCase();
                            return href.includes('download') ||
                                   href.includes('.pdf') ||
                                   text.includes('download') ||
                                   text.includes('pdf');
                        })
                        .map(a => a.href);
                    return downloadLinks;
                }
            """)

            if download_links and len(download_links) > 0:
                # Prefer links with .pdf in them
                for link in download_links:
                    if '.pdf' in link.lower():
                        return link
                # Otherwise return first download link
                return download_links[0]

            return None

        except Exception as e:
            logger.warning(f"Error finding download link: {e}")
            return None

    async def _find_pdf_link(self, page) -> Optional[str]:
        """Find PDF download link on the page.

        Args:
            page: Playwright page object

        Returns:
            PDF URL if found, None otherwise
        """
        try:
            # Look for links with .pdf extension
            pdf_links = await page.evaluate("""
                () => {
                    const links = Array.from(document.querySelectorAll('a[href]'));
                    const pdfLinks = links
                        .map(a => a.href)
                        .filter(href => href.toLowerCase().includes('.pdf'));
                    return pdfLinks;
                }
            """)

            if pdf_links and len(pdf_links) > 0:
                return pdf_links[0]

            # Look for download buttons
            download_button = await page.query_selector(
                'a[download], button[download], a:has-text("Download"), button:has-text("Download")'
            )

            if download_button:
                href = await download_button.get_attribute('href')
                if href:
                    return href

            return None

        except Exception as e:
            logger.warning(f"Error finding PDF link: {e}")
            return None


def download_pdf_with_browser(
    url: str,
    save_path: Path,
    headless: bool = True,
    timeout: int = 60000,
    expected_doi: Optional[str] = None
) -> Dict[str, Any]:
    """Synchronous wrapper for browser-based PDF download.

    Args:
        url: URL to download from
        save_path: Path to save the PDF
        headless: Run browser in headless mode
        timeout: Timeout in milliseconds
        expected_doi: If provided, validate embedded PDF URLs contain this DOI
                     to prevent downloading wrong papers from related article sections

    Returns:
        Dictionary with download result
    """
    async def _download():
        async with BrowserDownloader(headless=headless, timeout=timeout) as downloader:
            return await downloader.download_pdf(url, save_path, expected_doi=expected_doi)

    return asyncio.run(_download())


# Example usage
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    test_url = "https://example.com/paper.pdf"
    test_path = Path("/tmp/test_download.pdf")

    result = download_pdf_with_browser(test_url, test_path, headless=False)
    print(f"Download result: {result}")
