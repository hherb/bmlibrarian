"""URL Validation Utilities.

Provides secure URL validation functions to prevent SSRF attacks
and ensure proper URL format for institutional access.
"""

import ipaddress
import logging
from urllib.parse import urlparse
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


def is_private_ip_address(hostname: str) -> bool:
    """Check if a hostname resolves to a private or reserved IP address.

    Handles both IPv4 and IPv6 addresses using Python's ipaddress module.
    This includes:
    - IPv4 private ranges: 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16
    - IPv4 loopback: 127.0.0.0/8
    - IPv4 link-local: 169.254.0.0/16
    - IPv6 private (Unique Local Address): fc00::/7
    - IPv6 link-local: fe80::/10
    - IPv6 loopback: ::1

    Args:
        hostname: The hostname or IP address string to check

    Returns:
        True if the hostname is a private/reserved IP address, False otherwise
        (including for regular hostnames that aren't IP addresses)
    """
    try:
        # Try to parse as IP address
        ip = ipaddress.ip_address(hostname)
        # Check for private, loopback, link-local, or reserved addresses
        return (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
        )
    except ValueError:
        # Not a valid IP address (e.g., it's a hostname like "example.com")
        return False


def validate_openathens_url(url: Optional[str]) -> Tuple[bool, Optional[str], Optional[str]]:
    """Validate an OpenAthens institution URL for security.

    Performs security checks to prevent SSRF attacks:
    - Requires HTTPS protocol
    - Requires valid hostname
    - Rejects empty/malformed URLs

    Args:
        url: The URL to validate

    Returns:
        Tuple of (is_valid, normalized_url, error_message)
        - is_valid: True if URL is valid and safe to use
        - normalized_url: The validated URL (trailing slash removed), or None if invalid
        - error_message: Description of the validation error, or None if valid

    Example:
        >>> is_valid, url, error = validate_openathens_url("https://myinst.openathens.net")
        >>> if is_valid:
        ...     # Safe to use url
        ...     pass
    """
    if not url:
        return False, None, "Institution URL cannot be empty"

    if not isinstance(url, str):
        return False, None, f"Institution URL must be a string, got {type(url).__name__}"

    url = url.strip()
    if not url:
        return False, None, "Institution URL cannot be empty or whitespace only"

    try:
        parsed = urlparse(url)
    except Exception as e:
        logger.warning(f"Failed to parse URL '{url}': {e}")
        return False, None, f"Invalid URL format: {url}"

    # Security: Require HTTPS to prevent MITM attacks and credential leakage
    if parsed.scheme != 'https':
        return False, None, f"Institution URL must use HTTPS for security (got: {parsed.scheme or 'no scheme'})"

    # Require a valid hostname
    if not parsed.netloc:
        return False, None, f"Invalid URL format - missing hostname: {url}"

    # Check for localhost/loopback (potential SSRF vector)
    hostname = parsed.hostname.lower() if parsed.hostname else ""
    if hostname in ('localhost', '0.0.0.0'):
        return False, None, f"Institution URL cannot use localhost/loopback addresses: {hostname}"

    # Check for private/reserved network addresses (potential SSRF vector)
    # Uses ipaddress module for comprehensive IPv4 and IPv6 validation:
    # - IPv4: 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16, 127.0.0.0/8, 169.254.0.0/16
    # - IPv6: fc00::/7 (unique local), fe80::/10 (link-local), ::1 (loopback)
    if is_private_ip_address(hostname):
        return False, None, f"Institution URL cannot use private/reserved network addresses: {hostname}"

    # Normalize URL by removing trailing slash
    normalized_url = url.rstrip('/')

    logger.debug(f"Validated OpenAthens URL: {normalized_url}")
    return True, normalized_url, None


def validate_url_https(url: Optional[str], purpose: str = "URL") -> Tuple[bool, Optional[str], Optional[str]]:
    """Validate a URL requires HTTPS.

    General-purpose HTTPS URL validator for security-sensitive URLs.

    Args:
        url: The URL to validate
        purpose: Description of the URL's purpose for error messages

    Returns:
        Tuple of (is_valid, normalized_url, error_message)
    """
    if not url:
        return False, None, f"{purpose} cannot be empty"

    if not isinstance(url, str):
        return False, None, f"{purpose} must be a string, got {type(url).__name__}"

    url = url.strip()
    if not url:
        return False, None, f"{purpose} cannot be empty or whitespace only"

    try:
        parsed = urlparse(url)
    except Exception as e:
        logger.warning(f"Failed to parse {purpose} '{url}': {e}")
        return False, None, f"Invalid {purpose} format: {url}"

    if parsed.scheme != 'https':
        return False, None, f"{purpose} must use HTTPS for security (got: {parsed.scheme or 'no scheme'})"

    if not parsed.netloc:
        return False, None, f"Invalid {purpose} format - missing hostname: {url}"

    normalized_url = url.rstrip('/')
    return True, normalized_url, None


def get_validated_openathens_url(config: dict) -> Optional[str]:
    """Get validated OpenAthens URL from configuration dictionary.

    Convenience function for extracting and validating the OpenAthens
    institution URL from a configuration dictionary.

    Args:
        config: Configuration dictionary, expected to have 'openathens' key
                with 'enabled' and 'institution_url' subkeys

    Returns:
        Validated institution URL if enabled and valid, None otherwise

    Example:
        >>> config = {"openathens": {"enabled": True, "institution_url": "https://..."}}
        >>> url = get_validated_openathens_url(config)
    """
    openathens_config = config.get('openathens', {})

    if not openathens_config.get('enabled', False):
        logger.debug("OpenAthens is disabled in configuration")
        return None

    institution_url = openathens_config.get('institution_url')

    is_valid, normalized_url, error = validate_openathens_url(institution_url)

    if not is_valid:
        logger.warning(f"Invalid OpenAthens configuration: {error}")
        return None

    return normalized_url
