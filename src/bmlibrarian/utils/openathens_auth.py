"""OpenAthens Authentication Module

Provides secure session management for OpenAthens institutional authentication
using Playwright browser automation with proper security practices.

Supports two OpenAthens URL formats:
1. Redirector URLs (modern): go.openathens.net/redirector/{domain}?url={target}
   - URL wrapping service that triggers auth when navigating to wrapped URLs
   - No direct login page - auth happens via SSO when accessing wrapped resources

2. Portal URLs (legacy): my.openathens.net or institution-specific login pages
   - Direct login portal for manual authentication
"""

import json
import logging
import stat
import re
import asyncio
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
from urllib.parse import urlparse, quote
import requests

logger = logging.getLogger(__name__)

# Constants for OpenAthens URL detection
REDIRECTOR_HOST = "go.openathens.net"
REDIRECTOR_PATH_PREFIX = "/redirector/"

# Test URL for triggering redirector authentication
# Using PubMed as it's widely accessible and triggers institutional auth
REDIRECTOR_TEST_TARGET = "https://pubmed.ncbi.nlm.nih.gov/"


class OpenAthensConfig:
    """Configuration for OpenAthens authentication."""

    def __init__(
        self,
        institution_url: str,
        session_max_age_hours: int = 24,
        auth_check_interval: float = 1.0,
        cloudflare_wait: int = 30,
        page_timeout: int = 60000,
        headless: bool = True,
        session_cache_ttl: int = 60
    ):
        """Initialize OpenAthens configuration.

        Args:
            institution_url: Institution's OpenAthens login URL
            session_max_age_hours: Maximum session age in hours (default: 24)
            auth_check_interval: Polling interval for auth checks in seconds (default: 1.0)
            cloudflare_wait: Max seconds to wait for Cloudflare (default: 30)
            page_timeout: Page load timeout in milliseconds (default: 60000)
            headless: Run browser in headless mode (default: True)
            session_cache_ttl: Session validation cache TTL in seconds (default: 60)
        """
        self.institution_url = self._validate_url(institution_url)
        self.session_max_age_hours = session_max_age_hours
        self.auth_check_interval = auth_check_interval
        self.cloudflare_wait = cloudflare_wait
        self.page_timeout = page_timeout
        self.headless = headless
        self.session_cache_ttl = session_cache_ttl

        # Cookie patterns for different authentication systems
        # These patterns indicate SUCCESSFUL authentication, not just session start
        # IMPORTANT: Avoid generic patterns which are set before login completes:
        # - JSESSIONID: Java session cookie, set on page load
        # - amlbcookie: ForgeRock/OpenAM load balancer cookie, set on page load
        # - iPlanetDirectoryPro: Can be set early in some configurations
        # - TGC: CAS ticket granting cookie can be set early
        self.auth_cookie_patterns = [
            # OpenAthens-specific (set after successful auth)
            r'openathens.*session',
            r'oatoken',
            r'oasession',
            # SAML assertion cookies (set after successful SAML response)
            r'_saml_idp',
            r'saml.*token',
            # Shibboleth session cookies (set after IdP authentication)
            r'_shibsession_',
            r'shibsession.*',
            # SimpleSAML auth state (set after successful auth)
            r'SimpleSAMLAuthToken',
            # OpenID Connect tokens (set after successful auth)
            r'mod_auth_openidc_session',
            r'oidc.*token',
        ]

    def _validate_url(self, url: str) -> str:
        """Validate and normalize institution URL.

        Handles both full URLs and domain-only input (auto-converts to redirector URL).

        Args:
            url: URL or domain to validate

        Returns:
            Normalized URL

        Raises:
            ValueError: If URL is invalid or not HTTPS
        """
        if not url:
            raise ValueError("Institution URL cannot be empty")

        # Check if it's a domain-only input (e.g., "jcu.edu.au")
        # Domain has dots, no slashes (except possibly in protocol)
        url_stripped = url.strip()
        is_domain_only = (
            '.' in url_stripped and
            not url_stripped.startswith('http') and
            '/' not in url_stripped
        )

        if is_domain_only:
            # Convert domain to redirector URL
            url = f"https://{REDIRECTOR_HOST}{REDIRECTOR_PATH_PREFIX}{url_stripped}"
            logger.info(f"Converted domain '{url_stripped}' to redirector URL: {url}")

        # Parse URL
        parsed = urlparse(url)

        # Require HTTPS for security
        if parsed.scheme != 'https':
            raise ValueError(f"Institution URL must use HTTPS: {url}")

        # Require hostname
        if not parsed.netloc:
            raise ValueError(f"Invalid URL format: {url}")

        # Normalize by removing trailing slash
        return url.rstrip('/')

    def is_redirector_url(self) -> bool:
        """Check if the configured URL is an OpenAthens Redirector URL.

        Redirector URLs have the format: go.openathens.net/redirector/{domain}

        Returns:
            True if redirector URL, False if portal/login URL
        """
        parsed = urlparse(self.institution_url)
        return (
            parsed.netloc == REDIRECTOR_HOST and
            parsed.path.startswith(REDIRECTOR_PATH_PREFIX)
        )

    def get_redirector_auth_url(self, target_url: str = REDIRECTOR_TEST_TARGET) -> str:
        """Construct a redirector URL with a target for triggering authentication.

        Args:
            target_url: Target URL to wrap (default: PubMed)

        Returns:
            Full redirector URL that will trigger institutional SSO
        """
        if not self.is_redirector_url():
            raise ValueError("Not a redirector URL - use institution_url directly")

        encoded_target = quote(target_url, safe='')
        return f"{self.institution_url}?url={encoded_target}"


