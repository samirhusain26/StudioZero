"""Only the named app-icon derivatives may bypass the normal media folder rule."""
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('public_safety_check', Path(__file__).parents[1] / 'public_safety_check.py')
safety = importlib.util.module_from_spec(spec)
spec.loader.exec_module(safety)


class AppIconMediaTests(unittest.TestCase):
    def test_named_source_and_built_icons_are_allowed(self):
        with patch.object(safety, 'tracked', return_value=sorted(safety.APP_ICON_FILES)):
            self.assertEqual(safety.check(set())[1], [])

    def test_other_media_in_the_same_folders_is_still_rejected(self):
        names = ['publisher/ui/public/icons/screenshot.png',
                 'publisher/app/static/icons/studiozero-512.png.backup.png',
                 'publisher/app/static/upload.png', 'publisher/ui/public/cut.mp4']
        with patch.object(safety, 'tracked', return_value=names):
            findings = safety.check(set())[1]
        self.assertEqual([f[0] for f in findings], names)
        self.assertTrue(all(f[2] == 'media outside the licensed asset folders' for f in findings))


if __name__ == '__main__':
    unittest.main()
