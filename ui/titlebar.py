# SPDX-License-Identifier: GPL-3.0-or-later
"""
Custom frameless titlebar.
Includes an animated snowflake whose color reflects CPU temperature and whose
rotation speed reflects fan RPM. Adds an "Edit widgets" toggle button.
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal, QPoint
from PySide6.QtGui import (QMouseEvent, QPainter, QColor, QFont)
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QPushButton,
                                QSizePolicy, QWidget)

from core.i18n import tr

COLOR_CYAN = "#7FD7FF"


class TitleButton(QPushButton):
    """Fully QPainter-rendered minimalist vector button for the title bar.
    Crisp geometric icons (pin, mini, min, max, close) drawn with sub-pixel
    antialiased vector geometry, with theme-aware hover/press states."""

    def __init__(self, btn_type: str = "close", color: Optional[str] = None, parent=None):
        super().__init__(parent)
        self.setFixedSize(26, 26)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        type_map = {
            "◇": "mini", "mini": "mini",
            "📌": "pin", "pin": "pin",
            "–": "min", "-": "min", "min": "min",
            "□": "max", "❐": "max", "max": "max",
            "✕": "close", "x": "close", "close": "close",
        }
        self.btn_type = type_map.get(btn_type, btn_type)
        self._glyph = btn_type
        # When `color` is None the glyph follows the theme's title_color.
        self._color_override: Optional[str] = color
        self._theme = "dark"
        self._hover = False
        self._pressed = False
        self._is_active = False
        self.setFlat(True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setText("")
        self.setMouseTracking(True)

    def set_active(self, active: bool) -> None:
        self._is_active = active
        self.update()

    def setText(self, text: str) -> None:  # noqa: N802
        if text in ("❐", "fullscreen"):
            self._is_active = True
        elif text in ("□", "normal"):
            self._is_active = False
        self.update()

    def set_glyph_color(self, color: str) -> None:
        self._color_override = color
        self.update()

    def set_theme(self, theme: str) -> None:
        self._theme = theme
        self.update()

    def _theme_glyph_color(self) -> QColor:
        if self._color_override is not None:
            return QColor(self._color_override)
        # Light themes need a dark glyph and vice versa
        if self._theme in ("light", "sepia", "solarized_light"):
            return QColor(25, 30, 40)
        return QColor(235, 240, 250)

    def _theme_overlay_alpha(self) -> tuple[int, int, int]:
        """Returns (idle_alpha, hover_alpha, pressed_alpha) for the
        button surface fill. On light themes the overlay is dark, on
        dark themes it's light."""
        if self._theme in ("light", "sepia", "solarized_light"):
            return (15, 45, 80)
        return (15, 35, 60)

    def _overlay_color(self, alpha: int) -> QColor:
        if self._theme in ("light", "sepia", "solarized_light"):
            return QColor(20, 24, 32, alpha)
        return QColor(255, 255, 255, alpha)

    def enterEvent(self, ev):  # noqa: N802
        self._hover = True
        self.update()

    def leaveEvent(self, ev):  # noqa: N802
        self._hover = False
        self._pressed = False
        self.update()

    def mousePressEvent(self, ev):  # noqa: N802
        if ev.button() == Qt.MouseButton.LeftButton:
            self._pressed = True
            self.update()
        super().mousePressEvent(ev)

    def mouseReleaseEvent(self, ev):  # noqa: N802
        self._pressed = False
        self.update()
        super().mouseReleaseEvent(ev)

    def paintEvent(self, ev):  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        from PySide6.QtCore import QRectF, QPointF
        from PySide6.QtGui import QPainterPath, QBrush, QPen

        idle, hover, pressed = self._theme_overlay_alpha()
        is_close = (self.btn_type == "close")

        if self._pressed:
            bg = QColor(255, 60, 60, 160) if is_close else self._overlay_color(pressed)
        elif self._hover:
            bg = QColor(255, 75, 75, 120) if is_close else self._overlay_color(hover)
        elif self._is_active and self.btn_type == "pin":
            bg = QColor(127, 215, 255, 55)
        else:
            bg = self._overlay_color(idle)

        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        path = QPainterPath()
        path.addRoundedRect(rect, 13.0, 13.0)
        p.fillPath(path, QBrush(bg))

        glyph_col = self._theme_glyph_color()
        if is_close and (self._hover or self._pressed):
            glyph_col = QColor(255, 255, 255)
        elif self.btn_type == "pin" and self._is_active:
            glyph_col = QColor(127, 215, 255)

        pen = QPen(glyph_col, 1.4)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)

        cx, cy = rect.center().x(), rect.center().y()

        if self.btn_type == "mini":
            # Crisp minimalist Picture-in-Picture icon
            p.drawRoundedRect(QRectF(cx - 5.5, cy - 5.5, 11, 11), 2.0, 2.0)
            pip_fill = QColor(glyph_col)
            pip_fill.setAlpha(180)
            p.fillRect(QRectF(cx + 0.5, cy + 0.5, 4, 4), pip_fill)

        elif self.btn_type == "pin":
            # Sleek minimalist geometric pushpin
            pin_path = QPainterPath()
            pin_path.moveTo(cx - 4.5, cy - 5.5)
            pin_path.lineTo(cx + 4.5, cy - 5.5)
            pin_path.moveTo(cx - 3.5, cy - 5.5)
            pin_path.lineTo(cx - 3.0, cy + 0.5)
            pin_path.lineTo(cx - 5.0, cy + 2.0)
            pin_path.lineTo(cx + 5.0, cy + 2.0)
            pin_path.lineTo(cx + 3.0, cy + 0.5)
            pin_path.lineTo(cx + 3.5, cy - 5.5)
            if self._is_active:
                p.fillPath(pin_path, QBrush(QColor(127, 215, 255, 180)))
            p.drawPath(pin_path)
            needle_pen = QPen(glyph_col, 1.4)
            needle_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(needle_pen)
            p.drawLine(QPointF(cx, cy + 2.0), QPointF(cx, cy + 6.5))

        elif self.btn_type == "min":
            p.drawLine(QPointF(cx - 4.5, cy), QPointF(cx + 4.5, cy))

        elif self.btn_type == "max":
            if self._is_active:
                p.drawRoundedRect(QRectF(cx - 2.5, cy - 5.5, 7.5, 7.5), 1.5, 1.5)
                p.drawRoundedRect(QRectF(cx - 5.0, cy - 3.0, 7.5, 7.5), 1.5, 1.5)
            else:
                p.drawRoundedRect(QRectF(cx - 4.5, cy - 4.5, 9, 9), 1.5, 1.5)

        elif self.btn_type == "close":
            p.drawLine(QPointF(cx - 4.0, cy - 4.0), QPointF(cx + 4.0, cy + 4.0))
            p.drawLine(QPointF(cx + 4.0, cy - 4.0), QPointF(cx - 4.0, cy + 4.0))


