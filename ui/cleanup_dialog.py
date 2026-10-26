# SPDX-License-Identifier: GPL-3.0-or-later
"""Advanced cleanup dialog with per-target checkboxes and size estimates."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                                QPushButton, QCheckBox, QFrame, QMessageBox)

from core import sys_actions, sensors
from core.i18n import tr


class CleanupDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("cleanup_title"))
        self.setMinimumWidth(440)
        self.setModal(True)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(8)

        intro = QLabel(
            tr("desc_user_cache") if False else
            "Select targets to clean. Items marked with 🔐 require root privileges."
            if tr("save") == "Save" else
            "Scegli cosa pulire. Le voci marcate con 🔐 richiedono i privilegi di amministratore."
        )
        intro.setWordWrap(True)
        intro.setStyleSheet("color: rgba(255,255,255,200); font-size: 11px;")
        lay.addWidget(intro)

        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: rgba(255,255,255,30);")
        lay.addWidget(sep)

        self.checks: dict[str, QCheckBox] = {}
        self.targets = sys_actions.enumerate_cleanup_targets()
        for t in self.targets:
            row = QHBoxLayout()
            lock = "🔐 " if t.needs_root else "   "
            size_txt = ""
            if t.size_bytes > 0:
                size_txt = f"  ({sensors.format_bytes(t.size_bytes)})"
            cb = QCheckBox(f"{lock}{t.label}{size_txt}")
            cb.setToolTip(t.description)
            # Pre-select user-cache and trash by default? No — let user choose.
            row.addWidget(cb)
            self.checks[t.key] = cb
            lay.addLayout(row)
            desc = QLabel(t.description)
            desc.setStyleSheet("color: rgba(255,255,255,130); font-size: 10px; margin-left: 24px;")
            desc.setWordWrap(True)
            lay.addWidget(desc)

        # Status line
        self.status = QLabel("")
        self.status.setStyleSheet("color: rgba(255,255,255,180); font-size: 11px;")
        self.status.setWordWrap(True)
        lay.addWidget(self.status)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self.btn_cancel = QPushButton(tr("cancel"))
        self.btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(self.btn_cancel)
        self.btn_run = QPushButton(tr("clean_system").rstrip("…"))
        self.btn_run.setDefault(True)
        self.btn_run.clicked.connect(self._run)
        btn_row.addWidget(self.btn_run)
        lay.addLayout(btn_row)

        # Retint hard-coded whites on light themes
        try:
            from core import config as _cfg
            from .painted_frames import retint_labels
            retint_labels(self, _cfg.load().theme)
        except Exception:
            pass

    def _run(self) -> None:
        selected = [k for k, cb in self.checks.items() if cb.isChecked()]
        if not selected:
            self.status.setText("Nessuna voce selezionata.")
            return
        self.btn_run.setEnabled(False); self.btn_cancel.setEnabled(False)
        self.status.setText("Pulizia in corso… (può richiedere autenticazione)")
        from PySide6.QtWidgets import QApplication
        QApplication.processEvents()
        ok, msg, freed = sys_actions.run_cleanup(selected)
        self.btn_run.setEnabled(True); self.btn_cancel.setEnabled(True)
        if not ok:
            QMessageBox.warning(self, "Cleanup", f"Errore:\n{msg}")
            self.status.setText("Errore durante la pulizia.")
            return
        if freed > 0:
            self.status.setText(f"Liberati {sensors.format_bytes(freed)}.")
            QMessageBox.information(self, "Cleanup",
                                     f"Pulizia completata.\nLiberati {sensors.format_bytes(freed)}.")
        else:
            self.status.setText("Pulizia completata.")
            QMessageBox.information(self, "Cleanup", "Pulizia completata.")
        # Refresh sizes by closing/reopening visually
        self.accept()
