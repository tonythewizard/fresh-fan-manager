"""Top processes popup dialog: shows live top-N processes by CPU."""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                                QGridLayout, QPushButton)

from core import sensors


REFRESH_MS = 2500


class TopProcessesDialog(QDialog):
    def __init__(self, parent=None, count: int = 10):
        super().__init__(parent)
        self.setWindowTitle("Top processi")
        self.setModal(False)
        self.setMinimumWidth(340)
        self._count = max(5, min(20, count))

        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(8)

        title = QLabel(f"Primi {self._count} processi per CPU")
        title.setStyleSheet("font-weight: 600; font-size: 12px;")
        lay.addWidget(title)

        self.grid = QGridLayout()
        self.grid.setHorizontalSpacing(8)
        self.grid.setVerticalSpacing(2)
        legend_style = ("color: rgba(255,255,255,140); "
                        "font-family: monospace; font-size: 9px;")
        for col, txt in enumerate(("PID", "Nome", "CPU%", "MEM%")):
            l = QLabel(txt); l.setStyleSheet(legend_style)
            if col != 1:
                l.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.grid.addWidget(l, 0, col)
        self.grid.setColumnStretch(1, 1)
        self.grid.setColumnMinimumWidth(0, 56)
        self.grid.setColumnMinimumWidth(2, 54)
        self.grid.setColumnMinimumWidth(3, 54)

        row_style = ("font-family: monospace; font-size: 10px; "
                      "color: rgba(255,255,255,225);")
        self.rows: list[tuple[QLabel, QLabel, QLabel, QLabel]] = []
        for i in range(self._count):
            row = (QLabel("—"), QLabel("—"), QLabel("—"), QLabel("—"))
            for lbl in row:
                lbl.setStyleSheet(row_style)
            row[0].setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            row[2].setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            row[3].setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            for col, lbl in enumerate(row):
                self.grid.addWidget(lbl, i + 1, col)
            self.rows.append(row)
        lay.addLayout(self.grid)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        close = QPushButton("Chiudi")
        close.clicked.connect(self.close)
        btn_row.addWidget(close)
        lay.addLayout(btn_row)

        self._timer = QTimer(self)
        self._timer.setInterval(REFRESH_MS)
        self._timer.timeout.connect(self._tick)
        self._tick()
        try:
            from core import config as _cfg
            from .painted_frames import retint_labels
            retint_labels(self, _cfg.load().theme)
        except Exception:
            pass

    def showEvent(self, ev):  # noqa: N802
        super().showEvent(ev)
        self._timer.start()

    def hideEvent(self, ev):  # noqa: N802
        super().hideEvent(ev)
        self._timer.stop()

    def _tick(self) -> None:
        try:
            procs = sensors.read_top_processes(self._count)
        except Exception:
            return
        for i, (lp, ln, lc, lm) in enumerate(self.rows):
            if i < len(procs):
                p = procs[i]
                name = (p.name[:22] + "…") if len(p.name) > 23 else p.name
                lp.setText(str(p.pid))
                ln.setText(name)
                lc.setText(f"{p.cpu_percent:.1f}")
                lm.setText(f"{p.memory_percent:.1f}")
            else:
                lp.setText("—"); ln.setText("—"); lc.setText("—"); lm.setText("—")
