# SPDX-License-Identifier: GPL-3.0-or-later
"""
RootFrame: replacement for the rootContainer QWidget. Paints its own
rounded background (solid or gradient) and border using QPainter with
antialiasing. This bypasses Qt's QSS rasterizer, which produces jagged
edges when combined with WA_TranslucentBackground + border-radius and
silently no-ops on `background: qlineargradient(...)` for the same widget.
"""
from __future__ import annotations

import re
from typing import Optional

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import (QPainter, QColor, QBrush, QPen, QLinearGradient,
                            QPainterPath, QFont)
from PySide6.QtWidgets import QWidget

from . import styles as _styles


_RGBA_RX = re.compile(
    r"rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)(?:\s*,\s*(\d+(?:\.\d+)?))?\s*\)"
)


def parse_rgba(s: str) -> QColor:
    """Parse 'rgba(r,g,b,a)' / 'rgb(r,g,b)' / '#rrggbb' into QColor.
    Alpha component is 0–255 (Qt convention)."""
    s = s.strip()
    if s.startswith("#"):
        c = QColor(s)
        return c
    m = _RGBA_RX.match(s)
    if not m:
        return QColor("#202030")
    r, g, b = int(m.group(1)), int(m.group(2)), int(m.group(3))
    a = m.group(4)
    if a is None:
        return QColor(r, g, b)
    af = float(a)
    # styles.py uses 0–255 for alpha, but allow 0–1.0 just in case
    if af <= 1.0:
        af = af * 255
    return QColor(r, g, b, int(round(af)))


def retint_labels(root, theme: str) -> None:
    """Adapt every QLabel inside `root` to the active theme.

    Each label's first-seen stylesheet (the "white template" produced by
    the section builders) is cached on a Qt dynamic property `_orig_ss`.
    Every subsequent call regenerates the stylesheet from this cached
    original by remapping the rgba(255,255,255,α) token to a
    theme-appropriate (foreground, alpha) tuple. This is fully reversible
    across theme switches and idempotent."""
    from PySide6.QtWidgets import QLabel
    if theme in ("light", "solarized_light"):
        fg = "20, 24, 32"
        min_alpha = 215
    elif theme == "sepia":
        fg = "50, 32, 16"
        min_alpha = 220
    elif theme == "hicontrast":
        fg = "255, 255, 255"
        min_alpha = 245
    elif theme == "solarized_dark":
        fg = "238, 232, 213"
        min_alpha = 230
    else:
        # Dark / dark default themes: ensure legible contrast
        fg = "255, 255, 255"
        min_alpha = 175

    pattern = re.compile(
        r"color:\s*rgba\(\s*255\s*,\s*255\s*,\s*255\s*,\s*(\d+)\s*\)"
    )

    def remap(m):
        try:
            a = int(m.group(1))
        except Exception:
            a = 220
        eff_a = max(a, min_alpha) if min_alpha else a
        return f"color: rgba({fg}, {eff_a})"

    for lbl in root.findChildren(QLabel):
        # Labels whose colour is driven dynamically by _render (e.g. temp
        # gauges that recolour by band) must not be retinted — their cached
        # original might be a temporary builder placeholder.
        if lbl.property("_skip_retint"):
            continue
        current_ss = lbl.styleSheet() or ""
        orig = lbl.property("_orig_ss")
        # Capture the original only if the current stylesheet still contains
        # the white-template pattern (i.e. it's untouched, fresh from a builder).
        if orig is None and pattern.search(current_ss):
            orig = current_ss
            lbl.setProperty("_orig_ss", orig)
        if not orig:
            # No white-template found; nothing to retint.
            continue
        new_ss = pattern.sub(remap, orig)
        if new_ss != current_ss:
            lbl.setStyleSheet(new_ss)


