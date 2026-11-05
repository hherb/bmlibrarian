"""
Non-modal, dismissable toast notifications.

A toast is a small frame overlaid at the bottom right of a window. Unlike a
``QMessageBox`` it does not block the user (or a test run waiting inside Qt's
event loop). Info, success and warning toasts hide themselves after a while;
error toasts stay until the user dismisses them, so an error is not missed
while the user is away.

Usage:
    from bmlibrarian.gui.qt.widgets.toast import ToastLevel, show_toast

    show_toast(self, "Report saved", ToastLevel.SUCCESS)
"""

from enum import Enum
from typing import Dict, List, Optional, Tuple

from PySide6.QtCore import QEvent, QObject, Qt, QTimer
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QToolButton, QWidget

from ..resources.styles import StylesheetGenerator, ThemeColors, get_font_scale


class ToastLevel(str, Enum):
    """Severity of a toast; selects its accent color and lifetime."""

    INFO = "info"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"


# Object name scoping the toast stylesheet (and identifying toasts in tests)
TOAST_OBJECT_NAME = "bmlToast"

# Milliseconds before a toast hides itself; None = until dismissed
TOAST_TIMEOUT_MS: Dict[ToastLevel, Optional[int]] = {
    ToastLevel.INFO: 5000,
    ToastLevel.SUCCESS: 5000,
    ToastLevel.WARNING: 10000,
    ToastLevel.ERROR: None,
}

# (background, accent border) per level
_LEVEL_COLORS: Dict[ToastLevel, Tuple[str, str]] = {
    ToastLevel.INFO: (ThemeColors.PRIMARY_BG, ThemeColors.PRIMARY_BORDER),
    ToastLevel.SUCCESS: (ThemeColors.SUCCESS_BG, ThemeColors.SUCCESS_BORDER),
    ToastLevel.WARNING: (ThemeColors.WARNING_BG, ThemeColors.WARNING_BORDER),
    ToastLevel.ERROR: (ThemeColors.ERROR_BG, ThemeColors.ERROR_BORDER),
}

DISMISS_TEXT = "×"  # multiplication sign, the usual "close" glyph

# Longest message shown in a toast; the full text goes in its tooltip (and
# callers log it), so a huge provider/SQL error cannot outgrow the window
TOAST_MAX_MESSAGE_CHARS = 500
ELLIPSIS = "…"


def error_text(error: BaseException) -> str:
    """
    Describe an exception for a user-facing message.

    ``str(error)`` is empty for e.g. ``TimeoutError()`` and bare for
    ``KeyError('score')``, so the exception type is always included.

    Args:
        error: The exception to describe

    Returns:
        ``"TypeName: message"``, or just ``"TypeName"`` when the message is empty
    """
    message = str(error).strip()
    name = type(error).__name__
    return f"{name}: {message}" if message else name


def truncate_message(message: str, limit: int = TOAST_MAX_MESSAGE_CHARS) -> str:
    """
    Shorten a message to at most ``limit`` characters, ending in an ellipsis.

    Args:
        message: Text to shorten
        limit: Maximum length of the result (at least 1)

    Returns:
        ``message`` unchanged if it fits, else its start plus an ellipsis
    """
    if len(message) <= limit:
        return message
    return message[:max(0, limit - len(ELLIPSIS))] + ELLIPSIS


