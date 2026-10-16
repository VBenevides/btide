"""Real tmux attachment, shell lifetime and missing-terminal regressions."""
import os
from pathlib import Path
import pty
import select
import shlex
import shutil
import subprocess
import tempfile
import time
import unittest
import uuid

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which('tmux') and shutil.which('bash'), 'tmux and Bash required')
class BtideLauncherTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.home = self.root / 'home'
        self.home.mkdir()
        self.project = self.root / "project with 'quotes' ; $(touch INJECTED)"
        self.project.mkdir()
        self.socket = 'btide-launcher-test-' + uuid.uuid4().hex
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        self.real_tmux = shutil.which('tmux')
        wrapper = self.bin / 'tmux'
        wrapper.write_text('#!/bin/sh\nexec ' + shlex.quote(self.real_tmux) + ' -L ' + self.socket + ' "$@"\n')
        wrapper.chmod(0o755)
        self.env = dict(os.environ, HOME=str(self.home), PATH=str(self.bin) + os.pathsep + os.environ['PATH'],
                        TERM='xterm-256color', BTIDE_TMUX_SOCKET=self.socket)
        for key in ('TMUX', 'TMUX_PANE', 'KITTY_WINDOW_ID', 'DISPLAY', 'WAYLAND_DISPLAY'):
            self.env.pop(key, None)
        self.addCleanup(lambda: subprocess.run([self.real_tmux, '-L', self.socket, 'kill-server'],
                                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))

    def tmux(self, *args):
        return subprocess.check_output([self.real_tmux, '-L', self.socket, *args], env=self.env,
                                       text=True, timeout=5, stderr=subprocess.DEVNULL)

    def start_shell(self, shell, env, executable=False):
        script = self.root / 'launch.sh'
        prefix = ('source ' + shlex.quote(str(ROOT / 'config/btide.sh')) + '\n'
                  '_TM_EDITOR_CMD="sleep 120"\n_TM_PI_CMD="sleep 120"\n'
                  '_TM_GIT_CMD="sleep 120"\n_TM_SHELL_CMD="sleep 120"\n_TM_RANGER_CMD="sleep 120"\n')
        if executable:
            prefix = ''
            (self.bin / 'btide').symlink_to(ROOT / 'config/btide.sh')
            editor = self.bin / 'nvim'
            editor.write_text('#!/bin/sh\nexec sleep 120\n')
            editor.chmod(0o755)
        script.write_text(prefix + 'before=$$\nbtide\nbtide_status=$?\nprintf "SHELL_RETURNED:%s:%s:%s\\n" "$before" "$$" "$btide_status"\n')
        master, slave = pty.openpty()
        process = subprocess.Popen([shell, str(script)], cwd=self.project, env=env,
                                   stdin=slave, stdout=slave, stderr=slave, start_new_session=True)
        os.close(slave)
        self.addCleanup(os.close, master)
        self.addCleanup(lambda: self.stop_shell(process))
        return process, master

    @staticmethod
    def stop_shell(process):
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=5)

    def wait_client(self, process):
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if process.poll() is not None:
                self.fail('Launching shell exited before tmux attached')
            try:
                clients = self.tmux('list-clients', '-F', '#{client_pid}')
                if clients.strip():
                    return clients.strip()
            except subprocess.CalledProcessError:
                pass
            time.sleep(0.05)
        self.fail('Timed out waiting for tmux attachment')

    def read_output(self, master):
        data = bytearray()
        while select.select([master], [], [], 0.1)[0]:
            try:
                chunk = os.read(master, 65536)
            except OSError:
                break
            if not chunk:
                break
            data.extend(chunk)
        return data.decode(errors='replace')

    def test_attach_in_existing_kitty_or_headless_terminal_returns_to_original_shell(self):
        for terminal in ('kitty', 'headless', 'graphical'):
            for shell in filter(None, (shutil.which('bash'), shutil.which('zsh'))):
                with self.subTest(terminal=terminal, shell=shell):
                    env = dict(self.env)
                    if terminal == 'kitty':
                        env.update(KITTY_WINDOW_ID='1', DISPLAY=':test-no-new-window')
                    elif terminal == 'graphical':
                        env.update(DISPLAY=':test-no-new-window')
                    process, master = self.start_shell(shell, env)
                    self.wait_client(process)
                    name = self.tmux('list-sessions', '-F', '#{session_name}').strip()
                    panes = self.tmux('list-panes', '-s', '-t', name, '-F', '#{pane_current_path}')
                    self.assertTrue(all(path == str(self.project) for path in panes.splitlines()))
                    self.tmux('detach-client', '-s', name)
                    self.assertEqual(process.wait(timeout=5), 0)
                    output = self.read_output(master)
                    self.assertIn(f'SHELL_RETURNED:{process.pid}:{process.pid}:0', output)
                    self.assertEqual((self.home / '.config/btide/config.yml').read_text(),
                                     'open_separate_window: false\n')
                    self.assertFalse((self.project / 'INJECTED').exists())
                    self.tmux('kill-server')

    def test_btide_config_is_loaded_and_nouse_falls_back_on_new_server(self):
        config = self.home / '.config/btide/tmux.conf'
        config.parent.mkdir(parents=True)
        content = (ROOT / 'config/tmux/tmux.conf').read_text()
        fish = shutil.which('fish')
        if fish:
            content += '\nset -g default-shell ' + shlex.quote(fish) + '\n'
        config.write_text(content + '\nset -g @config_source btide\n')
        default = self.home / '.tmux.conf'
        default.write_text('set -g @config_source personal\n')
        for expected in ('btide', 'personal'):
            with self.subTest(expected=expected):
                process, _master = self.start_shell(shutil.which('bash'), self.env)
                self.wait_client(process)
                self.assertEqual(self.tmux('show-options', '-gqv', '@config_source').strip(), expected)
                self.assertEqual(len(self.tmux('list-windows').splitlines()), 5)
                self.assertEqual(self.tmux('show-options', '-gqv', 'allow-passthrough').strip(), 'off')
                self.tmux('detach-client')
                self.assertEqual(process.wait(timeout=5), 0)
                self.tmux('kill-server')
                if expected == 'btide':
                    config.rename(config.with_name('tmux.conf.nouse'))
        self.assertEqual(default.read_text(), 'set -g @config_source personal\n')

    def test_executable_launches_without_sourcing_and_returns_to_original_shell(self):
        process, master = self.start_shell(shutil.which('bash'), self.env, executable=True)
        self.wait_client(process)
        name = self.tmux('list-sessions', '-F', '#{session_name}').strip()
        self.assertEqual(self.tmux('list-windows', '-t', name, '-F', '#{window_name}').splitlines(),
                         ['Code', 'PiG', 'Git', 'Shell', 'Ranger'])
        self.assertEqual(len(self.tmux('list-panes', '-t', name + ':Code').splitlines()), 1)
        commands = self.tmux('list-panes', '-s', '-t', name, '-F', '#{pane_start_command}')
        self.assertEqual(commands.count('tmux wait-for'), 4)
        self.tmux('detach-client', '-s', name)
        self.assertEqual(process.wait(timeout=5), 0)
        self.assertIn(f'SHELL_RETURNED:{process.pid}:{process.pid}:0', self.read_output(master))

    def test_tabs_start_only_when_selected(self):
        script = self.root / 'tabs.sh'
        script.write_text('source ' + shlex.quote(str(ROOT / 'config/btide.sh')) + '\n'
                          '_TM_EDITOR_CMD="sleep 120"\n'
                          '_TM_PI_CMD="echo started >> pi.started; sleep 120"\n'
                          '_TM_GIT_CMD="echo started >> git.started; sleep 120"\n'
                          '_TM_SHELL_CMD="echo started >> shell.started; sleep 120"\n'
                          '_TM_RANGER_CMD="echo started >> ranger.started; sleep 120"\n'
                          'tmux new-session -d -s tabs -n Code -c "$PWD" "$_TM_EDITOR_CMD"\n'
                          'tmux set-option -t tabs renumber-windows off\n'
                          '_tm_install_keybindings\n_tm_install_lazy_hook tabs\n'
                          '_tm_create_pi_window tabs "$PWD"\n'
                          '_tm_create_git_window tabs "$PWD"\n'
                          '_tm_create_shell_window tabs "$PWD"\n'
                          '_tm_create_ranger_window tabs "$PWD"\n')
        subprocess.run(['bash', str(script)], cwd=self.project, env=self.env, check=True)
        self.assertEqual(self.tmux('list-windows', '-t', 'tabs', '-F', '#{window_name}').splitlines(),
                         ['Code', 'PiG', 'Git', 'Shell', 'Ranger'])
        self.assertEqual(len(self.tmux('list-panes', '-t', 'tabs:Code').splitlines()), 1)
        self.assertFalse(list(self.project.glob('*.started')))
        for tab, marker in [('PiG', 'pi'), ('Git', 'git'), ('Shell', 'shell'), ('Ranger', 'ranger')]:
            self.tmux('select-window', '-t', 'tabs:' + tab)
            path = self.project / (marker + '.started')
            deadline = time.monotonic() + 5
            while not path.exists() and time.monotonic() < deadline:
                time.sleep(0.02)
            self.assertTrue(path.exists(), tab)
            self.tmux('select-window', '-t', 'tabs:Code')
            self.tmux('select-window', '-t', 'tabs:' + tab)
            self.assertEqual(path.read_text(), 'started\n')

    def test_missing_kitty_fails_before_creating_session(self):
        config = self.home / '.config/btide/config.yml'
        config.parent.mkdir(parents=True)
        config.write_text('open_separate_window: true\n')
        (config.parent / 'kitty.conf').write_text('# Kitty enabled\n')
        env = dict(self.env, DISPLAY=':test', PATH=str(self.bin))
        process, master = self.start_shell(shutil.which('bash'), env)
        self.assertEqual(process.wait(timeout=5), 0)
        output = self.read_output(master)
        self.assertIn('Kitty is missing', output)
        self.assertIn(f'SHELL_RETURNED:{process.pid}:{process.pid}:1', output)
        result = subprocess.run([self.real_tmux, '-L', self.socket, 'list-sessions'],
                                text=True, capture_output=True, timeout=5)
        self.assertNotEqual(result.returncode, 0)

    def test_invalid_configuration_does_not_create_session(self):
        config = self.home / '.config/btide/config.yml'
        config.parent.mkdir(parents=True)
        for content in ('open_separate_window: yes\n',
                        'open_separate_window: false\nopen_separate_window: true\n'):
            for shell in filter(None, (shutil.which('bash'), shutil.which('zsh'))):
                with self.subTest(content=content, shell=shell):
                    config.write_text(content)
                    process, master = self.start_shell(shell, self.env)
                    self.assertEqual(process.wait(timeout=5), 0)
                    self.assertEqual(config.read_text(), content)
                    result = subprocess.run([self.real_tmux, '-L', self.socket, 'list-sessions'],
                                            capture_output=True, timeout=5)
                    self.assertNotEqual(result.returncode, 0)
