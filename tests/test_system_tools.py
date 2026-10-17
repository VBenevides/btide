import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import system_tools


class FixtureSetup:
    def __init__(self, home):
        self.home = Path(home)
        self.state = self.home / 'state'
        self.bin = self.home / 'bin'
        self.env = {'PATH': str(self.bin)}
        self.backup = False
        self.records = {}
        self.commands = []

    def command(self, args, **kwargs):
        self.commands.append(args)
        if args == ['make', '-j2']:
            path = Path(kwargs['cwd']) / 'tmux'
            path.write_text('tmux executable')
            path.chmod(0o755)
        return subprocess.CompletedProcess(args, 0, 'v99.0.0')

    def preserve(self, path):
        if not self.backup:
            raise RuntimeError('conflict')
        path.rename(path.with_name(path.name + '.backup'))

    def hashes(self, outputs):
        if any(p.is_symlink() for p in outputs):
            raise RuntimeError('receipt outputs must be regular files')
        return {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in outputs}

    def receipt(self, name, identity, outputs):
        self.records[name] = (identity, self.hashes(outputs))

    def receipt_valid(self, name, identity, outputs):
        try:
            return self.records.get(name) == (identity, self.hashes(outputs))
        except OSError:
            return False


def atomic_write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


class SystemToolsTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.setup = FixtureSetup(self.temporary.name)
        self.versions = json.loads((Path(__file__).resolve().parents[1] / 'versions.json').read_text())
        self.specs = {name: {'version': '99.0.0', 'url': 'https://go.dev/dl/fixture.tar.gz',
                             'sha256': 'a' * 64, 'asset': 'fixture.tar.gz'}
                      for name in system_tools.TOOLS}
        resolver = patch.object(system_tools, 'resolve_release', side_effect=lambda name, arch: self.specs[name])
        resolver.start()
        self.addCleanup(resolver.stop)

    def archive(self, name, destination, missing=None):
        with tarfile.open(destination, 'w:gz') as archive:
            required = system_tools.TOOLS[name][2]
            for relative in required:
                if relative == missing:
                    continue
                member = tarfile.TarInfo('runtime/' + relative)
                content = ('fixture ' + relative).encode()
                member.size = len(content)
                member.mode = 0o755 if relative.startswith('bin/') else 0o644
                archive.addfile(member, io.BytesIO(content))

    def install(self, name, missing=None):
        def download(url, path, expected):
            self.archive(name, path, missing)
        with patch.object(system_tools, '_compatible', side_effect=lambda setup, tool, minimum=None: tool != name):
            system_tools.ensure_compatible_tools(self.setup, self.versions, download, atomic_write)

    def test_extraction_preserves_generated_build_file_timestamps(self):
        archive = Path(self.temporary.name) / 'source.tar'
        destination = Path(self.temporary.name) / 'source'
        with tarfile.open(archive, 'w') as tar:
            for name, timestamp in [('configure', 200), ('configure.ac', 100)]:
                content = b'fixture\n'
                member = tarfile.TarInfo('tmux/' + name)
                member.size = len(content)
                member.mtime = timestamp
                tar.addfile(member, io.BytesIO(content))
        system_tools._extract(archive, destination)
        source = destination / 'tmux'
        self.assertEqual((source / 'configure').stat().st_mtime, 200)
        self.assertEqual((source / 'configure.ac').stat().st_mtime, 100)

    def test_compatible_executables_are_preserved(self):
        with patch.object(system_tools, '_compatible', return_value=True):
            system_tools.ensure_compatible_tools(self.setup, self.versions,
                                                 lambda *args: self.fail('downloaded compatible tool'), atomic_write)
        self.assertFalse(self.setup.state.exists())

    def test_existing_old_versions_do_not_resolve_or_download_releases(self):
        with patch.object(system_tools.shutil, 'which', return_value='/fixture/tool'), \
                patch.object(self.setup, 'command', return_value=subprocess.CompletedProcess([], 0, '0.1.0')), \
                patch.object(system_tools, 'resolve_release', side_effect=AssertionError('network')):
            system_tools.ensure_compatible_tools(self.setup, self.versions,
                                                 lambda *args: self.fail('download'), atomic_write)
        self.assertFalse(self.setup.state.exists())

    def test_missing_tools_receive_complete_reusable_runtime(self):
        for name in ('go', 'node', 'nvim', 'tmux'):
            with self.subTest(name=name):
                self.install(name)
                system_tools.check_managed_tools(self.setup, self.versions)
                self.assertTrue((self.setup.bin / name).is_symlink())
                root = self.setup.state / 'system-tools' / name
                self.assertTrue(all((root / entry).is_file() for entry in system_tools.TOOLS[name][2]))
        with patch.object(system_tools, '_compatible', side_effect=AssertionError('managed tool probed')):
            system_tools.ensure_compatible_tools(self.setup, self.versions,
                                                 lambda *args: self.fail('redownload'), atomic_write)

    def test_incomplete_runtime_has_no_receipt_or_cutover(self):
        with self.assertRaisesRegex(RuntimeError, 'Incomplete'):
            self.install('node', 'lib/node_modules/npm/package.json')
        self.assertFalse(self.setup.records)
        self.assertFalse((self.setup.bin / 'node').exists())

    def test_download_failure_has_no_receipt(self):
        def failure(*args):
            raise RuntimeError('checksum mismatch')
        with patch.object(system_tools, '_compatible', return_value=False):
            with self.assertRaisesRegex(RuntimeError, 'checksum'):
                system_tools.ensure_compatible_tools(self.setup, self.versions, failure, atomic_write)
        self.assertFalse(self.setup.records)

    def test_companion_tampering_is_rejected_without_execution(self):
        self.install('node')
        (self.setup.state / 'system-tools/node/lib/node_modules/npm/package.json').write_text('modified')
        self.setup.commands.clear()
        with self.assertRaisesRegex(RuntimeError, 'missing or changed'):
            system_tools.ensure_compatible_tools(self.setup, self.versions,
                                                 lambda *args: self.fail('download'), atomic_write)
        self.assertEqual(self.setup.commands, [])

    def test_changed_managed_runtime_can_be_explicitly_backed_up_and_repaired(self):
        self.install('node')
        companion = self.setup.state / 'system-tools/node/lib/node_modules/npm/package.json'
        companion.write_text('modified')
        self.setup.backup = True
        self.install('node')
        system_tools.check_managed_tools(self.setup, self.versions)
        preserved = self.setup.state / 'system-tools/node.backup/lib/node_modules/npm/package.json'
        self.assertEqual(preserved.read_text(), 'modified')

    def test_conflicts_require_backup_consent(self):
        self.setup.bin.mkdir()
        (self.setup.bin / 'node').write_text('old executable')
        with self.assertRaisesRegex(RuntimeError, 'backup-existing'):
            self.install('node')
        self.assertEqual((self.setup.bin / 'node').read_text(), 'old executable')
        self.setup.backup = True
        self.install('node')
        self.assertEqual((self.setup.bin / 'node.backup').read_text(), 'old executable')

    def test_archive_escape_and_special_files_are_rejected(self):
        for entry, kind, link in [('../escape', tarfile.REGTYPE, ''),
                                  ('root/link', tarfile.SYMTYPE, '../../escape'),
                                  ('root/device', tarfile.CHRTYPE, '')]:
            with self.subTest(entry=entry):
                archive_path = self.setup.home / 'unsafe.tar.gz'
                with tarfile.open(archive_path, 'w:gz') as archive:
                    member = tarfile.TarInfo(entry)
                    member.type = kind
                    member.linkname = link
                    archive.addfile(member)
                destination = self.setup.home / ('unpack-' + str(kind))
                destination.mkdir(exist_ok=True)
                with self.assertRaisesRegex(RuntimeError, 'Unsafe|Unsupported'):
                    system_tools._extract(archive_path, destination)

    def test_changed_release_keeps_existing_managed_runtime(self):
        self.install('node')
        self.specs['node'] = dict(self.specs['node'], version='100.0.0')
        self.install('node')
        self.assertEqual(system_tools._installed_spec(self.setup, 'node')['version'], '99.0.0')
        system_tools.check_managed_tools(self.setup, self.versions)

    def test_offline_validation_ignores_policy_version_changes(self):
        self.install('node')
        with patch.object(system_tools, 'resolve_release', side_effect=AssertionError('network')):
            system_tools.check_managed_tools(self.setup, {'system_tools': {}})

    def test_metadata_tampering_and_unsafe_entry_link_rejected(self):
        self.install('node')
        metadata = self.setup.state / 'releases/node.json'
        original = metadata.read_text()
        metadata.write_text(original.replace('99.0.0', '100.0.0'))
        self.assertFalse(system_tools._valid(self.setup, self.versions, 'node'))
        metadata.write_text(original)
        entry = self.setup.bin / 'npm'
        entry.unlink()
        entry.symlink_to('/bin/sh')
        self.assertFalse(system_tools._valid(self.setup, self.versions, 'node'))

    def test_runtime_below_minimum_is_not_installed_or_recorded_as_success(self):
        with patch.object(self.setup, 'command', return_value=subprocess.CompletedProcess([], 0, 'v0.0.0')):
            with self.assertRaisesRegex(RuntimeError, 'minimum version'):
                self.install('node')
        self.assertFalse((self.setup.state / 'system-tools/node').exists())
        self.assertNotIn('system-node', self.setup.records)

    def test_version_minimums(self):
        self.setup.bin.mkdir()
        for name, old, current in [('go', 'go version go1.24.0 linux/amd64', 'go version go1.25.0 linux/amd64'),
                                   ('node', 'v18.20.0', 'v20.0.0'),
                                   ('nvim', 'NVIM v0.10.4', 'NVIM v0.11.2'),
                                   ('tmux', 'tmux 3.1c', 'tmux 3.2a')]:
            executable = self.setup.bin / name
            executable.write_text('fixture')
            executable.chmod(0o755)
            for output, expected in [(old, False), (current, True)]:
                with patch.object(self.setup, 'command', return_value=subprocess.CompletedProcess([], 0, output)):
                    self.assertEqual(system_tools._compatible(self.setup, name), expected)


if __name__ == '__main__':
    unittest.main()
