"""Managed shell selection without requiring zsh or user shell configuration."""
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which('bash'), 'Bash required for launcher')
class DefaultShellTests(unittest.TestCase):
    def run_shell_command(self, env, input_text=''):
        command = subprocess.check_output(
            ['bash', '-c', 'source "$1"; printf "%s" "$_TM_SHELL_CMD"',
             'test', str(ROOT / 'config/btide.sh')], text=True, env=env)
        return subprocess.run(
            ['/bin/sh', '-c', 'sleep() { exit 0; }; ' + command],
            input=input_text, capture_output=True, text=True, env=env, timeout=5)

    def test_user_shell_path_is_quoted_and_launched_without_extra_arguments(self):
        with tempfile.TemporaryDirectory() as directory:
            shell = Path(directory) / 'user shell; special'
            marker = Path(directory) / 'started'
            shell.write_text('#!/bin/sh\nprintf "%s\\n" "$#" >> ' + shlex.quote(str(marker)) + '\n')
            shell.chmod(0o755)
            env = dict(os.environ, SHELL=str(shell))
            result = self.run_shell_command(env)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(marker.read_text(), '0\n')

    def test_unset_or_empty_shell_falls_back_to_sh(self):
        for value in (None, ''):
            with self.subTest(shell=value):
                env = dict(os.environ)
                env.pop('SHELL', None)
                if value is not None:
                    env['SHELL'] = value
                result = self.run_shell_command(env, 'printf "fallback works\\n"\nexit\n')
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout, 'fallback works\n')


if __name__ == '__main__':
    unittest.main()
