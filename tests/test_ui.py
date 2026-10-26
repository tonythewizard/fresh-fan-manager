# SPDX-License-Identifier: GPL-3.0-or-later
"""Qt regression tests never authorize or write to hardware."""
import json
import unittest
from unittest.mock import patch
from PySide6.QtCore import QEvent, QPoint, QRect, QCoreApplication, QByteArray
from PySide6.QtWidgets import QApplication
from PySide6.QtNetwork import QNetworkReply, QNetworkRequest
from core import config, sensors, updates
from ui.main_window import MainWindow
from ui.styles import build_qss, THEME_PALETTES
from ui.preferences_dialog import PreferencesDialog


class QtFixture:
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.patchers = [patch('core.config.save'),
                         patch.object(MainWindow, '_tick'),
                         patch.object(MainWindow, '_notify'),
                         patch('core.mbpfan_ctrl.get_backend', return_value='macsmc'),
                         patch('core.mbpfan_ctrl.manual_off', return_value=(True, 'ok')),
                         patch('core.sensors.read_fans', return_value=[sensors.FanInfo(1, 'Fan', 1500, 1200, 6500)])]
        self.mocks = [p.start() for p in self.patchers]
        self.window = MainWindow(config.Settings(first_run_completed=True))
        self.window._timer.stop()
        self.window._disk_timer.stop()
        self.window.updates.timer.stop()
        self.window.show()
        self.app.processEvents()
        self.snapshot = sensors.Snapshot(0, 45, 45, fans=[sensors.FanInfo(1, 'Fan', 1500, 1200, 6500)])

    def tearDown(self):
        self.window.hide()
        self.window.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        for p in reversed(self.patchers):
            p.stop()

    def settle(self):
        self.app.processEvents()
        self.window._update_min_height()
        self.app.processEvents()