class RootFrame(QWidget):
    """Top-level rounded container painted via QPainter (antialiased).
    When full screen or maximized, eliminates transparency and sharpens
    corners to cover the display solidly and cleanly."""

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.setObjectName("rootContainer")
        self._settings = settings
        # Required so Qt routes painting through this widget on translucent
        # top-level windows. Without it the background may not appear at all.
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, False)

    def refresh(self) -> None:
        """Call after theme or bg_effect changes."""
        self.update()

    def paintEvent(self, ev):  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

        win = self.window()
        is_fs = (win.isFullScreen() or win.isMaximized() or getattr(win, "_is_vert_maximized", False)) if win else False

        # Pick palette (theme + bg variant)
        palette = _styles.palette_for(
            self._settings.theme,
            self._settings.bg_effect,
            getattr(self._settings, "bg_variant", "default"),
        )

        if is_fs:
            # Fullscreen: completely eliminate transparency (alpha 255) and zero border radius
            if self._settings.bg_effect == "gradient":
                grad = QLinearGradient(0, 0, 0, self.height())
                c_top = parse_rgba(palette["grad_top"])
                c_top.setAlpha(255)
                c_mid = parse_rgba(palette["grad_mid"])
                c_mid.setAlpha(255)
                c_bot = parse_rgba(palette["grad_bot"])
                c_bot.setAlpha(255)
                grad.setColorAt(0.0, c_top)
                grad.setColorAt(0.5, c_mid)
                grad.setColorAt(1.0, c_bot)
                p.fillRect(self.rect(), grad)
            else:
                solid_col = parse_rgba(palette["root_bg"])
                solid_col.setAlpha(255)
                p.fillRect(self.rect(), solid_col)
            return

        # Normal windowed mode: outer rounded rect with 0.5px inset
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        radius = 14.0
        path = QPainterPath()
        path.addRoundedRect(rect, radius, radius)

        # Background
        if self._settings.bg_effect == "gradient":
            grad = QLinearGradient(0, 0, 0, self.height())
            grad.setColorAt(0.0, parse_rgba(palette["grad_top"]))
            grad.setColorAt(0.5, parse_rgba(palette["grad_mid"]))
            grad.setColorAt(1.0, parse_rgba(palette["grad_bot"]))
            p.fillPath(path, QBrush(grad))
        elif self._settings.bg_effect == "matrix":
            if self._settings.theme in ("light", "sepia", "solarized_light"):
                p.fillPath(path, QBrush(QColor(238, 242, 246, 230)))
            else:
                p.fillPath(path, QBrush(QColor(8, 10, 16, 230)))
        else:
            p.fillPath(path, QBrush(parse_rgba(palette["root_bg"])))

        # Border (antialiased)
        pen = QPen(parse_rgba(palette["root_border"]))
        pen.setWidthF(1.0)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path)


