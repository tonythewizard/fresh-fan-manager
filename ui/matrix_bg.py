# SPDX-License-Identifier: GPL-3.0-or-later
"""
Matrix-style background overlay. Opt-in only because it animates continuously
and uses CPU. Kept deliberately light:
  - ~30 columns regardless of width
  - 200 ms tick (5 fps), nessuna animazione subpixel
  - solo caratteri ascii, font monospace bitmap-friendly
  - opacity bassa così non disturba il contenuto sopra
"""
from __future__ import annotations

import random
import string
from typing import Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import QWidget


_CHARSET = string.ascii_letters + string.digits + "*+#@%&"


class MatrixBackground(QWidget):
    """Always sits behind everything else, transparent for mouse."""

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self._theme = "dark"
        # 5 fps – low CPU
        self._timer = QTimer(self)
        self._timer.setInterval(200)
        self._timer.timeout.connect(self._step)
        self._cols: list[list[str]] = []
        self._heads: list[int] = []
        self._speeds: list[int] = []
        self._char_w = 8
        self._char_h = 13
        self._rebuild_columns()
        if parent is not None:
            parent.installEventFilter(self)

    def set_theme(self, theme: str) -> None:
        self._theme = theme
        self.update()

    def start(self) -> None:
        self._timer.start()
        self.show()

    def stop(self) -> None:
        self._timer.stop()
        self.hide()

    def resizeEvent(self, ev) -> None:  # noqa: N802
        super().resizeEvent(ev)
        self._rebuild_columns()

    def _rebuild_columns(self) -> None:
        if self.width() <= 0 or self.height() <= 0:
            return
        n_cols = max(8, self.width() // self._char_w)
        n_rows = max(8, self.height() // self._char_h)
        # Re-init only if column count changed
        if len(self._cols) != n_cols:
            self._cols = [
                [random.choice(_CHARSET) for _ in range(n_rows)]
                for _ in range(n_cols)
            ]
            self._heads = [random.randint(-n_rows, 0) for _ in range(n_cols)]
            self._speeds = [random.randint(1, 2) for _ in range(n_cols)]
        else:
            # Rows changed: extend/truncate each column
            for c in self._cols:
                while len(c) < n_rows:
                    c.append(random.choice(_CHARSET))
                if len(c) > n_rows:
                    del c[n_rows:]

    def _step(self) -> None:
        if not self._cols:
            return
        n_rows = len(self._cols[0])
        for i in range(len(self._cols)):
            self._heads[i] += self._speeds[i]
            if self._heads[i] > n_rows + 8:
                self._heads[i] = -random.randint(0, n_rows)
                self._speeds[i] = random.randint(1, 2)
            # Occasionally mutate a char in the column for shimmer
            if random.random() < 0.04:
                k = random.randint(0, n_rows - 1)
                self._cols[i][k] = random.choice(_CHARSET)
        self.update()

    def paintEvent(self, ev):  # noqa: N802
        if not self._cols:
            return
        p = QPainter(self)
        font = QFont("monospace", 9)
        p.setFont(font)
        n_cols = len(self._cols)
        n_rows = len(self._cols[0])
        # Bright head color + trailing fade for a few cells above
        # Color depends on theme: bright green on dark, dark green on light
        if self._theme in ("light", "sepia", "solarized_light"):
            head_color = QColor(10, 90, 46)   # dark saturated green
            body_color = QColor(8, 70, 36)
        else:
            head_color = QColor(110, 217, 138)
            body_color = QColor(50, 130, 70)
        for c in range(n_cols):
            head = self._heads[c]
            x = c * self._char_w
            # Trail of ~6 cells
            for offset in range(6):
                r = head - offset
                if r < 0 or r >= n_rows:
                    continue
                y = (r + 1) * self._char_h
                if offset == 0:
                    p.setPen(head_color)
                else:
                    fade = max(20, 200 - offset * 35)
                    col = QColor(body_color)
                    col.setAlpha(fade)
                    p.setPen(col)
                p.drawText(x, y, self._cols[c][r])
