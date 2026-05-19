"""
Minimal sparkline widget with antialiased curve and gradient fill.
"""
from __future__ import annotations

from collections import deque
from typing import Optional

from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import QColor, QPainter, QPainterPath, QLinearGradient, QPen
from PySide6.QtWidgets import QWidget


class Sparkline(QWidget):
    def __init__(self, capacity: int = 60, color: str = "#7FD7FF",
                 fill: bool = True, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._values: deque[float] = deque(maxlen=capacity)
        self._capacity = capacity
        self._color = QColor(color)
        self._fill = fill
        self._min_y: Optional[float] = None
        self._max_y: Optional[float] = None
        self.setMinimumHeight(28)

    def set_color(self, color: str | QColor) -> None:
        self._color = QColor(color) if isinstance(color, str) else color
        self.update()

    def set_range(self, lo: Optional[float], hi: Optional[float]) -> None:
        """Force a fixed Y range. Pass (None, None) for auto-range."""
        self._min_y, self._max_y = lo, hi
        self.update()

    def add(self, value: float) -> None:
        self._values.append(value)
        self.update()

    def clear(self) -> None:
        self._values.clear()
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        if len(self._values) < 2:
            return

        if self._min_y is not None and self._max_y is not None:
            mn, mx = self._min_y, self._max_y
        else:
            mn = min(self._values)
            mx = max(self._values)
        if mx - mn < 1e-6:
            mx = mn + 1.0

        n = len(self._values)
        step = w / max(1, self._capacity - 1)
        # Right-align the data so newest values are on the right edge
        offset = (self._capacity - n) * step

        path = QPainterPath()
        pts: list[QPointF] = []
        for i, v in enumerate(self._values):
            x = offset + i * step
            y = h - ((v - mn) / (mx - mn)) * (h - 4) - 2
            pts.append(QPointF(x, y))
        path.moveTo(pts[0])
        for pt in pts[1:]:
            path.lineTo(pt)

        if self._fill:
            fill_path = QPainterPath(path)
            fill_path.lineTo(pts[-1].x(), h)
            fill_path.lineTo(pts[0].x(), h)
            fill_path.closeSubpath()
            grad = QLinearGradient(0, 0, 0, h)
            c1 = QColor(self._color); c1.setAlpha(110)
            c2 = QColor(self._color); c2.setAlpha(0)
            grad.setColorAt(0.0, c1)
            grad.setColorAt(1.0, c2)
            p.fillPath(fill_path, grad)

        pen = QPen(self._color)
        pen.setWidthF(1.6)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        p.drawPath(path)
