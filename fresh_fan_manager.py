#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Fresh Fan Manager — Linux fan and temperature control utility
# Copyright (C) 2025  Antonio Gullotta
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
"""
Fresh Fan Manager — entry point.

Usage:
  fresh-fan-manager              # normal window
  fresh-fan-manager --widget     # start pinned to the desktop (XWayland only)
  fresh-fan-manager --tray       # start hidden, tray only
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# Make local imports work when launched from any cwd
sys.path.insert(0, str(Path(__file__).resolve().parent))

APP_NAME = "Fresh Fan Manager"


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=APP_NAME)
    from core.version import __version__
    ap.add_argument("--version", action="version", version=f"{APP_NAME} {__version__}")
    ap.add_argument("--mini", action="store_true", help="Start in the compact floating window")
    ap.add_argument("--settings", action="store_true", help="Open preferences at startup")
    ap.add_argument("--widget", action="store_true",
                    help="Start pinned to the desktop as a widget (xcb only)")
    ap.add_argument("--tray", action="store_true",
                    help="Start hidden, only tray icon visible")
    ap.add_argument("--daemon", action="store_true",
                    help="Run headless background daemon (no GUI required)")
    return ap.parse_args()


# Parse CLI arguments early (handles --help, -h, and --daemon before any Qt imports)
_cli_args = parse_args()

if _cli_args.daemon:
    from core.daemon import HeadlessFanDaemon
    sys.exit(HeadlessFanDaemon().run())

# Read display server preference WITHOUT touching PySide6 yet, so we can set
# the QPA platform before Qt initializes.
from core.config import read_display_server_pref

_display_pref = read_display_server_pref()
if _display_pref == "wayland":
    os.environ.setdefault("QT_QPA_PLATFORM", "wayland;xcb")
else:
    os.environ.setdefault("QT_QPA_PLATFORM", "xcb")
os.environ.setdefault("QT_LOGGING_RULES", "qt.qpa.plugin=false")

try:
    from PySide6.QtCore import Qt, QTimer
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtWidgets import QApplication, QMessageBox, QSystemTrayIcon
except ImportError:
    sys.stderr.write(
        "Error: PySide6 is required for the graphical interface.\n"
        "Please run via the installed wrapper: fresh-fan-manager\n"
        "Or use: /opt/fresh-fan-manager/.venv/bin/python fresh_fan_manager.py\n"
        "For headless background control, use: fresh-fan-manager --daemon\n"
    )
    sys.exit(1)

# Honour fractional display scaling (KDE often uses 125%/150%). Default Qt
# rounding policy upscales at integer and then downsamples, producing jagged
# 1px borders on rounded widgets. PassThrough lets the compositor scale us
# without that artefact. Must be set BEFORE QApplication is constructed.
QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
    Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
)

# Make the process show up as 'fresh-fan-manager' in ps/top/htop instead of
# 'python3'. The kernel-level comm field is what most tools display.
try:
    import ctypes as _ctypes
    _libc = _ctypes.CDLL("libc.so.6", use_errno=True)
    _libc.prctl(15, b"fresh-fan-manager", 0, 0, 0)  # PR_SET_NAME = 15
except Exception:
    pass

from core import config, sensors, mbpfan_ctrl
from core.logger import get_logger
from core.i18n import tr
from ui.styles import build_qss
from ui.main_window import MainWindow, APP_NAME
from ui.tray import TrayController
from ui.tweaks_dialog import TweaksDialog
from ui.log_dialog import LogDialog
from ui.icons import app_icon


def main() -> int:
    args = _cli_args
    from core.runtime import ControlLease
    lease = ControlLease()
    if not lease.acquire():
        sys.stderr.write("Fresh Fan Manager GUI or daemon is already running.\n")
        return 1

    log = get_logger()
    log.info(f"{APP_NAME} starting (display={_display_pref})")

    # Set Qt-internal app metadata BEFORE QApplication so X11 WM_CLASS and
    # Wayland app-id are correct from the start.
    QApplication.setApplicationName(APP_NAME)
    QApplication.setApplicationDisplayName(APP_NAME)
    QApplication.setOrganizationName("freshfan")
    QApplication.setDesktopFileName("fresh-fan-manager")

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    app.setOrganizationName("freshfan")
    app.setDesktopFileName("fresh-fan-manager")
    app.setQuitOnLastWindowClosed(False)
    app.setWindowIcon(app_icon())

    if not QSystemTrayIcon.isSystemTrayAvailable():
        QMessageBox.critical(None, "Tray non disponibile",
                             f"Il system tray non è disponibile.\n"
                             f"{APP_NAME} continua comunque, ma 'chiudi' uscirà davvero.")

    settings = config.load()
    if args.mini:
        settings.mini_mode = True
    app.setStyleSheet(build_qss(settings.theme, settings.fx_level, settings.bg_effect))

    # If user selected Wayland but is requesting --widget, downgrade and warn
    if args.widget and _display_pref == "wayland":
        log.warning("Widget mode requested under Wayland — ignoring (limitation)")

    start_widget = (args.widget or settings.widget_pinned) and _display_pref == "xcb"

    win = MainWindow(settings, start_in_widget_mode=start_widget)
    tray = TrayController(show_temp_number=getattr(settings, "tray_show_temp", True))

    # Keep app icon live in sync with temperature so the taskbar icon shifts
    # color the same way as the tray icon
    def on_temp_updated(temp):
        try:
            new_icon = app_icon(temp)
            app.setWindowIcon(new_icon)
            win.setWindowIcon(new_icon)
            tray.update_state(temp, manual_mode=win.is_manual_mode(),
                              show_temp_number=getattr(settings, "tray_show_temp", True))
        except Exception:
            pass

    win.temp_updated.connect(on_temp_updated)

    # ----- wire signals -----
    tray.show_requested.connect(lambda: (win.show(), win.raise_(), win.activateWindow()))
    tray.toggle_widget_requested.connect(win.toggle_widget_mode)
    tray.open_log_requested.connect(lambda: LogDialog(win).exec())
    tray.open_tweaks_requested.connect(lambda: _open_tweaks(win))
    tray.preset_requested.connect(lambda name: _apply_preset(win, name))
    win.widget_mode_changed.connect(tray.update_widget_mode_label)
    QTimer.singleShot(200, lambda: tray.update_widget_mode_label(win._widget_mode))

    def quit_app() -> None:
        log.info("quit requested")
        try:
            fans = sensors.read_fans()
            indices = {f.index for f in fans if f.manual}
            if win.is_manual_mode():
                indices.add(1)
            for index in indices:
                ok, message = mbpfan_ctrl.manual_off(index)
                if not ok:
                    QMessageBox.critical(win, "Fresh Fan Manager", tr("fan_auto_failed", error=message))
                    return
        except Exception as exc:
            log.error(f"Fan shutdown check failed: {exc}")
            if win.is_manual_mode():
                return
        config.save(win.settings)
        try:
            win._timer.stop()
            win._disk_timer.stop()
            win.stress.stop()
        except Exception:
            pass
        tray.tray.hide()
        app.quit()

    tray.quit_requested.connect(quit_app)
    win.quit_requested.connect(quit_app)
    if not QSystemTrayIcon.isSystemTrayAvailable():
        win.title_bar.close_requested.disconnect()
        win.title_bar.close_requested.connect(quit_app)

    # Tray refresh
    refresh_timer = QTimer()
    refresh_timer.setInterval(2000)

    def refresh_tray() -> None:
        try:
            s = sensors.snapshot(include_top_processes=False)
            temp = s.cpu_temp_c
            fan_rpm = s.fans[0].rpm if s.fans else None
            manual = win.is_manual_mode()
            tip = APP_NAME
            if manual:
                tip += "  ·  MANUAL"
            if temp is not None:
                tip += f"  ·  {temp:.0f}°C"
            if fan_rpm is not None:
                tip += f"  ·  {fan_rpm} RPM"
            if s.cpu_percent_total:
                tip += f"  ·  CPU {s.cpu_percent_total:.0f}%"
            tray.update_tooltip(tip)
            tray.update_state(temp, manual_mode=manual,
                              show_temp_number=getattr(settings, "tray_show_temp", True))
        except Exception as e:
            log.error(f"tray refresh error: {e}")

    refresh_timer.timeout.connect(refresh_tray)
    refresh_timer.start()
    refresh_tray()

    tray.show()

    if args.tray:
        win.hide()
    else:
        win.show()

    if args.settings:
        QTimer.singleShot(600, win._open_preferences)
    QTimer.singleShot(400, lambda: _first_run_check(win, tray, log))
    result = app.exec()
    lease.release()
    return result


def _first_run_check(win: MainWindow, tray: TrayController, log) -> None:
    settings = win.settings
    if not getattr(settings, "first_run_completed", False):
        from ui.onboarding_dialog import OnboardingDialog
        dlg = OnboardingDialog(win, settings)
        if dlg.exec():
            log.info(f"First-run onboarding completed: lang={settings.language}, tray_show_temp={settings.tray_show_temp}")
            try:
                s = sensors.snapshot(include_top_processes=False)
                tray.update_state(s.cpu_temp_c, manual_mode=win.is_manual_mode(),
                                  show_temp_number=settings.tray_show_temp)
            except Exception:
                pass

    backend = mbpfan_ctrl.get_backend()
    log.info(f"Cooling backend detected: {backend}")
    if backend != "mbpfan":
        return
    status = mbpfan_ctrl.service_status()
    if status == "failed":
        log.warning("mbpfan service is in failed state at startup")
        msg = QMessageBox(win)
        msg.setWindowTitle("mbpfan error")
        msg.setText("The mbpfan service is in failed state.\n"
                    "Would you like to try restarting it now?")
        msg.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if msg.exec() == QMessageBox.StandardButton.Yes:
            ok, out = mbpfan_ctrl.restart_service()
            log.info(f"Restart attempt at startup: ok={ok} msg={out}")


def _apply_preset(win: MainWindow, name: str) -> None:
    log = get_logger()
    if not mbpfan_ctrl.can_control_fan() and mbpfan_ctrl.get_backend() == "firmware":
        QMessageBox.information(win, "Fresh Fan Manager", "Fan is managed by system firmware.")
        return
    win._apply_preset(name)


def _open_tweaks(win: MainWindow) -> None:
    fans = sensors.read_fans()
    fmin = fans[0].min_rpm if fans else 1200
    fmax = fans[0].max_rpm if fans else 6500
    TweaksDialog(win, fan_min=fmin, fan_max=fmax).exec()


if __name__ == "__main__":
    sys.exit(main())
