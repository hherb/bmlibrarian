"""Browser-based PDF downloader for handling Cloudflare and anti-bot protections.

This module uses Playwright to download PDFs from URLs that have anti-bot protections
like Cloudflare verification, CAPTCHAs, or other browser checks.

It uses playwright-stealth to avoid detection by anti-bot systems like Cloudflare.
The stealth plugin patches various browser properties that automation detection systems
check for, including:
- navigator.webdriver
- Chrome runtime properties
- Plugin and language settings
- WebGL vendor/renderer strings
- And many more fingerprinting vectors

It also supports institutional access via OpenAthens/SAML federation:
1. Navigate to publisher page with OpenAthens cookies
2. Find and click institutional login link
3. SAML flow authenticates via institution's OpenAthens
4. Publisher sets session cookies granting access
5. PDF can then be downloaded
"""

import logging
import time
import re
from pathlib import Path
from typing import Optional, Dict, Any, List
import asyncio

logger = logging.getLogger(__name__)

# Try to import playwright-stealth for anti-detection
try:
    from playwright_stealth import Stealth
    HAS_STEALTH = True
    # Create a stealth instance with all evasions enabled
    STEALTH_INSTANCE = Stealth()
    logger.debug("playwright-stealth available for anti-detection")
except ImportError:
    HAS_STEALTH = False
    STEALTH_INSTANCE = None
    logger.warning(
        "playwright-stealth not installed. Cloudflare-protected sites may not work. "
        "Install with: uv add playwright-stealth"
    )

# Patterns for finding institutional access links on publisher pages
INSTITUTIONAL_ACCESS_PATTERNS = [
    # Generic institutional access text
    r'access.*(through|via|using).*institution',
    r'institutional.*access',
    r'institution.*login',
    r'log\s*in.*institution',
    r'sign\s*in.*institution',
    # Shibboleth/SAML patterns
    r'shibboleth',
    r'wayf',  # Where Are You From (federation discovery)
    # OpenAthens specific
    r'openathens',
    # Publisher-specific patterns
    r'access.*openathens',
    r'access.*shibboleth',
]

