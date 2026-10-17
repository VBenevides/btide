"""Isolated configuration, optional Kitty, and automatic dependency installation."""
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import bootstrap

ROOT = Path(__file__).resolve().parents[1]


class IsolatedConfigTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.home = Path(temporary.name) / 'home with spaces'
        self.home.mkdir()
        self.setup = bootstrap.Setup(self.home)

    def test_default_configuration_and_pig_are_untouched(self):
        paths = ['.tmux.conf', '.config/nvim/init.lua', '.config/kitty/kitty.conf', '.pig/agent/auth.json']
        for name in paths:
            path = self.home / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('personal configuration\n')
        before = {name: (self.home / name).stat() for name in paths}
        with mock.patch.object(bootstrap, 'run') as run:
            self.setup.configure()
            run.assert_not_called()
        for name in paths:
            self.assertEqual((self.home / name).read_text(), 'personal configuration\n')
            self.assertEqual((self.home / name).stat().st_ino, before[name].st_ino)
        self.assertTrue((self.setup.config / 'tmux.conf').is_symlink())
        self.assertTrue((self.setup.config / 'nvim.conf').is_dir())
        self.assertFalse((self.setup.config / 'kitty.conf').exists())
        self.assertFalse((self.home / '.local/share/fonts/btide').exists())

    def test_nouse_configuration_stays_disabled_on_reinstall_and_check(self):
        self.setup.configure()
        for name in ('tmux.conf', 'nvim.conf'):
            path = self.setup.config / name
            path.rename(path.with_name(name + '.nouse'))
        setup = bootstrap.Setup(self.home)
        self.assertTrue(setup.editor_disabled)
        setup.configure()
        with mock.patch.object(bootstrap, 'run') as run:
            setup.install_editor()
            run.assert_not_called()
        for name in ('tmux.conf', 'nvim.conf'):
            self.assertFalse((setup.config / name).exists())
            self.assertTrue((setup.config / (name + '.nouse')).exists())
        scope = self.home / '.config/ranger/scope.sh'
        scope.parent.mkdir(parents=True)
        scope.write_text('#!/bin/sh\n')
        scope.chmod(0o755)
        with mock.patch.object(bootstrap, 'check_managed_tools'), \
                mock.patch.object(setup, 'prerequisites'), \
                mock.patch.object(setup, 'editor_valid', side_effect=AssertionError('disabled editor')):
            setup.check()

    def test_kitty_is_opt_in_and_remembered(self):
        setup = bootstrap.Setup(self.home, include_kitty=True)
        with mock.patch.object(bootstrap, 'run') as run:
            setup.configure()
            self.assertEqual(run.call_args.args[0][0], 'fc-cache')
        self.assertTrue((setup.config / 'kitty.conf').is_symlink())
        self.assertTrue(bootstrap.Setup(self.home).include_kitty)
        self.assertFalse((self.home / '.config/kitty').exists())

    def test_package_lists_exclude_shells_and_optional_kitty_by_default(self):
        for manager in ('apt-get', 'dnf', 'pacman'):
            for include in (False, True):
                with self.subTest(manager=manager, include=include), \
                        mock.patch.object(bootstrap.shutil, 'which', side_effect=lambda name, manager=manager: name == manager), \
                        mock.patch.object(bootstrap.subprocess, 'run',
                                          return_value=mock.Mock(returncode=1, stdout='')), \
                        mock.patch.object(bootstrap, 'run') as run:
                    bootstrap.install_dependencies(include_kitty=include)
                    packages = run.call_args.args[0]
                    self.assertEqual('kitty' in packages, include)
                    self.assertEqual('fontconfig' in packages, include)
                    self.assertEqual(any('pillow' in p or p == 'python3-pil' for p in packages), include)
                    self.assertNotIn('fish', packages)
                    self.assertNotIn('zsh', packages)

    def test_full_install_always_installs_dependencies_and_modes_do_not(self):
        for flags in ([], ['--include', 'kitty'], ['--config-only'], ['--check']):
            with self.subTest(flags=flags):
                setup = bootstrap.Setup(self.home, include_kitty='kitty' in flags)
                with mock.patch.object(sys, 'argv', ['bootstrap', *flags]), \
                        mock.patch.object(bootstrap.os, 'geteuid', return_value=1000), \
                        mock.patch.object(bootstrap, 'Setup', return_value=setup), \
                        mock.patch.object(bootstrap, 'install_dependencies') as dependencies, \
                        mock.patch.object(bootstrap, 'ensure_compatible_tools'), \
                        mock.patch.object(setup, 'install_lazygit'), \
                        mock.patch.object(setup, 'prerequisites'), \
                        mock.patch.object(setup, 'configure'), \
                        mock.patch.object(setup, 'install_editor'), \
                        mock.patch.object(setup, 'install_ranger'), \
                        mock.patch.object(setup, 'check'):
                    bootstrap.main()
                    if '--config-only' in flags or '--check' in flags:
                        dependencies.assert_not_called()
                    else:
                        dependencies.assert_called_once_with(include_kitty='kitty' in flags)

    def test_dependency_failure_stops_before_configuration(self):
        with mock.patch.object(sys, 'argv', ['bootstrap']), \
                mock.patch.object(bootstrap.os, 'geteuid', return_value=1000), \
                mock.patch.object(bootstrap, 'Setup', return_value=self.setup), \
                mock.patch.object(bootstrap, 'install_dependencies', side_effect=RuntimeError('package failure')), \
                mock.patch.object(self.setup, 'configure') as configure:
            with self.assertRaisesRegex(RuntimeError, 'package failure'):
                bootstrap.main()
            configure.assert_not_called()

    def test_ranger_provisioning_is_independent_of_disabled_neovim(self):
        self.setup.config.mkdir(parents=True)
        (self.setup.config / 'nvim.conf.nouse').mkdir()
        setup = bootstrap.Setup(self.home)
        scope = self.home / '.config/ranger/scope.sh'
        def create_scope(*args, **kwargs):
            scope.parent.mkdir(parents=True)
            scope.write_text('#!/bin/sh\n')
            scope.chmod(0o755)
        with mock.patch.object(setup, 'command', side_effect=create_scope) as command:
            setup.install_ranger()
            command.assert_called_once_with(['ranger', '--copy-config=scope'], timeout=30)
            setup.install_ranger()
            self.assertEqual(command.call_count, 1)


