"""Exercise lazygit's side-by-side command without an interactive terminal."""
import os
import shlex
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which('git'), 'Git required')
class GitDiffTests(unittest.TestCase):
    def test_diff_edits_working_file_and_preserves_head_and_index(self):
        config = (ROOT / 'config/lazygit.yml').read_text()
        command = next(line.strip()[len("command: '"):-1]
                       for line in config.splitlines() if line.strip().startswith('command:'))
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            env = dict(os.environ, HOME=directory, GIT_CONFIG_NOSYSTEM='1')
            def git(*args):
                return subprocess.check_output(['git', *args], cwd=project, env=env, text=True)
            git('init', '-q')
            git('-c', 'user.name=Test', '-c', 'user.email=test@example.invalid',
                'commit', '--allow-empty', '-qm', 'initial')
            name = "file with 'quotes; spaces.txt"
            file = project / name
            file.write_text('before\n')
            git('add', '--', name)
            git('-c', 'user.name=Test', '-c', 'user.email=test@example.invalid',
                'commit', '-qm', 'tracked')
            file.write_text('staged\n')
            git('add', '--', name)
            file.write_text('working\n')
            binary = project / 'bin'
            binary.mkdir()
            editor = binary / 'nvim'
            editor.write_text('#!/bin/sh\n[ "$1" = -d ] || exit 1\n'
                              '[ "$(cat "$2")" = before ] || exit 2\n'
                              '[ "$(cat "$3")" = working ] || exit 3\n'
                              'printf "edited\\n" > "$3"\n')
            editor.chmod(0o700)
            env['PATH'] = str(binary) + os.pathsep + env['PATH']
            command = command.replace('{{.SelectedFile.Name | quote}}', shlex.quote(name))
            subprocess.run(['sh', '-c', command], cwd=project, env=env,
                           check=True, capture_output=True, text=True, timeout=15)
            self.assertEqual(file.read_text(), 'edited\n')
            self.assertEqual(git('show', 'HEAD:' + name), 'before\n')
            self.assertEqual(git('show', ':' + name), 'staged\n')