# URL patterns that indicate institutional login pages/flows
INSTITUTIONAL_URL_PATTERNS = [
    r'idp\.',           # Identity Provider
    r'/shibboleth',
    r'/wayf',
    r'/login.*institution',
    r'/auth.*institution',
    r'openathens\.net',
    r'/saml/',
    r'/Shibboleth\.sso',
]


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
        # Additional args for better anti-detection
        launch_args = [
            '--disable-blink-features=AutomationControlled',
            '--disable-dev-shm-usage',
            '--no-sandbox',
            '--disable-setuid-sandbox',
            '--disable-web-security',
            '--disable-features=IsolateOrigins,site-per-process',
            # Additional stealth args
            '--disable-infobars',
            '--window-size=1920,1080',
            '--start-maximized',
        ]

        self.browser = await self.playwright.chromium.launch(
            headless=self.headless,
            args=launch_args
        )
        logger.info(f"Browser started (headless={self.headless}, stealth={HAS_STEALTH})")

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
        expected_doi: Optional[str] = None,
        cookies: Optional[list] = None,
        user_agent: Optional[str] = None
    ) -> Dict[str, Any]:
        """Download a PDF using browser automation.

        Args:
            url: URL to download from
            save_path: Path to save the PDF
            wait_for_cloudflare: Wait for Cloudflare verification to complete
            max_wait: Maximum seconds to wait for verification (default: 30)
            expected_doi: If provided, validate embedded PDF URLs contain this DOI
                         to prevent downloading wrong papers from related article sections
            cookies: Optional list of cookie dicts to inject (e.g., from OpenAthens session)
                    Each dict should have 'name', 'value', 'domain' keys
            user_agent: Optional custom user agent string (e.g., from OpenAthens session)

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
            # Use custom user agent if provided (e.g., from OpenAthens session)
            effective_user_agent = user_agent or (
                'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                'AppleWebKit/537.36 (KHTML, like Gecko) '
                'Chrome/131.0.0.0 Safari/537.36'
            )

            # Create browser context with realistic settings
            context = await self.browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent=effective_user_agent,
                locale='en-US',
                timezone_id='America/New_York',
                permissions=['notifications'],
                color_scheme='light',
                accept_downloads=True
            )

            # Inject cookies if provided (e.g., from OpenAthens authentication)
            if cookies:
                logger.info(f"Injecting {len(cookies)} authentication cookies")
                # Group cookies by domain for proper injection
                for cookie in cookies:
                    # Ensure cookie has required fields and valid domain
                    if 'name' in cookie and 'value' in cookie:
                        await context.add_cookies([cookie])
                logger.debug(f"Injected cookies for domains: {set(c.get('domain', 'unknown') for c in cookies)}")

            # Add fallback stealth scripts if playwright-stealth not available
            if not HAS_STEALTH:
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

            # Apply playwright-stealth if available (comprehensive anti-detection)
            if HAS_STEALTH and STEALTH_INSTANCE:
                await STEALTH_INSTANCE.apply_stealth_async(page)
                logger.debug("Applied playwright-stealth to page")

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
            cloudflare_passed = True
            if wait_for_cloudflare:
                logger.info("Checking for Cloudflare verification...")

                # Use longer timeout for visible browsers (user needs time to click)
                effective_wait = max_wait if self.headless else max(max_wait, 120)

                if not self.headless:
                    logger.info(
                        "If you see a Cloudflare 'I am human' checkbox, please click it. "
                        f"Waiting up to {effective_wait} seconds..."
                    )

                cloudflare_passed = await self._wait_for_cloudflare(page, effective_wait)

                # If Cloudflare challenge failed and we're headless, return special error
                # so caller can retry with non-headless browser
                if not cloudflare_passed and self.headless:
                    return {
                        'status': 'failed',
                        'error': 'Cloudflare challenge requires user interaction',
                        'cloudflare_blocked': True,
                        'doi_rejected_count': 0
                    }

            # Track if we should try institutional access later
            tried_institutional_access = False

            # STEP 0: Early paywall detection with proactive institutional access
            # If we have OpenAthens cookies, check if page shows paywall indicators
            # and try to gain institutional access BEFORE collecting PDF candidates
            if cookies:
                is_paywalled = await self._detect_paywall(page)
                if is_paywalled:
                    logger.info("Paywall detected - attempting institutional access...")
                    tried_institutional_access = True
                    institutional_success = await self._try_institutional_access(
                        page, openathens_cookies=cookies, max_wait=45
                    )
                    if institutional_success:
                        # Re-navigate to original URL with authenticated session
                        logger.info("Institutional access established - reloading page...")
                        await page.goto(url, wait_until='domcontentloaded', timeout=self.timeout)
                        await asyncio.sleep(2)  # Let page render with authenticated content

            # STEP 1: Collect ALL PDF candidates from the page
            pdf_candidates = await self._collect_all_pdf_candidates(page, url)
            logger.info(f"Found {len(pdf_candidates)} PDF candidate(s) on page")

            if not pdf_candidates:
                # Check if page content is already a PDF
                content = await page.content()
                if content.startswith('%PDF'):
                    logger.info("PDF content detected in page")
                    save_path.write_text(content)
                    return {
                        'status': 'success',
                        'path': str(save_path),
                        'size': len(content)
                    }

                # No PDF candidates - this might be a paywall
                # If we have OpenAthens cookies, try institutional access
                if cookies and not tried_institutional_access:
                    logger.info("No PDF candidates found - trying institutional access...")
                    tried_institutional_access = True
                    institutional_success = await self._try_institutional_access(
                        page, openathens_cookies=cookies, max_wait=45
                    )
                    if institutional_success:
                        # Re-navigate to original URL and try again
                        await page.goto(url, wait_until='domcontentloaded', timeout=self.timeout)
                        await asyncio.sleep(2)  # Let page render
                        pdf_candidates = await self._collect_all_pdf_candidates(page, url)
                        logger.info(f"After institutional access: found {len(pdf_candidates)} PDF candidate(s)")

                if not pdf_candidates:
                    return {
                        'status': 'failed',
                        'error': 'No PDF candidates found on page',
                        'doi_rejected_count': 0
                    }

            # STEP 2: Score and rank candidates based on DOI match and URL patterns
            ranked_candidates = self._rank_pdf_candidates(
                pdf_candidates, expected_doi, url
            )

            logger.info(f"Ranked {len(ranked_candidates)} PDF candidate(s):")
            for i, (candidate_url, score, source) in enumerate(ranked_candidates[:5]):
                logger.info(f"  {i+1}. Score {score}: [{source}] {candidate_url[:80]}...")

            # STEP 3: Try candidates in order until one works
            doi_matched_count = sum(1 for _, score, _ in ranked_candidates if score >= 100)
            doi_rejected_count = len(ranked_candidates) - doi_matched_count

            for candidate_url, score, source in ranked_candidates:
                # If we have a DOI and this candidate doesn't match, skip it
                # UNLESS there are no DOI-matching candidates at all
                if expected_doi and score < 100 and doi_matched_count > 0:
                    logger.debug(f"Skipping non-DOI-matching candidate: {candidate_url}")
                    continue

                logger.info(f"Trying PDF candidate (score={score}, source={source}): {candidate_url}")

                result = await self._try_download_pdf_candidate(
                    page, candidate_url, save_path, source
                )

                if result and result.get('status') == 'success':
                    return result

            # All candidates failed - maybe we need institutional access?
            # Try institutional login if we have OpenAthens cookies and haven't tried yet
            if cookies and not tried_institutional_access:
                logger.info("All PDF downloads failed - trying institutional access...")
                tried_institutional_access = True
                institutional_success = await self._try_institutional_access(
                    page, openathens_cookies=cookies, max_wait=45
                )
                if institutional_success:
                    # Re-try PDF candidates after gaining access
                    logger.info("Re-trying PDF candidates after institutional access...")
                    await page.goto(url, wait_until='domcontentloaded', timeout=self.timeout)
                    await asyncio.sleep(2)

                    pdf_candidates = await self._collect_all_pdf_candidates(page, url)
                    if pdf_candidates:
                        ranked_candidates = self._rank_pdf_candidates(
                            pdf_candidates, expected_doi, url
                        )

                        for candidate_url, score, source in ranked_candidates:
                            if expected_doi and score < 100 and doi_matched_count > 0:
                                continue

                            result = await self._try_download_pdf_candidate(
                                page, candidate_url, save_path, source
                            )
                            if result and result.get('status') == 'success':
                                logger.info("Successfully downloaded PDF after institutional access!")
                                return result

            # All methods failed
            if doi_rejected_count > 0 and expected_doi and doi_matched_count == 0:
                error_msg = (
                    f"Found {len(ranked_candidates)} PDF(s) on page but none matched "
                    f"expected DOI {expected_doi}. "
                    f"This paper may be paywalled or require institutional access."
                )
            elif len(ranked_candidates) > 0:
                error_msg = (
                    f"Found {len(ranked_candidates)} PDF candidate(s) but all download "
                    f"attempts failed"
                )
            else:
                error_msg = 'Could not find PDF content on page'

            return {
                'status': 'failed',
                'error': error_msg,
                'doi_rejected_count': doi_rejected_count
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

    async def _wait_for_cloudflare(self, page, max_wait: int) -> bool:
        """Wait for Cloudflare verification to complete.

        Args:
            page: Playwright page object
            max_wait: Maximum seconds to wait

        Returns:
            True if Cloudflare challenge was passed (or not present),
            False if still stuck on Cloudflare after max_wait
        """
        start_time = time.time()
        checkbox_click_attempted = False

        while time.time() - start_time < max_wait:
            # Check for common Cloudflare indicators
            try:
                title = await page.title()
                content = await page.content()
            except Exception as e:
                # Page might have navigated during check
                logger.debug(f"Error checking page during Cloudflare wait: {e}")
                await asyncio.sleep(1)
                continue

            # Specific Cloudflare challenge indicators (in page title or challenge elements)
            cloudflare_challenge_indicators = [
                'Just a moment',
                'Checking your browser',
                'cf-challenge',
                'cf_chl_',
                'challenge-platform',
                'turnstile',  # Cloudflare's captcha
            ]

            # Check specifically for challenge page (not just any page mentioning cloudflare)
            title_lower = title.lower()
            has_cloudflare = any(
                indicator.lower() in title_lower
                for indicator in cloudflare_challenge_indicators[:2]  # Title check
            ) or any(
                indicator.lower() in content.lower()
                for indicator in cloudflare_challenge_indicators[2:]  # Content check
            )

            if not has_cloudflare:
                logger.info("Cloudflare verification completed (or not present)")
                return True

            # Try to click the Turnstile checkbox if we haven't already
            # This works in visible mode when user is watching
            if not checkbox_click_attempted and not self.headless:
                checkbox_click_attempted = True
                await self._try_click_turnstile_checkbox(page)

            elapsed = int(time.time() - start_time)
            logger.info(f"Waiting for Cloudflare verification... ({elapsed}s)")
            await asyncio.sleep(1)

        logger.warning(f"Cloudflare verification timeout after {max_wait}s")
        return False

    async def _try_click_turnstile_checkbox(self, page) -> bool:
        """Try to click the Cloudflare Turnstile checkbox.

        The Turnstile widget is embedded in an iframe. We try to locate and click
        the checkbox to help pass the verification.

        Args:
            page: Playwright page object

        Returns:
            True if checkbox was clicked, False otherwise
        """
        try:
            # Turnstile is in an iframe with specific characteristics
            # Look for the Turnstile iframe
            frames = page.frames
            for frame in frames:
                frame_url = frame.url.lower()
                if 'challenges.cloudflare.com' in frame_url or 'turnstile' in frame_url:
                    logger.info("Found Cloudflare Turnstile iframe, attempting to interact...")

                    # Try to click the checkbox within the iframe
                    try:
                        # The checkbox is typically an input element or a div that acts as checkbox
                        checkbox_selectors = [
                            'input[type="checkbox"]',
                            '#cf-turnstile-response',
                            '[role="checkbox"]',
                            '.cf-turnstile',
                            'label',  # Sometimes the label is clickable
                        ]

                        for selector in checkbox_selectors:
                            try:
                                checkbox = await frame.query_selector(selector)
                                if checkbox:
                                    await checkbox.click()
                                    logger.info(f"Clicked Turnstile element: {selector}")
                                    await asyncio.sleep(2)  # Wait for challenge to process
                                    return True
                            except Exception as click_error:
                                logger.debug(f"Could not click {selector}: {click_error}")
                                continue
                    except Exception as iframe_error:
                        logger.debug(f"Error interacting with Turnstile iframe: {iframe_error}")

            # Also try clicking on the page directly (some implementations)
            try:
                # Try to find and click any verify button on the main page
                verify_selectors = [
                    'button:has-text("Verify")',
                    'input[type="checkbox"]',
                    '[data-testid="challenge"]',
                ]
                for selector in verify_selectors:
                    try:
                        element = await page.query_selector(selector)
                        if element:
                            await element.click()
                            logger.info(f"Clicked verify element on main page: {selector}")
                            await asyncio.sleep(2)
                            return True
                    except Exception:
                        continue
            except Exception:
                pass

            logger.debug("Could not find Turnstile checkbox to click")
            return False

        except Exception as e:
            logger.debug(f"Error trying to click Turnstile checkbox: {e}")
            return False

    async def _try_institutional_access(
        self,
        page,
        openathens_cookies: Optional[List[Dict[str, Any]]] = None,
        max_wait: int = 30
    ) -> bool:
        """Try to gain institutional access via SAML/Shibboleth flow.

        When OpenAthens cookies are present but direct access fails (paywall),
        this method looks for institutional access links and navigates through
        the SAML authentication flow.

        The flow:
        1. Find institutional access link on the page
        2. Click it to trigger SAML flow
        3. If redirected to OpenAthens, we're already authenticated (cookies)
        4. After SAML completes, publisher sets session cookies
        5. Return True if access was gained

        Args:
            page: Playwright page object
            openathens_cookies: List of OpenAthens cookies to inject if needed
            max_wait: Maximum seconds to wait for SAML flow to complete

        Returns:
            True if institutional access was successfully established
        """
        start_time = time.time()
        original_url = page.url

        try:
            logger.info("Looking for institutional access link on page...")

            # First, try to find institutional access links
            institutional_link = await self._find_institutional_access_link(page)

            if not institutional_link:
                logger.debug("No institutional access link found on page")
                return False

            logger.info(f"Found institutional access link: {institutional_link[:80]}...")

            # Inject OpenAthens cookies before clicking the link
            # This ensures SAML flow sees our authenticated session
            if openathens_cookies:
                context = page.context
                for cookie in openathens_cookies:
                    if 'name' in cookie and 'value' in cookie:
                        await context.add_cookies([cookie])
                logger.info(f"Injected {len(openathens_cookies)} OpenAthens cookies before SAML flow")

            # Navigate to the institutional access link
            try:
                await page.goto(institutional_link, wait_until='domcontentloaded', timeout=30000)
            except Exception as nav_error:
                logger.debug(f"Navigation to institutional link: {nav_error}")
                # Navigation might trigger redirect, that's okay

            # Wait for SAML flow to complete
            # Monitor URL changes - when we return to a non-IDP URL, flow is complete
            saml_completed = False
            while time.time() - start_time < max_wait:
                await asyncio.sleep(1)
                current_url = page.url.lower()

                # Check if we're still in SAML flow
                in_saml_flow = any(
                    re.search(pattern, current_url, re.IGNORECASE)
                    for pattern in INSTITUTIONAL_URL_PATTERNS
                )

                if not in_saml_flow:
                    # Check if we got redirected back with success indicators
                    # Look for session cookies that indicate successful auth
                    context = page.context
                    cookies = await context.cookies()
                    session_cookies = [c for c in cookies if any(
                        x in c.get('name', '').lower()
                        for x in ['session', 'auth', 'sso', 'jwt']
                    )]

                    if session_cookies:
                        logger.info(f"SAML flow complete - received {len(session_cookies)} session cookies")
                        saml_completed = True
                        break

                    # Also check if we can now access the page (no paywall indicators)
                    content = await page.content()
                    content_lower = content.lower()

                    # Paywall indicators
                    paywall_indicators = [
                        'access denied',
                        'subscription required',
                        'purchase this article',
                        'sign in to access',
                        'log in to access',
                        'institutional access',  # Still showing access options = not authenticated
                    ]

                    has_paywall = any(indicator in content_lower for indicator in paywall_indicators)

                    if not has_paywall:
                        logger.info("SAML flow appears complete - no paywall indicators")
                        saml_completed = True
                        break

                logger.debug(f"Waiting for SAML flow... ({int(time.time() - start_time)}s)")

            if saml_completed:
                # Navigate back to original URL with new session
                try:
                    await page.goto(original_url, wait_until='domcontentloaded', timeout=30000)
                    logger.info("Returned to original URL with institutional access")
                except Exception:
                    pass  # May not need to navigate back if already there

                return True

            logger.warning(f"SAML flow timed out after {max_wait}s")
            return False

        except Exception as e:
            logger.error(f"Institutional access flow failed: {e}")
            return False

    async def _detect_paywall(self, page) -> bool:
        """Detect if the current page shows a paywall.

        Checks for common paywall indicators like subscription prompts,
        access denied messages, or institutional login options.

        Args:
            page: Playwright page object

        Returns:
            True if page appears to be paywalled
        """
        try:
            content = await page.content()
            content_lower = content.lower()

            # Paywall indicators
            paywall_indicators = [
                'access denied',
                'subscription required',
                'purchase this article',
                'buy this article',
                'rent this article',
                'sign in to access',
                'log in to access',
                'get access',
                'full text access',
                'view pdf requires',
                'institutional access',
                'access through your institution',
                'check if you have access',
                'you do not have access',
                'access to this content',
            ]

            # Check for paywall indicators
            for indicator in paywall_indicators:
                if indicator in content_lower:
                    logger.debug(f"Paywall indicator found: {indicator}")
                    return True

            return False

        except Exception as e:
            logger.debug(f"Error detecting paywall: {e}")
            return False

    async def _find_institutional_access_link(self, page) -> Optional[str]:
        """Find institutional access link on the current page.

        Searches for links that match institutional access patterns,
        prioritizing more specific patterns over generic ones.

        Args:
            page: Playwright page object

        Returns:
            URL of institutional access link, or None if not found
        """
        try:
            # Find all links and their text/attributes
            links_data = await page.evaluate("""
                () => {
                    const results = [];
                    const links = Array.from(document.querySelectorAll('a[href]'));

                    for (const link of links) {
                        const href = link.href;
                        const text = (link.textContent || '').toLowerCase().trim();
                        const title = (link.getAttribute('title') || '').toLowerCase();
                        const ariaLabel = (link.getAttribute('aria-label') || '').toLowerCase();
                        const className = (link.className || '').toLowerCase();
                        const id = (link.id || '').toLowerCase();

                        // Skip empty or javascript links
                        if (!href || href.startsWith('javascript:') || href === '#') {
                            continue;
                        }

                        results.push({
                            href: href,
                            text: text.substring(0, 200),
                            title: title.substring(0, 200),
                            ariaLabel: ariaLabel.substring(0, 200),
                            className: className.substring(0, 200),
                            id: id
                        });
                    }

                    return results;
                }
            """)

            # Score each link based on pattern matches
            scored_links: List[tuple[str, int]] = []

            for link in links_data:
                score = 0
                href = link['href']
                text = link['text']
                title = link['title']
                aria_label = link['ariaLabel']
                class_name = link['className']
                link_id = link['id']

                # Check URL patterns (highest priority)
                for pattern in INSTITUTIONAL_URL_PATTERNS:
                    if re.search(pattern, href, re.IGNORECASE):
                        score += 50
                        break

                # Check text/attribute patterns
                searchable = f"{text} {title} {aria_label} {class_name} {link_id}"
                for pattern in INSTITUTIONAL_ACCESS_PATTERNS:
                    if re.search(pattern, searchable, re.IGNORECASE):
                        score += 30
                        break

                # Bonus for explicit institutional terms
                if 'institutional' in searchable:
                    score += 20
                if 'openathens' in searchable:
                    score += 25
                if 'shibboleth' in searchable:
                    score += 25

                # Penalty for generic links that might be false positives
                if 'login' in text and 'institution' not in searchable:
                    score -= 10  # Generic login, not institutional

                if score > 0:
                    scored_links.append((href, score))

            if not scored_links:
                return None

            # Sort by score and return highest
            scored_links.sort(key=lambda x: x[1], reverse=True)
            best_link, best_score = scored_links[0]

            logger.debug(f"Best institutional link (score={best_score}): {best_link}")
            return best_link

        except Exception as e:
            logger.debug(f"Error finding institutional link: {e}")
            return None

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

    async def _collect_all_pdf_candidates(
        self,
        page,
        base_url: str
    ) -> list[tuple[str, str]]:
        """Collect ALL PDF candidates from the page.

        Gathers PDF URLs from multiple sources:
        - Embedded PDF viewers (embed, object, iframe)
        - Download links and buttons
        - Direct PDF links
        - Meta tags and canonical links

        Args:
            page: Playwright page object
            base_url: Base URL for resolving relative URLs

        Returns:
            List of (url, source_type) tuples where source_type describes
            where the URL was found (e.g., 'embedded', 'download_link', 'pdf_link')
        """
        from urllib.parse import urljoin, urlparse, urlunparse

        candidates: list[tuple[str, str]] = []
        seen_urls: set[str] = set()

        def normalize_url(url: str) -> str:
            """Normalize URL by removing anchor fragments.

            URLs like example.com/article#main and example.com/article#ref-CR1
            are effectively the same page, so we deduplicate by stripping fragments.
            """
            parsed = urlparse(url)
            # Remove fragment (anchor) from URL
            return urlunparse(parsed._replace(fragment=''))

        def add_candidate(url: str, source: str) -> None:
            """Add a candidate URL if not already seen (ignoring anchor fragments)."""
            if url and url != 'about:blank':
                # Make URL absolute
                abs_url = urljoin(base_url, url)
                # Normalize by stripping anchor fragment for deduplication
                normalized = normalize_url(abs_url)
                if normalized not in seen_urls:
                    seen_urls.add(normalized)
                    # Store the normalized URL (without fragment)
                    candidates.append((normalized, source))

        # 1. Check embedded PDF viewers
        selectors = [
            ('embed[type="application/pdf"]', 'embedded_pdf'),
            ('object[type="application/pdf"]', 'embedded_object'),
            ('iframe[src*=".pdf"]', 'embedded_iframe'),
            ('embed[src*=".pdf"]', 'embedded_src'),
            ('object[data*=".pdf"]', 'embedded_data'),
        ]

        for selector, source in selectors:
            try:
                elements = await page.query_selector_all(selector)
                for element in elements:
                    src = await element.get_attribute('src')
                    data = await element.get_attribute('data')
                    if src:
                        add_candidate(src, source)
                    if data:
                        add_candidate(data, source)
            except Exception as e:
                logger.debug(f"Error checking selector {selector}: {e}")

        # 2. Collect all PDF-related links from the page
        try:
            all_links = await page.evaluate("""
                () => {
                    const results = [];
                    const links = Array.from(document.querySelectorAll('a[href]'));

                    for (const link of links) {
                        const href = link.href;
                        const text = (link.textContent || '').toLowerCase().trim();
                        const title = (link.getAttribute('title') || '').toLowerCase();
                        const className = (link.className || '').toLowerCase();
                        const id = (link.id || '').toLowerCase();

                        // Categorize the link
                        let category = null;

                        // Direct PDF links (highest priority)
                        if (href.toLowerCase().includes('.pdf')) {
                            category = 'pdf_link';
                        }
                        // Download links
                        else if (
                            text.includes('download') ||
                            title.includes('download') ||
                            className.includes('download') ||
                            id.includes('download') ||
                            href.toLowerCase().includes('download')
                        ) {
                            category = 'download_link';
                        }
                        // Full text / PDF text links
                        else if (
                            text.includes('full text') ||
                            text.includes('fulltext') ||
                            text.includes('pdf') ||
                            text === 'pdf' ||
                            title.includes('pdf') ||
                            title.includes('full text')
                        ) {
                            category = 'fulltext_link';
                        }
                        // View article links
                        else if (
                            text.includes('view') && (text.includes('article') || text.includes('paper')) ||
                            className.includes('article') ||
                            href.includes('/article/') ||
                            href.includes('/pdf/')
                        ) {
                            category = 'article_link';
                        }

                        if (category) {
                            results.push({
                                href: href,
                                category: category,
                                text: text.substring(0, 100),
                                title: title.substring(0, 100)
                            });
                        }
                    }

                    return results;
                }
            """)

            for link_info in all_links:
                add_candidate(link_info['href'], link_info['category'])

        except Exception as e:
            logger.debug(f"Error collecting links: {e}")

        # 3. Check meta tags for PDF URLs
        try:
            meta_pdf = await page.evaluate("""
                () => {
                    const results = [];

                    // Check citation_pdf_url meta tag
                    const citationPdf = document.querySelector('meta[name="citation_pdf_url"]');
                    if (citationPdf) {
                        results.push({href: citationPdf.content, category: 'meta_citation_pdf'});
                    }

                    // Check DC.identifier with PDF
                    const dcId = document.querySelectorAll('meta[name="DC.identifier"]');
                    dcId.forEach(meta => {
                        if (meta.content && meta.content.toLowerCase().includes('.pdf')) {
                            results.push({href: meta.content, category: 'meta_dc_identifier'});
                        }
                    });

                    // Check og:url if it's a PDF
                    const ogUrl = document.querySelector('meta[property="og:url"]');
                    if (ogUrl && ogUrl.content && ogUrl.content.toLowerCase().includes('.pdf')) {
                        results.push({href: ogUrl.content, category: 'meta_og_url'});
                    }

                    return results;
                }
            """)

            for meta_info in meta_pdf:
                add_candidate(meta_info['href'], meta_info['category'])

        except Exception as e:
            logger.debug(f"Error checking meta tags: {e}")

        return candidates

    def _rank_pdf_candidates(
        self,
        candidates: list[tuple[str, str]],
        expected_doi: Optional[str],
        page_url: str
    ) -> list[tuple[str, int, str]]:
        """Score and rank PDF candidates.

        Higher scores indicate better matches. Scoring criteria:
        - DOI match in URL: +100 points (highest priority)
        - Same domain as page URL: +20 points
        - Source type bonuses: meta_citation_pdf (+30), embedded (+25), etc.
        - URL contains 'pdf': +10 points
        - URL contains 'download': +5 points

        Args:
            candidates: List of (url, source_type) tuples
            expected_doi: DOI to match against (if known)
            page_url: Original page URL for domain comparison

        Returns:
            List of (url, score, source_type) tuples, sorted by score descending
        """
        from urllib.parse import urlparse

        page_domain = urlparse(page_url).netloc.lower()

        scored: list[tuple[str, int, str]] = []

        # Source type priority scores
        source_scores = {
            'meta_citation_pdf': 30,  # Most reliable - publisher's own PDF link
            'embedded_pdf': 25,
            'embedded_object': 25,
            'embedded_iframe': 20,
            'embedded_src': 20,
            'embedded_data': 20,
            'pdf_link': 15,
            'download_link': 10,
            'fulltext_link': 8,
            'article_link': 5,
            'meta_dc_identifier': 5,
            'meta_og_url': 3,
        }

        for url, source in candidates:
            score = 0
            url_lower = url.lower()

            # DOI match is the strongest signal
            if expected_doi and self._url_matches_doi(url, expected_doi):
                score += 100

            # Same domain bonus
            candidate_domain = urlparse(url).netloc.lower()
            if candidate_domain == page_domain:
                score += 20

            # Source type bonus
            score += source_scores.get(source, 0)

            # URL pattern bonuses
            if '.pdf' in url_lower:
                score += 10
            if 'download' in url_lower:
                score += 5
            if 'fulltext' in url_lower or 'full-text' in url_lower:
                score += 5

            # Penalties for likely wrong documents
            if 'supplement' in url_lower or 'supporting' in url_lower:
                score -= 15  # Supplementary materials
            if 'related' in url_lower or 'recommend' in url_lower:
                score -= 30  # Related articles
            if 'advertisement' in url_lower or 'banner' in url_lower:
                score -= 50  # Ads

            scored.append((url, score, source))

        # Sort by score descending
        scored.sort(key=lambda x: x[1], reverse=True)

        return scored

    async def _try_download_pdf_candidate(
        self,
        page,
        candidate_url: str,
        save_path: Path,
        source: str
    ) -> Optional[Dict[str, Any]]:
        """Try to download a PDF from a candidate URL.

        Args:
            page: Playwright page object
            candidate_url: URL to download from
            save_path: Path to save the PDF
            source: Source type for logging

        Returns:
            Success result dict if downloaded, None if failed
        """
        try:
            # Try direct navigation first
            response = await page.goto(candidate_url, timeout=self.timeout, wait_until='load')

            if response:
                content_type = response.headers.get('content-type', '').lower()

                # Direct PDF response
                if 'application/pdf' in content_type:
                    pdf_content = await response.body()
                    if pdf_content and pdf_content[:4] == b'%PDF':
                        save_path.write_bytes(pdf_content)
                        logger.info(f"Downloaded PDF from {source}: {len(pdf_content)} bytes")
                        return {
                            'status': 'success',
                            'path': str(save_path),
                            'size': len(pdf_content)
                        }

            # Wait for download to trigger
            await asyncio.sleep(1)

            # Try fetching as binary
            try:
                response_binary = await page.evaluate('''async () => {
                    try {
                        const response = await fetch(window.location.href);
                        const buffer = await response.arrayBuffer();
                        const bytes = new Uint8Array(buffer);
                        return Array.from(bytes.slice(0, 50000));  // Limit to first 50KB for check
                    } catch (e) {
                        return null;
                    }
                }''')

                if response_binary:
                    # Check if it's a PDF
                    header = bytes(response_binary[:4]) if len(response_binary) >= 4 else b''
                    if header == b'%PDF':
                        # Fetch full content
                        full_binary = await page.evaluate('''async () => {
                            const response = await fetch(window.location.href);
                            const buffer = await response.arrayBuffer();
                            const bytes = new Uint8Array(buffer);
                            return Array.from(bytes);
                        }''')

                        if full_binary:
                            pdf_bytes = bytes(full_binary)
                            save_path.write_bytes(pdf_bytes)
                            logger.info(f"Downloaded PDF via fetch from {source}: {len(pdf_bytes)} bytes")
                            return {
                                'status': 'success',
                                'path': str(save_path),
                                'size': len(pdf_bytes)
                            }
            except Exception as fetch_error:
                logger.debug(f"Fetch attempt failed: {fetch_error}")

            return None

        except Exception as e:
            logger.debug(f"Failed to download from {candidate_url}: {e}")
            return None

    async def _find_download_link(
        self,
        page,
        expected_doi: Optional[str] = None
    ) -> tuple[Optional[str], int]:
        """Find download link on the page (more aggressive than _find_pdf_link).

        Args:
            page: Playwright page object
            expected_doi: If provided, only return links that match this DOI

        Returns:
            Tuple of (Download URL if found, count of DOI-rejected links)
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
                # If we have an expected DOI, filter links to only those matching it
                if expected_doi:
                    matching_links = [
                        link for link in download_links
                        if self._url_matches_doi(link, expected_doi)
                    ]
                    rejected_count = len(download_links) - len(matching_links)
                    if matching_links:
                        # Prefer links with .pdf in them
                        for link in matching_links:
                            if '.pdf' in link.lower():
                                return link, rejected_count
                        return matching_links[0], rejected_count
                    else:
                        logger.warning(
                            f"Found {len(download_links)} download links but none match "
                            f"expected DOI {expected_doi}"
                        )
                        return None, rejected_count

                # No DOI validation - prefer links with .pdf in them
                for link in download_links:
                    if '.pdf' in link.lower():
                        return link, 0
                # Otherwise return first download link
                return download_links[0], 0

            return None, 0

        except Exception as e:
            logger.warning(f"Error finding download link: {e}")
            return None, 0

    async def _find_pdf_link(
        self,
        page,
        expected_doi: Optional[str] = None
    ) -> tuple[Optional[str], int]:
        """Find PDF download link on the page.

        Args:
            page: Playwright page object
            expected_doi: If provided, only return links that match this DOI

        Returns:
            Tuple of (PDF URL if found, count of DOI-rejected links)
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
                # If we have an expected DOI, filter links to only those matching it
                if expected_doi:
                    matching_links = [
                        link for link in pdf_links
                        if self._url_matches_doi(link, expected_doi)
                    ]
                    rejected_count = len(pdf_links) - len(matching_links)
                    if matching_links:
                        return matching_links[0], rejected_count
                    else:
                        logger.warning(
                            f"Found {len(pdf_links)} PDF links but none match "
                            f"expected DOI {expected_doi}"
                        )
                        return None, rejected_count
                return pdf_links[0], 0

            # Look for download buttons
            download_button = await page.query_selector(
                'a[download], button[download], a:has-text("Download"), button:has-text("Download")'
            )

            if download_button:
                href = await download_button.get_attribute('href')
                if href:
                    # Validate against expected DOI if provided
                    if expected_doi and not self._url_matches_doi(href, expected_doi):
                        logger.warning(
                            f"Download button href {href} does not match "
                            f"expected DOI {expected_doi}"
                        )
                        return None, 1
                    return href, 0

            return None, 0

        except Exception as e:
            logger.warning(f"Error finding PDF link: {e}")
            return None, 0


async def _download_with_persistent_context(
    url: str,
    save_path: Path,
    headless: bool,
    timeout: int,
    expected_doi: Optional[str],
    cookies: Optional[list],
    user_agent: Optional[str],
    user_data_dir: Optional[str]
) -> Dict[str, Any]:
    """Download PDF using a persistent browser context.

    Persistent contexts preserve cookies, localStorage, and other state
    between sessions. This is useful for:
    - Cloudflare clearance cookies (cf_clearance)
    - Sites that remember "trusted" browsers
    - Avoiding repeated CAPTCHA verification

    Args:
        url: URL to download from
        save_path: Path to save the PDF
        headless: Run browser in headless mode
        timeout: Timeout in milliseconds
        expected_doi: DOI to validate against
        cookies: Additional cookies to inject
        user_agent: Custom user agent
        user_data_dir: Directory for browser data

    Returns:
        Dictionary with download result
    """
    from playwright.async_api import async_playwright
    import os

    # Default user data directory
    if not user_data_dir:
        user_data_dir = os.path.expanduser("~/.bmlibrarian/browser_data")

    # Ensure directory exists
    os.makedirs(user_data_dir, exist_ok=True)

    logger.info(f"Using persistent browser context at: {user_data_dir}")

    playwright = None
    context = None

    try:
        playwright = await async_playwright().start()

        # Launch args for stealth
        launch_args = [
            '--disable-blink-features=AutomationControlled',
            '--disable-dev-shm-usage',
            '--no-sandbox',
            '--disable-setuid-sandbox',
            '--disable-infobars',
            '--window-size=1920,1080',
        ]

        # Use persistent context (launch_persistent_context)
        context = await playwright.chromium.launch_persistent_context(
            user_data_dir,
            headless=headless,
            args=launch_args,
            viewport={'width': 1920, 'height': 1080},
            user_agent=user_agent or (
                'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                'AppleWebKit/537.36 (KHTML, like Gecko) '
                'Chrome/131.0.0.0 Safari/537.36'
            ),
            locale='en-US',
            timezone_id='America/New_York',
            accept_downloads=True
        )

        # Inject additional cookies if provided
        if cookies:
            logger.info(f"Injecting {len(cookies)} additional cookies")
            for cookie in cookies:
                if 'name' in cookie and 'value' in cookie:
                    await context.add_cookies([cookie])

        # Get the page (persistent context has one page by default)
        pages = context.pages
        if pages:
            page = pages[0]
        else:
            page = await context.new_page()

        # Apply stealth if available
        if HAS_STEALTH and STEALTH_INSTANCE:
            await STEALTH_INSTANCE.apply_stealth_async(page)
            logger.debug("Applied playwright-stealth to persistent context page")

        # Navigate to URL
        logger.info(f"Navigating to: {url}")
        save_path.parent.mkdir(parents=True, exist_ok=True)

        response = await page.goto(url, wait_until='domcontentloaded', timeout=timeout)

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

            if pdf_content and pdf_content[:4] == b'%PDF':
                save_path.write_bytes(pdf_content)
                return {
                    'status': 'success',
                    'path': str(save_path),
                    'size': len(pdf_content)
                }

        # Wait for page to load
        try:
            await page.wait_for_load_state('networkidle', timeout=10000)
        except Exception:
            pass

        # Check for Cloudflare
        title = await page.title()
        content = await page.content()

        cloudflare_indicators = ['Just a moment', 'Checking your browser', 'cf-challenge', 'turnstile']
        has_cloudflare = any(ind.lower() in title.lower() or ind.lower() in content.lower()
                           for ind in cloudflare_indicators)

        if has_cloudflare:
            # Wait for user to complete verification (persistent context remembers it)
            logger.info("Cloudflare detected - waiting for verification (up to 120s)...")
            if not headless:
                logger.info("Please complete the Cloudflare verification in the browser window.")

            start_time = time.time()
            max_wait = 120

            while time.time() - start_time < max_wait:
                try:
                    title = await page.title()
                    content = await page.content()
                except Exception:
                    await asyncio.sleep(1)
                    continue

                has_cloudflare = any(ind.lower() in title.lower() or ind.lower() in content.lower()
                                   for ind in cloudflare_indicators)
                if not has_cloudflare:
                    logger.info("Cloudflare verification completed!")
                    break

                await asyncio.sleep(1)

            if has_cloudflare:
                return {
                    'status': 'failed',
                    'error': 'Cloudflare verification timeout',
                    'cloudflare_blocked': True
                }

        # Try to find and download PDF (simplified version)
        # Look for PDF links or embedded viewers
        pdf_links = await page.evaluate("""
            () => {
                const links = Array.from(document.querySelectorAll('a[href]'));
                return links
                    .map(a => a.href)
                    .filter(href => href.toLowerCase().includes('.pdf') ||
                                   href.toLowerCase().includes('download'));
            }
        """)

        if pdf_links:
            # Try the first PDF link
            for pdf_url in pdf_links[:3]:
                if expected_doi and expected_doi.lower() not in pdf_url.lower():
                    continue

                try:
                    pdf_response = await page.goto(pdf_url, timeout=timeout)
                    if pdf_response:
                        ct = pdf_response.headers.get('content-type', '').lower()
                        if 'application/pdf' in ct:
                            pdf_content = await pdf_response.body()
                            if pdf_content and pdf_content[:4] == b'%PDF':
                                save_path.write_bytes(pdf_content)
                                return {
                                    'status': 'success',
                                    'path': str(save_path),
                                    'size': len(pdf_content)
                                }
                except Exception as e:
                    logger.debug(f"Error downloading from {pdf_url}: {e}")

        return {
            'status': 'failed',
            'error': 'Could not find or download PDF'
        }

    except Exception as e:
        logger.error(f"Persistent context download failed: {e}")
        return {
            'status': 'failed',
            'error': str(e)
        }

    finally:
        if context:
            await context.close()
        if playwright:
            await playwright.stop()


def download_pdf_with_browser(
    url: str,
    save_path: Path,
    headless: bool = True,
    timeout: int = 60000,
    expected_doi: Optional[str] = None,
    cookies: Optional[list] = None,
    user_agent: Optional[str] = None,
    retry_cloudflare_visible: bool = True,
    use_persistent_context: bool = False,
    user_data_dir: Optional[str] = None
) -> Dict[str, Any]:
    """Synchronous wrapper for browser-based PDF download.

    Args:
        url: URL to download from
        save_path: Path to save the PDF
        headless: Run browser in headless mode
        timeout: Timeout in milliseconds
        expected_doi: If provided, validate embedded PDF URLs contain this DOI
                     to prevent downloading wrong papers from related article sections
        cookies: Optional list of cookie dicts to inject (e.g., from OpenAthens session)
        user_agent: Optional custom user agent string
        retry_cloudflare_visible: If True and Cloudflare blocks headless browser,
                                 automatically retry with visible browser for user to
                                 complete the verification (default: True)
        use_persistent_context: If True, use a persistent browser context that preserves
                               Cloudflare clearance cookies across sessions. This helps
                               bypass Cloudflare for sites you've manually verified before.
        user_data_dir: Directory for persistent browser data. If not specified,
                      defaults to ~/.bmlibrarian/browser_data/

    Returns:
        Dictionary with download result
    """
    async def _download(use_headless: bool, persistent: bool = False):
        if persistent:
            return await _download_with_persistent_context(
                url, save_path, use_headless, timeout, expected_doi, cookies, user_agent, user_data_dir
            )
        async with BrowserDownloader(headless=use_headless, timeout=timeout) as downloader:
            return await downloader.download_pdf(
                url, save_path,
                expected_doi=expected_doi,
                cookies=cookies,
                user_agent=user_agent
            )

    # First attempt with specified headless mode
    # If persistent context requested, use it directly
    if use_persistent_context:
        result = asyncio.run(_download(headless, persistent=True))
        return result

    result = asyncio.run(_download(headless))

    # If Cloudflare blocked and we should retry with better methods
    if (result.get('cloudflare_blocked') and
        headless and
        retry_cloudflare_visible):

        logger.info(
            "\n============================================================\n"
            "CLOUDFLARE PROTECTION DETECTED\n"
            "============================================================\n"
            "This site uses Cloudflare anti-bot protection.\n"
            "Trying undetected-chromedriver (better Cloudflare bypass)...\n"
            "============================================================"
        )

        # Try with undetected-chromedriver first (best Cloudflare bypass)
        uc_result = download_pdf_with_undetected_chrome(
            url=url,
            save_path=save_path,
            headless=False,  # Non-headless for best results
            timeout=120,
            expected_doi=expected_doi,
            cookies=cookies
        )

        if uc_result.get('status') == 'success':
            return uc_result

        # If undetected-chromedriver failed but got past Cloudflare,
        # the site is likely paywalled - not a Cloudflare issue
        logger.info(
            "undetected-chromedriver got past Cloudflare but couldn't download PDF. "
            "This site may require institutional access (OpenAthens) or login."
        )

        # Return the original result with enhanced error message
        result['error'] = (
            "Cloudflare was bypassed but PDF download failed. "
            "This site likely requires institutional access (OpenAthens) "
            "or a subscription login. Configure OpenAthens in settings if "
            "your institution has access."
        )

    return result


def download_pdf_with_undetected_chrome(
    url: str,
    save_path: Path,
    headless: bool = False,
    timeout: int = 120,
    expected_doi: Optional[str] = None,
    cookies: Optional[list] = None,
    openathens_url: Optional[str] = None,
    ezproxy_url: Optional[str] = None
) -> Dict[str, Any]:
    """Download PDF using undetected-chromedriver (best Cloudflare bypass).

    This uses undetected-chromedriver which patches Chrome/Chromium to evade
    Cloudflare and other bot detection systems. It's more effective than
    Playwright for sites with aggressive anti-bot protection.

    Also supports clicking through institutional login flows (like LWW OneID)
    when OpenAthens or EZproxy is configured.

    Args:
        url: URL to download from
        save_path: Path to save the PDF
        headless: Run browser in headless mode (default: False for Cloudflare)
        timeout: Timeout in seconds (default: 120)
        expected_doi: If provided, validate PDF links contain this DOI
        cookies: Optional list of cookie dicts to inject
        openathens_url: OpenAthens redirector URL for institutional access
                       (e.g., "https://go.openathens.net/redirector/jcu.edu.au")
        ezproxy_url: EZproxy login URL for institutional access
                    (e.g., "http://elibrary.jcu.edu.au/login?url=")

    Returns:
        Dictionary with download result
    """
    try:
        import undetected_chromedriver as uc
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
    except ImportError:
        return {
            'status': 'failed',
            'error': 'undetected-chromedriver not installed. Install with: uv add undetected-chromedriver'
        }

    import os
    from urllib.parse import urlparse, quote

    driver = None
    try:
        logger.info(f"Starting undetected Chrome (headless={headless})...")

        # Configure Chrome options
        options = uc.ChromeOptions()

        if headless:
            options.add_argument('--headless=new')

        # Set download directory
        download_dir = str(save_path.parent.absolute())
        os.makedirs(download_dir, exist_ok=True)

        prefs = {
            'download.default_directory': download_dir,
            'download.prompt_for_download': False,
            'download.directory_upgrade': True,
            'plugins.always_open_pdf_externally': True,  # Download PDFs instead of viewing
        }
        options.add_experimental_option('prefs', prefs)

        # Launch undetected Chrome
        driver = uc.Chrome(options=options, version_main=None)
        driver.set_page_load_timeout(timeout)

        # Inject cookies if provided
        if cookies:
            # First navigate to a page on the domain to set cookies
            parsed = urlparse(url)
            base_url = f"{parsed.scheme}://{parsed.netloc}"
            try:
                driver.get(base_url)
                time.sleep(1)
                for cookie in cookies:
                    if 'name' in cookie and 'value' in cookie:
                        # Selenium requires specific cookie format
                        selenium_cookie = {
                            'name': cookie['name'],
                            'value': cookie['value'],
                            'domain': cookie.get('domain', parsed.netloc),
                            'path': cookie.get('path', '/'),
                        }
                        try:
                            driver.add_cookie(selenium_cookie)
                        except Exception as ce:
                            logger.debug(f"Could not add cookie {cookie['name']}: {ce}")
                logger.info(f"Injected {len(cookies)} cookies")
            except Exception as e:
                logger.debug(f"Error setting cookies: {e}")

        # Navigate to the target URL
        logger.info(f"Navigating to: {url}")
        driver.get(url)

        # Wait for Cloudflare challenge to complete (if present)
        # undetected-chromedriver usually bypasses it automatically
        max_wait = 60
        start_time = time.time()

        while time.time() - start_time < max_wait:
            title = driver.title.lower()
            page_source = driver.page_source.lower()

            cloudflare_indicators = [
                'just a moment',
                'checking your browser',
                'cf-challenge',
                'challenge-platform',
            ]

            has_cloudflare = any(ind in title or ind in page_source for ind in cloudflare_indicators)

            if not has_cloudflare:
                logger.info("Page loaded (no Cloudflare challenge or it was bypassed)")
                break

            logger.info(f"Waiting for Cloudflare... ({int(time.time() - start_time)}s)")
            time.sleep(2)

        # Give page time to fully render
        time.sleep(3)

        # Check if we need institutional access (look for login links)
        # LWW uses login.journals.lww.com/OneID/Login.aspx with "Access through Ovid" text
        institutional_login_needed = False
        institutional_login_link = None

        try:
            links = driver.find_elements(By.TAG_NAME, 'a')

            # First pass: look for high-confidence institutional patterns
            # (specific URLs that indicate institutional access)
            high_confidence_patterns = [
                'login.journals.lww.com',  # LWW institutional login
                'openathens',
                'shibboleth',
                '/wayf',  # Where Are You From (federation)
                'idp.',   # Identity Provider
            ]

            # Second pass: look for links with institutional text
            institutional_text_patterns = [
                'institutional',
                'ovid',  # LWW uses "Access through Ovid" for institutional
                'institution',
                'university',
                'library access',
            ]

            candidate_links = []

            for link in links:
                href = link.get_attribute('href') or ''
                text = (link.text or '').lower().strip()
                href_lower = href.lower()

                # Skip empty or javascript links
                if not href or href.startswith('javascript:'):
                    continue

                # High confidence: URL matches institutional pattern
                if any(pattern in href_lower for pattern in high_confidence_patterns):
                    logger.info(f"Found high-confidence institutional link: {href}")
                    institutional_login_link = href
                    institutional_login_needed = True
                    break

                # Medium confidence: link text suggests institutional access
                if any(pattern in text for pattern in institutional_text_patterns):
                    candidate_links.append((href, text, 'text_match'))

            # If no high-confidence link, use best text-matched candidate
            if not institutional_login_needed and candidate_links:
                # Prefer links with "ovid" or "institutional" in text
                for href, text, _ in candidate_links:
                    if 'ovid' in text or 'institutional' in text:
                        institutional_login_link = href
                        institutional_login_needed = True
                        logger.info(f"Found institutional link via text match: {href} (text: {text})")
                        break

                # Fallback to first candidate
                if not institutional_login_needed and candidate_links:
                    institutional_login_link = candidate_links[0][0]
                    institutional_login_needed = True
                    logger.info(f"Found institutional link (fallback): {institutional_login_link}")

        except Exception as e:
            logger.debug(f"Error checking for institutional login: {e}")

        # If institutional login is needed and we have OpenAthens or EZproxy URL
        if institutional_login_needed and (openathens_url or ezproxy_url):
            # Prefer EZproxy if available (more reliable for PDF downloads)
            proxy_url = ezproxy_url or openathens_url
            proxy_type = "EZproxy" if ezproxy_url else "OpenAthens"

            logger.info(f"Attempting institutional access via {proxy_type}...")

            # Construct the proxy-wrapped URL
            target_url = url
            encoded_target = quote(target_url, safe='')

            if ezproxy_url:
                # EZproxy format: base?url=target
                if '?' in ezproxy_url:
                    wrapped_url = f"{ezproxy_url}{encoded_target}"
                else:
                    wrapped_url = f"{ezproxy_url}?url={encoded_target}"
            elif 'go.openathens.net/redirector' in openathens_url:
                # OpenAthens Redirector format
                wrapped_url = f"{openathens_url}?url={encoded_target}"
            else:
                # Traditional proxy format
                wrapped_url = f"{openathens_url}/login?url={encoded_target}"

            logger.info(f"Navigating to {proxy_type} wrapped URL: {wrapped_url[:100]}...")
            driver.get(wrapped_url)

            # Wait for SSO login to complete
            # User will need to complete their institution's SSO manually
            logger.info(
                f"\n============================================================\n"
                f"INSTITUTIONAL LOGIN REQUIRED ({proxy_type})\n"
                f"============================================================\n"
                f"Please complete your institutional login in the browser window.\n"
                f"Waiting up to 120 seconds for authentication...\n"
                f"============================================================"
            )

            # Wait for user to complete SSO login
            sso_timeout = 120
            sso_start = time.time()

            while time.time() - sso_start < sso_timeout:
                current_url = driver.current_url.lower()

                # Check if we're back on the publisher site (not on SSO/login pages)
                sso_indicators = [
                    '/login', '/signin', '/auth', '/sso', '/saml',
                    'idp.', 'sso.', 'auth.', 'login.microsoftonline',
                    'go.openathens.net', 'my.openathens.net',
                    'elibrary.', 'ezproxy.',  # EZproxy login pages
                ]

                still_on_sso = any(ind in current_url for ind in sso_indicators)

                if not still_on_sso:
                    logger.info(f"SSO complete - now on: {driver.current_url}")
                    time.sleep(3)  # Let page load
                    break

                time.sleep(2)

        # Now try to find PDF download link
        pdf_url = None

        # FIRST: Check meta tags for PDF URLs (most reliable source)
        # Different publishers use different meta tag names
        pdf_meta_names = [
            'citation_pdf_url',     # Standard academic meta tag
            'wkhealth_pdf_url',     # Wolters Kluwer / LWW
            'dc.identifier.uri',    # Dublin Core (some use for PDF)
            'pdf_url',              # Generic
        ]

        for meta_name in pdf_meta_names:
            if pdf_url:
                break
            try:
                meta = driver.find_element(By.CSS_SELECTOR, f'meta[name="{meta_name}"]')
                content = meta.get_attribute('content')
                if content and ('pdf' in content.lower() or 'download' in content.lower()):
                    pdf_url = content
                    logger.info(f"Found PDF URL in meta tag '{meta_name}': {pdf_url}")
            except Exception:
                pass

        # SECOND: Look for links with "download pdf" or similar text
        if not pdf_url:
            try:
                links = driver.find_elements(By.TAG_NAME, 'a')
                download_candidates = []

                for link in links:
                    href = link.get_attribute('href') or ''
                    text = (link.text or '').lower().strip()
                    href_lower = href.lower()

                    # Skip non-http links
                    if not href or href.startswith('javascript:') or href.startswith('#'):
                        continue

                    # Score the link
                    score = 0

                    # Links with 'downloadpdf' or similar in URL (high confidence)
                    if 'downloadpdf' in href_lower or 'download.pdf' in href_lower:
                        score += 50
                    elif '.pdf' in href_lower:
                        score += 30
                    elif 'download' in href_lower and 'pdf' in href_lower:
                        score += 40

                    # Link text mentions PDF download
                    if 'download' in text and 'pdf' in text:
                        score += 25
                    elif text == 'pdf' or text == 'download pdf':
                        score += 20
                    elif 'pdf' in text:
                        score += 10

                    # Bonus for being on the same domain
                    if 'journals.lww.com' in href_lower or 'lww.com' in href_lower:
                        score += 5

                    # Penalty for obvious non-article PDFs
                    if 'author-document' in href_lower or 'permission' in href_lower:
                        score -= 30
                    if 'supplement' in href_lower:
                        score -= 20

                    if score > 0:
                        download_candidates.append((href, score, text))

                # Sort by score and pick best
                if download_candidates:
                    download_candidates.sort(key=lambda x: x[1], reverse=True)
                    best_href, best_score, best_text = download_candidates[0]
                    logger.info(f"Found PDF link (score={best_score}): {best_href} (text: {best_text})")
                    pdf_url = best_href

            except Exception as e:
                logger.debug(f"Error finding PDF links: {e}")

        # If we found a PDF URL, try multiple methods to download it
        if pdf_url:
            logger.info(f"Found PDF URL: {pdf_url}")

            # Method 1: Try JavaScript fetch with credentials (preserves auth cookies)
            logger.info("Attempting JavaScript fetch with credentials...")
            try:
                # Use fetch API to download PDF content
                fetch_script = f"""
                return (async () => {{
                    try {{
                        const response = await fetch("{pdf_url}", {{
                            credentials: 'include',
                            headers: {{
                                'Accept': 'application/pdf, */*'
                            }}
                        }});

                        if (!response.ok) {{
                            return {{error: 'HTTP ' + response.status, status: response.status}};
                        }}

                        const contentType = response.headers.get('content-type') || '';
                        const buffer = await response.arrayBuffer();
                        const bytes = new Uint8Array(buffer);

                        // Check if response is PDF
                        const header = String.fromCharCode(...bytes.slice(0, 4));

                        return {{
                            contentType: contentType,
                            size: bytes.length,
                            isPdf: header === '%PDF',
                            header: header,
                            // Return full content as base64 for smaller files
                            data: bytes.length < 50000000 ? btoa(String.fromCharCode(...bytes)) : null
                        }};
                    }} catch (e) {{
                        return {{error: e.toString()}};
                    }}
                }})();
                """

                result = driver.execute_script(fetch_script)
                logger.debug(f"Fetch result: contentType={result.get('contentType')}, size={result.get('size')}, isPdf={result.get('isPdf')}")

                if result.get('isPdf') and result.get('data'):
                    # Decode base64 and save
                    import base64
                    pdf_data = base64.b64decode(result['data'])
                    save_path.write_bytes(pdf_data)
                    size = len(pdf_data)
                    logger.info(f"PDF downloaded via JavaScript fetch: {size} bytes")
                    return {
                        'status': 'success',
                        'path': str(save_path),
                        'size': size
                    }
                elif result.get('error'):
                    logger.debug(f"JavaScript fetch failed: {result.get('error')}")
                elif not result.get('isPdf'):
                    logger.debug(f"Response is not a PDF (header: {result.get('header')})")

            except Exception as fetch_error:
                logger.debug(f"JavaScript fetch exception: {fetch_error}")

            # Method 2: Direct navigation (may trigger download)
            logger.info("Attempting direct navigation to PDF URL...")
            driver.get(pdf_url)
            time.sleep(5)  # Wait for download to start/complete

            # Check if file was downloaded
            downloaded_files = list(Path(download_dir).glob('*.pdf'))

            # Find most recently modified PDF
            if downloaded_files:
                newest_file = max(downloaded_files, key=lambda f: f.stat().st_mtime)

                # Move/rename to expected path
                if newest_file != save_path:
                    import shutil
                    shutil.move(str(newest_file), str(save_path))

                if save_path.exists():
                    # Verify it's a PDF
                    with open(save_path, 'rb') as f:
                        header = f.read(4)
                    if header == b'%PDF':
                        size = save_path.stat().st_size
                        logger.info(f"PDF downloaded successfully: {save_path} ({size} bytes)")
                        return {
                            'status': 'success',
                            'path': str(save_path),
                            'size': size
                        }
                    else:
                        logger.warning("Downloaded file is not a valid PDF")

        # If no PDF link found, try to get page content
        # Some sites embed PDFs in viewers
        try:
            # Check for embedded PDF viewer
            iframes = driver.find_elements(By.TAG_NAME, 'iframe')
            for iframe in iframes:
                src = iframe.get_attribute('src') or ''
                if '.pdf' in src.lower():
                    logger.info(f"Found PDF in iframe: {src}")
                    driver.get(src)
                    time.sleep(5)

                    downloaded_files = list(Path(download_dir).glob('*.pdf'))
                    if downloaded_files:
                        newest_file = max(downloaded_files, key=lambda f: f.stat().st_mtime)
                        if newest_file != save_path:
                            import shutil
                            shutil.move(str(newest_file), str(save_path))
                        if save_path.exists():
                            size = save_path.stat().st_size
                            return {
                                'status': 'success',
                                'path': str(save_path),
                                'size': size
                            }
        except Exception as e:
            logger.debug(f"Error checking iframes: {e}")

        # If institutional login was needed but not successful
        if institutional_login_needed:
            # Check if we're on a publisher page that still shows paywalled content
            page_source = driver.page_source.lower()
            paywall_indicators = [
                'subscribe', 'subscription required', 'purchase this article',
                'buy this article', 'access denied', 'institutional access',
                'sign in to access', 'log in to access'
            ]

            still_paywalled = any(ind in page_source for ind in paywall_indicators)

            if still_paywalled:
                # Provide detailed error with troubleshooting steps
                error_msg = (
                    "Could not authenticate for PDF download. Possible causes:\n"
                    "1. Your institution may not have access to this publisher\n"
                    "2. OpenAthens/EZproxy may not be configured for this publisher\n"
                    "3. For LWW/Lippincott journals, try accessing via Ovid platform instead\n\n"
                    "Troubleshooting:\n"
                    "- Check if your library has access to this journal\n"
                    "- Try accessing through your library's A-Z database list\n"
                    "- For LWW journals, search for the article in Ovid"
                )
                return {
                    'status': 'failed',
                    'error': error_msg,
                    'needs_institutional_access': True,
                    'publisher_detected': 'lww' if 'lww.com' in url.lower() else 'unknown'
                }

            if not openathens_url and not ezproxy_url:
                return {
                    'status': 'failed',
                    'error': 'This article requires institutional access. Configure OpenAthens or EZproxy in settings.',
                    'needs_institutional_access': True
                }

        return {
            'status': 'failed',
            'error': 'Could not find or download PDF from page'
        }

    except Exception as e:
        logger.error(f"Undetected Chrome download failed: {e}")
        return {
            'status': 'failed',
            'error': str(e)
        }

    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass


# Example usage
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    test_url = "https://example.com/paper.pdf"
    test_path = Path("/tmp/test_download.pdf")

    # Try undetected-chromedriver first (best for Cloudflare)
    print("Testing with undetected-chromedriver...")
    result = download_pdf_with_undetected_chrome(test_url, test_path, headless=False)
    print(f"Download result: {result}")
