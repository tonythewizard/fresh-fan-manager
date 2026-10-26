#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Render the actual Qt widgets with synthetic telemetry, without hardware writes."""
import os
from pathlib import Path
import sys
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
os.environ.setdefault('QT_SCALE_FACTOR', '2')
from PySide6.QtCore import QRect, QEvent, QCoreApplication
from PySide6.QtWidgets import QApplication
from core import config, sensors
from core.i18n import set_language
from ui.main_window import MainWindow
from ui.mini_window import MiniWindow
from ui.styles import build_qss
from tools.demo_data import demo_snapshot


def main():
    output = Path(__file__).resolve().parents[1] / 'docs/screenshots'
    output.mkdir(parents=True, exist_ok=True)
    app = QApplication([])
    set_language('en')
    sample = demo_snapshot()
    with patch('core.config.save'), patch.object(MainWindow, '_tick'), \
         patch('core.mbpfan_ctrl.get_backend', return_value='applesmc'), \
         patch('core.sensors.read_fans', return_value=sample.fans):
        for theme in ('dark', 'light', 'sepia', 'hicontrast', 'solarized_dark', 'solarized_light'):
            app.setStyleSheet(build_qss(theme))
            settings = config.Settings(first_run_completed=True, theme=theme, active_preset='Balanced')
            window = MainWindow(settings)
            window._timer.stop()
            window._disk_timer.stop()
            window.updates.timer.stop()
            window._available_geometry = lambda: QRect(0, 0, 1920, 5000)
            window.show()
            window._render(sample)
            app.processEvents()
            window._update_min_height()
            window.resize(360, window.maximumHeight())
            app.processEvents()
            window.grab().save(str(output / f'{theme}-all.png'))
            if theme == 'dark':
                window._set_view_mode('essentials')
                app.processEvents()
                window._render(sample)
                window._update_min_height()
                window.resize(360, window.maximumHeight())
                app.processEvents()
                window.grab().save(str(output / 'dark-essentials.png'))
                window.widgets.set_edit_mode(True)
                window.widgets._wiggle_timer.stop()
                window._render(sample)
                app.processEvents()
                window._update_min_height()
                window.resize(360, window.maximumHeight())
                app.processEvents()
                window.grab().save(str(output / 'dark-edit.png'))
                window.widgets.set_edit_mode(False)
                window.settings.widget_pinned = True
                window.enter_widget_mode()
                app.processEvents()
                window._update_min_height()
                window.grab().save(str(output / 'dark-widget.png'))
            window.hide()
            window.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        mini = MiniWindow()
        mini.update_values(sample.cpu_temp_c, sample.fans[0].rpm)
        mini.show()
        app.processEvents()
        mini.grab().save(str(output / 'mini.png'))
        mini.hide()
    print(f'Screenshots written to {output} (synthetic telemetry, 2× rendering).')


if __name__ == '__main__':
    main()
