"""Tests for the non-modal toast notifications (gui/qt/widgets/toast.py)."""

from typing import Callable
from unittest.mock import patch

import pytest

try:
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget

    from bmlibrarian.gui.qt.widgets import toast as toast_module
    from bmlibrarian.gui.qt.widgets.toast import (
        TOAST_MAX_MESSAGE_CHARS,
        Toast,
        ToastLevel,
        active_toasts,
        error_text,
        show_toast,
        truncate_message,
    )
    HAS_QT = True
except ImportError:  # pragma: no cover - Qt missing
    HAS_QT = False

pytestmark = pytest.mark.skipif(not HAS_QT, reason="Qt not available")

# Window size for the tests (logical pixels; any size well above a toast)
WINDOW_WIDTH, WINDOW_HEIGHT = 900, 700
SHORT_TIMEOUT_MS = 20
# Upper bound for a short timer to fire on a loaded machine (a fixed wait flaked in the full suite)
TIMER_DEADLINE_MS = 5000


def wait_until(condition: Callable[[], bool], deadline_ms: int = TIMER_DEADLINE_MS) -> bool:
    """Process Qt events until ``condition()`` is true or ``deadline_ms`` passes; return the last result."""
    for _ in range(deadline_ms // SHORT_TIMEOUT_MS):
        if condition():
            return True
        QTest.qWait(SHORT_TIMEOUT_MS)
    return condition()


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


@pytest.mark.parametrize("level", [ToastLevel.INFO, ToastLevel.SUCCESS, ToastLevel.WARNING])
def test_non_error_levels_time_out_but_error_stays(window, level):
    """Non-error toasts hide themselves; errors wait for the user."""
    win, _ = window
    assert toast_module.TOAST_TIMEOUT_MS[level] is not None
    assert toast_module.TOAST_TIMEOUT_MS[ToastLevel.ERROR] is None
    with patch.dict(toast_module.TOAST_TIMEOUT_MS, {level: SHORT_TIMEOUT_MS}):
        error = show_toast(win, "error", ToastLevel.ERROR)
        show_toast(win, "transient", level)

    assert wait_until(lambda: active_toasts(win) == [error]), active_toasts(win)


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


# A window much smaller than a stack of toasts
SMALL_WIDTH, SMALL_HEIGHT = 300, 200
# Far beyond TOAST_MAX_MESSAGE_CHARS, like a provider error echoing its body
HUGE_MESSAGE_CHARS = 5000


def _dismiss_button_inside(toast, win) -> bool:
    """Whether the toast's dismiss button lies inside the window."""
    top_left = toast.dismiss_button.mapTo(win, QPoint(0, 0))
    return win.rect().contains(top_left) and top_left.y() >= 0


def test_huge_error_stays_inside_the_window_and_dismissable(window):
    """A very long error is cut off; the toast and its × stay on screen."""
    win, _ = window
    win.resize(SMALL_WIDTH, SMALL_HEIGHT)
    QApplication.processEvents()
    message = "x " * (HUGE_MESSAGE_CHARS // 2)
    toast = show_toast(win, message, ToastLevel.ERROR)
    QApplication.processEvents()

    assert toast.geometry().top() >= 0
    assert toast.geometry().bottom() <= win.height()
    assert _dismiss_button_inside(toast, win)
    assert len(toast.message_label.text()) <= TOAST_MAX_MESSAGE_CHARS
    assert toast.message == message
    assert toast.message_label.toolTip() == message


def test_toasts_that_do_not_fit_are_dropped_oldest_first(window):
    """Old error toasts pushed off the top are dropped; every shown one fits."""
    win, _ = window
    win.resize(SMALL_WIDTH, SMALL_HEIGHT)
    QApplication.processEvents()
    toasts = [
        show_toast(win, f"error {i}\nline two\nline three", ToastLevel.ERROR)
        for i in range(6)
    ]
    QApplication.processEvents()

    shown = active_toasts(win)
    assert shown[-1] is toasts[-1]
    assert len(shown) < len(toasts)
    assert shown == toasts[-len(shown):]
    for toast in shown:
        assert toast.geometry().top() >= 0
        assert _dismiss_button_inside(toast, win)


def test_toast_built_on_a_child_is_hosted_on_its_window(window):
    """Constructing Toast directly on a nested widget still overlays the window."""
    win, child = window
    toast = Toast(child, "direct", ToastLevel.INFO)

    assert toast.parentWidget() is win


def test_level_is_validated_and_read_only(window):
    """A level string is converted to ToastLevel; an unknown one is rejected."""
    win, _ = window
    toast = Toast(win, "from a string", "error")
    assert toast.level is ToastLevel.ERROR
    with pytest.raises(AttributeError):
        toast.level = ToastLevel.INFO
    with pytest.raises(ValueError):
        Toast(win, "bad", "Error")


def test_pending_timer_after_host_deleted_does_not_crash():
    """Deleting the window before a toast times out cancels the timer."""
    app = QApplication.instance() or QApplication([])
    win = QWidget()
    win.resize(WINDOW_WIDTH, WINDOW_HEIGHT)
    win.show()
    with patch.dict(toast_module.TOAST_TIMEOUT_MS, {ToastLevel.INFO: SHORT_TIMEOUT_MS}):
        show_toast(win, "transient", ToastLevel.INFO)
    win.deleteLater()
    app.processEvents()

    QTest.qWait(SHORT_TIMEOUT_MS * 10)  # the timer would fire here


@pytest.mark.parametrize("error, expected", [
    (TimeoutError(), "TimeoutError"),
    (KeyError("score"), "KeyError: 'score'"),
    (RuntimeError("  model missing  "), "RuntimeError: model missing"),
])
def test_error_text_always_names_the_exception(error, expected):
    """Empty or bare exception messages still say what went wrong."""
    assert error_text(error) == expected


def test_truncate_message():
    """Short messages pass through; long ones are cut to the limit with an ellipsis."""
    assert truncate_message("short", 10) == "short"
    cut = truncate_message("a" * 20, 10)
    assert len(cut) == 10
    assert cut.endswith("…")
