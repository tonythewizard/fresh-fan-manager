# SPDX-License-Identifier: GPL-3.0-or-later
"""
RadialGauge — Ultra-lightweight, high-performance vector arc gauge.
Drawn via antialiased QPainter with zero external dependencies and zero CPU overhead.
"""
from __future__ import annotations

import math
from typing import Optional

from PySide6.QtCore import Qt, QRectF, QSize
from PySide6.QtGui import (
    QPainter, QPen, QColor, QFont, QPainterPath, QLinearGradient
)
from PySide6.QtWidgets import QWidget


class RadialGauge(QWidget):
    """Circular arc gauge with center readout for metrics (Temp, RPM, Power, etc)."""

    def __init__(self,
                 min_val: float = 0.0,
                 max_val: float = 100.0,
                 unit: str = "°C",
                 label: str = "",
                 color: str = "#7FD7FF",
                 parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._min_val = float(min_val)
        self._max_val = float(max_val)
        self._value = float(min_val)
        self._unit = unit
        self._label = label
        self._color = QColor(color)
        self._custom_color: Optional[QColor] = None
        self._compact = False

        self.setAutoFillBackground(False)
        self.setMinimumSize(70, 65)

    def sizeHint(self) -> QSize:  # noqa: N802
        if self._compact:
            return QSize(75, 65)
        return QSize(95, 80)

    def set_range(self, min_val: float, max_val: float) -> None:
        self._min_val = float(min_val)
        self._max_val = max(self._min_val + 1.0, float(max_val))
        self.update()

    def set_value(self, val: Optional[float]) -> None:
        if val is None:
            self._value = self._min_val
        else:
            self._value = float(val)
        self.update()

    def set_unit(self, unit: str) -> None:
        self._unit = unit
        self.update()

    def set_label(self, label: str) -> None:
        self._label = label
        self.update()

    def set_color(self, color: str | QColor) -> None:
        self._custom_color = QColor(color)
        self.update()

    def set_compact(self, compact: bool) -> None:
        self._compact = compact
        self.updateGeometry()
        self.update()

    def set_theme(self, theme: str) -> None:
        self._theme = theme
        self.update()

    def _current_theme(self) -> str:
        theme = getattr(self, "_theme", None)
        if not theme:
            try:
                win = self.window()
                theme = getattr(win.settings, "theme", "dark")
            except Exception:
                theme = "dark"
        return theme or "dark"

    def _auto_color(self, ratio: float) -> QColor:
        """Dynamic color based on percentage if no custom color is forced,
        adapting to theme for high contrast."""
        if self._custom_color:
            return self._custom_color
        theme = self._current_theme()
        if theme in ("light", "solarized_light"):
            if ratio < 0.50:
                return QColor("#166534")  # High-contrast deep green
            elif ratio < 0.75:
                return QColor("#0284c7")  # High-contrast cerulean blue
            elif ratio < 0.88:
                return QColor("#b45309")  # High-contrast amber/brown
            return QColor("#cf222e")       # High-contrast red
        elif theme == "sepia":
            if ratio < 0.50:
                return QColor("#1b5e20")
            elif ratio < 0.75:
                return QColor("#00695c")
            elif ratio < 0.88:
                return QColor("#a0522d")
            return QColor("#b71c1c")
        elif theme == "hicontrast":
            if ratio < 0.50:
                return QColor("#00ff66")
            elif ratio < 0.75:
                return QColor("#00ffff")
            elif ratio < 0.88:
                return QColor("#ffff00")
            return QColor("#ff3333")
        elif theme == "solarized_dark":
            if ratio < 0.50:
                return QColor("#859900")
            elif ratio < 0.75:
                return QColor("#2aa198")
            elif ratio < 0.88:
                return QColor("#b58900")
            return QColor("#dc322f")
        else:  # dark
            if ratio < 0.50:
                return QColor("#6ed98a")  # Cool green
            elif ratio < 0.75:
                return QColor("#7FD7FF")  # Vibrant cyan
            elif ratio < 0.88:
                return QColor("#ffb454")  # Warm amber
            return QColor("#ff5e57")       # Hot coral red

    def paintEvent(self, ev) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

        theme = self._current_theme()
        if theme in ("light", "solarized_light"):
            track_col = QColor(0, 0, 0, 35)
            val_col = QColor(15, 23, 42, 245)
            unit_col = QColor(71, 85, 105, 235)
        elif theme == "sepia":
            track_col = QColor(120, 85, 45, 40)
            val_col = QColor(46, 28, 12, 245)
            unit_col = QColor(97, 67, 39, 230)
        elif theme == "hicontrast":
            track_col = QColor(255, 255, 255, 75)
            val_col = QColor(255, 255, 255, 255)
            unit_col = QColor(255, 255, 0, 245)
        elif theme == "solarized_dark":
            track_col = QColor(147, 161, 161, 40)
            val_col = QColor(238, 232, 213, 245)
            unit_col = QColor(147, 161, 161, 220)
        else:  # dark
            track_col = QColor(255, 255, 255, 28)
            val_col = QColor(255, 255, 255, 240)
            unit_col = QColor(255, 255, 255, 175)

        w = self.width()
        h = self.height()
        cx = w / 2.0
        cy = h / 2.0 + 2.0

        # Geometry
        radius = min(cx, cy) - (4.0 if self._compact else 6.0)
        if radius < 15:
            return

        pen_width = 4.5 if self._compact else 6.0
        arc_rect = QRectF(cx - radius, cy - radius, radius * 2.0, radius * 2.0)

        # Standard 240-degree dashboard arc: from 210° (bottom left) to -30° (bottom right)
        start_angle = 210 * 16
        total_span = -240 * 16

        # Ratio calculation
        val_range = max(1.0, self._max_val - self._min_val)
        ratio = max(0.0, min(1.0, (self._value - self._min_val) / val_range))
        active_span = int(round(total_span * ratio))

        # 1. Background Track
        track_pen = QPen(track_col)
        track_pen.setWidthF(pen_width)
        track_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(track_pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawArc(arc_rect, start_angle, total_span)

        # 2. Active Arc
        arc_color = self._auto_color(ratio)
        active_pen = QPen(arc_color)
        active_pen.setWidthF(pen_width)
        active_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(active_pen)
        if abs(active_span) > 0:
            p.drawArc(arc_rect, start_angle, active_span)

        # 3. Center Value Text
        p.setPen(val_col)
        f = QFont(self.font())
        f.setBold(True)
        val_px = int(radius * (0.55 if self._compact else 0.50))
        f.setPixelSize(max(10, val_px))
        p.setFont(f)

        if self._value >= 1000:
            val_str = f"{int(round(self._value))}"
        elif self._value >= 10 or abs(self._value - round(self._value)) < 0.05:
            val_str = f"{int(round(self._value))}"
        else:
            val_str = f"{self._value:.1f}"

        # Draw value string slightly above center
        val_rect = QRectF(cx - radius, cy - radius * 0.45, radius * 2.0, radius * 0.8)
        p.drawText(val_rect, Qt.AlignmentFlag.AlignCenter, val_str)

        # 4. Small Unit and/or Label
        unit_f = QFont(self.font())
        unit_f.setBold(False)
        unit_f.setPixelSize(max(8, int(val_px * 0.46)))
        p.setFont(unit_f)
        p.setPen(unit_col)

        sub_text = self._unit
        if self._label and not self._compact:
            sub_text = f"{self._label} {self._unit}".strip()

        unit_rect = QRectF(cx - radius, cy + radius * 0.25, radius * 2.0, radius * 0.5)
        p.drawText(unit_rect, Qt.AlignmentFlag.AlignCenter, sub_text)