@unittest.skipUnless(shutil.which('bash'), 'Bash required')
class ConfigurationLaunchTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.home = Path(temporary.name) / 'home with spaces'
        self.home.mkdir()
        self.bin = self.home / 'bin'
        self.bin.mkdir()
        self.config = self.home / '.config/btide'
        self.config.mkdir(parents=True)
        self.env = dict(os.environ, HOME=str(self.home), PATH=str(self.bin) + ':' + os.environ['PATH'])

    def script(self, name, content):
        path = self.bin / name
        path.write_text('#!/bin/sh\n' + content)
        path.chmod(0o755)

    def managed_command(self, name):
        command = subprocess.check_output(
            ['bash', '-c', 'source "$1"; printf "%s" "${!2}"', 'test',
             str(ROOT / 'config/btide.sh'), name], env=self.env, text=True)
        return subprocess.check_output(['/bin/sh', '-c', 'sleep() { exit 0; }; ' + command],
                                       env=self.env, text=True, timeout=5)

    def test_neovim_uses_isolated_appname_then_falls_back_after_rename(self):
        self.script('nvim', 'printf "%s\\n" "${NVIM_APPNAME-default}" "$XDG_CONFIG_HOME"\n')
        (self.config / 'nvim.conf').mkdir()
        self.assertEqual(self.managed_command('_TM_EDITOR_CMD').splitlines(),
                         ['btide/nvim.conf', str(self.home / '.config')])
        (self.config / 'nvim.conf').rename(self.config / 'nvim.conf.nouse')
        self.env['NVIM_APPNAME'] = 'unrelated'
        self.assertEqual(self.managed_command('_TM_EDITOR_CMD').splitlines(),
                         ['default', str(self.home / '.config')])

    @unittest.skipUnless(shutil.which('nvim'), 'Neovim required')
    def test_actual_neovim_loads_btide_directory_and_default_directory(self):
        nvim = shutil.which('nvim')
        assert nvim is not None
        init = self.config / 'nvim.conf/init.lua'
        init.parent.mkdir()
        init.write_text('vim.g.config_source = "btide"\n')
        default = self.home / '.config/nvim/init.lua'
        default.parent.mkdir()
        default.write_text('vim.g.config_source = "personal"\n')
        self.script('nvim', 'exec ' + shlex.quote(nvim) +
                    ' --headless -c ' + shlex.quote('lua io.stdout:write(vim.g.config_source .. "\\n")') + ' +qa\n')
        self.assertEqual(self.managed_command('_TM_EDITOR_CMD'), 'btide\n')
        init.parent.rename(self.config / 'nvim.conf.nouse')
        self.assertEqual(self.managed_command('_TM_EDITOR_CMD'), 'personal\n')

    def test_ranger_images_are_off_unless_kitty_was_included(self):
        self.script('ranger', 'printf "%s\\n" "$@"\n')
        self.assertEqual(self.managed_command('_TM_RANGER_CMD').splitlines(),
                         ['--cmd=set preview_images false'])
        (self.config / 'kitty.conf').write_text('# enabled\n')
        result = self.managed_command('_TM_RANGER_CMD')
        self.assertIn('--cmd=set preview_images true', result)
        self.assertIn('--cmd=set preview_images_method kitty', result)

    def test_reload_and_close_refuse_other_tmux_servers(self):
        self.script('tmux', 'if [ "$1" = -L ]; then shift 2; socket=btide; else socket=foreign; fi\n'
                    'if [ "$1" != display-message ]; then printf "UNEXPECTED OPERATION\\n"; exit 4; fi\n'
                    'printf "%s\\n" "$socket"\n')
        self.env['TMUX'] = '/tmp/foreign,123,0'
        for function in ('btide_reload', 'btide_close'):
            with self.subTest(function=function):
                result = subprocess.run(
                    ['bash', '-c', 'source "$1"; ' + function, 'test', str(ROOT / 'config/btide.sh')],
                    env=self.env, text=True, capture_output=True, check=False, timeout=5)
                self.assertEqual(result.returncode, 1)
                self.assertEqual(result.stdout, '')
                self.assertIn('inside a BTIDE tmux session', result.stderr)

    def test_tmux_selects_btide_config_then_default_after_rename(self):
        self.script('tmux', 'printf "%s\\n" "$@"\n')
        (self.config / 'tmux.conf').write_text('# isolated\n')
        (self.home / '.tmux.conf').write_text('# personal\n')
        self.env['BTIDE_TMUX_SOCKET'] = 'test-isolated'
        command = ['bash', '-c', 'source ' + shlex.quote(str(ROOT / 'config/btide.sh')) + '; tmux new-session']
        result = subprocess.check_output(command, env=self.env, text=True)
        self.assertEqual(result.splitlines(), ['-L', 'test-isolated', '-f', str(self.config / 'tmux.conf'), 'new-session'])
        (self.config / 'tmux.conf').rename(self.config / 'tmux.conf.nouse')
        result = subprocess.check_output(command, env=self.env, text=True)
        self.assertEqual(result.splitlines(), ['-L', 'test-isolated', '-f', str(self.home / '.tmux.conf'), 'new-session'])


if __name__ == '__main__':
    unittest.main()
