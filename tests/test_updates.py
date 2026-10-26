# SPDX-License-Identifier: GPL-3.0-or-later
import unittest
from core import updates


def release(tag='v2.1.0', **kw):
    data = dict(tag_name=tag, html_url=updates.RELEASES_URL + '/tag/' + tag,
                body='## Changes\nFan safety fixes.', draft=False, prerelease=False, assets=[])
    data.update(kw)
    return data


class ReleaseTests(unittest.TestCase):
    def test_numeric_version_order(self):
        self.assertGreater(updates.stable_version('v2.10.0'), updates.stable_version('2.9.9'))
        self.assertEqual(updates.stable_version('2.0'), (2, 0, 0))
        self.assertFalse(updates.parse_release(release('v2.0.0')).newer)
        self.assertTrue(updates.parse_release(release()).newer)

    def test_reject_invalid_versions_and_prereleases(self):
        for tag in ('latest', 'v2.0.0-rc1', '2.0.0;id', '02.0.0'):
            with self.subTest(tag=tag), self.assertRaises(ValueError):
                updates.parse_release(release(tag))
        for flag in ('draft', 'prerelease'):
            with self.assertRaises(ValueError):
                updates.parse_release(release(**{flag: True}))

    def test_only_official_https_asset_urls(self):
        good = updates.RELEASES_URL + '/download/v2.1.0/fresh-fan-manager.deb'
        data = release(assets=[dict(name='fresh-fan-manager.deb', browser_download_url=good),
                               dict(name='bad.deb', browser_download_url='file:///tmp/bad'),
                               dict(name='bad.rpm', browser_download_url=good.replace('github.com', 'github.com.evil.test'))])
        self.assertEqual(updates.parse_release(data).assets, (('fresh-fan-manager.deb', good),))
        with self.assertRaises(ValueError):
            updates.parse_release(release(html_url='https://evil.test/release'))

    def test_opt_in_schedule_and_clock_rollback(self):
        self.assertFalse(updates.check_due(0, 0, 1e10))
        self.assertFalse(updates.check_due(24, 100, 101))
        self.assertTrue(updates.check_due(24, 100, 86500))
        self.assertTrue(updates.check_due(168, 1000, 900))


class CheckoutUpdateTests(unittest.TestCase):
    def test_dirty_checkout_is_never_discarded_or_updated(self):
        import shutil
        import subprocess
        import tempfile
        from pathlib import Path
        script = Path(__file__).parents[1] / 'tools/update_checkout.sh'
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'tools').mkdir()
            shutil.copy(script, root/'tools/update_checkout.sh')
            subprocess.run(['git', 'init', '-q', '-b', 'main', directory], check=True)
            sentinel = root/'keep.txt'; sentinel.write_text('uncommitted work')
            result = subprocess.run(['bash', str(root/'tools/update_checkout.sh')],
                                    input='\n', text=True, capture_output=True, timeout=5)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('local changes', result.stdout)
            self.assertEqual(sentinel.read_text(), 'uncommitted work')
