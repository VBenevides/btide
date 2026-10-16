"""Exercise Neo-tree Ranger actions against real tmux and Ranger processes."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import unittest
import uuid

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(all(shutil.which(tool) for tool in ('nvim', 'tmux', 'ranger', 'ps')),
                     'Neovim, tmux, Ranger and ps required')
class NeoTreeActionsTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.socket = 'neo-tree-test-' + uuid.uuid4().hex
        self.tmux('new-session', '-d', '-s', 'ide', '-n', 'Code', 'sleep 120')
        self.addCleanup(lambda: subprocess.run(['tmux', '-L', self.socket, 'kill-server'],
                                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
        socket_path = self.tmux('display-message', '-p', '#{socket_path}').strip()
        self.editor = self.tmux('display-message', '-p', '-t', 'ide:Code', '#{pane_id}').strip()
        self.env = dict(os.environ, TMUX=socket_path + ',0,0', TMUX_PANE=self.editor,
                        TERM='xterm-256color', HOME=str(self.directory))
        self.start = self.directory / 'start'
        self.start.mkdir()
        self.result = self.directory / 'chosen-directory'
        self.tmux('new-window', '-d', '-t', 'ide:5', '-n', 'Ranger',
                  '-c', str(self.start), 'ranger', '--clean', '--choosedir=' + str(self.result))
        self.pane = self.tmux('display-message', '-p', '-t', 'ide:5', '#{pane_id}').strip()
        self.tmux('set-option', '-p', '-t', self.pane, '@role', 'ranger')
        self.wait_for(lambda: 'start' in self.tmux('capture-pane', '-p', '-t', self.pane))

    def tmux(self, *args):
        return subprocess.check_output(['tmux', '-L', self.socket, *args], text=True, timeout=5)

    def wait_for(self, predicate):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if predicate():
                return
            time.sleep(0.05)
        self.fail('Timed out waiting for Ranger state:\n' + self.tmux('capture-pane', '-p', '-t', self.pane))

    def invoke(self, path, node_type='directory'):
        script = self.directory / 'invoke.lua'
        script.write_text('local spec = dofile(' + json.dumps(str(ROOT / 'config/nvim/lua/plugins/neo-tree.lua')) + ')\n'
                          'vim.notify = function(message) print("ACTION_ERROR: " .. message) end\n'
                          'local node = { type = ' + json.dumps(node_type) + ', path = ' + json.dumps(str(path)) + ' }\n'
                          'spec[1].opts.window.mappings["<leader>r"][1]({ tree = { get_node = function() return node end } })\n'
                          'vim.cmd("qa!")\n')
        result = subprocess.run(['nvim', '--headless', '-u', 'NONE', '-c', 'lua dofile(' + json.dumps(str(script)) + ')'],
                                env=self.env, text=True, capture_output=True, timeout=15, check=True)
        return result.stdout + result.stderr

    def test_literal_file_parent_navigation_and_same_session_selection(self):
        target = self.directory / "folder with spaces 'quotes' ; $(touch INJECTED) %f"
        target.mkdir()
        file = target / 'file.txt'
        file.write_text('selected file\n')
        self.tmux('new-session', '-d', '-s', 'other', '-n', 'untouched', 'sleep 120')
        output = self.invoke(file, 'file')
        self.assertNotIn('ACTION_ERROR', output)
        self.assertEqual(self.tmux('display-message', '-p', '-t', 'ide', '#{window_index} #{pane_id}').strip(),
                         '5 ' + self.pane)
        self.assertEqual(self.tmux('display-message', '-p', '-t', 'other', '#{window_name}').strip(), 'untouched')
        tty = self.tmux('display-message', '-p', '-t', self.pane, '#{pane_tty}').strip()
        def navigated():
            processes = subprocess.check_output(['ps', '-t', tty, '-o', 'pid=,comm='], text=True)
            return any(name == 'ranger' and os.readlink('/proc/' + pid + '/cwd') == str(target)
                       for pid, name in (line.split() for line in processes.splitlines()))
        self.wait_for(navigated)
        self.wait_for(lambda: self.tmux('capture-pane', '-p', '-t', self.pane).rstrip().endswith('All'))
        self.tmux('send-keys', '-t', self.pane, ':')
        self.wait_for(lambda: self.tmux('capture-pane', '-p', '-t', self.pane).rstrip().endswith(':'))
        self.tmux('send-keys', '-t', self.pane, '-l', 'quit')
        self.tmux('send-keys', '-t', self.pane, 'Enter')
        self.wait_for(self.result.exists)
        self.assertEqual(self.result.read_text(), str(target))
        self.assertFalse((self.start / 'INJECTED').exists())

    def test_foreground_shell_is_refused_without_injecting_path(self):
        target = self.directory / '$(touch INJECTED)'
        target.mkdir()
        self.tmux('send-keys', '-t', self.pane, ':')
        self.wait_for(lambda: self.tmux('capture-pane', '-p', '-t', self.pane).rstrip().endswith(':'))
        self.tmux('send-keys', '-t', self.pane, '-l', 'shell bash /dev/stdin')
        self.tmux('send-keys', '-t', self.pane, 'Enter')
        tty = self.tmux('display-message', '-p', '-t', self.pane, '#{pane_tty}').strip()
        self.wait_for(lambda: 'bash' in subprocess.check_output(['ps', '-t', tty, '-o', 'comm='], text=True))
        output = self.invoke(target)
        self.assertIn('busy with another foreground application', output)
        self.assertFalse((self.start / 'INJECTED').exists())
        self.assertEqual(self.tmux('display-message', '-p', '-t', 'ide', '#{window_name}').strip(), 'Code')

    def test_control_character_path_is_refused(self):
        target = self.directory / 'unsafe\nname'
        target.mkdir()
        output = self.invoke(target)
        self.assertIn('control characters', output)
        self.assertEqual(self.tmux('display-message', '-p', '-t', 'ide', '#{window_name}').strip(), 'Code')

    def test_missing_managed_pane_is_refused(self):
        self.tmux('set-option', '-p', '-t', self.pane, '@role', 'unmanaged')
        output = self.invoke(self.start)
        self.assertIn('No managed Ranger pane', output)
        self.assertEqual(self.tmux('display-message', '-p', '-t', 'ide', '#{window_name}').strip(), 'Code')
