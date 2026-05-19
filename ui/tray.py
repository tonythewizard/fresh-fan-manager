"""
System tray icon + context menu. The tray menu is the single source of truth
for quitting the application (right-click → Esci).
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QSystemTrayIcon, QMenu, QApplication

from . import icons


class TrayController(QObject):
    show_requested = Signal()
    hide_requested = Signal()
    toggle_widget_requested = Signal()
    quit_requested = Signal()
    preset_requested = Signal(str)
    open_log_requested = Signal()
    open_tweaks_requested = Signal()

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self.tray = QSystemTrayIcon(icons.tray_icon())
        self.tray.setToolTip("Fresh Fan Manager")

        self.menu = QMenu()
        self.act_show = self.menu.addAction("Mostra finestra")
        self.act_show.triggered.connect(self.show_requested.emit)

        self.act_pin = self.menu.addAction("Aggancia al desktop (widget)")
        self.act_pin.triggered.connect(self.toggle_widget_requested.emit)

        self.menu.addSeparator()

        preset_menu = self.menu.addMenu("Preset ventola")
        for name in ("Silent", "Balanced", "Performance"):
            act = preset_menu.addAction(name)
            act.triggered.connect(lambda _=False, n=name: self.preset_requested.emit(n))

        self.act_tweaks = self.menu.addAction("Modifica tweak…")
        self.act_tweaks.triggered.connect(self.open_tweaks_requested.emit)

        self.menu.addSeparator()
        self.act_log = self.menu.addAction("Mostra log")
        self.act_log.triggered.connect(self.open_log_requested.emit)

        self.menu.addSeparator()
        self.act_quit = self.menu.addAction("Esci")
        self.act_quit.triggered.connect(self.quit_requested.emit)

        self.tray.setContextMenu(self.menu)
        self.tray.activated.connect(self._on_activated)

    def update_widget_mode_label(self, in_widget_mode: bool) -> None:
        if in_widget_mode:
            self.act_pin.setText("Sgancia dal desktop (torna a finestra)")
        else:
            self.act_pin.setText("Aggancia al desktop (widget)")

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.show_requested.emit()

    def show(self) -> None:
        self.tray.show()

    def update_tooltip(self, text: str) -> None:
        self.tray.setToolTip(text)

    def update_state(self, temp: Optional[float], manual_mode: bool = False) -> None:
        """Refresh the tray icon to reflect current temp + manual mode state."""
        self.tray.setIcon(icons.tray_icon(temp, manual_mode))

    # Backward-compat alias
    def update_icon_temp(self, temp: Optional[float]) -> None:
        self.update_state(temp, manual_mode=False)
