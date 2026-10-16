"""Executable uninstall retains backups, tools, data and shell startup files."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class UninstallTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.home = Path(directory.name) / 'home with spaces'
        self.home.mkdir()
        self.launcher = self.home / '.local/bin/btide'
        self.launcher.parent.mkdir(parents=True)
        self.launcher.symlink_to(ROOT / 'config/btide.sh')
        self.env = dict(os.environ, HOME=str(self.home), PYTHONDONTWRITEBYTECODE='1')

    def run_uninstall(self):
        return subprocess.run([ROOT / 'uninstall.sh'], env=self.env, text=True, capture_output=True, timeout=10)

    def test_removal_and_repeat_preserve_startup_config_tools_and_backups(self):
        retained = [self.home / '.bashrc', self.home / '.zshrc',
                    self.home / '.config/fish/config.fish',
                    self.home / '.config/tm_ide/config.yml',
                    self.launcher.with_name('btide.123.bak'), self.launcher.parent / 'pig-plugins']
        for path in retained:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('retained fixture\n')
        result = self.run_uninstall()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(os.path.lexists(self.launcher))
        for path in retained:
            self.assertEqual(path.read_text(), 'retained fixture\n')
        self.assertEqual(self.run_uninstall().returncode, 0)

    def test_foreign_launcher_is_not_removed(self):
        foreign = self.home / 'personal-launcher'
        foreign.write_text('user launcher\n')
        for kind in ('file', 'symlink'):
            with self.subTest(kind=kind):
                self.launcher.unlink()
                if kind == 'file':
                    self.launcher.write_text('user launcher\n')
                else:
                    self.launcher.symlink_to(foreign)
                result = self.run_uninstall()
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('not owned', result.stderr)
                self.assertEqual(self.launcher.read_text(), 'user launcher\n')
                self.assertEqual(foreign.read_text(), 'user launcher\n')

    def test_symlinked_bin_parent_is_not_followed(self):
        directory = self.launcher.parent
        outside = self.home / 'outside-bin'
        directory.rename(outside)
        directory.symlink_to(outside, target_is_directory=True)
        result = self.run_uninstall()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('unsafe launcher parent', result.stderr)
        self.assertTrue((outside / 'btide').is_symlink())


if __name__ == '__main__':
    unittest.main()
