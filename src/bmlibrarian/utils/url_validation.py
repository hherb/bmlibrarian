"""URL Validation Utilities.

Provides secure URL validation functions to prevent SSRF attacks
and ensure proper URL format for institutional access.
"""

import logging
from urllib.parse import urlparse
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


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
    if hostname in ('localhost', '127.0.0.1', '::1', '0.0.0.0'):
        return False, None, f"Institution URL cannot use localhost/loopback addresses: {hostname}"

    # Check for private network addresses (potential SSRF vector)
    if hostname.startswith('10.') or hostname.startswith('192.168.'):
        return False, None, f"Institution URL cannot use private network addresses: {hostname}"
    if hostname.startswith('172.'):
        # Check 172.16.0.0/12 range
        try:
            second_octet = int(hostname.split('.')[1])
            if 16 <= second_octet <= 31:
                return False, None, f"Institution URL cannot use private network addresses: {hostname}"
        except (IndexError, ValueError):
            pass  # Not a valid private IP format, allow it

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
