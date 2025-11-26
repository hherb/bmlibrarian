"""
Tests for OpenAthens configuration validation.

Tests the validate_openathens_url and validate_openathens_config functions
that were added to prevent runtime errors from invalid configuration.
"""

import pytest
from bmlibrarian.config import (
    validate_openathens_url,
    validate_openathens_config,
    ValidationResult,
)


class TestValidateOpenAthensUrl:
    """Tests for validate_openathens_url function."""

    def test_valid_https_url(self) -> None:
        """Test valid HTTPS URL passes validation."""
        result = validate_openathens_url("https://institution.openathens.net/login")
        assert result.valid is True
        assert len(result.errors) == 0

    def test_valid_https_url_with_path(self) -> None:
        """Test valid HTTPS URL with path passes validation."""
        result = validate_openathens_url("https://idp.university.edu/sso/saml2")
        assert result.valid is True
        assert len(result.errors) == 0

    def test_http_url_rejected(self) -> None:
        """Test HTTP URL is rejected with clear error."""
        result = validate_openathens_url("http://institution.openathens.net/login")
        assert result.valid is False
        assert len(result.errors) == 1
        assert "HTTPS" in result.errors[0]
        assert "HTTP" in result.errors[0]

    def test_empty_url_rejected(self) -> None:
        """Test empty URL is rejected."""
        result = validate_openathens_url("")
        assert result.valid is False
        assert "empty" in result.errors[0].lower()

    def test_whitespace_only_url_rejected(self) -> None:
        """Test whitespace-only URL is rejected."""
        result = validate_openathens_url("   ")
        assert result.valid is False
        assert "empty" in result.errors[0].lower()

    def test_url_without_scheme_rejected(self) -> None:
        """Test URL without scheme is rejected."""
        result = validate_openathens_url("institution.openathens.net/login")
        assert result.valid is False
        assert "scheme" in result.errors[0].lower() or "HTTPS" in result.errors[0]

    def test_ftp_url_rejected(self) -> None:
        """Test FTP URL is rejected."""
        result = validate_openathens_url("ftp://institution.openathens.net")
        assert result.valid is False
        assert "HTTPS" in result.errors[0]

    def test_url_without_hostname_rejected(self) -> None:
        """Test URL without hostname is rejected."""
        result = validate_openathens_url("https:///login")
        assert result.valid is False
        assert "hostname" in result.errors[0].lower()

    def test_overly_long_hostname_rejected(self) -> None:
        """Test URL with overly long hostname is rejected."""
        long_host = "a" * 300 + ".example.com"
        result = validate_openathens_url(f"https://{long_host}/login")
        assert result.valid is False
        assert "253" in result.errors[0] or "length" in result.errors[0].lower()

    def test_url_with_double_dots_warning(self) -> None:
        """Test URL with suspicious double dots generates warning."""
        result = validate_openathens_url("https://bad..example.com/login")
        # This is still technically a valid URL format, but suspicious
        assert len(result.warnings) > 0 or result.valid is False

    def test_none_url_rejected(self) -> None:
        """Test None URL is rejected."""
        # Note: type checker would catch this, but runtime should handle it
        result = validate_openathens_url(None)  # type: ignore
        assert result.valid is False


class TestPrivateIPValidation:
    """Tests for IPv4 and IPv6 private address validation in URL validation."""

    def test_ipv4_private_10_rejected(self) -> None:
        """Test IPv4 10.x.x.x private range is rejected."""
        from bmlibrarian.utils.url_validation import validate_openathens_url
        result = validate_openathens_url("https://10.0.0.1/login")
        is_valid, _, error = result
        assert is_valid is False
        assert "private" in error.lower() or "reserved" in error.lower()

    def test_ipv4_private_172_rejected(self) -> None:
        """Test IPv4 172.16-31.x.x private range is rejected."""
        from bmlibrarian.utils.url_validation import validate_openathens_url
        result = validate_openathens_url("https://172.16.0.1/login")
        is_valid, _, error = result
        assert is_valid is False
        assert "private" in error.lower() or "reserved" in error.lower()

    def test_ipv4_private_192_rejected(self) -> None:
        """Test IPv4 192.168.x.x private range is rejected."""
        from bmlibrarian.utils.url_validation import validate_openathens_url
        result = validate_openathens_url("https://192.168.1.1/login")
        is_valid, _, error = result
        assert is_valid is False
        assert "private" in error.lower() or "reserved" in error.lower()

    def test_ipv4_loopback_rejected(self) -> None:
        """Test IPv4 127.x.x.x loopback range is rejected."""
        from bmlibrarian.utils.url_validation import validate_openathens_url
        result = validate_openathens_url("https://127.0.0.1/login")
        is_valid, _, error = result
        assert is_valid is False
        assert "private" in error.lower() or "reserved" in error.lower() or "loopback" in error.lower()

    def test_ipv6_loopback_rejected(self) -> None:
        """Test IPv6 ::1 loopback is rejected."""
        from bmlibrarian.utils.url_validation import validate_openathens_url
        result = validate_openathens_url("https://[::1]/login")
        is_valid, _, error = result
        assert is_valid is False
        assert "private" in error.lower() or "reserved" in error.lower()

    def test_ipv6_unique_local_rejected(self) -> None:
        """Test IPv6 fc00::/7 unique local addresses are rejected."""
        from bmlibrarian.utils.url_validation import validate_openathens_url
        # fc00::/7 includes fc00:: through fdff::
        result = validate_openathens_url("https://[fd00::1]/login")
        is_valid, _, error = result
        assert is_valid is False
        assert "private" in error.lower() or "reserved" in error.lower()

    def test_ipv6_link_local_rejected(self) -> None:
        """Test IPv6 fe80::/10 link-local addresses are rejected."""
        from bmlibrarian.utils.url_validation import validate_openathens_url
        result = validate_openathens_url("https://[fe80::1]/login")
        is_valid, _, error = result
        assert is_valid is False
        assert "private" in error.lower() or "reserved" in error.lower()

    def test_public_ipv4_accepted(self) -> None:
        """Test public IPv4 addresses are accepted."""
        from bmlibrarian.utils.url_validation import validate_openathens_url
        result = validate_openathens_url("https://8.8.8.8/login")
        is_valid, _, _ = result
        assert is_valid is True

    def test_public_ipv6_accepted(self) -> None:
        """Test public IPv6 addresses are accepted."""
        from bmlibrarian.utils.url_validation import validate_openathens_url
        # Google Public DNS IPv6
        result = validate_openathens_url("https://[2001:4860:4860::8888]/login")
        is_valid, _, _ = result
        assert is_valid is True

    def test_is_private_ip_address_helper(self) -> None:
        """Test the is_private_ip_address helper function directly."""
        from bmlibrarian.utils.url_validation import is_private_ip_address

        # IPv4 private ranges
        assert is_private_ip_address("10.0.0.1") is True
        assert is_private_ip_address("172.16.0.1") is True
        assert is_private_ip_address("192.168.1.1") is True
        assert is_private_ip_address("127.0.0.1") is True

        # IPv6 private/reserved ranges
        assert is_private_ip_address("::1") is True
        assert is_private_ip_address("fd00::1") is True
        assert is_private_ip_address("fe80::1") is True

        # Public addresses
        assert is_private_ip_address("8.8.8.8") is False
        assert is_private_ip_address("2001:4860:4860::8888") is False

        # Not an IP address (hostname)
        assert is_private_ip_address("example.com") is False


