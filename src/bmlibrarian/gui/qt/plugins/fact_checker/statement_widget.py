"""
Statement Widget for Fact-Checker Review.

Displays the statement and original/AI annotations.
"""

from typing import Optional
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QFrame,
)
from PySide6.QtCore import Qt


class StatementWidget(QWidget):
    """Widget for displaying statement and annotations."""

    def __init__(self, blind_mode: bool = False, parent: Optional[QWidget] = None):
        """
        Initialize statement widget.

        Args:
            blind_mode: If True, hide original and AI annotations
            parent: Optional parent widget
        """
        super().__init__(parent)

        self.blind_mode = blind_mode

        self._setup_ui()

    def _setup_ui(self):
        """Setup the user interface."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(15)

        # Progress section
        self.progress_label = QLabel("Statement 1 of 1")
        self.progress_label.setStyleSheet("font-weight: bold; color: #1976d2; font-size: 13px;")
        layout.addWidget(self.progress_label)

        # Statement section
        statement_title = QLabel("Statement to Review:")
        statement_title.setStyleSheet("font-weight: bold; color: #263238; font-size: 12px;")
        layout.addWidget(statement_title)

        self.statement_text = QLabel("No statement loaded")
        self.statement_text.setWordWrap(True)
        self.statement_text.setStyleSheet(
            """
            QLabel {
                background-color: #f5f5f5;
                padding: 12px;
                border-radius: 6px;
                border: 1px solid #ddd;
                font-size: 14px;
                color: #263238;
            }
        """
        )
        self.statement_text.setMinimumHeight(60)
        layout.addWidget(self.statement_text)

        # Annotations section (only if not blind mode)
        if not self.blind_mode:
            annotations_layout = QHBoxLayout()

            # Original answer
            original_widget = QWidget()
            original_layout = QVBoxLayout(original_widget)
            original_layout.setContentsMargins(10, 10, 10, 10)

            original_title = QLabel("Original Answer")
            original_title.setStyleSheet("font-weight: bold; color: #3949ab; font-size: 11px;")
            original_layout.addWidget(original_title)

            self.original_annotation = QLabel("N/A")
            self.original_annotation.setWordWrap(True)
            self.original_annotation.setStyleSheet("color: #263238;")
            original_layout.addWidget(self.original_annotation)

            original_widget.setStyleSheet(
                """
                QWidget {
                    background-color: #e8eaf6;
                    border: 1px solid: #c5cae9;
                    border-radius: 6px;
                }
            """
            )
            annotations_layout.addWidget(original_widget)

            # AI evaluation
            ai_widget = QWidget()
            ai_layout = QVBoxLayout(ai_widget)
            ai_layout.setContentsMargins(10, 10, 10, 10)

            ai_title = QLabel("AI Evaluation")
            ai_title.setStyleSheet("font-weight: bold; color: #5e35b1; font-size: 11px;")
            ai_layout.addWidget(ai_title)

            self.ai_annotation = QLabel("N/A")
            self.ai_annotation.setWordWrap(True)
            self.ai_annotation.setStyleSheet("color: #263238;")
            ai_layout.addWidget(self.ai_annotation)

            ai_widget.setStyleSheet(
                """
                QWidget {
                    background-color: #ede7f6;
                    border: 1px solid #d1c4e9;
                    border-radius: 6px;
                }
            """
            )
            annotations_layout.addWidget(ai_widget)

            layout.addLayout(annotations_layout)

            # AI rationale
            rationale_title = QLabel("AI Rationale:")
            rationale_title.setStyleSheet("font-weight: bold; color: #5e35b1; font-size: 11px;")
            layout.addWidget(rationale_title)

            self.ai_rationale = QLabel("No rationale provided")
            self.ai_rationale.setWordWrap(True)
            self.ai_rationale.setStyleSheet(
                """
                QLabel {
                    background-color: #f3e5f5;
                    padding: 10px;
                    border-radius: 6px;
                    border: 1px solid #e1bee7;
                    font-size: 12px;
                    color: #4a148c;
                }
            """
            )
            layout.addWidget(self.ai_rationale)

        # Style the widget
        self.setStyleSheet(
            """
            StatementWidget {
                background-color: white;
                border: 1px solid #ccc;
                border-radius: 8px;
            }
        """
        )

    def update_progress(self, current: int, total: int):
        """
        Update progress display.

        Args:
            current: Current statement index (0-based)
            total: Total number of statements
        """
        self.progress_label.setText(f"Statement {current + 1} of {total}")

    def update_statement(self, statement: str):
        """
        Update statement text.

        Args:
            statement: Statement text to display
        """
        self.statement_text.setText(statement)

    def update_annotations(self, original: str, ai_evaluation: str, ai_rationale: str):
        """
        Update annotations display.

        Args:
            original: Original expected answer
            ai_evaluation: AI evaluation
            ai_rationale: AI rationale/explanation
        """
        if not self.blind_mode:
            self.original_annotation.setText(original if original else "N/A")
            self.ai_annotation.setText(ai_evaluation if ai_evaluation else "N/A")
            self.ai_rationale.setText(ai_rationale if ai_rationale else "No rationale provided")
