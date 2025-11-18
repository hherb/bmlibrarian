"""OpenAthens Authentication Module

Provides secure session management for OpenAthens institutional authentication
using Playwright browser automation with proper security practices.
"""

import json
import logging
import stat
import re
import asyncio
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
from urllib.parse import urlparse
import requests

logger = logging.getLogger(__name__)


class OpenAthensConfig:
    """Configuration for OpenAthens authentication."""
class OpenAthensAuth:
    """Manages OpenAthens authentication and session persistence."""

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
        self.auth_cookie_patterns = [
            r'openathens.*session',
            r'_saml_.*',
            r'shib.*session',
            r'shibsession.*',
            r'_shibstate_.*'
        ]

    def _validate_url(self, url: str) -> str:
        """Validate and normalize institution URL.

        Args:
            url: URL to validate

        Returns:
            Normalized URL

        Raises:
            ValueError: If URL is invalid or not HTTPS
        """
        if not url:
            raise ValueError("Institution URL cannot be empty")

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


class OpenAthensAuth:
    """Manages OpenAthens institutional authentication sessions."""

    def __init__(
        self,
        config: OpenAthensConfig,
        session_file: Optional[Path] = None
    ):
        """Initialize OpenAthens authentication.

        Args:
            config: OpenAthens configuration
            session_file: Path to session storage file (default: ~/.bmlibrarian/openathens_session.json)
        """
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

        Returns:
            True if reachable, False otherwise
        """
        try:
            response = requests.head(
                self.config.institution_url,
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

    def _detect_auth_success(self, cookies: List[Dict]) -> bool:
        """Detect successful authentication from cookies.

        Args:
            cookies: List of cookie dictionaries

        Returns:
            True if authentication cookies detected, False otherwise
        """
        cookie_names = [c['name'] for c in cookies]

        # Check each cookie pattern
        for pattern in self.config.auth_cookie_patterns:
            for name in cookie_names:
                if re.search(pattern, name, re.IGNORECASE):
                    logger.info(f"Authentication cookie detected: {name}")
                    return True

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

            # Navigate to institution login
            logger.info(f"Navigating to: {self.config.institution_url}")
            try:
                await page.goto(
                    self.config.institution_url,
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
            auth_success = False
            start_time = asyncio.get_event_loop().time()
            max_wait_time = 300  # 5 minutes max

            while (asyncio.get_event_loop().time() - start_time) < max_wait_time:
                try:
                    cookies = await context.cookies()

                    if self._detect_auth_success(cookies):
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
