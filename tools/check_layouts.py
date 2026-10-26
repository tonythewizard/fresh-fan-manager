#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Exhaustively check all 4096 card visibility combinations on actual Qt layouts."""
from pathlib import Path
import sys
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QRect, QPoint
from core.config import Settings
from ui.main_window import MainWindow
from tools.demo_data import demo_snapshot

app = QApplication([])
sample = demo_snapshot()
with patch('core.config.save'), patch.object(MainWindow, '_tick'), \
     patch('core.mbpfan_ctrl.get_backend', return_value='applesmc'), \
     patch('core.sensors.read_fans', return_value=sample.fans):
    window = MainWindow(Settings(first_run_completed=True))
    window._timer.stop(); window._disk_timer.stop(); window.updates.timer.stop()
    window._available_geometry = lambda: QRect(0, 0, 1920, 9000)
    window.show(); window._render(sample); app.processEvents()
    slots = list(window.widgets.slots.values())
    count = len(slots)
    for combination in range(1 << count):
        for index, slot in enumerate(slots):
            slot.setVisible(bool(combination & (1 << index)))
        app.processEvents()
        window._update_min_height()
        window.resize(360, window.maximumHeight())
        app.processEvents()
        visible = [slot for slot in slots if not slot.isHidden()]
        if visible:
            last = visible[-1]
            viewport = window.scroll_area.viewport()
            bottom = last.mapTo(viewport, QPoint(0, last.height())).y()
            assert viewport.height()-bottom == window.scroll_layout.contentsMargins().bottom(), combination
            assert window.scroll_area.verticalScrollBar().maximum() == 0, combination
        assert window.width() == 360
        for height in (768, 900, 1080, 1440, 2160):
            with patch.object(window, '_available_geometry', return_value=QRect(0, 0, 1920, height)):
                stops = window._compute_widget_stops()
                assert 0 < stops[0] <= stops[-1] <= int(height*.95), (combination, height)
        if combination % 512 == 0:
            print(f'Validated {combination}/{1 << count} visibility combinations', flush=True)
    window.hide()
    print(f'PASS: all {1 << count} combinations; 5 work-area heights; exact final card margin.', flush=True)