class PaintedButton(QWidget):
    """Antialiased rounded button. Drop-in replacement for QPushButton when
    QSS-rendered borders look jagged on translucent windows.
    Supports text + hover/press states + checked/enabled + clicked signal.
    """
    from PySide6.QtCore import Signal as _Signal
    clicked = _Signal()
    toggled = _Signal(bool)

    def __init__(self, text: str = "", parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, False)
        self._text = text
        self._theme = "dark"
        self._hover = False
        self._pressed = False
        self._checkable = False
        self._checked = False
        self._enabled = True
        self._radius = 8.0
        self._padding_h = 10
        self._padding_v = 5
        self._font_px = 11
        # Custom appearance overrides (for preset buttons)
        self._custom_checked_bg: Optional[QColor] = None
        self._custom_checked_border: Optional[QColor] = None
        self._custom_checked_text: Optional[QColor] = None
        # Allow horizontal expansion but fix height to font + padding
        from PySide6.QtWidgets import QSizePolicy
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMouseTracking(True)
        self._compute_size()

    # ---- public API mirroring QPushButton ----
    def setText(self, text: str) -> None:  # noqa: N802
        self._text = text
        self._compute_size()
        self.update()

    def text(self) -> str:
        return self._text

    def setCheckable(self, on: bool) -> None:  # noqa: N802
        self._checkable = on

    def isChecked(self) -> bool:  # noqa: N802
        return self._checked

    def setChecked(self, on: bool) -> None:  # noqa: N802
        if on != self._checked:
            self._checked = on
            self.toggled.emit(on)
            self.update()

    def setEnabled(self, on: bool) -> None:  # noqa: N802
        if on != self._enabled:
            self._enabled = on
            self.setCursor(Qt.CursorShape.PointingHandCursor if on else Qt.CursorShape.ArrowCursor)
            self.update()
        super().setEnabled(on)

    def set_theme(self, theme: str) -> None:
        self._theme = theme
        self.update()

    def set_checked_appearance(self, bg: str, border: str, text: str) -> None:
        """Override the colours used when the button is checked (for presets)."""
        self._custom_checked_bg = parse_rgba(bg)
        self._custom_checked_border = parse_rgba(border)
        self._custom_checked_text = parse_rgba(text)
        self.update()

    def setFixedWidth(self, w: int) -> None:  # noqa: N802
        super().setFixedWidth(w)

    def setDefault(self, on: bool) -> None:  # noqa: N802
        # No-op for parity with QPushButton API; PaintedButton doesn't
        # have a special "default" rendering, but callers expect this method.
        pass

    # ---- sizing ----
    def _compute_size(self) -> None:
        from PySide6.QtGui import QFontMetrics
        fm = QFontMetrics(self._font())
        w = fm.horizontalAdvance(self._text) + 2 * self._padding_h
        h = fm.height() + 2 * self._padding_v
        self.setMinimumHeight(h)
        self.setMinimumWidth(max(28, min(w, 90)))
        self._hint_w = max(36, w)
        self._hint_h = h

    def sizeHint(self):  # noqa: N802
        from PySide6.QtCore import QSize
        return QSize(getattr(self, "_hint_w", 60), getattr(self, "_hint_h", 24))

    def minimumSizeHint(self):  # noqa: N802
        from PySide6.QtCore import QSize
        return QSize(getattr(self, "_hint_w", 60), getattr(self, "_hint_h", 24))

    def _font(self) -> QFont:
        f = QFont(self.font())
        f.setPixelSize(self._font_px)
        return f

    # ---- input handling ----
    def enterEvent(self, ev):  # noqa: N802
        if self._enabled:
            self._hover = True
            self.update()

    def leaveEvent(self, ev):  # noqa: N802
        self._hover = False
        self._pressed = False
        self.update()

    def mousePressEvent(self, ev):  # noqa: N802
        if not self._enabled:
            return
        if ev.button() == Qt.MouseButton.LeftButton:
            self._pressed = True
            self.update()

    def mouseReleaseEvent(self, ev):  # noqa: N802
        if not self._enabled:
            return
        was_pressed = self._pressed
        self._pressed = False
        self.update()
        if was_pressed and ev.button() == Qt.MouseButton.LeftButton and self.rect().contains(ev.position().toPoint()):
            if self._checkable:
                self.setChecked(not self._checked)
            self.clicked.emit()

    # ---- painting ----
    def paintEvent(self, ev):  # noqa: N802
        palette = _styles.THEME_PALETTES.get(self._theme, _styles.DARK)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

        # Determine state colours
        if not self._enabled:
            bg = parse_rgba(palette["btn_disabled_bg"])
            text_col = parse_rgba(palette["btn_disabled_text"])
            border_col = parse_rgba(palette["btn_border"])
        elif self._checked and self._custom_checked_bg is not None:
            bg = self._custom_checked_bg
            text_col = self._custom_checked_text or parse_rgba(palette["btn_text"])
            border_col = self._custom_checked_border or parse_rgba(palette["btn_border"])
        elif self._pressed:
            bg = parse_rgba(palette["btn_press"])
            text_col = parse_rgba(palette["btn_text"])
            border_col = parse_rgba(palette["btn_border"])
        elif self._hover:
            bg = parse_rgba(palette["btn_hover"])
            text_col = parse_rgba(palette["btn_text"])
            border_col = parse_rgba(palette["btn_border"])
        else:
            bg = parse_rgba(palette["btn_bg"])
            text_col = parse_rgba(palette["btn_text"])
            border_col = parse_rgba(palette["btn_border"])

        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        path = QPainterPath()
        path.addRoundedRect(rect, self._radius, self._radius)
        p.fillPath(path, QBrush(bg))
        border_width = 1.5 if (self._checked and self._custom_checked_border is not None) else 1.0
        pen = QPen(border_col)
        pen.setWidthF(border_width)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path)

        # Text with elide safety
        p.setFont(self._font())
        p.setPen(text_col)
        from PySide6.QtGui import QFontMetrics
        fm = QFontMetrics(self._font())
        avail_w = max(10, int(rect.width() - 4))
        disp_text = fm.elidedText(self._text, Qt.TextElideMode.ElideRight, avail_w)
        p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, disp_text)


