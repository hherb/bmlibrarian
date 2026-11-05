"""Tests for the non-modal toast notifications (gui/qt/widgets/toast.py)."""

from unittest.mock import patch

import pytest

try:
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget

    from bmlibrarian.gui.qt.widgets import toast as toast_module
    from bmlibrarian.gui.qt.widgets.toast import ToastLevel, active_toasts, show_toast
    HAS_QT = True
except ImportError:  # pragma: no cover - Qt missing
    HAS_QT = False

pytestmark = pytest.mark.skipif(not HAS_QT, reason="Qt not available")

# Window size for the tests (logical pixels; any size well above a toast)
WINDOW_WIDTH, WINDOW_HEIGHT = 900, 700
SHORT_TIMEOUT_MS = 20


@pytest.fixture
def window():
    """A shown top-level window with a nested child widget."""
    app = QApplication.instance() or QApplication([])
    win = QWidget()
    child = QLabel("content", win)
    QVBoxLayout(win).addWidget(child)
    win.resize(WINDOW_WIDTH, WINDOW_HEIGHT)
    win.show()
    app.processEvents()
    yield win, child
    win.deleteLater()
    app.processEvents()


def test_toast_overlays_the_child_widgets_window(window):
    """A toast shown from a nested widget sits inside its top-level window."""
    win, child = window
    toast = show_toast(child, "Saved", ToastLevel.SUCCESS)

    assert toast.parentWidget() is win
    assert active_toasts(child) == [toast]
    assert win.rect().contains(toast.geometry())
    assert toast.message == "Saved"


def test_message_is_plain_text(window):
    """Error text containing markup is shown literally, not as rich text."""
    win, _ = window
    toast = show_toast(win, "<b>bad</b> & <script>", ToastLevel.ERROR)

    assert toast.message_label.textFormat() == Qt.TextFormat.PlainText
    assert toast.message == "<b>bad</b> & <script>"


def test_toasts_stack_newest_lowest_and_close_gaps(window):
    """Several toasts stack upwards; dismissing one moves the others down."""
    win, _ = window
    first = show_toast(win, "first", ToastLevel.ERROR)
    second = show_toast(win, "second", ToastLevel.ERROR)

    assert second.geometry().top() > first.geometry().bottom()

    second_top = second.geometry().top()
    second.dismiss()
    QApplication.processEvents()

    assert active_toasts(win) == [first]
    assert first.geometry().top() >= second_top


def test_dismiss_button_removes_the_toast(window):
    """Clicking the dismiss button closes the toast."""
    win, _ = window
    toast = show_toast(win, "Workflow failed", ToastLevel.ERROR)

    QTest.mouseClick(toast.dismiss_button, Qt.MouseButton.LeftButton)
    QApplication.processEvents()

    assert active_toasts(win) == []


def test_info_times_out_but_error_stays(window):
    """Non-error toasts hide themselves; errors wait for the user."""
    win, _ = window
    timeouts = dict(toast_module.TOAST_TIMEOUT_MS)
    timeouts[ToastLevel.INFO] = SHORT_TIMEOUT_MS
    with patch.dict(toast_module.TOAST_TIMEOUT_MS, timeouts):
        error = show_toast(win, "error", ToastLevel.ERROR)
        show_toast(win, "info", ToastLevel.INFO)

    QTest.qWait(SHORT_TIMEOUT_MS * 10)

    assert active_toasts(win) == [error]


def test_toasts_follow_a_window_resize(window):
    """Toasts stay anchored to the bottom-right corner when the window resizes."""
    win, _ = window
    toast = show_toast(win, "info", ToastLevel.ERROR)
    gap_right = win.width() - toast.geometry().right()
    gap_bottom = win.height() - toast.geometry().bottom()

    win.resize(WINDOW_WIDTH // 2, WINDOW_HEIGHT // 2)
    QApplication.processEvents()

    assert win.rect().contains(toast.geometry())
    assert win.width() - toast.geometry().right() == gap_right
    assert win.height() - toast.geometry().bottom() == gap_bottom
