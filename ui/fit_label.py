"""
FitLabel — a QLabel that shrinks its font size so the text always fits
the available width. Used for the big GPU/Battery numbers that would
otherwise get truncated by the ellipsis when the window is narrow.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QFont, QFontMetrics, QPaintEvent
from PySide6.QtWidgets import QLabel


class FitLabel(QLabel):
    """Auto-resizing label.

    Picks the largest font size between `min_px` and `max_px` such that
    the current text fits in the current widget width. Recomputes on
    text change and on resize. Other style (color, weight) stays under
    user control via the inline stylesheet.
    """

    def __init__(self, text: str = "", max_px: int = 40, min_px: int = 18,
                 parent=None):
        super().__init__(text, parent)
        self._max_px = max_px
        self._min_px = min_px
        self._current_px = max_px
        # Allow the label to take the full row width so we always know
        # the actual usable space.
        self.setSizePolicy(self.sizePolicy().horizontalPolicy(),
                           self.sizePolicy().verticalPolicy())
        self.setMinimumWidth(0)
        self.setTextFormat(Qt.TextFormat.PlainText)
        self._apply_size(max_px)

    def set_max_px(self, px: int) -> None:
        self._max_px = max(self._min_px, int(px))
        self._refit()

    def setText(self, text):  # noqa: N802
        super().setText(text)
        self._refit()

    def resizeEvent(self, ev):  # noqa: N802
        super().resizeEvent(ev)
        self._refit()

    def _apply_size(self, px: int) -> None:
        f = QFont(self.font())
        f.setPixelSize(px)
        f.setBold(True)
        self.setFont(f)
        self._current_px = px
        # Update inline style font-size so the global QSS QLabel rule can't
        # override what we just set via setFont.
        prev = self.styleSheet()
        # Strip any existing font-size:* from previous calls, leave other style
        cleaned = []
        for chunk in prev.split(";"):
            if "font-size" in chunk.lower():
                continue
            chunk = chunk.strip()
            if chunk:
                cleaned.append(chunk)
        cleaned.append(f"font-size: {px}px")
        cleaned.append("font-weight: 700")
        self.setStyleSheet("; ".join(cleaned) + ";")

    def _refit(self) -> None:
        avail = max(1, self.width() - 4)
        text = self.text()
        if not text:
            return
        # Binary-ish search from max down; small range so just iterate
        for px in range(self._max_px, self._min_px - 1, -1):
            fm = QFontMetrics(self._with_size(px))
            if fm.horizontalAdvance(text) <= avail:
                if px != self._current_px:
                    self._apply_size(px)
                return
        # Even min didn't fit — apply min anyway, the label will elide
        if self._current_px != self._min_px:
            self._apply_size(self._min_px)

    def _with_size(self, px: int) -> QFont:
        f = QFont(self.font())
        f.setPixelSize(px)
        f.setBold(True)
        return f

    def sizeHint(self) -> QSize:  # noqa: N802
        # Keep a sensible default height based on max_px so layouts reserve
        # enough room and the row doesn't visibly jump while shrinking.
        return QSize(super().sizeHint().width(),
                     int(self._max_px * 1.25))
