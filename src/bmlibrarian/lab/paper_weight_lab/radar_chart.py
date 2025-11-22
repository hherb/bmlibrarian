"""
Radar Chart Widget for Paper Weight Assessment Visualization

A custom Qt widget that displays assessment dimension scores as a radar/spider chart.
This provides an intuitive visual representation of paper quality across multiple dimensions.
"""

import math
from typing import Dict, List, Optional

from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import (
    QPainter, QPen, QBrush, QColor, QFont, QFontMetrics,
    QPainterPath, QPolygonF, QRadialGradient
)

from bmlibrarian.gui.qt.resources.styles.dpi_scale import get_font_scale


# Chart configuration constants
CHART_PADDING_RATIO = 0.15  # Padding as ratio of widget size
LABEL_PADDING = 15  # Pixels between chart edge and labels
MAX_SCORE = 10.0  # Maximum possible score
GRID_LEVELS = 5  # Number of concentric grid circles
CHART_ROTATION_OFFSET = -90  # Rotate so first axis points up (degrees)


class RadarChartWidget(QWidget):
    """
    A radar/spider chart widget for visualizing multi-dimensional scores.

    Displays 5 dimensions of paper weight assessment:
    - Study Design
    - Sample Size
    - Methodological Quality
    - Risk of Bias
    - Replication Status

    The chart shows:
    - Concentric grid circles for score levels (0-10)
    - Axis lines from center to each dimension
    - Labels for each dimension
    - Filled polygon showing current scores
    - Score values at each axis point
    """

    def __init__(self, parent: Optional[QWidget] = None):
        """
        Initialize the radar chart widget.

        Args:
            parent: Parent widget
        """
        super().__init__(parent)

        self.scale = get_font_scale()

        # Dimension labels (formatted for display)
        self.dimension_labels: List[str] = [
            "Study Design",
            "Sample Size",
            "Methodology",
            "Bias Risk",
            "Replication"
        ]

        # Current scores (0-10 scale)
        self.scores: List[float] = [0.0] * len(self.dimension_labels)

        # Colors
        self.grid_color = QColor("#CCCCCC")
        self.axis_color = QColor("#999999")
        self.fill_color = QColor("#2196F3")  # Material Blue
        self.fill_color.setAlpha(100)
        self.stroke_color = QColor("#1976D2")  # Darker blue for stroke
        self.label_color = QColor("#333333")
        self.score_color = QColor("#1976D2")
        self.background_color = QColor("#FAFAFA")

        # Set minimum size
        min_size = self.scale['control_width_large']
        self.setMinimumSize(min_size, min_size)

    def set_scores(self, scores: Dict[str, float]) -> None:
        """
        Update the chart with new scores.

        Args:
            scores: Dictionary mapping dimension names to scores (0-10)
                   Keys should be: 'study_design', 'sample_size',
                   'methodological_quality', 'risk_of_bias', 'replication_status'
        """
        # Map internal dimension names to display order
        dimension_order = [
            'study_design',
            'sample_size',
            'methodological_quality',
            'risk_of_bias',
            'replication_status'
        ]

        self.scores = [
            min(MAX_SCORE, max(0.0, scores.get(dim, 0.0)))
            for dim in dimension_order
        ]

        self.update()  # Trigger repaint

    def clear_scores(self) -> None:
        """Reset all scores to zero."""
        self.scores = [0.0] * len(self.dimension_labels)
        self.update()

    def paintEvent(self, event) -> None:
        """Paint the radar chart."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Fill background
        painter.fillRect(self.rect(), self.background_color)

        # Calculate chart geometry
        width = self.width()
        height = self.height()
        center_x = width / 2
        center_y = height / 2

        # Calculate radius with padding for labels
        padding = min(width, height) * CHART_PADDING_RATIO
        label_space = self.scale['font_normal'] * 3  # Space for labels
        radius = (min(width, height) / 2) - padding - label_space

        if radius <= 0:
            return  # Widget too small

        num_axes = len(self.dimension_labels)
        angle_step = 360.0 / num_axes

        # Draw grid circles
        self._draw_grid_circles(painter, center_x, center_y, radius)

        # Draw axis lines
        self._draw_axes(painter, center_x, center_y, radius, num_axes, angle_step)

        # Draw score polygon
        self._draw_score_polygon(painter, center_x, center_y, radius, num_axes, angle_step)

        # Draw labels and score values
        self._draw_labels(painter, center_x, center_y, radius, num_axes, angle_step)

        painter.end()

    def _draw_grid_circles(
        self,
        painter: QPainter,
        cx: float,
        cy: float,
        radius: float
    ) -> None:
        """Draw concentric grid circles."""
        pen = QPen(self.grid_color, 1, Qt.DashLine)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)

        for i in range(1, GRID_LEVELS + 1):
            r = radius * (i / GRID_LEVELS)
            painter.drawEllipse(QPointF(cx, cy), r, r)

    def _draw_axes(
        self,
        painter: QPainter,
        cx: float,
        cy: float,
        radius: float,
        num_axes: int,
        angle_step: float
    ) -> None:
        """Draw axis lines from center to each dimension."""
        pen = QPen(self.axis_color, 1)
        painter.setPen(pen)

        for i in range(num_axes):
            angle_deg = CHART_ROTATION_OFFSET + (i * angle_step)
            angle_rad = math.radians(angle_deg)

            end_x = cx + radius * math.cos(angle_rad)
            end_y = cy + radius * math.sin(angle_rad)

            painter.drawLine(QPointF(cx, cy), QPointF(end_x, end_y))

    def _draw_score_polygon(
        self,
        painter: QPainter,
        cx: float,
        cy: float,
        radius: float,
        num_axes: int,
        angle_step: float
    ) -> None:
        """Draw the filled polygon representing scores."""
        if all(s == 0 for s in self.scores):
            return  # No scores to draw

        points = []
        for i, score in enumerate(self.scores):
            angle_deg = CHART_ROTATION_OFFSET + (i * angle_step)
            angle_rad = math.radians(angle_deg)

            # Calculate point position based on score
            score_ratio = score / MAX_SCORE
            point_radius = radius * score_ratio

            x = cx + point_radius * math.cos(angle_rad)
            y = cy + point_radius * math.sin(angle_rad)
            points.append(QPointF(x, y))

        # Create polygon
        polygon = QPolygonF(points)

        # Draw filled polygon with gradient
        gradient = QRadialGradient(cx, cy, radius)
        gradient.setColorAt(0, QColor(33, 150, 243, 150))  # Blue center
        gradient.setColorAt(1, QColor(33, 150, 243, 80))   # Lighter edge

        painter.setBrush(QBrush(gradient))
        painter.setPen(QPen(self.stroke_color, 2))
        painter.drawPolygon(polygon)

        # Draw points at each vertex
        painter.setBrush(QBrush(self.stroke_color))
        painter.setPen(Qt.NoPen)
        point_radius = 4
        for point in points:
            painter.drawEllipse(point, point_radius, point_radius)

    def _draw_labels(
        self,
        painter: QPainter,
        cx: float,
        cy: float,
        radius: float,
        num_axes: int,
        angle_step: float
    ) -> None:
        """Draw dimension labels and score values."""
        font = QFont()
        font.setPixelSize(self.scale['font_normal'])
        painter.setFont(font)

        font_metrics = QFontMetrics(font)
        label_offset = LABEL_PADDING

        for i, (label, score) in enumerate(zip(self.dimension_labels, self.scores)):
            angle_deg = CHART_ROTATION_OFFSET + (i * angle_step)
            angle_rad = math.radians(angle_deg)

            # Position for label (outside the chart)
            label_radius = radius + label_offset
            label_x = cx + label_radius * math.cos(angle_rad)
            label_y = cy + label_radius * math.sin(angle_rad)

            # Create display text
            score_text = f"{score:.1f}" if score > 0 else "--"
            display_text = f"{label}\n({score_text})"

            # Calculate text bounds
            lines = display_text.split('\n')
            max_width = max(font_metrics.horizontalAdvance(line) for line in lines)
            total_height = font_metrics.height() * len(lines)

            # Adjust position based on angle quadrant
            if angle_deg < -45 or angle_deg > 135:  # Top
                text_x = label_x - max_width / 2
                text_y = label_y - total_height
            elif angle_deg < 45:  # Right
                text_x = label_x + 5
                text_y = label_y - total_height / 2
            elif angle_deg < 135:  # Bottom
                text_x = label_x - max_width / 2
                text_y = label_y + 5
            else:  # Left
                text_x = label_x - max_width - 5
                text_y = label_y - total_height / 2

            # Draw label
            painter.setPen(self.label_color)
            for j, line in enumerate(lines):
                line_y = text_y + (j + 1) * font_metrics.height()
                if j == 1:  # Score line
                    painter.setPen(self.score_color)
                painter.drawText(QPointF(text_x, line_y), line)


__all__ = ['RadarChartWidget']
