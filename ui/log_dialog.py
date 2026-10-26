# SPDX-License-Identifier: GPL-3.0-or-later
"""
Read-only log viewer.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QPlainTextEdit,
                                QHBoxLayout, QPushButton, QLabel)

from core.logger import log_path


class LogDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Log macfan-monitor")
        self.resize(700, 420)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        header = QLabel(f"File: {log_path()}")
        header.setStyleSheet("color: rgba(255,255,255,160); font-size: 10px;")
        layout.addWidget(header)

        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        layout.addWidget(self.text)

        row = QHBoxLayout()
        row.addStretch()
        refresh = QPushButton("Aggiorna")
        refresh.clicked.connect(self._load)
        close_btn = QPushButton("Chiudi")
        close_btn.clicked.connect(self.accept)
        row.addWidget(refresh)
        row.addWidget(close_btn)
        layout.addLayout(row)

        self._load()
        # Auto-refresh every 2s while visible
        self._timer = QTimer(self)
        self._timer.setInterval(2000)
        self._timer.timeout.connect(self._load)
        self._timer.start()
        try:
            from core import config as _cfg
            from .painted_frames import retint_labels
            retint_labels(self, _cfg.load().theme)
        except Exception:
            pass

    def _load(self) -> None:
        path = log_path()
        if not path.exists():
            self.text.setPlainText("(log vuoto)")
            return
        try:
            data = path.read_text(errors="replace")
            # Show last 400 lines so we don't choke on a huge log
            lines = data.splitlines()[-400:]
            new_text = "\n".join(lines)
            # Avoid clobbering the scroll position if nothing changed
            if self.text.toPlainText() != new_text:
                vsb = self.text.verticalScrollBar()
                at_bottom = vsb.value() >= vsb.maximum() - 4
                self.text.setPlainText(new_text)
                if at_bottom:
                    vsb.setValue(vsb.maximum())
        except Exception as e:
            self.text.setPlainText(f"Errore lettura log: {e}")
