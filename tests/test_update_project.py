"""Consumer-visible reverse synchronization through the actual CLI."""
import importlib.util
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class UpdateProjectTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'repo'
        self.home = Path(self.temp.name) / 'home'
        self.root.mkdir()
        shutil.copytree(ROOT / 'config', self.root / 'config')
        (self.root / 'scripts').mkdir()
        for path in ('scripts/bootstrap.py', 'scripts/system_tools.py', 'scripts/releases.py',
                     'scripts/update.py', 'VERSION', 'versions.json', 'update-project.py'):
            shutil.copy2(ROOT / path, self.root / path)
        spec = importlib.util.spec_from_file_location('capture_bootstrap', self.root / 'scripts/bootstrap.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.setup = module.Setup(self.home)
        for source, target in self.setup.links:
            target.parent.mkdir(parents=True, exist_ok=True)
            if source.is_dir():
                shutil.copytree(source, target)
            else:
                shutil.copy2(source, target)

    def run_cli(self, *args):
        return subprocess.run([str(self.root / 'update-project.py'), '--home', str(self.home), *args],
                              capture_output=True, text=True)

    def test_update_artifacts_are_not_reverse_synchronized(self):
        for name in ('update.py', 'VERSION'):
            (self.home / '.config/btide' / name).write_text('not configuration\n')
        result = self.run_cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.root / 'scripts/update.py').read_bytes(),
                         (ROOT / 'scripts/update.py').read_bytes())
        self.assertEqual((self.root / 'VERSION').read_bytes(), (ROOT / 'VERSION').read_bytes())

    def test_changes_and_dry_run(self):
        target = self.home / '.config/btide/tmux.conf'
        original = (self.root / 'config/tmux/tmux.conf').read_text()
        target.write_text(original + '\n# captured change\n')
        skill_root, installed = self.root / 'config/nvim', self.home / '.config/btide/nvim.conf'
        (installed / 'new.txt').write_text('new skill instructions\n')
        dry = self.run_cli('--dry-run')
        self.assertEqual(dry.returncode, 0, dry.stderr)
        self.assertEqual((self.root / 'config/tmux/tmux.conf').read_text(), original)
        self.assertFalse((skill_root / 'new.txt').exists())
        result = self.run_cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.root / 'config/tmux/tmux.conf').read_text(), target.read_text())
        self.assertEqual((skill_root / 'new.txt').read_text(), 'new skill instructions\n')
        target.unlink()
        target.symlink_to(self.root / 'config/tmux/tmux.conf')
        self.assertEqual(self.run_cli().returncode, 0)

    def test_failures_do_not_discard_independent_changes(self):
        (self.home / '.config/btide/tmux.conf').unlink()
        skill_root, installed = self.root / 'config/nvim', self.home / '.config/btide/nvim.conf'
        secret = self.home / 'secret'
        secret.write_text('private')
        (installed / 'leak').symlink_to(secret)
        (installed / 'valid.txt').write_text('valid instructions')
        result = self.run_cli()
        self.assertEqual(result.returncode, 1)
        self.assertIn('Missing mapped file', result.stderr)
        self.assertIn('nested configuration symlink', result.stderr)
        self.assertFalse((skill_root / 'leak').exists())
        self.assertEqual((skill_root / 'valid.txt').read_text(), 'valid instructions')

    def test_private_paths_and_unmanaged_root_links_are_not_imported(self):
        skill_root, installed = self.root / 'config/nvim', self.home / '.config/btide/nvim.conf'
        (installed / 'credentials.json').write_text('private')
        (installed / 'node_modules').mkdir()
        (installed / 'node_modules/secret.txt').write_text('private')
        target = self.home / '.config/btide/tmux.conf'
        original = (self.root / 'config/tmux/tmux.conf').read_bytes()
        target.unlink()
        target.symlink_to(installed / 'credentials.json')
        result = self.run_cli()
        self.assertEqual(result.returncode, 1)
        self.assertIn('unmanaged source symlink', result.stderr)
        self.assertEqual((self.root / 'config/tmux/tmux.conf').read_bytes(), original)
        self.assertFalse((skill_root / 'credentials.json').exists())
        self.assertFalse((skill_root / 'node_modules').exists())
        shutil.rmtree(installed)
        installed.symlink_to(self.home, target_is_directory=True)
        result = self.run_cli()
        self.assertEqual(result.returncode, 1)
        self.assertIn(str(installed), result.stderr)

    def test_lazyvim_and_launcher_capture_with_safe_directory_traversal(self):
        nvim = self.home / '.config/btide/nvim.conf'
        plugin = nvim / 'lua/plugins/captured.lua'
        plugin.parent.mkdir(parents=True, exist_ok=True)
        plugin.write_text('return {}\n')
        (nvim / 'lazy-lock.json').write_text('{"fixture": {"commit": "abc"}}\n')
        secret = self.home / 'secret'
        secret.write_text('private')
        (nvim / 'leak.lua').symlink_to(secret)
        launcher = self.home / '.local/bin/btide'
        launcher.write_text(launcher.read_text() + '\n# local launcher change\n')
        dry = self.run_cli('--dry-run')
        self.assertEqual(dry.returncode, 1)
        self.assertFalse((self.root / 'config/nvim/lua/plugins/captured.lua').exists())
        result = self.run_cli()
        self.assertEqual(result.returncode, 1)
        self.assertIn('nested configuration symlink', result.stderr)
        self.assertFalse((self.root / 'config/nvim/leak.lua').exists())
        self.assertEqual((self.root / 'config/nvim/lua/plugins/captured.lua').read_text(), 'return {}\n')
        self.assertFalse((self.root / 'config/nvim/lazy-lock.json').exists())
        self.assertEqual((self.root / 'config/btide.sh').read_text(), launcher.read_text())


if __name__ == '__main__':
    unittest.main()
