# SPDX-License-Identifier: GPL-3.0-or-later
"""
Icon rendering for Fresh Fan Manager. We use the same snowflake glyph ❄
everywhere — taskbar, ALT-TAB, window title, tray — and tint it by CPU
temperature so the icon itself reads as a status indicator.
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPen, QPixmap


def _color_for_temp(temp: Optional[float]) -> QColor:
    if temp is None:
        return QColor("#7FD7FF")     # neutral cyan
    if temp < 50:
        return QColor("#6ed98a")     # green
    if temp < 65:
        return QColor("#7FD7FF")     # cyan
    if temp < 78:
        return QColor("#ffb454")     # orange
    if temp < 90:
        return QColor("#ff7a45")     # red-orange
    return QColor("#ff5e57")         # red


def _draw_snowflake(size: int, color: QColor,
                    manual_ring: bool = False,
                    temp: Optional[float] = None,
                    show_temp_number: bool = False) -> QPixmap:
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing)

    if show_temp_number and temp is not None:
        # Dynamic text: displays e.g. 42° in the tray icon
        f = QFont()
        f.setBold(True)
        t_int = int(round(temp))
        t_str = f"{t_int}°"
        f.setPixelSize(max(10, int(size * 0.52)))
        p.setFont(f)
        p.setPen(color)
        p.drawText(pm.rect(), Qt.AlignmentFlag.AlignCenter, t_str)

        if manual_ring:
            pen = QPen(QColor("#ffb454"))
            pen.setWidthF(max(1.5, size * 0.08))
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            m = max(1, int(size * 0.05))
            p.drawEllipse(m, m, size - 2 * m, size - 2 * m)
    else:
        # Snowflake glyph filled as large as the frame allows.
        f = QFont()
        f.setPixelSize(int(size * 0.96))
        f.setBold(True)
        p.setFont(f)
        p.setPen(color)
        p.drawText(pm.rect(), Qt.AlignmentFlag.AlignCenter, "❄")

        if manual_ring:
            pen = QPen(QColor("#ffb454"))
            pen.setWidthF(max(1.5, size * 0.06))
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            m = int(size * 0.06)
            p.drawEllipse(m, m, size - 2 * m, size - 2 * m)

    p.end()
    return pm


def app_icon(temp: Optional[float] = None) -> QIcon:
    """Application/window icon. Renders at every size KDE typically asks
    for in the Kickoff menu, taskbar, ALT-TAB switcher and window decoration.
    Big sizes included so the menu icon stays sharp at any scale."""
    color = _color_for_temp(temp)
    icon = QIcon()
    for s in (16, 22, 24, 32, 48, 64, 96, 128, 192, 256, 384, 512):
        icon.addPixmap(_draw_snowflake(s, color))
    return icon


def tray_icon(temp: Optional[float] = None,
              manual_mode: bool = False,
              show_temp_number: bool = False) -> QIcon:
    """Tray icon: snowflake or numeric temp colored by temperature,
    with optional manual ring."""
    color = _color_for_temp(temp)
    icon = QIcon()
    for s in (16, 22, 24, 32, 40, 48, 64, 96, 128, 256):
        icon.addPixmap(_draw_snowflake(s, color, manual_ring=manual_mode,
                                       temp=temp, show_temp_number=show_temp_number))
    return icon


# ---------------------------------------------------------------------------
# Custom GPU card icon and Battery icon
# Drawn programmatically so they can recolor with state without external SVGs.
# ---------------------------------------------------------------------------

from PySide6.QtCore import QRectF, QPointF
from PySide6.QtGui import QBrush, QLinearGradient, QPolygonF
from PySide6.QtWidgets import QWidget


class GPUCardIcon(QWidget):
    """Stylised desktop graphics card: PCB with cooler shroud, fan, and bracket."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._busy = 0.0       # 0..100
        self._temp: Optional[float] = None
        self.setMinimumSize(48, 48)

    def set_state(self, busy: Optional[float], temp: Optional[float]) -> None:
        changed = False
        if busy is not None and abs((self._busy or 0) - busy) > 0.5:
            self._busy = busy; changed = True
        if temp != self._temp:
            self._temp = temp; changed = True
        if changed:
            self.update()

    def paintEvent(self, ev):  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        # Color of fan accent reflects temperature
        accent = _color_for_temp(self._temp)
        # Coordinates in normalised units, then scaled
        s = min(w, h)
        ox = (w - s) / 2
        oy = (h - s) / 2

        def R(x, y, ww, hh) -> QRectF:
            return QRectF(ox + x * s, oy + y * s, ww * s, hh * s)

        # PCB substrate (dark green)
        pcb_color = QColor(28, 70, 38)
        p.setBrush(QBrush(pcb_color))
        p.setPen(QPen(QColor(10, 30, 18), max(1.0, s * 0.02)))
        p.drawRoundedRect(R(0.05, 0.30, 0.90, 0.45), s * 0.04, s * 0.04)

        # PCI bracket (left edge)
        p.setBrush(QBrush(QColor(180, 180, 190)))
        p.setPen(QPen(QColor(90, 90, 100), max(1.0, s * 0.02)))
        p.drawRect(R(0.02, 0.28, 0.05, 0.50))

        # Output ports (DP/HDMI) on bracket
        p.setBrush(QBrush(QColor(20, 24, 32)))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRect(R(0.025, 0.36, 0.04, 0.08))
        p.drawRect(R(0.025, 0.50, 0.04, 0.08))
        p.drawRect(R(0.025, 0.62, 0.04, 0.08))

        # Cooler shroud (dark plate covering most of PCB)
        grad = QLinearGradient(0, oy + 0.30 * s, 0, oy + 0.75 * s)
        grad.setColorAt(0, QColor(60, 64, 76))
        grad.setColorAt(1, QColor(34, 38, 48))
        p.setBrush(QBrush(grad))
        p.setPen(QPen(QColor(20, 22, 28), max(1.0, s * 0.02)))
        p.drawRoundedRect(R(0.10, 0.32, 0.82, 0.41), s * 0.03, s * 0.03)

        # Heatsink fins on the right (vertical lines)
        p.setPen(QPen(QColor(80, 85, 95), max(1.0, s * 0.018)))
        for i in range(7):
            x = 0.62 + i * 0.045
            p.drawLine(QPointF(ox + x * s, oy + 0.35 * s),
                        QPointF(ox + x * s, oy + 0.70 * s))

        # Fan on the left of the shroud
        cx = ox + 0.30 * s
        cy = oy + 0.525 * s
        fr = s * 0.16
        # Fan ring
        p.setBrush(QBrush(QColor(22, 24, 30)))
        p.setPen(QPen(QColor(50, 54, 64), max(1.0, s * 0.02)))
        p.drawEllipse(QPointF(cx, cy), fr, fr)
        # Fan blades — color = accent (temp)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(accent))
        n_blades = 5
        import math as _m
        for k in range(n_blades):
            a = (k / n_blades) * 360 + (self._busy * 0.5)
            poly = QPolygonF()
            poly.append(QPointF(cx, cy))
            for t in (a - 18, a, a + 18):
                rad = _m.radians(t)
                poly.append(QPointF(cx + _m.cos(rad) * fr * 0.85,
                                     cy + _m.sin(rad) * fr * 0.85))
            p.drawPolygon(poly)
        # Hub
        p.setBrush(QBrush(QColor(20, 22, 28)))
        p.drawEllipse(QPointF(cx, cy), fr * 0.18, fr * 0.18)


