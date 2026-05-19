"""
Preferences dialog: aspetto (tema, effetti, dimensione temp), alert,
sicurezza override manuale, server grafico.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                                QSpinBox, QCheckBox, QComboBox, QPushButton,
                                QSlider, QFrame, QTabWidget, QWidget)

from core import config


class PreferencesDialog(QDialog):
    appearance_changed = Signal()

    def __init__(self, settings: config.Settings, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Preferenze")
        self.setMinimumWidth(460)
        self._settings = settings
        self._restart_required = False
        self._appearance_dirty = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        tabs = QTabWidget()
        layout.addWidget(tabs, 1)

        tabs.addTab(self._build_appearance_tab(), "Aspetto")
        tabs.addTab(self._build_alerts_tab(), "Allerte")
        tabs.addTab(self._build_advanced_tab(), "Avanzate")

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel = QPushButton("Annulla")
        cancel.clicked.connect(self.reject)
        save = QPushButton("Salva")
        save.setDefault(True)
        save.clicked.connect(self._save)
        btn_row.addWidget(cancel)
        btn_row.addWidget(save)
        layout.addLayout(btn_row)

        # Make any hard-coded white labels readable on light themes.
        from .painted_frames import retint_labels
        retint_labels(self, settings.theme)

    # ---------------- tabs ----------------
    def _section_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet("font-weight: 600; font-size: 12px; margin-top: 4px;")
        return lbl

    def _info(self, text: str) -> QLabel:
        from . import styles as _styles
        theme = self._settings.theme
        palette = _styles.THEME_PALETTES.get(theme, _styles.DARK)
        muted = palette.get("muted", "rgba(255,255,255,160)")
        lbl = QLabel(text)
        lbl.setWordWrap(True)
        lbl.setStyleSheet(f"color: {muted}; font-size: 10px;")
        return lbl

    def _build_appearance_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(4, 8, 4, 8); lay.setSpacing(10)
        s = self._settings

        # Tema
        lay.addWidget(self._section_label("Tema"))
        row_theme = QHBoxLayout()
        row_theme.addWidget(QLabel("Modalità:"))
        self.cb_theme = QComboBox()
        self.cb_theme.setMinimumWidth(180)
        self.cb_theme.view().setMinimumWidth(200)
        self.cb_theme.addItem("Scuro", "dark")
        self.cb_theme.addItem("Chiaro", "light")
        self.cb_theme.addItem("Sepia (carta antica)", "sepia")
        self.cb_theme.addItem("Alto contrasto scuro", "hicontrast")
        self.cb_theme.addItem("Solarized scuro", "solarized_dark")
        self.cb_theme.addItem("Solarized chiaro", "solarized_light")
        idx = self.cb_theme.findData(s.theme)
        if idx >= 0: self.cb_theme.setCurrentIndex(idx)
        self.cb_theme.currentIndexChanged.connect(self._refresh_variant_options_safe)
        row_theme.addWidget(self.cb_theme); row_theme.addStretch()
        lay.addLayout(row_theme)

        # Dimensione temperatura: fissa, non più configurabile.

        # Effetti / sfondo
        lay.addWidget(self._section_label("Sfondo"))
        lay.addWidget(self._info(
            "Stile e variante di colore dello sfondo. 'Matrix' è opt-in: "
            "anima caratteri verdi tra le sezioni e consuma un po' di CPU."
        ))
        row_bg = QHBoxLayout()
        row_bg.addWidget(QLabel("Stile:"))
        self.cb_bg = QComboBox()
        self.cb_bg.setMinimumWidth(180)
        self.cb_bg.view().setMinimumWidth(200)
        self.cb_bg.addItem("Tinta unita", "none")
        self.cb_bg.addItem("Gradient", "gradient")
        self.cb_bg.addItem("Matrix (sperimentale)", "matrix")
        idx = self.cb_bg.findData(s.bg_effect)
        if idx >= 0: self.cb_bg.setCurrentIndex(idx)
        self.cb_bg.currentIndexChanged.connect(self._refresh_variant_options)
        row_bg.addWidget(self.cb_bg); row_bg.addStretch()
        lay.addLayout(row_bg)

        row_var = QHBoxLayout()
        row_var.addWidget(QLabel("Variante:"))
        self.cb_variant = QComboBox()
        self.cb_variant.setMinimumWidth(180)
        self.cb_variant.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToContents
        )
        # Make the popup at least as wide as the visible field
        self.cb_variant.view().setMinimumWidth(200)
        row_var.addWidget(self.cb_variant); row_var.addStretch()
        lay.addLayout(row_var)
        self._current_variant = getattr(s, "bg_variant", "default")
        self._refresh_variant_options()

        lay.addStretch()
        return w

    def _refresh_variant_options_safe(self) -> None:
        # Theme combobox fires changes during construction (before cb_variant
        # is created); guard against that.
        if hasattr(self, "cb_variant"):
            self._refresh_variant_options()

    def _refresh_variant_options(self) -> None:
        """Populate the variant combo based on selected theme + bg style."""
        from . import styles as _styles
        bg = self.cb_bg.currentData()
        theme = self.cb_theme.currentData()
        self.cb_variant.blockSignals(True)
        self.cb_variant.clear()
        if bg == "gradient":
            variants = _styles.GRADIENT_VARIANTS.get(theme, {})
        elif bg == "none":
            variants = _styles.SOLID_VARIANTS.get(theme, {})
        else:
            variants = {}
        if not variants:
            self.cb_variant.addItem("—", "default")
            self.cb_variant.setEnabled(False)
        else:
            self.cb_variant.setEnabled(True)
            labels = {
                "default":   "Predefinito",
                "blue":      "Blu",
                "purple":    "Viola",
                "green":     "Verde",
                "graphite":  "Grafite",
                "ivory":     "Avorio",
                "sunset":    "Tramonto",
                "forest":    "Foresta",
                "fire":      "Fuoco",
                "rose":      "Rosa",
                "mint":      "Menta",
                "peach":     "Pesca",
                # New dark variants
                "ocean":     "Oceano",
                "midnight":  "Mezzanotte",
                "cyberpunk": "Cyberpunk",
                "wine":      "Vino",
                "carbon":    "Carbone",
                "emerald":   "Smeraldo",
                "lavender":  "Lavanda scura",
                "steel":     "Acciaio",
                "aurora":    "Aurora",
                # New light variants
                "cream":     "Crema",
                "sky":       "Cielo",
                "sage":      "Salvia",
                "sand":      "Sabbia",
                "pearl":     "Perla",
                "apricot":   "Albicocca",
                # Sepia / hicontrast / solarized
                "tan":       "Tabacco",
                "coffee":    "Caffè",
                "warm":      "Caldo",
                "amber":     "Ambra",
                "cyan":      "Ciano",
                "base02":    "Base02",
                "base2":     "Base2",
            }
            for k in variants.keys():
                self.cb_variant.addItem(labels.get(k, k.capitalize()), k)
            # Re-select previous if available
            ix = self.cb_variant.findData(self._current_variant)
            if ix < 0:
                ix = 0
            self.cb_variant.setCurrentIndex(ix)
        self.cb_variant.blockSignals(False)

    def _build_alerts_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(4, 8, 4, 8); lay.setSpacing(10)
        s = self._settings

        lay.addWidget(self._section_label("Allerta temperatura"))
        self.chk_alert = QCheckBox("Mostra notifica quando la CPU supera la soglia")
        self.chk_alert.setChecked(s.alert_enabled)
        lay.addWidget(self.chk_alert)
        row_alert = QHBoxLayout()
        row_alert.addWidget(QLabel("Soglia:"))
        self.sp_alert = QSpinBox()
        self.sp_alert.setRange(50, 105); self.sp_alert.setSuffix(" °C")
        self.sp_alert.setValue(s.alert_temp_c)
        row_alert.addWidget(self.sp_alert); row_alert.addStretch()
        lay.addLayout(row_alert)

        lay.addWidget(self._section_label("Sicurezza override manuale"))
        lay.addWidget(self._info(
            "Quando l'override manuale è attivo e la CPU supera questa soglia, "
            "la ventola viene riportata in modalità automatica."
        ))
        self.chk_safety = QCheckBox("Abilita protezione automatica")
        self.chk_safety.setChecked(s.manual_safety_enabled)
        lay.addWidget(self.chk_safety)
        row_safety = QHBoxLayout()
        row_safety.addWidget(QLabel("Soglia sblocco:"))
        self.sp_safety = QSpinBox()
        self.sp_safety.setRange(55, 100); self.sp_safety.setSuffix(" °C")
        self.sp_safety.setValue(s.manual_safety_temp_c)
        row_safety.addWidget(self.sp_safety); row_safety.addStretch()
        lay.addLayout(row_safety)
        lay.addStretch()
        return w

    def _build_advanced_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(4, 8, 4, 8); lay.setSpacing(10)
        s = self._settings

        lay.addWidget(self._section_label("Server grafico"))
        lay.addWidget(self._info(
            "XWayland (xcb) consente la modalità widget pinnata sul desktop. "
            "Wayland nativo è più nitido su HiDPI ma non supporta il pin. "
            "Il cambio richiede il riavvio dell'app."
        ))
        row_d = QHBoxLayout()
        row_d.addWidget(QLabel("Backend:"))
        self.cb_display = QComboBox()
        self.cb_display.addItem("XWayland (xcb) — consigliato", "xcb")
        self.cb_display.addItem("Wayland nativo", "wayland")
        idx = self.cb_display.findData(s.display_server)
        if idx >= 0: self.cb_display.setCurrentIndex(idx)
        row_d.addWidget(self.cb_display); row_d.addStretch()
        lay.addLayout(row_d)
        lay.addStretch()
        return w

    def restart_required(self) -> bool:
        return self._restart_required

    def appearance_dirty(self) -> bool:
        return self._appearance_dirty

    def _save(self) -> None:
        s = self._settings
        old = (s.theme, s.bg_effect, getattr(s, "bg_variant", "default"))
        s.theme = self.cb_theme.currentData()
        s.bg_effect = self.cb_bg.currentData()
        s.bg_variant = self.cb_variant.currentData() or "default"
        new = (s.theme, s.bg_effect, s.bg_variant)
        if old != new:
            self._appearance_dirty = True

        s.alert_enabled = self.chk_alert.isChecked()
        s.alert_temp_c = self.sp_alert.value()
        s.manual_safety_enabled = self.chk_safety.isChecked()
        s.manual_safety_temp_c = self.sp_safety.value()

        new_display = self.cb_display.currentData()
        if new_display != s.display_server:
            self._restart_required = True
            s.display_server = new_display

        config.save(s)
        self.accept()