class UiTests(QtFixture, unittest.TestCase):
    def test_macsmc_override_is_enabled(self):
        self.window._render(self.snapshot)
        self.assertTrue(self.window._refs['fan']['toggle'].isEnabled())

    def test_failed_auto_preserves_watchdog_and_toggle(self):
        self.window._manual_mode = True
        self.mocks[4].return_value = (False, 'denied')
        self.window._toggle_manual(False)
        self.assertTrue(self.window.is_manual_mode())
        self.assertTrue(self.window._refs['fan']['toggle'].isChecked())

    def test_watchdog_operates_with_hidden_fan_widget(self):
        self.window.widgets.hide_section('fan')
        self.snapshot.cpu_temp_c = 85
        self.snapshot.fans[0].manual = True
        self.window._render(self.snapshot)
        self.mocks[4].assert_called_once_with(1)

    def test_missing_temperature_restores_auto(self):
        self.window._manual_mode = True
        self.snapshot.cpu_temp_c = None
        self.window._render(self.snapshot)
        self.mocks[4].assert_called_once()
        self.assertFalse(self.window.is_manual_mode())

    def test_stress_stops_on_temperature_or_sensor_loss(self):
        for temp in (95, None):
            with self.subTest(temp=temp), patch.object(self.window.stress, 'running', return_value=True), \
                 patch.object(self.window, '_stop_stress') as stop:
                self.snapshot.cpu_temp_c = temp
                self.window._render(self.snapshot)
                stop.assert_called_once()

    def test_no_network_on_default_schedule(self):
        with patch.object(self.window.updates.network, 'get') as get:
            self.window.updates.check_scheduled()
            get.assert_not_called()

    def test_preferences_save_update_schedule(self):
        dialog = PreferencesDialog(self.window.settings, self.window)
        dialog.cb_updates.setCurrentIndex(dialog.cb_updates.findData(168))
        dialog._save()
        self.assertEqual(self.window.settings.update_interval_hours, 168)
        dialog.deleteLater()

    def test_badge_and_changelog(self):
        release = updates.Release('v2.1.0', '## Fixes\nThermal safety.', updates.RELEASES_URL + '/tag/v2.1.0', ())
        self.window.updates.release = release
        self.window.title_bar.set_update_version(release.tag)
        self.assertFalse(self.window.title_bar.btn_update.isHidden())
        self.window.updates.show_release()
        self.assertIsNotNone(self.window.updates._dialog)
        self.window.updates._dialog.accept()
        self.assertIsNone(self.window.updates._dialog)

    def test_heights_modes_themes_and_reordering(self):
        # 768p through 4K are logical work areas; fractional scale checked in
        # separate make-test invocations using QT_SCALE_FACTOR.
        for height in (768, 900, 1080, 1440, 2160):
            with patch.object(self.window, '_available_geometry', return_value=QRect(0, 0, 1920, height)):
                for mode in ('essentials', 'all'):
                    self.window._set_view_mode(mode)
                    self.settle()
                    self.assertEqual(self.window.width(), 360)
                    self.assertLessEqual(self.window.height(), int(height * .95))
                    self.assertLessEqual(self.window.minimumHeight(), self.window.maximumHeight())
        for theme in THEME_PALETTES:
            self.window.settings.theme = theme
            self.app.setStyleSheet(build_qss(theme))
            self.window._apply_bg_overlay()
            self.window._render(self.snapshot)
            self.settle()
            self.assertEqual(self.window.width(), 360)
        self.window.widgets._on_move_requested('maintenance', 'cpu')
        self.window.widgets.set_edit_mode(True)
        self.settle()
        self.window.widgets.set_edit_mode(False)
        self.settle()
        self.assertEqual(next(iter(self.window.widgets.slots)), 'maintenance')

    def test_all_hidden_and_single_widget_have_valid_bounds(self):
        for key in self.window.settings.widget_visible:
            self.window.settings.widget_visible[key] = False
        self.window.widgets.set_view_mode('all')
        self.settle()
        self.assertGreater(self.window.minimumHeight(), 0)
        self.assertEqual(self.window.minimumHeight(), self.window.maximumHeight())
        self.window.widgets.show_section('cpu')
        self.settle()
        self.assertEqual(self.window.minimumHeight(), self.window.maximumHeight())

    def test_last_card_ends_at_bottom_without_extra_gap(self):
        with patch.object(self.window, '_available_geometry', return_value=QRect(0, 0, 1920, 9000)):
            self.window._set_view_mode('all')
            self.settle()
            self.window.resize(360, self.window.maximumHeight())
            self.settle()
            last = list(self.window.widgets.slots.values())[-1]
            viewport = self.window.scroll_area.viewport()
            bottom = last.mapTo(viewport, QPoint(0, last.height())).y()
            margin = self.window.scroll_layout.contentsMargins().bottom()
            self.assertEqual(viewport.height() - bottom, margin)
            self.assertEqual(self.window.scroll_area.verticalScrollBar().maximum(), 0)

    def test_snap_from_both_edges_uses_nearest_stop(self):
        with patch.object(self.window, '_available_geometry', return_value=QRect(0, 0, 1920, 9000)):
            self.settle()
            stops = self.window._compute_widget_stops()
            target = stops[1]
            self.window._resize_start_mouse = QPoint(100, 100)
            for edge in ('b', 't'):
                self.window._resize_start_geom = QRect(100, 100, 360, stops[0])
                self.window._resize_edge = edge
                delta = target + 6 - stops[0]
                self.window._do_resize(QPoint(100, 100 + (delta if edge == 'b' else -delta)))
                self.assertEqual(self.window.height(), target)
                self.assertEqual(self.window.width(), 360)


class FakeReply:
    def __init__(self, status, payload=b'', error=QNetworkReply.NetworkError.NoError):
        self.status, self.payload, self.err = status, payload, error
    def readAll(self):
        data, self.payload = self.payload, b''
        return QByteArray(data)
    def attribute(self, _): return self.status
    def error(self): return self.err
    def deleteLater(self): pass
    def abort(self): pass


