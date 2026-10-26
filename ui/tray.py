# SPDX-License-Identifier: GPL-3.0-or-later
"""
System tray icon + context menu. The tray menu is the single source of truth
for quitting the application (right-click → Esci).
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QSystemTrayIcon, QMenu, QApplication

from core.i18n import tr
from . import icons


class TrayController(QObject):
    show_requested = Signal()
    hide_requested = Signal()
    toggle_widget_requested = Signal()
    quit_requested = Signal()
    preset_requested = Signal(str)
    open_log_requested = Signal()
    open_tweaks_requested = Signal()

    def __init__(self, parent: Optional[QObject] = None, show_temp_number: bool = False):
        super().__init__(parent)
        self.show_temp_number = show_temp_number
        self.tray = QSystemTrayIcon(icons.tray_icon(show_temp_number=show_temp_number))
        self.tray.setToolTip("Fresh Fan Manager")

        self.menu = QMenu()
        show_txt = "Show Window" if tr("save") == "Save" else "Mostra finestra"
        self.act_show = self.menu.addAction(show_txt)
        self.act_show.triggered.connect(self.show_requested.emit)

        pin_txt = "Pin to Desktop (Widget)" if tr("save") == "Save" else "Aggancia al desktop (widget)"
        self.act_pin = self.menu.addAction(pin_txt)
        self.act_pin.triggered.connect(self.toggle_widget_requested.emit)

        self.menu.addSeparator()

        preset_title = "Fan Presets" if tr("save") == "Save" else "Preset ventola"
        preset_menu = self.menu.addMenu(preset_title)
        for name in ("Silent", "Balanced", "Performance"):
            act = preset_menu.addAction(name)
            act.triggered.connect(lambda _=False, n=name: self.preset_requested.emit(n))

        tweaks_txt = "Edit Tweaks…" if tr("save") == "Save" else "Modifica tweak…"
        self.act_tweaks = self.menu.addAction(tweaks_txt)
        self.act_tweaks.triggered.connect(self.open_tweaks_requested.emit)

        self.menu.addSeparator()
        logs_txt = "View Logs" if tr("save") == "Save" else "Mostra log"
        self.act_log = self.menu.addAction(logs_txt)
        self.act_log.triggered.connect(self.open_log_requested.emit)

        self.menu.addSeparator()
        quit_txt = "Quit" if tr("save") == "Save" else "Esci"
        self.act_quit = self.menu.addAction(quit_txt)
        self.act_quit.triggered.connect(self.quit_requested.emit)

        self.tray.setContextMenu(self.menu)
        self.tray.activated.connect(self._on_activated)

    def update_widget_mode_label(self, in_widget_mode: bool) -> None:
        if in_widget_mode:
            self.act_pin.setText("Unpin from Desktop" if tr("save") == "Save" else "Sgancia dal desktop")
        else:
            self.act_pin.setText("Pin to Desktop (Widget)" if tr("save") == "Save" else "Aggancia al desktop (widget)")

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.show_requested.emit()

    def show(self) -> None:
        self.tray.show()

    def update_tooltip(self, text: str) -> None:
        self.tray.setToolTip(text)

    def update_state(self, temp: Optional[float], manual_mode: bool = False,
                     show_temp_number: Optional[bool] = None) -> None:
        """Refresh the tray icon to reflect current temp + manual mode state."""
        stn = self.show_temp_number if show_temp_number is None else show_temp_number
        self.tray.setIcon(icons.tray_icon(temp, manual_mode, show_temp_number=stn))

    # Backward-compat alias
    def update_icon_temp(self, temp: Optional[float]) -> None:
        self.update_state(temp, manual_mode=False)
