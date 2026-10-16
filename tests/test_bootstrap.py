"""Bootstrap replacement, backup and integrity regressions without downloads."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('portable_ide_bootstrap', ROOT / 'scripts/bootstrap.py')
bootstrap = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bootstrap)


class BootstrapTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.home = Path(directory.name) / 'home with spaces'
        self.home.mkdir()
        self.setup = bootstrap.Setup(self.home)
        runner = mock.patch.object(bootstrap, 'run')
        runner.start()
        self.addCleanup(runner.stop)

    def test_every_install_replaces_links_and_backs_up_previous_paths(self):
        target = self.home / '.config/btide/tmux.conf'
        target.parent.mkdir(parents=True)
        target.write_bytes(b'personal config\x00\n')
        target.chmod(0o640)
        self.setup.configure()
        first = next(target.parent.glob('tmux.conf.*.bak'))
        self.assertRegex(first.name, r'^tmux\.conf\.\d+\.bak$')
        self.assertEqual(first.read_bytes(), b'personal config\x00\n')
        self.assertEqual(first.stat().st_mode & 0o777, 0o640)
        self.setup.configure()
        backups = list(target.parent.glob('tmux.conf.*.bak'))
        self.assertEqual(len(backups), 2)
        self.assertEqual(first.read_bytes(), b'personal config\x00\n')
        for source, destination in self.setup.links:
            self.assertTrue(destination.is_symlink())
            self.assertEqual(destination.resolve(), source)

    def test_timestamp_collision_does_not_overwrite_a_backup(self):
        target = self.home / 'old_name.ext'
        target.write_text('old')
        with mock.patch.object(bootstrap.time, 'time_ns', return_value=123):
            self.setup.preserve(target)
            target.write_text('new')
            self.setup.preserve(target)
        self.assertEqual((self.home / 'old_name.ext.123.bak').read_text(), 'old')
        self.assertEqual((self.home / 'old_name.ext.124.bak').read_text(), 'new')

    def test_broken_symlink_is_backed_up_without_following_it(self):
        target = self.home / '.config/btide/tmux.conf'
        target.parent.mkdir(parents=True)
        missing = self.home / 'missing'
        target.symlink_to(missing)
        self.setup.configure()
        backup = next(target.parent.glob('tmux.conf.*.bak'))
        self.assertTrue(backup.is_symlink())
        self.assertEqual(backup.readlink(), missing)
        self.assertFalse(missing.exists())

    def test_existing_directory_is_backed_up(self):
        target = self.home / '.config/btide/nvim.conf'
        target.mkdir(parents=True)
        (target / 'init.lua').write_text('-- personal editor config\n')
        self.setup.configure()
        backup = next(target.parent.glob('nvim.*.bak'))
        self.assertEqual((backup / 'init.lua').read_text(), '-- personal editor config\n')
        self.assertEqual(target.resolve(), ROOT / 'config/nvim')

    def test_symlinked_installation_parent_is_refused_before_changes(self):
        outside = self.home / 'outside'
        outside.mkdir()
        (outside / 'keep').write_text('unchanged')
        (self.home / '.local').symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(RuntimeError, 'symlinked installation directory'):
            self.setup.configure()
        self.assertEqual(list(outside.iterdir()), [outside / 'keep'])
        self.assertFalse((self.home / '.tmux.conf').exists())

    def test_configure_does_not_download_or_provision_agent_state(self):
        private = self.home / '.pig/agent/auth.json'
        private.parent.mkdir(parents=True)
        private.write_text('private fixture')
        with mock.patch.object(bootstrap, 'open_url', side_effect=AssertionError('network')):
            self.setup.configure()
        self.assertEqual(private.read_text(), 'private fixture')
        self.assertFalse((self.setup.state / 'env.sh').exists())

    def test_receipt_rejects_changed_and_missing_outputs(self):
        output = self.home / 'binary'
        output.write_bytes(b'compiled')
        self.setup.receipt('fixture', 'identity', [output])
        self.assertTrue(self.setup.receipt_valid('fixture', 'identity', [output]))
        output.write_bytes(b'tampered')
        self.assertFalse(self.setup.receipt_valid('fixture', 'identity', [output]))
        output.unlink()
        self.assertFalse(self.setup.receipt_valid('fixture', 'identity', [output]))

    def test_check_does_not_execute_unverified_artifacts(self):
        spec = {'version': '99.0.0', 'asset': 'lazygit.tar.gz',
                'url': 'https://github.com/jesseduffield/lazygit/releases/download/v99.0.0/lazygit.tar.gz',
                'sha256': 'a' * 64}
        bootstrap.atomic_write(self.setup.release_path('lazygit'), json.dumps(spec))
        with mock.patch.object(self.setup, 'prerequisites', side_effect=AssertionError('executed')):
            with self.assertRaisesRegex(RuntimeError, 'Missing or changed installation'):
                self.setup.check()

    def test_only_minimum_versions_are_enforced(self):
        for name in ('bun', 'lazygit'):
            with self.subTest(name=name):
                self.setup.require_minimum(name, bootstrap.VERSIONS[name]['minimum_version'])
                self.setup.require_minimum(name, '999.0.0')
                with self.assertRaises(RuntimeError):
                    self.setup.require_minimum(name, '0.0.0')


if __name__ == '__main__':
    unittest.main()
