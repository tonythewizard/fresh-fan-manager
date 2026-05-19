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

COLOR_CYAN = "#7FD7FF"


class TitleButton(QPushButton):
    """Fully QPainter-rendered button for the title bar. Bypasses QSS so
    rounded corners are properly antialiased even on translucent windows.
    Glyph color and hover background follow the active theme so titlebar
    buttons stay visible on both dark and light themes."""

    def __init__(self, glyph: str, color: Optional[str] = None, parent=None):
        super().__init__(parent)
        self.setFixedSize(26, 26)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._glyph = glyph
        # When `color` is None the glyph follows the theme's title_color.
        self._color_override: Optional[str] = color
        self._theme = "dark"
        self._hover = False
        self._pressed = False
        self.setFlat(True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setText("")
        self.setMouseTracking(True)

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
            return QColor(20, 24, 32)
        return QColor(255, 255, 255)

    def _theme_overlay_alpha(self) -> tuple[int, int, int]:
        """Returns (idle_alpha, hover_alpha, pressed_alpha) for the
        button surface fill. On light themes the overlay is dark, on
        dark themes it's light."""
        if self._theme in ("light", "sepia", "solarized_light"):
            # Dark overlay over light background
            return (20, 50, 90)
        return (20, 40, 60)

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
        # Do NOT call super().paintEvent — that'd repaint the QSS pixmap on top.
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        from PySide6.QtCore import QRectF
        from PySide6.QtGui import QPainterPath, QBrush
        idle, hover, pressed = self._theme_overlay_alpha()
        if self._pressed:
            bg = self._overlay_color(pressed)
        elif self._hover:
            bg = self._overlay_color(hover)
        else:
            bg = self._overlay_color(idle)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        path = QPainterPath()
        path.addRoundedRect(rect, 13.0, 13.0)
        p.fillPath(path, QBrush(bg))
        # Glyph
        font = QFont(self.font())
        font.setPixelSize(15)
        font.setBold(True)
        p.setFont(font)
        p.setPen(self._theme_glyph_color())
        p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self._glyph)


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
        self.snowflake.setToolTip("Il colore segue la temperatura della CPU")
        layout.addWidget(self.snowflake)

        self.title_label = QLabel("Fresh Fan Manager")
        self.title_label.setObjectName("titleLabel")
        self.title_label.setSizePolicy(QSizePolicy.Policy.Expanding,
                                        QSizePolicy.Policy.Preferred)
        layout.addWidget(self.title_label)

        self.btn_mini = TitleButton("◇")
        self.btn_mini.setToolTip("Modalità mini-finestra")
        self.btn_pin = TitleButton("📌")
        self.btn_pin.setToolTip("Aggancia al desktop (modalità widget)")
        self.btn_min = TitleButton("–")
        self.btn_min.setToolTip("Riduci a icona")
        self.btn_max = TitleButton("□")
        self.btn_max.setToolTip("Ingrandisci/Ripristina")
        self.btn_close = TitleButton("✕")
        self.btn_close.setToolTip("Nascondi (resta nel tray)")

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

    def set_edit_active(self, on: bool) -> None:
        """Highlight the footer edit button via main window — kept as a no-op
        in titlebar for backward compat with existing callers."""
        pass

    def update_indicators(self, temp_color: str, fan_rpm: int) -> None:
        self.snowflake.set_color(temp_color)
        self.snowflake.set_rpm(fan_rpm)

    def set_widget_mode(self, widget_mode: bool) -> None:
        self._widget_mode = widget_mode
        for b in (self.btn_min, self.btn_max, self.btn_close, self.btn_mini):
            b.setVisible(not widget_mode)
        self.btn_pin.setVisible(True)
        if widget_mode:
            self.btn_pin.setToolTip("Sgancia dal desktop (torna a finestra)")
            self.title_label.setText("Fresh Fan")
        else:
            self.btn_pin.setToolTip("Aggancia al desktop (modalità widget)")
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
