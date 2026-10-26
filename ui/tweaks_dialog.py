# SPDX-License-Identifier: GPL-3.0-or-later
"""
Modal dialog to edit mbpfan tweaks.
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QFormLayout, QHBoxLayout,
                                QSpinBox, QCheckBox, QPushButton, QLabel,
                                QDialogButtonBox, QMessageBox, QWidget)

from core import mbpfan_ctrl
from core.mbpfan_ctrl import MbpfanConfig


class TweaksDialog(QDialog):
    def __init__(self, parent: Optional[QWidget] = None,
                 fan_min: int = 1200, fan_max: int = 6500):
        super().__init__(parent)
        self.setWindowTitle("Modifica tweak mbpfan")
        self.setMinimumWidth(400)
        self._fan_min = fan_min
        self._fan_max = fan_max

        cfg = mbpfan_ctrl.read_config()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        info = QLabel(
            "Modifica i parametri di /etc/mbpfan.conf. Le modifiche richiedono "
            "privilegi di root (verrà chiesta la password) e il servizio "
            "mbpfan verrà riavviato."
        )
        info.setWordWrap(True)
        info.setProperty("class", "muted")
        info.setStyleSheet("color: rgba(255,255,255,160); font-size: 11px;")
        layout.addWidget(info)

        form = QFormLayout()
        form.setSpacing(8)

        self.low_temp = QSpinBox()
        self.low_temp.setRange(30, 90)
        self.low_temp.setSuffix(" °C")
        self.low_temp.setValue(cfg.low_temp)
        self.low_temp.setToolTip("Sotto questa temperatura la ventola gira al minimo")
        form.addRow("Low temp:", self.low_temp)

        self.high_temp = QSpinBox()
        self.high_temp.setRange(40, 95)
        self.high_temp.setSuffix(" °C")
        self.high_temp.setValue(cfg.high_temp)
        self.high_temp.setToolTip("Soglia di transizione media. Tra low e high la ventola scala linearmente")
        form.addRow("High temp:", self.high_temp)

        self.max_temp = QSpinBox()
        self.max_temp.setRange(60, 105)
        self.max_temp.setSuffix(" °C")
        self.max_temp.setValue(cfg.max_temp)
        self.max_temp.setToolTip("Sopra questa temperatura la ventola va al massimo")
        form.addRow("Max temp:", self.max_temp)

        self.polling = QSpinBox()
        self.polling.setRange(1, 30)
        self.polling.setSuffix(" s")
        self.polling.setValue(cfg.polling_interval)
        self.polling.setToolTip("Intervallo di polling di mbpfan")
        form.addRow("Polling:", self.polling)

        # Override fan speeds (optional)
        self.override_speeds = QCheckBox("Override velocità ventola (sovrascrive limiti SMC)")
        self.override_speeds.setChecked(cfg.min_fan1_speed is not None or cfg.max_fan1_speed is not None)
        layout.addLayout(form)
        layout.addWidget(self.override_speeds)

        speed_form = QFormLayout()
        speed_form.setSpacing(8)
        self.min_fan = QSpinBox()
        self.min_fan.setRange(800, 7000)
        self.min_fan.setSuffix(" RPM")
        self.min_fan.setSingleStep(100)
        self.min_fan.setValue(cfg.min_fan1_speed or fan_min)
        self.max_fan = QSpinBox()
        self.max_fan.setRange(2000, 8000)
        self.max_fan.setSuffix(" RPM")
        self.max_fan.setSingleStep(100)
        self.max_fan.setValue(cfg.max_fan1_speed or fan_max)
        speed_form.addRow("Min RPM:", self.min_fan)
        speed_form.addRow("Max RPM:", self.max_fan)
        layout.addLayout(speed_form)

        self.override_speeds.toggled.connect(self._toggle_speeds)
        self._toggle_speeds(self.override_speeds.isChecked())

        # Sanity hint
        self.hint = QLabel()
        self.hint.setWordWrap(True)
        self.hint.setStyleSheet("color: rgba(255,255,255,160); font-size: 10px;")
        layout.addWidget(self.hint)

        for sb in (self.low_temp, self.high_temp, self.max_temp):
            sb.valueChanged.connect(self._update_hint)
        self._update_hint()

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel_btn = QPushButton("Annulla")
        cancel_btn.clicked.connect(self.reject)
        save_btn = QPushButton("Applica e riavvia mbpfan")
        save_btn.setDefault(True)
        save_btn.clicked.connect(self._apply)
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(save_btn)
        layout.addLayout(btn_row)
        try:
            from core import config as _cfg
            from .painted_frames import retint_labels
            retint_labels(self, _cfg.load().theme)
        except Exception:
            pass

    def _toggle_speeds(self, on: bool) -> None:
        self.min_fan.setEnabled(on)
        self.max_fan.setEnabled(on)

    def _update_hint(self) -> None:
        if not (self.low_temp.value() < self.high_temp.value() < self.max_temp.value()):
            self.hint.setText("⚠ Le soglie devono essere crescenti: low < high < max")
            self.hint.setStyleSheet("color: #ffb454; font-size: 10px;")
        else:
            self.hint.setText("Soglie valide. La curva ventola sarà low → high → max.")
            self.hint.setStyleSheet("color: rgba(255,255,255,160); font-size: 10px;")

    def _apply(self) -> None:
        if not (self.low_temp.value() < self.high_temp.value() < self.max_temp.value()):
            QMessageBox.warning(self, "Valori non validi",
                                "Le soglie devono essere crescenti: low < high < max")
            return
        cfg = MbpfanConfig(
            low_temp=self.low_temp.value(),
            high_temp=self.high_temp.value(),
            max_temp=self.max_temp.value(),
            polling_interval=self.polling.value(),
            min_fan1_speed=self.min_fan.value() if self.override_speeds.isChecked() else None,
            max_fan1_speed=self.max_fan.value() if self.override_speeds.isChecked() else None,
        )
        ok, msg = mbpfan_ctrl.write_config(cfg)
        if not ok:
            QMessageBox.critical(self, "Errore", f"Scrittura config fallita:\n{msg}")
            return
        ok, msg = mbpfan_ctrl.restart_service()
        if not ok:
            QMessageBox.warning(self, "Servizio non riavviato",
                                f"Config scritta, ma riavvio fallito:\n{msg}")
            self.accept()
            return
        QMessageBox.information(self, "Fatto",
                                "Configurazione salvata e mbpfan riavviato.")
        self.accept()