class StaticSnowflake(QWidget):
    """A non-rotating ❄ icon. Color is externally controlled to track CPU temp."""

    def __init__(self, size: int = 30, parent=None):
        super().__init__(parent)
        self._size = size
        self.setFixedSize(size, size)
        self._color = QColor(COLOR_CYAN)

    def set_rpm(self, rpm: int) -> None:
        # Kept as a no-op for API compatibility — snowflake is now static.
        pass

    def set_color(self, color: str) -> None:
        self._color = QColor(color)
        self.update()

    def paintEvent(self, ev):  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        font = QFont(self.font())
        font.setPixelSize(int(self._size * 0.85))
        font.setBold(True)
        p.setFont(font)
        p.setPen(self._color)
        p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "❄")


# Back-compat alias (other modules may still import AnimatedSnowflake)
AnimatedSnowflake = StaticSnowflake


class TitleBar(QFrame):
    minimize_requested = Signal()
    maximize_toggle_requested = Signal()
    close_requested = Signal()
    pin_toggle_requested = Signal()
    edit_toggle_requested = Signal()
    mini_requested = Signal()
    update_requested = Signal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("titleBar")
        self.setFixedHeight(40)
        self._drag_pos: Optional[QPoint] = None
        self._widget_mode = False

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 4, 6, 4)
        layout.setSpacing(8)

        # Larger, static snowflake — colors track CPU temperature
        self.snowflake = StaticSnowflake(size=30)
        self.snowflake.setToolTip(tr("snowflake_tip"))
        layout.addWidget(self.snowflake)

        self.title_label = QLabel("Fresh Fan Manager")
        self.title_label.setObjectName("titleLabel")
        self.title_label.setSizePolicy(QSizePolicy.Policy.Expanding,
                                        QSizePolicy.Policy.Preferred)
        layout.addWidget(self.title_label)

        self.btn_update = QPushButton("↑")
        self.btn_update.setFixedSize(22, 26)
        self.btn_update.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_update.hide()
        self.btn_update.clicked.connect(self.update_requested.emit)
        layout.addWidget(self.btn_update)

        self.btn_mini = TitleButton("◇")
        self.btn_mini.setToolTip(tr("mini_mode"))
        self.btn_pin = TitleButton("📌")
        self.btn_pin.setToolTip(tr("pin_widget_mode"))
        self.btn_min = TitleButton("–")
        self.btn_min.setToolTip(tr("minimize"))
        self.btn_max = TitleButton("□")
        self.btn_max.setToolTip(tr("maximize_restore"))
        self.btn_close = TitleButton("✕")
        self.btn_close.setToolTip(tr("close_to_tray"))

        layout.addWidget(self.btn_mini)
        layout.addWidget(self.btn_pin)
        layout.addWidget(self.btn_min)
        layout.addWidget(self.btn_max)
        layout.addWidget(self.btn_close)

        self.btn_mini.clicked.connect(self.mini_requested.emit)
        self.btn_min.clicked.connect(self.minimize_requested.emit)
        self.btn_max.clicked.connect(self.maximize_toggle_requested.emit)
        self.btn_close.clicked.connect(self.close_requested.emit)
        self.btn_pin.clicked.connect(self.pin_toggle_requested.emit)

    def set_update_version(self, version: Optional[str]) -> None:
        self.btn_update.setVisible(bool(version))
        self.btn_update.setToolTip(tr("update_available", version=version or ""))

    def set_edit_active(self, on: bool) -> None:
        """Highlight the footer edit button via main window — kept as a no-op
        in titlebar for backward compat with existing callers."""
        pass

    def update_indicators(self, temp_color: str, fan_rpm: int) -> None:
        self.snowflake.set_color(temp_color)
        self.snowflake.set_rpm(fan_rpm)

    def set_widget_mode(self, widget_mode: bool) -> None:
        self._widget_mode = widget_mode
        self.btn_pin.set_active(widget_mode)
        for b in (self.btn_min, self.btn_max, self.btn_close, self.btn_mini):
            b.setVisible(not widget_mode)
        self.btn_pin.setVisible(True)
        if widget_mode:
            self.btn_pin.setToolTip(tr("unpin_widget_mode"))
            self.title_label.setText("Fresh Fan")
        else:
            self.btn_pin.setToolTip(tr("pin_widget_mode"))
            self.title_label.setText("Fresh Fan Manager")

    def set_theme(self, theme: str) -> None:
        """Propagate the active theme to title buttons so the X/–/□/◇/📌
        glyphs and their hover backgrounds adapt to light vs dark themes."""
        for b in (self.btn_mini, self.btn_pin, self.btn_min,
                  self.btn_max, self.btn_close):
            b.set_theme(theme)

    def set_buttons_visible(self, visible: bool) -> None:
        self.set_widget_mode(not visible)

    def mousePressEvent(self, ev: QMouseEvent) -> None:  # noqa: N802
        if ev.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = ev.globalPosition().toPoint() - self.window().frameGeometry().topLeft()
            ev.accept()

    def mouseMoveEvent(self, ev: QMouseEvent) -> None:  # noqa: N802
        if self._drag_pos is not None and ev.buttons() & Qt.MouseButton.LeftButton:
            new_pos = ev.globalPosition().toPoint() - self._drag_pos
            self.window().move(new_pos)
            ev.accept()

    def mouseReleaseEvent(self, ev: QMouseEvent) -> None:  # noqa: N802
        self._drag_pos = None

    def mouseDoubleClickEvent(self, ev: QMouseEvent) -> None:  # noqa: N802
        if ev.button() == Qt.MouseButton.LeftButton and not self._widget_mode:
            self.maximize_toggle_requested.emit()
