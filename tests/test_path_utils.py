"""Unit tests for bmlibrarian.utils.path_utils.

Focus: the shared archive-member safety guard (is_safe_archive_member),
which protects every tar/zip importer against path-traversal ("zip slip")
attacks. These tests are hermetic — no filesystem, network, or DB access.
"""

import os
import stat
from unittest.mock import patch

import pytest

from bmlibrarian.utils.path_utils import is_safe_archive_member, write_private_text


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


def _mode(path) -> int:
    """Return the permission bits of ``path``."""
    return stat.S_IMODE(os.stat(path).st_mode)


@pytest.mark.skipif(os.name == "nt", reason="POSIX permission bits")
class TestWritePrivateText:
    """write_private_text never leaves a secret readable by others (#450)."""

    def test_new_file_is_0600_even_with_open_umask(self, tmp_path) -> None:
        """A new file is created 0600, whatever the umask."""
        target = tmp_path / "token"
        old = os.umask(0)
        try:
            write_private_text(target, "secret")
        finally:
            os.umask(old)
        assert target.read_text() == "secret"
        assert _mode(target) == 0o600

    def test_existing_readable_file_is_narrowed_and_replaced(self, tmp_path) -> None:
        """A pre-existing 0644 file is narrowed to 0600 and its content replaced."""
        target = tmp_path / ".env"
        target.write_text("old content that is longer")
        target.chmod(0o644)
        write_private_text(target, "new")
        assert target.read_text() == "new"
        assert _mode(target) == 0o600

    def test_append_keeps_content(self, tmp_path) -> None:
        """append=True adds to the end and still narrows the mode."""
        target = tmp_path / ".env"
        target.write_text("A=1\n")
        target.chmod(0o644)
        write_private_text(target, "B=2\n", append=True)
        assert target.read_text() == "A=1\nB=2\n"
        assert _mode(target) == 0o600

    def test_failed_chmod_raises_before_writing(self, tmp_path) -> None:
        """If the mode cannot be narrowed, nothing is written and OSError propagates."""
        target = tmp_path / ".env"
        target.write_text("old")
        target.chmod(0o644)
        with patch("bmlibrarian.utils.path_utils.os.fchmod", side_effect=OSError("exFAT")):
            with pytest.raises(OSError):
                write_private_text(target, "secret")
        assert target.read_text() == "old"