class Toast(QFrame):
    """A single dismissable notification overlaid on a host window."""

    def __init__(self, host: QWidget, message: str, level: ToastLevel) -> None:
        """
        Create a toast (hidden; use ``show_toast`` to display one).

        Args:
            host: Widget whose top-level window the toast is overlaid on
            message: Plain-text message (never interpreted as rich text);
                long messages are truncated, the full text is the tooltip
            level: Severity, selects color and lifetime

        Raises:
            ValueError: If ``level`` is not a ToastLevel value
        """
        level = ToastLevel(level)
        host = host.window()
        super().__init__(host)
        self._level = level
        self._message = message
        self.setObjectName(TOAST_OBJECT_NAME)
        bg_color, border_color = _LEVEL_COLORS[level]
        self.setStyleSheet(StylesheetGenerator().toast_stylesheet(
            TOAST_OBJECT_NAME, bg_color, border_color, ThemeColors.TEXT_PRIMARY,
        ))
        self.setAccessibleName(f"{level.value} notification")

        scale = get_font_scale()
        layout = QHBoxLayout(self)
        pad = scale['padding_medium']
        layout.setContentsMargins(pad, pad, pad, pad)
        layout.setSpacing(scale['spacing_medium'])

        self.message_label = QLabel(truncate_message(message))
        self.message_label.setTextFormat(Qt.TextFormat.PlainText)
        if self.message_label.text() != message:
            self.message_label.setToolTip(message)
        self.message_label.setWordWrap(True)
        # Let the user copy an error message (e.g. into a bug report)
        self.message_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        layout.addWidget(self.message_label, 1)

        self.dismiss_button = QToolButton()
        self.dismiss_button.setText(DISMISS_TEXT)
        self.dismiss_button.setAccessibleName("Dismiss notification")
        self.dismiss_button.setToolTip("Dismiss")
        self.dismiss_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.dismiss_button.clicked.connect(self.dismiss)
        layout.addWidget(self.dismiss_button, 0, Qt.AlignmentFlag.AlignTop)

        host.installEventFilter(self)
        timeout = TOAST_TIMEOUT_MS[level]
        if timeout is not None:
            QTimer.singleShot(timeout, self, self.dismiss)

    @property
    def level(self) -> ToastLevel:
        """The toast's severity (fixed at construction)."""
        return self._level

    @property
    def message(self) -> str:
        """The toast's full message text (the label may show it truncated)."""
        return self._message

    def dismiss(self) -> None:
        """Hide and delete the toast; the remaining toasts close the gap."""
        host = self.parentWidget()
        self._discard()
        if host is not None:
            _layout_toasts(host)

    def _discard(self) -> None:
        """Hide and delete the toast without re-laying out the others."""
        host = self.parentWidget()
        self.hide()
        self.deleteLater()
        if host is not None:
            host.removeEventFilter(self)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        """Re-place the host's toasts when the host is resized."""
        if event.type() == QEvent.Type.Resize and isinstance(watched, QWidget):
            _layout_toasts(watched)
        return False


def active_toasts(host: QWidget) -> List[Toast]:
    """
    Toasts currently shown on a window, oldest first.

    Args:
        host: Any widget; its top-level window is searched

    Returns:
        Toasts that have not been dismissed
    """
    return [
        child for child in host.window().findChildren(
            Toast, options=Qt.FindChildOption.FindDirectChildrenOnly
        )
        if not child.isHidden()
    ]


def _layout_toasts(host: QWidget) -> None:
    """
    Stack the host's toasts upwards from its bottom-right corner, newest lowest.

    A toast is never taller than the window (its dismiss button, at the top,
    stays reachable), and older toasts that no longer fit above the newer
    ones are dropped: off-screen they could be neither read nor dismissed.
    """
    scale = get_font_scale()
    margin = scale['spacing_large']
    width = max(1, min(scale['control_width_xlarge'], host.width() - 2 * margin))
    max_height = max(1, host.height() - 2 * margin)
    bottom = host.height() - margin
    for index, toast in enumerate(reversed(active_toasts(host))):
        toast.setFixedWidth(width)
        height = toast.heightForWidth(width)
        if height <= 0:
            height = toast.sizeHint().height()
        height = min(height, max_height)
        if index > 0 and bottom - height < margin:
            toast._discard()
            continue
        toast.setFixedHeight(height)
        bottom -= height
        toast.move(host.width() - margin - width, bottom)
        bottom -= scale['spacing_small']


def show_toast(
    parent: QWidget,
    message: str,
    level: ToastLevel = ToastLevel.INFO,
) -> Toast:
    """
    Show a non-modal toast on ``parent``'s window and return at once.

    Args:
        parent: Any widget; the toast is overlaid on its top-level window
        message: Plain-text message
        level: Severity (errors stay until dismissed, others time out)

    Returns:
        The shown toast
    """
    toast = Toast(parent, message, level)
    toast.show()
    toast.raise_()
    _layout_toasts(toast.parentWidget())
    return toast