class NetworkReplyTests(QtFixture, unittest.TestCase):
    # Inherit fixture, but only run network methods in this class.
    def test_release_and_failure_responses(self):
        controller = self.window.updates
        payload = dict(tag_name='v2.1.0', html_url=updates.RELEASES_URL+'/tag/v2.1.0', body='Notes', assets=[])
        for status, body, error in [
            (200, json.dumps(payload).encode(), QNetworkReply.NetworkError.NoError),
            (404, b'{}', QNetworkReply.NetworkError.ContentNotFoundError),
            (429, b'{}', QNetworkReply.NetworkError.UnknownContentError),
            (200, b'broken JSON', QNetworkReply.NetworkError.NoError),
            (None, b'', QNetworkReply.NetworkError.TimeoutError),
        ]:
            with self.subTest(status=status):
                controller.reply = FakeReply(status, body, error)
                controller._body.clear()
                controller._finished()
                self.assertIsNone(controller.reply)
        self.assertEqual(controller.release.tag, 'v2.1.0')


class FullRenderTests(QtFixture, unittest.TestCase):
    def test_all_cards_with_full_and_absent_telemetry(self):
        from tools.demo_data import demo_snapshot
        for sample in (demo_snapshot(), sensors.Snapshot(0, None, None)):
            self.window._render(sample)
            self.settle()
        self.assertEqual(len(self.window.widgets.slots), 12)
        self.assertEqual(self.window._refs['cpu']['temp'].text(), '—°')
        self.assertEqual(self.window._refs['ram']['lbl'].text(), '—')

    def test_fallback_workload_stop_terminates_children(self):
        import os
        import psutil
        from PySide6.QtTest import QTest
        from core.stress import StressTest
        workload = StressTest()
        finished = []
        workload.finished.connect(lambda *args: finished.append(args))
        with patch.object(StressTest, 'has_stress_ng', return_value=False), \
             patch.object(StressTest, 'has_stress', return_value=False), patch('core.stress.os.cpu_count', return_value=2):
            try:
                self.assertTrue(workload.start(3))
                group = workload._process_group
                QTest.qWait(80)
                children = psutil.Process(group).children()
                workload.stop()
                QTest.qWait(80)
                self.assertFalse(workload.running())
                self.assertEqual(len(finished), 1)
                for child in children:
                    self.assertTrue(not child.is_running() or child.status() == psutil.STATUS_ZOMBIE)
            finally:
                workload.stop()
                workload.deleteLater()

    def test_ui_watchdog_restores_multiple_fans(self):
        self.snapshot.cpu_temp_c = 85
        self.snapshot.fans = [sensors.FanInfo(i, f'Fan {i}', 1800, 1200, 6500, True) for i in (1, 2)]
        self.window._render(self.snapshot)
        self.assertEqual(self.mocks[4].call_count, 2)

    def test_oversized_release_response_is_aborted(self):
        controller = self.window.updates
        fake = FakeReply(200, b'x' * (updates.MAX_RESPONSE_BYTES + 1))
        with patch.object(fake, 'abort') as abort:
            controller.reply = fake
            controller._body.clear()
            controller._read()
            abort.assert_called_once()
            self.assertTrue(controller._too_large)
            controller._finished()
            self.assertIsNone(controller.reply)

    def test_release_notes_never_load_file_or_network_resources(self):
        from PySide6.QtCore import QUrl
        from ui.update_controller import ReleaseNotes
        notes = ReleaseNotes()
        for url in ('file:///etc/passwd', 'https://example.com/tracking.png'):
            self.assertTrue(notes.loadResource(2, QUrl(url)).isEmpty())
        notes.deleteLater()

    def test_absolute_network_deadline_aborts_a_stalled_response(self):
        controller = self.window.updates
        fake = FakeReply(None, error=QNetworkReply.NetworkError.TimeoutError)
        controller.reply = fake
        with patch.object(fake, 'abort') as abort:
            controller.deadline.timeout.emit()
            abort.assert_called_once()
        controller._finished()
        self.assertIsNone(controller.reply)