class TestValidateOpenAthensConfig:
    """Tests for validate_openathens_config function."""

    def test_disabled_config_always_valid(self) -> None:
        """Test that disabled config is always valid, even with invalid URL."""
        config = {
            "enabled": False,
            "institution_url": "",  # Invalid if enabled
        }
        result = validate_openathens_config(config)
        assert result.valid is True

    def test_enabled_with_valid_url(self) -> None:
        """Test enabled config with valid URL passes validation."""
        config = {
            "enabled": True,
            "institution_url": "https://institution.openathens.net",
            "session_timeout_hours": 24,
            "login_timeout": 300,
        }
        result = validate_openathens_config(config)
        assert result.valid is True
        assert len(result.errors) == 0

    def test_enabled_with_invalid_url(self) -> None:
        """Test enabled config with invalid URL fails validation."""
        config = {
            "enabled": True,
            "institution_url": "http://insecure.example.com",  # HTTP not allowed
        }
        result = validate_openathens_config(config)
        assert result.valid is False
        assert len(result.errors) > 0
        assert "HTTPS" in result.errors[0]

    def test_enabled_with_empty_url(self) -> None:
        """Test enabled config with empty URL fails validation."""
        config = {
            "enabled": True,
            "institution_url": "",
        }
        result = validate_openathens_config(config)
        assert result.valid is False
        assert "empty" in result.errors[0].lower()

    def test_negative_session_timeout_rejected(self) -> None:
        """Test negative session_timeout_hours is rejected."""
        config = {
            "enabled": True,
            "institution_url": "https://valid.example.com",
            "session_timeout_hours": -1,
        }
        result = validate_openathens_config(config)
        assert result.valid is False
        assert any("session_timeout_hours" in e for e in result.errors)

    def test_zero_session_timeout_rejected(self) -> None:
        """Test zero session_timeout_hours is rejected."""
        config = {
            "enabled": True,
            "institution_url": "https://valid.example.com",
            "session_timeout_hours": 0,
        }
        result = validate_openathens_config(config)
        assert result.valid is False
        assert any("session_timeout_hours" in e for e in result.errors)

    def test_negative_login_timeout_rejected(self) -> None:
        """Test negative login_timeout is rejected."""
        config = {
            "enabled": True,
            "institution_url": "https://valid.example.com",
            "login_timeout": -10,
        }
        result = validate_openathens_config(config)
        assert result.valid is False
        assert any("login_timeout" in e for e in result.errors)

    def test_invalid_timeout_type_rejected(self) -> None:
        """Test non-numeric timeout is rejected."""
        config = {
            "enabled": True,
            "institution_url": "https://valid.example.com",
            "session_timeout_hours": "24",  # String instead of int
        }
        result = validate_openathens_config(config)
        assert result.valid is False
        assert any("number" in e.lower() for e in result.errors)


class TestValidationResultHelper:
    """Tests for ValidationResult helper methods."""

    def test_raise_if_invalid_raises(self) -> None:
        """Test raise_if_invalid raises ValueError for invalid results."""
        result = ValidationResult(
            valid=False,
            errors=["Error 1", "Error 2"],
        )
        with pytest.raises(ValueError) as exc_info:
            result.raise_if_invalid()

        assert "Error 1" in str(exc_info.value)
        assert "Error 2" in str(exc_info.value)

    def test_raise_if_invalid_silent_for_valid(self) -> None:
        """Test raise_if_invalid does nothing for valid results."""
        result = ValidationResult(valid=True, errors=[])
        # Should not raise
        result.raise_if_invalid()

    def test_validation_result_bool(self) -> None:
        """Test ValidationResult can be used in boolean context."""
        valid_result = ValidationResult(valid=True, errors=[])
        invalid_result = ValidationResult(valid=False, errors=["Error"])

        assert valid_result  # Should be truthy
        assert not invalid_result  # Should be falsy


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
