# SPDX-License-Identifier: GPL-3.0-or-later
"""
First-run onboarding wizard for Fresh Fan Manager.
Allows users to choose their language and preferred tray icon style (Snowflake vs Numeric Temp).
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QColor
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QRadioButton,
    QPushButton, QComboBox, QButtonGroup, QFrame, QWidget
)

from core.config import Settings, save
from core.i18n import tr, set_language, SUPPORTED_LANGUAGES
from ui.icons import tray_icon, app_icon

COLOR_CYAN = "#7FD7FF"
COLOR_GREEN = "#6ed98a"


class OnboardingDialog(QDialog):
    def __init__(self, parent: Optional[QWidget] = None, settings: Optional[Settings] = None):
        super().__init__(parent)
        self._settings = settings or Settings()
        self.setWindowTitle(tr("welcome_title"))
        self.setWindowIcon(app_icon())
        self.setModal(True)
        self.setMinimumWidth(440)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self._build_ui()
        self._retranslate()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)

        self.card = QFrame()
        self.card.setObjectName("onboardingCard")
        self.card.setStyleSheet(
            "QFrame#onboardingCard { "
            "background-color: #1a1a24; "
            "border: 1px solid rgba(127, 215, 255, 60); "
            "border-radius: 12px; "
            "}"
        )
        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(20, 20, 20, 20)
        card_layout.setSpacing(14)
        outer.addWidget(self.card)

        # Header with snowflake
        header_row = QHBoxLayout()
        header_row.setSpacing(10)
        self.logo_lbl = QLabel("❄")
        self.logo_lbl.setStyleSheet(f"font-size: 32px; color: {COLOR_CYAN};")
        header_row.addWidget(self.logo_lbl)

        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        self.title_lbl = QLabel()
        self.title_lbl.setStyleSheet("font-size: 16px; font-weight: 700; color: #ffffff;")
        title_col.addWidget(self.title_lbl)

        self.subtitle_lbl = QLabel()
        self.subtitle_lbl.setStyleSheet("font-size: 11px; color: rgba(255, 255, 255, 160);")
        self.subtitle_lbl.setWordWrap(True)
        title_col.addWidget(self.subtitle_lbl)
        header_row.addLayout(title_col, 1)
        card_layout.addLayout(header_row)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: rgba(255, 255, 255, 30);")
        card_layout.addWidget(sep)

        # 1. Language Row
        lang_row = QHBoxLayout()
        self.lang_label = QLabel()
        self.lang_label.setStyleSheet("font-size: 12px; font-weight: 600; color: #ffffff;")
        lang_row.addWidget(self.lang_label)

        self.cb_lang = QComboBox()
        self.cb_lang.setMinimumWidth(180)
        self.cb_lang.setStyleSheet(
            "QComboBox { background: #242436; color: #ffffff; border: 1px solid rgba(255,255,255,50); "
            "border-radius: 6px; padding: 4px 8px; font-size: 11px; }"
            "QComboBox::drop-down { border: none; }"
            "QComboBox QAbstractItemView { background: #242436; color: #ffffff; selection-background-color: #383854; }"
        )
        for code, name in SUPPORTED_LANGUAGES.items():
            self.cb_lang.addItem(name, code)
        cur_idx = self.cb_lang.findData(self._settings.language)
        if cur_idx >= 0:
            self.cb_lang.setCurrentIndex(cur_idx)
        self.cb_lang.currentIndexChanged.connect(self._on_lang_changed)
        lang_row.addWidget(self.cb_lang)
        card_layout.addLayout(lang_row)

        # 2. Tray Icon Style Section
        self.tray_sec_lbl = QLabel()
        self.tray_sec_lbl.setStyleSheet("font-size: 12px; font-weight: 600; color: #ffffff; margin-top: 6px;")
        card_layout.addWidget(self.tray_sec_lbl)

        self.style_group = QButtonGroup(self)

        # Option A: Numeric Temp Badge
        self.opt_numeric = QFrame()
        self.opt_numeric.setStyleSheet(
            "QFrame { background: rgba(255,255,255,6); border: 1px solid rgba(255,255,255,20); border-radius: 8px; padding: 6px; }"
        )
        opt_num_lay = QHBoxLayout(self.opt_numeric)
        opt_num_lay.setContentsMargins(8, 6, 8, 6)
        opt_num_lay.setSpacing(10)

        self.rb_numeric = QRadioButton()
        self.rb_numeric.setChecked(self._settings.tray_show_temp)
        self.style_group.addButton(self.rb_numeric, 1)
        opt_num_lay.addWidget(self.rb_numeric)

        num_text_col = QVBoxLayout()
        num_text_col.setSpacing(2)
        self.lbl_num_title = QLabel()
        self.lbl_num_title.setStyleSheet("font-size: 11px; font-weight: 600; color: #ffffff;")
        num_text_col.addWidget(self.lbl_num_title)
        self.lbl_num_desc = QLabel()
        self.lbl_num_desc.setStyleSheet("font-size: 10px; color: rgba(255,255,255,150);")
        self.lbl_num_desc.setWordWrap(True)
        num_text_col.addWidget(self.lbl_num_desc)
        opt_num_lay.addLayout(num_text_col, 1)

        # Badge preview
        badge_preview = QLabel(" 48° ")
        badge_preview.setStyleSheet(
            f"background: rgba(127, 215, 255, 30); color: {COLOR_CYAN}; "
            "border: 1px solid rgba(127, 215, 255, 80); border-radius: 6px; "
            "font-size: 12px; font-weight: 700; padding: 2px 4px;"
        )
        opt_num_lay.addWidget(badge_preview)
        card_layout.addWidget(self.opt_numeric)

        # Option B: Classic Snowflake
        self.opt_snowflake = QFrame()
        self.opt_snowflake.setStyleSheet(
            "QFrame { background: rgba(255,255,255,6); border: 1px solid rgba(255,255,255,20); border-radius: 8px; padding: 6px; }"
        )
        opt_snow_lay = QHBoxLayout(self.opt_snowflake)
        opt_snow_lay.setContentsMargins(8, 6, 8, 6)
        opt_snow_lay.setSpacing(10)

        self.rb_snowflake = QRadioButton()
        self.rb_snowflake.setChecked(not self._settings.tray_show_temp)
        self.style_group.addButton(self.rb_snowflake, 2)
        opt_snow_lay.addWidget(self.rb_snowflake)

        snow_text_col = QVBoxLayout()
        snow_text_col.setSpacing(2)
        self.lbl_snow_title = QLabel()
        self.lbl_snow_title.setStyleSheet("font-size: 11px; font-weight: 600; color: #ffffff;")
        snow_text_col.addWidget(self.lbl_snow_title)
        self.lbl_snow_desc = QLabel()
        self.lbl_snow_desc.setStyleSheet("font-size: 10px; color: rgba(255,255,255,150);")
        self.lbl_snow_desc.setWordWrap(True)
        snow_text_col.addWidget(self.lbl_snow_desc)
        opt_snow_lay.addLayout(snow_text_col, 1)

        # Snowflake preview
        snow_preview = QLabel(" ❄ ")
        snow_preview.setStyleSheet(
            f"background: rgba(110, 217, 138, 30); color: {COLOR_GREEN}; "
            "border: 1px solid rgba(110, 217, 138, 80); border-radius: 6px; "
            "font-size: 14px; font-weight: 700; padding: 2px 4px;"
        )
        opt_snow_lay.addWidget(snow_preview)
        card_layout.addWidget(self.opt_snowflake)

        # 3. Action button
        btn_box = QHBoxLayout()
        btn_box.addStretch()
        self.btn_done = QPushButton()
        self.btn_done.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_done.setStyleSheet(
            f"QPushButton {{ background: {COLOR_CYAN}; color: #101018; "
            "font-size: 12px; font-weight: 700; border-radius: 6px; padding: 8px 24px; }"
            "QPushButton:hover { background: #a2e2ff; }"
            "QPushButton:pressed { background: #5dbada; }"
        )
        self.btn_done.clicked.connect(self._on_done)
        btn_box.addWidget(self.btn_done)
        card_layout.addLayout(btn_box)

    def _on_lang_changed(self, idx: int) -> None:
        lang_code = self.cb_lang.itemData(idx)
        if lang_code:
            set_language(lang_code)
            self._settings.language = lang_code
            self._retranslate()

    def _retranslate(self) -> None:
        self.setWindowTitle(tr("welcome_title"))
        self.title_lbl.setText(tr("welcome_title"))
        self.subtitle_lbl.setText(tr("welcome_subtitle"))
        self.lang_label.setText(f"{tr('language')}:")
        self.tray_sec_lbl.setText(tr("choose_tray_icon_style"))
        self.lbl_num_title.setText(tr("tray_style_numeric"))
        self.lbl_num_desc.setText(tr("tray_style_numeric_desc"))
        self.lbl_snow_title.setText(tr("tray_style_snowflake"))
        self.lbl_snow_desc.setText(tr("tray_style_snowflake_desc"))
        self.btn_done.setText(tr("get_started"))

    def _on_done(self) -> None:
        self._settings.tray_show_temp = self.rb_numeric.isChecked()
        self._settings.first_run_completed = True
        save(self._settings)
        self.accept()
