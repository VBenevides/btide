"""Executable launcher, untouched startup files and editor-completion regressions."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import bootstrap


class ShellInstallTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.home = Path(temporary.name) / 'home with spaces'
        self.home.mkdir()
        self.setup = bootstrap.Setup(self.home)
        self.setup.state.mkdir(parents=True)

    def test_shell_startup_files_and_modes_are_unchanged(self):
        paths = [self.home / name for name in ('.bashrc', '.zshrc', '.profile', '.p10k.zsh', '.config/fish/config.fish')]
        for path in paths:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b'# personal configuration\xff\n')
            path.chmod(0o640)
        before = {path: (path.read_bytes(), path.stat()) for path in paths}
        self.setup.configure()
        self.setup.configure()
        for path, (content, stat) in before.items():
            self.assertEqual(path.read_bytes(), content)
            self.assertEqual(path.stat().st_mode, stat.st_mode)
            self.assertEqual(path.stat().st_ino, stat.st_ino)
            self.assertEqual(path.stat().st_mtime_ns, stat.st_mtime_ns)

    def test_startup_symlinks_are_not_followed_or_replaced(self):
        outside = self.home / 'personal-shell-config'
        outside.write_text('# personal\n')
        (self.home / '.bashrc').symlink_to(outside)
        self.setup.configure()
        self.assertTrue((self.home / '.bashrc').is_symlink())
        self.assertEqual(outside.read_text(), '# personal\n')
        self.assertFalse((self.home / '.zshrc').exists())
        self.assertFalse((self.home / '.btide.sh').exists())

    def test_installed_command_runs_from_bash_zsh_and_fish_without_sourcing(self):
        self.setup.configure()
        launcher = self.setup.bin / 'btide'
        self.assertTrue(launcher.is_symlink())
        for shell in ('bash', 'zsh', 'fish'):
            if not shutil.which(shell):
                continue
            with self.subTest(shell=shell):
                result = subprocess.run([shell, '-c', 'btide --help'], env=self.setup.env,
                                        text=True, capture_output=True, timeout=10)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn('Usage: btide', result.stdout)

    def test_launcher_replacement_preserves_existing_script_and_backup(self):
        launcher = self.setup.bin / 'btide'
        launcher.parent.mkdir(parents=True)
        launcher.write_text('#!/bin/sh\necho personal launcher\n')
        launcher.chmod(0o750)
        self.setup.configure()
        backup = next(launcher.parent.glob('btide.*.bak'))
        self.assertEqual(backup.read_text(), '#!/bin/sh\necho personal launcher\n')
        self.assertEqual(backup.stat().st_mode & 0o777, 0o750)
        self.assertEqual(launcher.resolve(), bootstrap.ROOT / 'config/btide.sh')

    def test_missing_editor_output_cannot_be_recorded_as_complete(self):
        self.setup.configure()
        with mock.patch.object(bootstrap, 'run') as run:
            def incomplete(*args, **kwargs):
                Path(kwargs['env']['PORTABLE_IDE_NVIM_REPORT']).write_text('{"plugins": {}}')
            run.side_effect = incomplete
            with self.assertRaisesRegex(RuntimeError, 'package output is missing'):
                self.setup.install_editor()
        self.assertFalse((self.setup.state / 'receipts/nvim.json').exists())

    def test_editor_receipt_rejects_missing_and_changed_required_tools(self):
        self.setup.editor_tools = {'fixture': ['fixture-tool']}
        plugin = self.setup.editor_data / 'lazy/fixture'
        plugin.mkdir(parents=True)
        subprocess.run(['git', 'init', '-q', plugin], check=True)
        subprocess.run(['git', '-C', plugin, '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
                        'commit', '--allow-empty', '-qm', 'fixture'], check=True)
        commit = subprocess.check_output(['git', '-C', plugin, 'rev-parse', 'HEAD'], text=True).strip()
        report = self.setup.state / 'nvim-install.json'
        report.write_text(json.dumps({'plugins': {'fixture': {'directory': str(plugin), 'commit': commit}},
                                     'parsers': ['fixture']}))
        content = report.read_text()
        outputs = self.setup.editor_outputs()
        for output in outputs:
            output.parent.mkdir(parents=True, exist_ok=True)
            if output != report:
                output.write_text('fixture')
        binary = self.setup.editor_binaries()[0]
        binary.chmod(0o755)
        target = self.setup.editor_data / 'mason/packages/fixture/bin/fixture-tool'
        target.parent.mkdir(parents=True)
        binary.rename(target)
        binary.symlink_to(target)
        outputs = self.setup.editor_outputs()
        report.write_text(content)
        self.setup.receipt('nvim', self.setup.editor_identity(), outputs)
        self.assertTrue(self.setup.editor_valid())
        binary.write_text('changed')
        self.assertFalse(self.setup.editor_valid())
        binary.unlink()
        self.assertFalse(self.setup.editor_valid())
        outside = self.home / 'unmanaged-tool'
        outside.write_text('fixture')
        outside.chmod(0o755)
        binary.symlink_to(outside)
        self.assertFalse(self.setup.editor_valid())


if __name__ == '__main__':
    unittest.main()
