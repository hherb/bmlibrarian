"""OpenAthens Authentication and Session Management

This module handles OpenAthens proxy authentication for accessing paywalled
journal articles through institutional subscriptions. It supports 2FA login,
session persistence, and automatic proxy URL construction.
"""

import logging
import json
import time
import asyncio
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
import pickle

logger = logging.getLogger(__name__)


class OpenAthensAuth:
    """Manages OpenAthens authentication and session persistence."""

    def __init__(
        self,
        institution_url: str,
        session_file: Optional[Path] = None,
        session_timeout_hours: int = 24,
        headless: bool = False
    ):
        """Initialize OpenAthens authenticator.

        Args:
            institution_url: Your institution's OpenAthens URL
                           (e.g., "https://institution.openathens.net")
            session_file: Path to store session cookies (default: ~/.bmlibrarian/openathens_session.pkl)
            session_timeout_hours: Hours before session expires (default: 24)
            headless: Run browser in headless mode for login (default: False for 2FA visibility)
        """
        self.institution_url = institution_url.rstrip('/')
        self.session_timeout_hours = session_timeout_hours
        self.headless = headless

        # Default session file location
        if session_file is None:
            config_dir = Path.home() / '.bmlibrarian'
            config_dir.mkdir(exist_ok=True)
            session_file = config_dir / 'openathens_session.pkl'

        self.session_file = session_file
        self.session_data: Optional[Dict[str, Any]] = None
        self.cookies: Optional[Dict[str, str]] = None

        # Load existing session if available
        self._load_session()

    def _load_session(self) -> bool:
        """Load session from disk if available and valid.

        Returns:
            True if session loaded successfully, False otherwise
        """
        if not self.session_file.exists():
            logger.info("No existing OpenAthens session found")
            return False

        try:
            with open(self.session_file, 'rb') as f:
                self.session_data = pickle.load(f)

            # Check if session is expired
            created_at = self.session_data.get('created_at')
            if created_at:
                expires_at = created_at + timedelta(hours=self.session_timeout_hours)
                if datetime.now() > expires_at:
                    logger.info("OpenAthens session expired, re-login required")
                    self.session_data = None
                    self.cookies = None
                    return False

            self.cookies = self.session_data.get('cookies', {})
            logger.info(f"Loaded OpenAthens session (created: {created_at}, "
                       f"{len(self.cookies)} cookies)")
            return True

        except Exception as e:
            logger.error(f"Failed to load OpenAthens session: {e}")
            self.session_data = None
            self.cookies = None
            return False

    def _save_session(self) -> bool:
        """Save session to disk.

        Returns:
            True if session saved successfully, False otherwise
        """
        if not self.session_data:
            return False

        try:
            # Ensure directory exists
            self.session_file.parent.mkdir(parents=True, exist_ok=True)

            with open(self.session_file, 'wb') as f:
                pickle.dump(self.session_data, f)

            logger.info(f"Saved OpenAthens session to {self.session_file}")
            return True

        except Exception as e:
            logger.error(f"Failed to save OpenAthens session: {e}")
            return False

    def is_authenticated(self) -> bool:
        """Check if currently authenticated with valid session.

        Returns:
            True if authenticated, False otherwise
        """
        if not self.session_data or not self.cookies:
            return False

        # Check expiration
        created_at = self.session_data.get('created_at')
        if created_at:
            expires_at = created_at + timedelta(hours=self.session_timeout_hours)
            if datetime.now() > expires_at:
                return False

        return True

    async def login(self, wait_for_login: int = 300) -> bool:
        """Perform OpenAthens login using browser automation.

        Opens browser for user to complete login with 2FA, then captures session.

        Args:
            wait_for_login: Maximum seconds to wait for user to complete login (default: 300)

        Returns:
            True if login successful, False otherwise
        """
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            logger.error(
                "Playwright not installed. Install with: "
                "uv add playwright && uv run python -m playwright install chromium"
            )
            return False

        logger.info("Starting OpenAthens login flow...")
        logger.info(f"Browser will open for login (2FA supported, timeout: {wait_for_login}s)")

        playwright = None
        browser = None
        context = None

        try:
            playwright = await async_playwright().start()

            # Launch browser (visible for 2FA)
            browser = await playwright.chromium.launch(
                headless=self.headless,
                args=['--disable-blink-features=AutomationControlled']
            )

            # Create context with realistic settings
            context = await browser.new_context(
                viewport={'width': 1280, 'height': 800},
                user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                          'AppleWebKit/537.36 (KHTML, like Gecko) '
                          'Chrome/131.0.0.0 Safari/537.36',
                locale='en-US'
            )

            page = await context.new_page()

            # Navigate to institution's OpenAthens login
            logger.info(f"Opening: {self.institution_url}")
            await page.goto(self.institution_url)

            # Wait for user to complete login
            logger.info("Please complete login in the browser (including 2FA if required)")
            logger.info("Waiting for successful authentication...")

            start_time = time.time()
            authenticated = False

            while time.time() - start_time < wait_for_login:
                # Check for successful authentication indicators
                current_url = page.url

                # Common success indicators:
                # 1. URL contains "authenticated" or "success"
                # 2. Specific cookies are set (OpenAthens session cookies)
                # 3. Redirected to authorized page

                cookies = await context.cookies()
                cookie_names = [c['name'] for c in cookies]

                # Check for OpenAthens session cookies
                openathens_cookies = [
                    name for name in cookie_names
                    if 'openathens' in name.lower() or
                       '_saml' in name.lower() or
                       'shib' in name.lower()  # Common SSO cookie patterns
                ]

                if openathens_cookies or 'authenticated' in current_url.lower():
                    authenticated = True
                    logger.info("Authentication successful!")
                    break

                await asyncio.sleep(1)

            if not authenticated:
                logger.error(f"Login timeout after {wait_for_login} seconds")
                return False

            # Capture all cookies
            all_cookies = await context.cookies()

            # Convert to dict format for requests library
            cookie_dict = {
                cookie['name']: cookie['value']
                for cookie in all_cookies
            }

            # Save session data
            self.session_data = {
                'created_at': datetime.now(),
                'cookies': cookie_dict,
                'institution_url': self.institution_url,
                'user_agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                             'AppleWebKit/537.36 (KHTML, like Gecko) '
                             'Chrome/131.0.0.0 Safari/537.36'
            }
            self.cookies = cookie_dict

            # Save to disk
            self._save_session()

            logger.info(f"OpenAthens session captured ({len(cookie_dict)} cookies)")
            return True

        except Exception as e:
            logger.error(f"OpenAthens login failed: {e}")
            return False

        finally:
            if context:
                await context.close()
            if browser:
                await browser.close()
            if playwright:
                await playwright.stop()

    def login_sync(self, wait_for_login: int = 300) -> bool:
        """Synchronous wrapper for login().

        Args:
            wait_for_login: Maximum seconds to wait for login

        Returns:
            True if login successful, False otherwise
        """
        return asyncio.run(self.login(wait_for_login))

    def construct_proxy_url(self, original_url: str) -> str:
        """Construct OpenAthens proxy URL for accessing content.

        Args:
            original_url: Original journal/article URL

        Returns:
            Proxied URL that routes through OpenAthens
        """
        # OpenAthens proxy URL format:
        # https://institution.openathens.net/direct?url=<encoded_original_url>

        from urllib.parse import quote

        encoded_url = quote(original_url, safe='')
        proxy_url = f"{self.institution_url}/direct?url={encoded_url}"

        return proxy_url

    def get_session_headers(self) -> Dict[str, str]:
        """Get HTTP headers including session cookies.

        Returns:
            Dictionary of headers for authenticated requests
        """
        if not self.session_data:
            return {}

        headers = {
            'User-Agent': self.session_data.get('user_agent',
                'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                'AppleWebKit/537.36'),
            'Accept': 'application/pdf,*/*',
            'Referer': self.institution_url
        }

        return headers

    def get_cookies_dict(self) -> Dict[str, str]:
        """Get session cookies as dictionary.

        Returns:
            Dictionary of cookie name-value pairs
        """
        return self.cookies if self.cookies else {}

    def clear_session(self) -> None:
        """Clear current session and delete session file."""
        self.session_data = None
        self.cookies = None

        if self.session_file.exists():
            self.session_file.unlink()
            logger.info("OpenAthens session cleared")

    def get_session_info(self) -> Dict[str, Any]:
        """Get information about current session.

        Returns:
            Dictionary with session metadata
        """
        if not self.session_data:
            return {
                'authenticated': False,
                'message': 'No active session'
            }

        created_at = self.session_data.get('created_at')
        expires_at = created_at + timedelta(hours=self.session_timeout_hours) if created_at else None

        return {
            'authenticated': self.is_authenticated(),
            'institution_url': self.institution_url,
            'created_at': created_at.isoformat() if created_at else None,
            'expires_at': expires_at.isoformat() if expires_at else None,
            'cookie_count': len(self.cookies) if self.cookies else 0,
            'time_remaining_hours': (expires_at - datetime.now()).total_seconds() / 3600
                                   if expires_at and expires_at > datetime.now() else 0
        }


# Convenience function for quick setup
def create_openathens_auth(
    institution_url: str,
    auto_login: bool = False,
    **kwargs
) -> OpenAthensAuth:
    """Create OpenAthens authenticator and optionally login.

    Args:
        institution_url: Institution's OpenAthens URL
        auto_login: If True, perform login if not already authenticated
        **kwargs: Additional arguments for OpenAthensAuth

    Returns:
        OpenAthensAuth instance
    """
    auth = OpenAthensAuth(institution_url, **kwargs)

    if auto_login and not auth.is_authenticated():
        logger.info("No valid session found, initiating login...")
        auth.login_sync()

    return auth


# Example usage
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    # Example: Create authenticator and login
    auth = OpenAthensAuth(
        institution_url="https://myinstitution.openathens.net",
        headless=False  # Show browser for 2FA
    )

    if not auth.is_authenticated():
        print("Not authenticated, please login...")
        if auth.login_sync():
            print("Login successful!")
            print(f"Session info: {auth.get_session_info()}")
        else:
            print("Login failed")
    else:
        print("Already authenticated")
        print(f"Session info: {auth.get_session_info()}")

    # Example: Construct proxy URL
    original_url = "https://www.nature.com/articles/s41586-024-12345-6.pdf"
    proxy_url = auth.construct_proxy_url(original_url)
    print(f"\nProxy URL: {proxy_url}")
