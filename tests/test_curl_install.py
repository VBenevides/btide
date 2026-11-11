"""Disposable-checkout installation without network access or system changes."""
import importlib.util
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('curl_bootstrap', ROOT / 'scripts/bootstrap.py')
assert SPEC is not None and SPEC.loader is not None
bootstrap = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bootstrap)


class CurlInstallTests(unittest.TestCase):
    def test_copied_configuration_survives_checkout_removal_and_reinstall(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            checkout = root / 'checkout'
            shutil.copytree(ROOT / 'config', checkout / 'config')
            (checkout / 'scripts').mkdir()
            shutil.copy2(ROOT / 'scripts/update.py', checkout / 'scripts/update.py')
            shutil.copy2(ROOT / 'VERSION', checkout / 'VERSION')
            with mock.patch.object(bootstrap, 'ROOT', checkout):
                setup = bootstrap.Setup(root / 'home', include_kitty=True, copy_config=True)
                with mock.patch.object(bootstrap, 'run'):
                    setup.configure()
                    setup.configure()
                for source, target in setup.links:
                    self.assertFalse(target.is_symlink())
                    if source.is_file():
                        self.assertEqual(source.read_bytes(), target.read_bytes())
                shutil.rmtree(checkout)
                self.assertTrue(os.access(setup.bin / 'btide', os.X_OK))
                self.assertTrue((setup.config / 'nvim.conf/init.lua').is_file())
                self.assertTrue((setup.config / 'kitty.conf').is_file())
                self.assertEqual(len(list(setup.bin.glob('btide.*.bak'))), 1)
                with mock.patch.object(bootstrap, 'check_managed_tools'), \
                        mock.patch.object(setup, 'prerequisites'), \
                        mock.patch.object(setup, 'editor_valid', return_value=True):
                    scope = setup.home / '.config/ranger/scope.sh'
                    scope.parent.mkdir(parents=True)
                    scope.write_text('#!/bin/sh\n')
                    scope.chmod(0o755)
                    setup.check()

    def test_piped_installer_forwards_kitty_and_cleans_up_on_success_and_failure(self):
        for status in (0, 7):
            with self.subTest(status=status), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                bin_path = root / 'bin'
                bin_path.mkdir()
                temp = root / 'temp with spaces'
                temp.mkdir()
                git = bin_path / 'git'
                git.write_text(
                    '#!/bin/sh\n'
                    'for destination do :; done\n'
                    'mkdir -p "$destination"\n'
                    'printf "%s\\n" "$destination" > "$RECORD.checkout"\n'
                    'printf \'printf "%%s\\n" "$@" > "$RECORD.args"\\nexit "$STATUS"\\n\' '
                    '> "$destination/install.sh"\n'
                    'cp "$MAKEFILE_SOURCE" "$destination/Makefile"\n'
                )
                git.chmod(0o755)
                record = root / 'record'
                env = dict(os.environ, PATH=str(bin_path) + os.pathsep + os.environ['PATH'],
                           TMPDIR=str(temp), RECORD=str(record), STATUS=str(status),
                           MAKEFILE_SOURCE=str(ROOT / 'Makefile'))
                result = subprocess.run(['sh', '-s', '--', '--include', 'kitty'],
                                        input=(ROOT / 'get.sh').read_text(), text=True,
                                        capture_output=True, env=env, check=False)
                self.assertEqual(result.returncode, 0 if status == 0 else 2, result.stderr)
                self.assertIn('make', result.stdout)
                self.assertEqual(record.with_suffix('.args').read_text().splitlines(),
                                 ['--copy-config', '--include', 'kitty'])
                checkout = Path(record.with_suffix('.checkout').read_text().strip())
                self.assertEqual(checkout.parent.parent, temp / 'btide')
                self.assertFalse(checkout.exists())
                self.assertEqual(list((temp / 'btide').iterdir()), [])

    def test_make_install_runs_full_installer_and_preserves_literal_options(self):
        with tempfile.TemporaryDirectory(prefix='btide make ') as directory:
            checkout = Path(directory)
            shutil.copy2(ROOT / 'Makefile', checkout / 'Makefile')
            installer = checkout / 'install.sh'
            installer.write_text('printf "%s\\n" "$@" > args\nexit "${STATUS:-0}"\n')
            env = dict(os.environ)
            env.pop('INSTALL_ARGS', None)
            result = subprocess.run(['make', '-C', str(checkout), 'install'],
                                    env=env, text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((checkout / 'args').read_text().split(), [])
            options = "--include kitty '--literal=$(touch injected); with spaces'"
            result = subprocess.run(['make', '-C', str(checkout), 'install',
                                     'INSTALL_ARGS=' + options],
                                    env=env, text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((checkout / 'args').read_text().splitlines(),
                             ['--include', 'kitty', '--literal=$(touch injected); with spaces'])
            self.assertFalse((checkout / 'injected').exists())
            env['STATUS'] = '7'
            result = subprocess.run(['make', '-C', str(checkout), 'install'],
                                    env=env, text=True, capture_output=True)
            self.assertNotEqual(result.returncode, 0)


if __name__ == '__main__':
    unittest.main()
