"""
Timer component for Fact Checker Review GUI.

Tracks time spent reviewing each statement with pause/resume functionality.
"""

import time
from typing import Optional, Callable
import flet as ft

from .styles import (
    Colors, ContainerStyles, TextStyles, LayoutConfig, DPIScale
)


class ReviewTimer:
    """Timer component for tracking review time."""

    def __init__(self, on_timer_update: Optional[Callable] = None):
        """
        Initialize review timer.

        Args:
            on_timer_update: Optional callback when timer updates (receives elapsed_seconds)
        """
        self.on_timer_update = on_timer_update

        # Timer state
        self._start_time: Optional[float] = None
        self._pause_time: Optional[float] = None
        self._elapsed_seconds: int = 0  # Cumulative time across sessions
        self._current_session_start: Optional[float] = None
        self._is_running: bool = False
        self._is_paused: bool = False

        # UI components
        timer_style = TextStyles.timer_display()
        self.timer_display = ft.Text(
            "00:00",
            **timer_style
        )

        self.pause_button = ft.IconButton(
            icon=ft.Icons.PAUSE,
            icon_color=Colors.PRIMARY_BLUE_LIGHT,
            icon_size=DPIScale.font_size(DPIScale.FONT_SIZE_LARGE),
            tooltip="Pause timer",
            on_click=self._on_pause_click
        )

        status_style = TextStyles.label_small()
        self.status_text = ft.Text(
            "Timer ready",
            size=status_style['size'],
            color=Colors.GREY_LIGHT,
            italic=True
        )

    def _format_time(self, seconds: int) -> str:
        """Format seconds as MM:SS."""
        mins = seconds // 60
        secs = seconds % 60
        return f"{mins:02d}:{secs:02d}"

    def _get_current_elapsed(self) -> int:
        """Get current elapsed time including any running session."""
        if not self._is_running:
            return self._elapsed_seconds

        if self._is_paused:
            # Paused - return time up to pause
            return self._elapsed_seconds

        # Running - add current session time
        current_session = int(time.time() - self._current_session_start)
        return self._elapsed_seconds + current_session

    def _update_display(self):
        """Update timer display."""
        elapsed = self._get_current_elapsed()
        self.timer_display.value = self._format_time(elapsed)

        if self._is_paused:
            self.status_text.value = "⏸ Paused"
            self.status_text.color = Colors.WARNING
        elif self._is_running:
            self.status_text.value = "⏱ Recording..."
            self.status_text.color = Colors.SUCCESS
        else:
            self.status_text.value = "Timer stopped"
            self.status_text.color = Colors.GREY_LIGHT

    def start(self, previous_seconds: int = 0):
        """
        Start or restart the timer.

        Args:
            previous_seconds: Previously accumulated time for this statement
        """
        self._elapsed_seconds = previous_seconds
        self._current_session_start = time.time()
        self._is_running = True
        self._is_paused = False
        self._pause_time = None

        self._update_display()

    def pause(self):
        """Pause the timer."""
        if not self._is_running or self._is_paused:
            return

        # Save elapsed time up to now
        current_session = int(time.time() - self._current_session_start)
        self._elapsed_seconds += current_session

        self._is_paused = True
        self._pause_time = time.time()
        self._update_display()

    def resume(self):
        """Resume the timer from pause."""
        if not self._is_paused:
            return

        # Start a new session from now
        self._current_session_start = time.time()
        self._is_paused = False
        self._pause_time = None
        self._update_display()

    def stop(self) -> int:
        """
        Stop the timer and return total elapsed seconds.

        Returns:
            Total elapsed seconds
        """
        if self._is_running and not self._is_paused:
            # Save current session time
            current_session = int(time.time() - self._current_session_start)
            self._elapsed_seconds += current_session

        self._is_running = False
        self._is_paused = False
        self._current_session_start = None
        self._pause_time = None

        self._update_display()
        return self._elapsed_seconds

    def reset(self):
        """Reset the timer to zero."""
        self._elapsed_seconds = 0
        self._current_session_start = None
        self._is_running = False
        self._is_paused = False
        self._pause_time = None

        self._update_display()

    def get_elapsed_seconds(self) -> int:
        """Get current elapsed seconds."""
        return self._get_current_elapsed()

    def is_running(self) -> bool:
        """Check if timer is running (not paused)."""
        return self._is_running and not self._is_paused

    def is_paused(self) -> bool:
        """Check if timer is paused."""
        return self._is_paused

    def _on_pause_click(self, e):
        """Handle pause/resume button click."""
        if self._is_paused:
            self.resume()
            self.pause_button.icon = ft.Icons.PAUSE
            self.pause_button.tooltip = "Pause timer"
        else:
            self.pause()
            self.pause_button.icon = ft.Icons.PLAY_ARROW
            self.pause_button.tooltip = "Resume timer"

        if hasattr(self.pause_button, 'update'):
            self.pause_button.update()

    def build_section(self) -> ft.Container:
        """Build timer UI section."""
        label_style = TextStyles.label_small()
        timer_style = ContainerStyles.timer_container()

        return ft.Container(
            content=ft.Column([
                ft.Row([
                    ft.Icon(ft.Icons.TIMER, size=DPIScale.font_size(DPIScale.FONT_SIZE_LARGE), color=Colors.PRIMARY_BLUE_LIGHT),
                    ft.Text("Review Time", **label_style, color=Colors.PRIMARY_BLUE_LIGHT),
                ], spacing=LayoutConfig.SPACING_TINY),
                ft.Row([
                    self.timer_display,
                    self.pause_button
                ], spacing=LayoutConfig.SPACING_SMALL, alignment=ft.MainAxisAlignment.CENTER),
                self.status_text
            ], spacing=LayoutConfig.SPACING_TINY, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
            **timer_style
        )