class BatteryIcon(QWidget):
    """Battery shape with fill level + bolt/plug overlay."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._percent = 0.0
        self._plugged = False
        self._color = QColor("#6ed98a")
        self.setMinimumSize(28, 40)

    def set_state(self, percent: Optional[float], plugged: bool) -> None:
        changed = False
        if percent is not None and abs(self._percent - percent) > 0.5:
            self._percent = max(0.0, min(100.0, percent)); changed = True
        if plugged != self._plugged:
            self._plugged = plugged; changed = True
        # Color
        if plugged:
            col = QColor("#7FD7FF")
        elif self._percent >= 70:
            col = QColor("#6ed98a")
        elif self._percent >= 30:
            col = QColor("#ffb454")
        else:
            col = QColor("#ff5e57")
        if col.rgba() != self._color.rgba():
            self._color = col; changed = True
        if changed:
            self.update()

    def paintEvent(self, ev):  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        body_w = w * 0.85
        body_h = h * 0.88
        x = (w - body_w) / 2
        y = (h - body_h) / 2 + h * 0.04   # leave room for nipple
        # Top nipple
        nip_w = body_w * 0.32
        nip_h = h * 0.06
        nip_x = (w - nip_w) / 2
        nip_y = y - nip_h
        p.setBrush(QBrush(QColor(180, 180, 200)))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(QRectF(nip_x, nip_y, nip_w, nip_h),
                          nip_h * 0.4, nip_h * 0.4)
        # Body outline
        outline_pen = QPen(QColor(200, 200, 215), max(1.5, w * 0.06))
        outline_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(outline_pen)
        p.setBrush(QBrush(QColor(0, 0, 0, 0)))
        p.drawRoundedRect(QRectF(x, y, body_w, body_h),
                          w * 0.10, w * 0.10)
        # Inner fill
        pad = max(2.0, w * 0.10)
        fx = x + pad
        fy = y + pad
        fw = body_w - 2 * pad
        fh = body_h - 2 * pad
        if fw > 0 and fh > 0:
            fill_h = fh * (self._percent / 100.0)
            fill_y = fy + (fh - fill_h)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(self._color))
            p.drawRoundedRect(QRectF(fx, fill_y, fw, fill_h),
                              w * 0.04, w * 0.04)
        # Charging bolt
        if self._plugged:
            p.setBrush(QBrush(QColor(255, 255, 255)))
            p.setPen(QPen(QColor(0, 0, 0, 120), max(1.0, w * 0.025)))
            cx = x + body_w / 2
            cy = y + body_h / 2
            unit = body_w * 0.18
            poly = QPolygonF()
            poly.append(QPointF(cx - unit * 0.4, cy - unit * 1.2))
            poly.append(QPointF(cx + unit * 0.1, cy - unit * 0.2))
            poly.append(QPointF(cx - unit * 0.1, cy - unit * 0.1))
            poly.append(QPointF(cx + unit * 0.4, cy + unit * 1.2))
            poly.append(QPointF(cx - unit * 0.1, cy + unit * 0.2))
            poly.append(QPointF(cx + unit * 0.1, cy + unit * 0.1))
            p.drawPolygon(poly)