class PaintedTitleButton(PaintedButton):
    """Small 26x26 circular-ish title bar button. Glyph is drawn in `text`."""

    def __init__(self, glyph: str = "", color: str = "#ffffff", parent=None):
        super().__init__(glyph, parent)
        self._radius = 13.0
        self._padding_h = 0
        self._padding_v = 0
        self._font_px = 14
        self._glyph_color = QColor(color)
        self.setFixedSize(26, 26)

    def set_glyph_color(self, color: str) -> None:
        self._glyph_color = QColor(color)
        self.update()

    def paintEvent(self, ev):  # noqa: N802
        palette = _styles.THEME_PALETTES.get(self._theme, _styles.DARK)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        if self._pressed:
            bg = parse_rgba(palette["btn_press"])
        elif self._hover:
            bg = parse_rgba(palette["btn_hover"])
        else:
            bg = parse_rgba(palette["btn_bg"])
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        path = QPainterPath()
        path.addRoundedRect(rect, self._radius, self._radius)
        p.fillPath(path, QBrush(bg))
        # Glyph
        f = QFont(self.font())
        f.setPixelSize(self._font_px)
        f.setBold(True)
        p.setFont(f)
        p.setPen(self._glyph_color)
        p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self._text)


class RoundedSection(QWidget):
    """Antialiased rounded section frame with subtle glassmorphic depth
    and specular rim highlight. Modern, premium, and zero CPU overhead."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setProperty("class", "section")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, False)
        self._theme = "dark"
        self._matrix_mode = False

    def set_theme(self, theme: str) -> None:
        self._theme = theme
        self.update()

    def set_matrix_mode(self, on: bool) -> None:
        """When matrix bg is active, sections become opaque so the rain
        only shows between sections (not through them onto the text)."""
        self._matrix_mode = on
        self.update()

    def paintEvent(self, ev):  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        palette = _styles.THEME_PALETTES.get(self._theme, _styles.DARK)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        radius = 8.0
        path = QPainterPath()
        path.addRoundedRect(rect, radius, radius)

        if self._matrix_mode:
            # Mostly opaque base; covers the matrix rain that's painted below.
            if self._theme in ("light", "sepia", "solarized_light"):
                base = QColor(244, 244, 248, 235)
            else:
                base = QColor(20, 24, 32, 235)
            p.fillPath(path, QBrush(base))
        else:
            base_color = parse_rgba(palette["section_bg"])
            grad = QLinearGradient(rect.topLeft(), rect.bottomLeft())
            if self._theme in ("light", "sepia", "solarized_light"):
                grad.setColorAt(0.0, base_color.lighter(103))
                grad.setColorAt(1.0, base_color.darker(102))
            else:
                top_col = QColor(base_color)
                top_col.setAlpha(min(255, base_color.alpha() + 16))
                bot_col = QColor(base_color)
                bot_col.setAlpha(max(0, base_color.alpha() - 4))
                grad.setColorAt(0.0, top_col)
                grad.setColorAt(1.0, bot_col)
            p.fillPath(path, QBrush(grad))

            # Specular top rim highlight (1px subtle glass reflection)
            if self._theme not in ("light", "sepia", "solarized_light"):
                p.save()
                p.setClipPath(path)
                rim_pen = QPen(QColor(255, 255, 255, 24))
                rim_pen.setWidthF(1.0)
                p.setPen(rim_pen)
                p.drawLine(rect.left() + radius, rect.top() + 0.5,
                           rect.right() - radius, rect.top() + 0.5)
                p.restore()

        pen = QPen(parse_rgba(palette["section_border"]))
        pen.setWidthF(1.0)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path)
