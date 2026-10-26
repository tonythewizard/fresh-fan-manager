# SPDX-License-Identifier: GPL-3.0-or-later
from dataclasses import replace
from pathlib import Path
import importlib.machinery
import importlib.util
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch
from core import config, mbpfan_ctrl
from core.daemon import HeadlessFanDaemon
from core.macsmc import decode_rpm, encode_rpm_fpe2
from core.runtime import ControlLease


class DaemonSafetyTests(unittest.TestCase):
    def setUp(self):
        self.settings = config.Settings(active_preset='Balanced')
        self.s = SimpleNamespace(cpu_temp_c=80, fans=[SimpleNamespace(index=1, manual=True)])
        self.patches = [patch('core.daemon.config.load', return_value=self.settings),
                        patch('core.daemon.sensors.snapshot', side_effect=lambda **_: self.s),
                        patch('core.daemon.mbpfan_ctrl.get_backend', return_value='applesmc'),
                        patch('core.daemon.mbpfan_ctrl.manual_off', return_value=(True, 'ok')),
                        patch('core.daemon.mbpfan_ctrl.manual_on', return_value=(True, 'ok'))]
        self.mocks = [p.start() for p in self.patches]
        self.addCleanup(lambda: [p.stop() for p in reversed(self.patches)])
        self.daemon = HeadlessFanDaemon()

    def test_safety_does_not_reapply_manual_in_same_tick(self):
        self.daemon._tick()
        self.mocks[3].assert_called_once_with(1)
        self.mocks[4].assert_not_called()

    def test_missing_sensor_restores_all_manual_fans(self):
        self.s.cpu_temp_c = None
        self.s.fans.append(SimpleNamespace(index=2, manual=True))
        self.daemon._tick()
        self.assertEqual(self.mocks[3].call_count, 2)
        self.mocks[4].assert_not_called()

    def test_failed_release_is_retried(self):
        self.mocks[3].return_value = (False, 'permission denied')
        self.daemon._tick()
        self.assertIn(1, self.daemon._owned_fans)
        self.daemon._tick()
        self.assertEqual(self.mocks[3].call_count, 2)

    def test_hysteresis_and_shutdown(self):
        self.daemon._tick()
        self.s.cpu_temp_c = self.settings.manual_safety_temp_c - 1
        self.daemon._tick()
        self.mocks[4].assert_not_called()
        self.s.cpu_temp_c = 45
        self.daemon._tick()
        self.mocks[4].assert_called_once()
        self.assertIn(1, self.daemon._owned_fans)
        self.assertTrue(self.daemon._restore_owned())
        self.assertFalse(self.daemon._owned_fans)

    def test_failed_target_not_cached(self):
        self.s.cpu_temp_c = 40
        self.mocks[4].return_value = (False, 'denied')
        self.daemon._tick()
        self.assertIsNone(self.daemon._last_rpm)
        self.daemon._tick()
        self.assertEqual(self.mocks[4].call_count, 2)

    def test_no_implicit_preset(self):
        self.s.cpu_temp_c = 40
        self.settings.active_preset = ''
        self.daemon._tick()
        self.mocks[4].assert_not_called()


