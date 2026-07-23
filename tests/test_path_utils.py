"""Unit tests for bmlibrarian.utils.path_utils.

Focus: the shared archive-member safety guard (is_safe_archive_member),
which protects every tar/zip importer against path-traversal ("zip slip")
attacks. These tests are hermetic — no filesystem, network, or DB access.
"""

import pytest

from bmlibrarian.utils.path_utils import is_safe_archive_member


class TestIsSafeArchiveMember:
    """Path-traversal guard for tar/zip archive members."""

    @pytest.mark.parametrize(
        "member_name",
        [
            "PMC123456.pdf",
            "data/papers/PMC123456.pdf",
            "content/12345.nxml",
            "PMC..123456.pdf",          # '..' inside a filename, not a component
            "a.b/c.d/file.txt",
            "deeply/nested/but/safe/path.xml",
        ],
    )
    def test_safe_members_allowed(self, member_name: str) -> None:
        """Relative paths without traversal components are allowed."""
        assert is_safe_archive_member(member_name) is True

    @pytest.mark.parametrize(
        "member_name",
        [
            "/etc/passwd",                       # absolute (leading slash)
            "../../../etc/passwd",               # classic traversal
            "data/../../../etc/passwd",          # traversal after a safe prefix
            "..\\..\\..\\windows\\system32",     # Windows-style separators
            "foo/../../bar/../../etc/passwd",    # interleaved traversal
            "./../secret",                       # './' then traversal
            "..",                                # bare traversal component
            "C:\\Windows\\system32\\evil.dll",   # Windows drive-rooted (backslash)
            "C:/Windows/system32/evil.dll",      # Windows drive-rooted (forward slash)
        ],
    )
    def test_unsafe_members_blocked(self, member_name: str) -> None:
        """Absolute paths and '..' traversal components are rejected."""
        assert is_safe_archive_member(member_name) is False

    def test_backslash_traversal_blocked_on_posix(self) -> None:
        """Windows-style '..\\' traversal is caught even on POSIX hosts.

        Path() alone treats a backslash as an ordinary filename character on
        POSIX, so the guard normalizes separators before checking components.
        """
        assert is_safe_archive_member("..\\..\\secret") is False

    def test_rejection_is_logged(self, caplog: pytest.LogCaptureFixture) -> None:
        """Rejections emit a WARNING so batch imports leave an audit trail."""
        with caplog.at_level("WARNING"):
            assert is_safe_archive_member("../evil") is False
        assert any("traversal" in rec.message.lower() for rec in caplog.records)