class OpenAthensAuth:
    """Manages OpenAthens institutional authentication sessions."""

    def __init__(
        self,
        config: Optional[OpenAthensConfig] = None,
        session_file: Optional[Path] = None,
        # Deprecated parameters for backward compatibility
        institution_url: Optional[str] = None,
        session_timeout_hours: Optional[int] = None,
        headless: Optional[bool] = None
    ):
        """Initialize OpenAthens authentication.

        Args:
            config: OpenAthensConfig instance (recommended)
            session_file: Path to session storage file

            # Deprecated (backward compatibility with old API):
            institution_url: Institution's OpenAthens URL (deprecated, use config instead)
            session_timeout_hours: Session timeout hours (deprecated, use config instead)
            headless: Headless browser mode (deprecated, use config instead)
        """
        # Handle backward compatibility with old API
        if config is None:
            if institution_url is None:
                raise ValueError(
                    "Either 'config' (recommended) or 'institution_url' (deprecated) must be provided"
                )

            # Old API used - create config from parameters
            import warnings
            warnings.warn(
                "Passing institution_url directly is deprecated. "
                "Use OpenAthensConfig instead:\n"
                "  config = OpenAthensConfig(institution_url='...')\n"
                "  auth = OpenAthensAuth(config=config)",
                DeprecationWarning,
                stacklevel=2
            )

            self.config = OpenAthensConfig(
                institution_url=institution_url,
                session_max_age_hours=session_timeout_hours or 24,
                headless=headless if headless is not None else True
            )
        else:
            # New API - use provided config
            self.config = config

        if session_file is None:
            session_dir = Path.home() / '.bmlibrarian'
            session_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
            session_file = session_dir / 'openathens_session.json'

        self.session_file = session_file
        self.session_data: Optional[Dict[str, Any]] = None
        self.browser = None
        self.playwright = None

        # Session validation cache
        self._last_validation_time: Optional[datetime] = None
        self._last_validation_result: bool = False

        # Load existing session if available
        self._load_session()

    def _check_network_connectivity(self) -> bool:
        """Check if institutional URL is reachable.

        For redirector URLs, we skip the check because:
        - The redirector host returns 404 on root path
        - The redirector path returns 400 without a url= parameter
        - The redirector is designed to redirect, not respond directly

        Returns:
            True if reachable (or redirector URL), False otherwise
        """
        try:
            if self.config.is_redirector_url():
                # For redirector URLs, skip the connectivity check
                # The redirector service doesn't have a testable endpoint
                # (returns 400 without url= param, 404 on root)
                # We'll find out if it works when we actually navigate
                logger.debug(
                    f"Skipping connectivity check for redirector URL: "
                    f"{self.config.institution_url}"
                )
                return True

            # For traditional login portals, do the connectivity check
            check_url = self.config.institution_url
            logger.debug(f"Checking portal connectivity: {check_url}")

            response = requests.head(
                check_url,
                timeout=10,
                allow_redirects=True
            )
            return response.status_code < 400
        except Exception as e:
            logger.warning(f"Network connectivity check failed: {e}")
            return False

    def _serialize_session_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Convert session data to JSON-safe format.

        Args:
            data: Session data to serialize

        Returns:
            JSON-serializable dictionary
        """
        return {
            'created_at': data['created_at'].isoformat(),
            'cookies': data['cookies'],
            'institution_url': data['institution_url'],
            'user_agent': data['user_agent']
        }

    def _deserialize_session_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Convert JSON data back to session format.

        Args:
            data: Serialized session data

        Returns:
            Session data dictionary
        """
        data['created_at'] = datetime.fromisoformat(data['created_at'])
        return data

    def _load_session(self) -> None:
        """Load session data from file."""
        if not self.session_file.exists():
            logger.debug("No existing session file found")
            return

        try:
            with open(self.session_file, 'r') as f:
                serialized_data = json.load(f)

            self.session_data = self._deserialize_session_data(serialized_data)
            logger.info(f"Loaded session from {self.session_file}")

        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.error(f"Failed to load session: {e}")
            self.session_data = None

    def _save_session(self) -> None:
        """Save session data to file with secure permissions."""
        if not self.session_data:
            logger.warning("No session data to save")
            return

        try:
            # Ensure parent directory exists with secure permissions
            self.session_file.parent.mkdir(parents=True, exist_ok=True, mode=0o700)

            # Serialize session data
            serialized_data = self._serialize_session_data(self.session_data)

            # Write to file
            with open(self.session_file, 'w') as f:
                json.dump(serialized_data, f, indent=2)

            # Set restrictive file permissions (600 = owner read/write only)
            self.session_file.chmod(stat.S_IRUSR | stat.S_IWUSR)

            logger.info(f"Saved session to {self.session_file} with secure permissions")

        except (IOError, OSError) as e:
            logger.error(f"Failed to save session: {e}")

    def _detect_auth_success(self, cookies: List[Dict], current_url: str = "") -> bool:
        """Detect successful authentication from cookies or URL change.

        Args:
            cookies: List of cookie dictionaries
            current_url: Current page URL (for detecting SSO completion)

        Returns:
            True if authentication cookies detected, False otherwise
        """
        cookie_names = [c['name'] for c in cookies]

        # Log all cookies for debugging (useful for adding new SSO patterns)
        if cookie_names:
            logger.debug(f"Current cookies ({len(cookie_names)}): {cookie_names}")

        # Check each cookie pattern
        for pattern in self.config.auth_cookie_patterns:
            for name in cookie_names:
                if re.search(pattern, name, re.IGNORECASE):
                    logger.info(f"Authentication cookie detected: {name}")
                    return True

        # Fallback: Check if we've completed SSO and returned to a resource page
        # We need to be careful here - just changing domains doesn't mean we're authenticated
        # (e.g., redirecting from OpenAthens to SSO login page)
        if current_url:
            current_url_lower = current_url.lower()

            # First check for successful OpenAthens authentication
            # When auth completes, user is redirected to my.openathens.net/app/...
            if 'my.openathens.net/app/' in current_url_lower:
                logger.info(f"OpenAthens authentication complete - redirected to dashboard: {current_url}")
                return True

            # Check if we've left the OpenAthens redirector and SSO flow entirely
            # and reached a publisher page with authenticated content
            left_openathens = REDIRECTOR_HOST not in current_url_lower

            # SSO login pages typically have these patterns in the URL
            sso_login_indicators = [
                '/login', '/signin', '/auth', '/sso', '/saml',
                '/openam', '/adfs', '/cas', 'passiveLogin',
                'login.microsoftonline', 'accounts.google',
                # Identity provider domains (still authenticating)
                'idp.', 'sso.', 'auth.',
                # Common IdP paths
                '/idp/', '/simplesaml/', '/shibboleth/',
                # Institution-specific patterns (Australian universities)
                '.edu.au/idp', '.edu.au/sso', '.edu.au/login',
                # OpenAthens portal (selecting institution, not authenticated yet)
                # Note: my.openathens.net/app/* indicates SUCCESSFUL auth (dashboard)
                'my.openathens.net/?',  # Only the login/selection page, not /app/
                # SAML/Shibboleth federation pages
                'wayf', 'discovery', 'ds.aaf.edu.au',
            ]

            # Check if we're still on a login page (not authenticated yet)
            is_login_page = any(indicator in current_url_lower for indicator in sso_login_indicators)

            if is_login_page:
                logger.debug(f"Still on login page: {current_url}")
                return False

            # Additional check: are we on a known publisher domain?
            # This helps avoid false positives on IdP/SSO domains
            publisher_indicators = [
                'springer.com', 'nature.com', 'wiley.com', 'elsevier.com',
                'sciencedirect.com', 'tandfonline.com', 'sagepub.com',
                'oup.com', 'bmj.com', 'nejm.org', 'thelancet.com',
                'cell.com', 'pnas.org', 'acs.org', 'rsc.org',
                'ieee.org', 'acm.org', 'jstor.org', 'pubmed.ncbi',
            ]
            on_publisher = any(pub in current_url_lower for pub in publisher_indicators)

            # If we have many cookies (≥8) AND we're on a publisher domain,
            # that's a strong indicator of successful authentication
            has_many_cookies = len(cookies) >= 8

            if has_many_cookies and on_publisher:
                logger.info(
                    f"SSO completion detected: {len(cookies)} cookies, "
                    f"on publisher domain: {current_url}"
                )
                logger.info(f"Cookies: {cookie_names}")
                return True

            # For redirector flow: if we've left OpenAthens/SSO and reached publisher
            # with some cookies (authentication may have completed)
            if left_openathens and on_publisher and len(cookies) >= 4 and not is_login_page:
                logger.info(
                    f"Redirector auth complete: reached publisher with {len(cookies)} cookies: {current_url}"
                )
                return True

            if has_many_cookies and not is_login_page:
                # Not on a recognized publisher but lots of cookies - log but don't auto-detect
                logger.debug(
                    f"Many cookies ({len(cookies)}) but not on recognized publisher: {current_url}"
                )

        logger.debug(f"No authentication cookies found. Present cookies: {cookie_names}")
        return False

    def is_session_valid(self) -> bool:
        """Check if current session is valid (not expired).

        Returns:
            True if session is valid, False otherwise
        """
        if not self.session_data:
            return False

        # Check session age
        age = datetime.now() - self.session_data['created_at']
        max_age = timedelta(hours=self.config.session_max_age_hours)

        if age > max_age:
            logger.info(f"Session expired (age: {age} > max: {max_age})")
            return False

        return True

    def is_authenticated(self) -> bool:
        """Check if currently authenticated with caching.

        Uses cached result if within TTL, otherwise performs full validation.

        Returns:
            True if authenticated, False otherwise
        """
        # Check cache first
        if self._last_validation_time:
            cache_age = (datetime.now() - self._last_validation_time).total_seconds()
            if cache_age < self.config.session_cache_ttl:
                logger.debug(f"Using cached validation result (age: {cache_age:.1f}s)")
                return self._last_validation_result

        # Perform validation
        result = self.is_session_valid()

        # Update cache
        self._last_validation_time = datetime.now()
        self._last_validation_result = result

        return result

    def get_cookies(self) -> List[Dict[str, Any]]:
        """Get authentication cookies.

        Returns:
            List of cookie dictionaries, or empty list if not authenticated
        """
        if not self.is_session_valid():
            return []

        return self.session_data.get('cookies', [])

    def get_user_agent(self) -> Optional[str]:
        """Get user agent from session.

        Returns:
            User agent string, or None if not authenticated
        """
        if not self.is_session_valid():
            return None

        return self.session_data.get('user_agent')

    async def login_interactive(self) -> bool:
        """Perform interactive login using browser automation.

        Opens browser window for user to complete institutional login,
        then captures and saves the authentication cookies.

        Returns:
            True if login successful, False otherwise
        """
        # Clear any existing session to ensure fresh authentication
        # This prevents stale cookies from interfering with auth detection
        logger.info("Clearing existing session before re-authentication...")
        self.clear_session()

        # Check network connectivity first
        if not self._check_network_connectivity():
            logger.error(f"Cannot reach institution URL: {self.config.institution_url}")
            return False

        try:
            from playwright.async_api import async_playwright
        except ImportError:
            logger.error(
                "Playwright not installed. Install with: "
                "uv add playwright && uv run python -m playwright install chromium"
            )
            return False

        try:
            # Start Playwright
            self.playwright = await async_playwright().start()

            # Launch browser
            try:
                self.browser = await self.playwright.chromium.launch(
                    headless=self.config.headless,
                    args=[
                        '--disable-blink-features=AutomationControlled',
                        '--disable-dev-shm-usage',
                        '--no-sandbox'
                    ]
                )
            except Exception as e:
                logger.error(f"Browser launch failed: {e}")
                await self._cleanup_browser()
                return False

            # Create context with realistic settings
            context = await self.browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                          'AppleWebKit/537.36 (KHTML, like Gecko) '
                          'Chrome/131.0.0.0 Safari/537.36',
                locale='en-US',
                timezone_id='America/New_York'
            )

            page = await context.new_page()

            # Determine the URL to navigate to
            if self.config.is_redirector_url():
                # For redirector URLs, we need to wrap a target URL to trigger SSO
                # Use a paywalled publisher URL that will require authentication
                test_target = "https://link.springer.com/article/10.1007/s00381-016-3068-4"
                nav_url = self.config.get_redirector_auth_url(test_target)
                logger.info(f"Using OpenAthens Redirector flow")
                logger.info(f"Navigating to wrapped URL: {nav_url}")
            else:
                # For portal URLs, navigate directly
                nav_url = self.config.institution_url
                logger.info(f"Navigating to portal URL: {nav_url}")

            try:
                await page.goto(
                    nav_url,
                    wait_until='domcontentloaded',
                    timeout=self.config.page_timeout
                )
            except Exception as e:
                logger.error(f"Navigation failed: {e}")
                await context.close()
                await self._cleanup_browser()
                return False

            # Wait for user to complete login
            # Poll for authentication cookies
            logger.info("Waiting for authentication to complete...")
            logger.info("Please complete your institutional login in the browser window.")
            auth_success = False
            start_time = asyncio.get_event_loop().time()
            max_wait_time = 300  # 5 minutes max

            while (asyncio.get_event_loop().time() - start_time) < max_wait_time:
                try:
                    cookies = await context.cookies()
                    current_url = page.url

                    if self._detect_auth_success(cookies, current_url):
                        auth_success = True
                        logger.info("Authentication successful!")
                        break

                    await asyncio.sleep(self.config.auth_check_interval)

                except Exception as e:
                    logger.error(f"Error checking cookies: {e}")
                    break

            if not auth_success:
                logger.error("Authentication timeout or failed")
                await context.close()
                await self._cleanup_browser()
                return False

            # Capture session data
            cookies = await context.cookies()
            user_agent = await page.evaluate('navigator.userAgent')

            self.session_data = {
                'created_at': datetime.now(),
                'cookies': cookies,
                'institution_url': self.config.institution_url,
                'user_agent': user_agent
            }

            # Save session
            self._save_session()

            # Cleanup
            await context.close()
            await self._cleanup_browser()

            # Reset validation cache
            self._last_validation_time = None

            return True

        except Exception as e:
            logger.error(f"Login failed: {e}", exc_info=True)
            await self._cleanup_browser()
            return False

    async def login(self, wait_for_login: int = 300) -> bool:
        """Perform interactive login (deprecated alias).

        This method is an alias for login_interactive() for backward compatibility.

        Args:
            wait_for_login: Maximum seconds to wait (ignored, uses configured timeout)

        Returns:
            True if login successful, False otherwise
        """
        import warnings
        warnings.warn(
            "login() is deprecated. Use login_interactive() instead.",
            DeprecationWarning,
            stacklevel=2
        )
        return await self.login_interactive()

    async def _cleanup_browser(self):
        """Cleanup browser resources."""
        try:
            if self.browser:
                await self.browser.close()
                self.browser = None
        except Exception as e:
            logger.debug(f"Error closing browser: {e}")

        try:
            if self.playwright:
                await self.playwright.stop()
                self.playwright = None
        except Exception as e:
            logger.debug(f"Error stopping playwright: {e}")

    def clear_session(self) -> None:
        """Clear current session and delete session file."""
        self.session_data = None
        self._last_validation_time = None
        self._last_validation_result = False

        if self.session_file.exists():
            try:
                self.session_file.unlink()
                logger.info(f"Deleted session file: {self.session_file}")
            except OSError as e:
                logger.error(f"Failed to delete session file: {e}")


def login_interactive_sync(config: OpenAthensConfig) -> OpenAthensAuth:
    """Synchronous wrapper for interactive login.

    Args:
        config: OpenAthens configuration

    Returns:
        OpenAthensAuth instance with active session

    Raises:
        RuntimeError: If login fails
    """
    auth = OpenAthensAuth(config)

    async def _login():
        return await auth.login_interactive()

    success = asyncio.run(_login())

    if not success:
        raise RuntimeError("OpenAthens login failed")

    return auth