class HelperAndBackendTests(unittest.TestCase):
    def test_pwm_mode_failure_aborts_target_write(self):
        with patch.object(mbpfan_ctrl, 'get_backend', return_value='hwmon_pwm'), \
             patch.object(mbpfan_ctrl, 'find_generic_pwm', return_value=('hwmon2', 1)), \
             patch.object(mbpfan_ctrl, '_run_helper', return_value=(False, 'denied')) as helper:
            self.assertFalse(mbpfan_ctrl.manual_on(2000)[0])
            helper.assert_called_once_with(['set-pwm-enable', 'hwmon2', '1', '1'])

    def test_untrusted_library_is_rejected(self):
        loader = importlib.machinery.SourceFileLoader('ffm_helper', str(Path(__file__).parents[1] / 'bin/macfan-helper'))
        spec = importlib.util.spec_from_loader(loader.name, loader)
        helper = importlib.util.module_from_spec(spec)
        loader.exec_module(helper)
        with tempfile.TemporaryDirectory() as directory:
            lib = Path(directory) / 'test.so'
            lib.write_bytes(b'not a library')
            lib.chmod(0o777)
            self.assertFalse(helper._trusted_library(lib))

    def test_fpe2_roundtrip(self):
        for rpm in (1200, 1500, 4500, 6500):
            self.assertEqual(decode_rpm(encode_rpm_fpe2(rpm)), rpm)
        self.assertIsNone(decode_rpm(None))

    def test_only_one_controller_lease(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict('os.environ', XDG_RUNTIME_DIR=directory):
            first, second = ControlLease(), ControlLease()
            try:
                self.assertTrue(first.acquire())
                self.assertFalse(second.acquire())
                first.release()
                self.assertTrue(second.acquire())
            finally:
                first.release()
                second.release()


class SensorAndCleanupTests(unittest.TestCase):
    def test_btrfs_and_nvme_root_devices(self):
        from core import sensors
        for source, expected in (('/dev/sda2[/@]', 'sda'), ('/dev/nvme0n1p2[/@root]', 'nvme0n1'), ('/dev/mmcblk0p2', 'mmcblk0')):
            with self.subTest(source=source), patch('core.sensors.subprocess.run', return_value=SimpleNamespace(stdout=source)):
                self.assertEqual(sensors._detect_primary_disk(), expected)

    def test_user_cleanup_unlinks_symlinks_without_following(self):
        from core.sys_actions import _clean_user_directory
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            cache, outside = base/'cache', base/'outside'
            cache.mkdir(); outside.mkdir()
            sentinel = outside/'keep.txt'; sentinel.write_text('keep')
            (cache/'link').symlink_to(outside, target_is_directory=True)
            (cache/'file').write_text('delete')
            _clean_user_directory(cache)
            self.assertTrue(sentinel.exists())
            self.assertFalse(list(cache.iterdir()))
            link = base/'root-link'; link.symlink_to(outside, target_is_directory=True)
            with self.assertRaises(ValueError): _clean_user_directory(link)

    def test_hwmon_traversal_rejected_before_filesystem_writes(self):
        loader = importlib.machinery.SourceFileLoader('ffm_helper_validation', str(Path(__file__).parents[1] / 'bin/macfan-helper'))
        spec = importlib.util.spec_from_loader(loader.name, loader)
        helper = importlib.util.module_from_spec(spec); loader.exec_module(helper)
        with patch.object(helper.Path, 'write_text') as write:
            for operation in (helper.cmd_set_pwm, helper.cmd_set_pwm_enable):
                with self.assertRaises(SystemExit): operation('../../tmp', '1', '1')
            write.assert_not_called()


class BackendPresetTests(unittest.TestCase):
    def test_vendor_presets_dispatch_to_expected_helper(self):
        cases = [('thinkpad', ['set-thinkpad-fan', '4']),
                 ('asus_wmi', ['set-asus-profile', '0']),
                 ('dell', ['set-dell-profile', 'balanced']),
                 ('macsmc', ['manual-on-macsmc', '1', '1500'])]
        for backend, expected in cases:
            with self.subTest(backend=backend), patch.object(mbpfan_ctrl, 'get_backend', return_value=backend), \
                 patch.object(mbpfan_ctrl, '_run_helper', return_value=(True, 'ok')) as helper:
                self.assertTrue(mbpfan_ctrl.apply_preset('Balanced')[0])
                helper.assert_called_once_with(expected)

    def test_firmware_preset_is_read_only(self):
        with patch.object(mbpfan_ctrl, 'get_backend', return_value='firmware'), \
             patch.object(mbpfan_ctrl, '_run_helper') as helper:
            self.assertTrue(mbpfan_ctrl.apply_preset('Silent')[0])
            helper.assert_not_called()
