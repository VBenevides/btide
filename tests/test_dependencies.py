"""Dependency fallback regressions without network or workstation executables."""
import hashlib
import importlib.util
import io
import os
from pathlib import Path
import shlex
import subprocess
import tarfile
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('portable_ide_dependencies', ROOT / 'scripts/bootstrap.py')
bootstrap = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bootstrap)


class DependencyTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.home = self.root / 'home with spaces'
        self.home.mkdir()
        self.tools = self.root / 'system bin'
        self.tools.mkdir()
        environment = mock.patch.dict(os.environ, PATH=str(self.tools), HOME=str(self.home))
        environment.start()
        self.addCleanup(environment.stop)
        self.setup = bootstrap.Setup(self.home)
        self.setup.bin.mkdir(parents=True)
        self.setup.state.mkdir(parents=True)
        self.target = self.setup.bin / 'lazygit'
        self.receipt = self.setup.state / 'receipts/lazygit.json'
        self.payload = self.archive('lazygit', b'#!/bin/sh\nprintf "lazygit fixture 1.0\\n"\n')
        self.sha = hashlib.sha256(self.payload).hexdigest()
        self.spec = {'version': '1.0.0', 'asset': 'lazygit-fixture.tar',
                     'url': 'https://github.com/jesseduffield/lazygit/releases/download/v1.0.0/lazygit-fixture.tar',
                     'sha256': self.sha}
        resolver = mock.patch.object(bootstrap, 'resolve_release', side_effect=lambda *args: dict(self.spec))
        resolver.start()
        self.addCleanup(resolver.stop)
        machine = mock.patch.object(bootstrap.platform, 'machine', return_value='x86_64')
        machine.start()
        self.addCleanup(machine.stop)

    @staticmethod
    def archive(name, data):
        stream = io.BytesIO()
        with tarfile.open(fileobj=stream, mode='w', format=tarfile.USTAR_FORMAT) as archive:
            member = tarfile.TarInfo(name)
            member.size = len(data)
            member.mode = 0o755
            member.mtime = 0
            archive.addfile(member, io.BytesIO(data))
        return stream.getvalue()

    def script(self, name, body):
        path = self.tools / name
        path.write_text('#!/bin/sh\n' + body)
        path.chmod(0o755)
        return path

    def apt_fixture(self):
        marker = self.root / 'packages-installed'
        self.script('sudo', 'exec "$@"\n')
        self.script('apt-get',
                    'for package in "$@"; do\n'
                    '  if [ "$package" = lazygit ]; then\n'
                    '    printf "Unable to locate package lazygit\\n" >&2\n'
                    '    exit 100\n'
                    '  fi\n'
                    'done\n'
                    'if [ "$1" = install ]; then\n'
                    '  printf "installed\\n" > ' + shlex.quote(str(marker)) + '\n'
                    'fi\n')
        return marker

    def download_fixture(self, payload=None):
        payload = self.payload if payload is None else payload
        return mock.patch.object(bootstrap, 'open_url',
                                 side_effect=lambda *args, **kwargs: io.BytesIO(payload))

    def assert_installed(self, setup=None):
        setup = setup or self.setup
        output = subprocess.check_output([self.target, '--version'], env=setup.env, text=True)
        self.assertEqual(output, 'lazygit fixture 1.0\n')
        self.assertTrue(setup.receipt_valid('lazygit', setup.release_identity(self.spec),
                                            setup.archive_outputs('lazygit')))

    def test_apt_without_lazygit_package_installs_verified_fallback_and_reuses_it(self):
        marker = self.apt_fixture()
        bootstrap.install_dependencies()
        self.assertEqual(marker.read_text(), 'installed\n')
        with self.download_fixture():
            self.setup.install_lazygit()
        self.assert_installed()
        binary_before = self.target.stat()
        receipt_before = self.receipt.read_bytes()
        with mock.patch.object(bootstrap, 'open_url',
                               side_effect=AssertionError('A verified rerun must not download')):
            self.setup.install_lazygit()
        self.assert_installed()
        self.assertEqual(self.target.stat().st_ino, binary_before.st_ino)
        self.assertEqual(self.target.stat().st_mtime_ns, binary_before.st_mtime_ns)
        self.assertEqual(self.receipt.read_bytes(), receipt_before)

    def test_old_system_lazygit_is_preserved_but_latest_managed_release_is_installed(self):
        existing = self.script('lazygit', 'printf "old system lazygit\\n"\n')
        before = existing.read_bytes()
        with self.download_fixture():
            self.setup.install_lazygit()
        self.assertEqual(existing.read_bytes(), before)
        self.assert_installed()

    def test_checksum_mismatch_does_not_install_or_record_success(self):
        with self.download_fixture(self.payload + b'corruption'):
            with self.assertRaises(RuntimeError):
                self.setup.install_lazygit()
        self.assertFalse(self.target.exists())
        self.assertFalse(self.receipt.exists())

    def test_oversized_expanded_binary_is_rejected_before_cutover(self):
        member = tarfile.TarInfo('lazygit')
        member.size = 1024**3
        payload = member.tobuf() + b'\0' * 1024
        self.spec['sha256'] = hashlib.sha256(payload).hexdigest()
        with self.download_fixture(payload), self.assertRaisesRegex(RuntimeError, 'bounded'):
            self.setup.install_lazygit()
        self.assertFalse(self.target.exists())
        self.assertFalse(self.receipt.exists())

    def test_verified_archive_without_lazygit_does_not_install_or_record_success(self):
        payload = self.archive('README', b'No executable here\n')
        self.spec['sha256'] = hashlib.sha256(payload).hexdigest()
        with self.download_fixture(payload):
            with self.assertRaises(RuntimeError):
                self.setup.install_lazygit()
        self.assertFalse(self.target.exists())
        self.assertFalse(self.receipt.exists())

    def test_conflicting_file_is_automatically_backed_up_and_replaced(self):
        original = b'user-owned non-executable file\x00\n'
        self.target.write_bytes(original)
        with self.download_fixture():
            self.setup.install_lazygit()
        backups = list(self.setup.bin.glob('lazygit.*.bak'))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_bytes(), original)
        self.assert_installed(self.setup)

    def test_failed_replacement_does_not_execute_or_discard_changed_binary(self):
        with self.download_fixture():
            self.setup.install_lazygit()
        executed = self.root / 'tampered-executed'
        self.target.write_text('#!/bin/sh\nprintf "executed\\n" > ' + shlex.quote(str(executed)) + '\n')
        original = self.target.read_bytes()
        receipt_before = self.receipt.read_bytes()
        with self.download_fixture(b'invalid download'):
            with self.assertRaisesRegex(RuntimeError, 'SHA-256 mismatch'):
                self.setup.install_lazygit()
        self.assertFalse(executed.exists())
        self.assertEqual(self.target.read_bytes(), original)
        self.assertEqual(self.receipt.read_bytes(), receipt_before)
        self.assertFalse(list(self.setup.bin.glob('lazygit.*.bak')))

    def test_prerequisites_do_not_require_zsh(self):
        with mock.patch.object(bootstrap, 'check_managed_tools'), \
                mock.patch.object(self.setup, 'executable', return_value='fixture') as executable, \
                mock.patch.object(self.setup, 'require_minimum'), \
                mock.patch.object(self.setup, 'editor_prerequisites'):
            self.setup.prerequisites()
        self.assertNotIn('zsh', [call.args[0] for call in executable.call_args_list])

    def test_package_managers_do_not_install_zsh(self):
        for manager in ('apt-get', 'dnf', 'pacman'):
            with self.subTest(manager=manager), \
                    mock.patch.object(bootstrap.shutil, 'which', side_effect=lambda name: name == manager), \
                    mock.patch.object(bootstrap, 'run') as run:
                bootstrap.install_dependencies()
                self.assertTrue(run.called)
                for call in run.call_args_list:
                    self.assertNotIn('zsh', call.args[0])

    def test_prerequisites_never_execute_tampered_managed_lazygit(self):
        with self.download_fixture():
            self.setup.install_lazygit()
        executed = self.root / 'tampered-prerequisite-executed'
        self.target.write_text('#!/bin/sh\nprintf "executed\\n" > ' +
                               shlex.quote(str(executed)) + '\n')
        for name, version in [('git', 'git version 2.0'), ('go', 'go version go1.23.0 linux/amd64'),
                              ('node', 'v20.0.0'), ('tmux', 'tmux 3.5'),
                              ('nvim', 'NVIM v0.11.2'), ('ranger', 'ranger version: 1.9.4'),
                              ('rg', 'ripgrep 14'), ('fd', 'fd 10'), ('cc', 'cc 14')]:
            self.script(name, 'printf "%s\\n" ' + shlex.quote(version) + '\n')
        with self.assertRaises(RuntimeError):
            self.setup.prerequisites()
        self.assertFalse(executed.exists())


if __name__ == '__main__':
    unittest.main()
