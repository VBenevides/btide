"""Exercise BTIDE keymaps in an isolated Neovim process."""

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KEYMAPS = ROOT / "config/nvim/lua/config/keymaps.lua"


@unittest.skipUnless(shutil.which("nvim"), "Neovim required")
class NvimKeymapTests(unittest.TestCase):
    def run_lua(self, source):
        with tempfile.TemporaryDirectory() as directory:
            script = Path(directory) / "test.lua"
            script.write_text(
                "local ok, err = pcall(function()\n"
                + source
                + '\nend)\nif not ok then print(err); vim.cmd("cquit 1") end\n'
                + 'vim.cmd("qa!")\n'
            )
            result = subprocess.run(
                ["nvim", "--headless", "-u", "NONE", "-i", "NONE", "-l", str(script)],
                text=True,
                capture_output=True,
                timeout=15,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_select_all_empty_single_and_multiple_lines(self):
        self.run_lua(
            f"dofile({json.dumps(str(KEYMAPS))})\n"
            + r"""
local function keys(input)
  vim.api.nvim_feedkeys(vim.api.nvim_replace_termcodes(input, true, false, true), "xt", false)
end
for _, lines in ipairs({ { "" }, { "one" }, { "one", "two", "three" } }) do
  vim.api.nvim_buf_set_lines(0, 0, -1, false, lines)
  vim.api.nvim_win_set_cursor(0, { #lines, 0 })
  keys("<C-a>")
  assert(vim.fn.mode() == "V", "Expected linewise visual mode")
  assert(vim.fn.line("v") == 1, "Selection must start at first line")
  assert(vim.fn.line(".") == #lines, "Selection must end at last line")
  keys("<Esc>")
end
"""
        )

    @unittest.skipUnless(shutil.which("tmux"), "tmux required")
    def test_tmux_does_not_consume_ctrl_a(self):
        with tempfile.TemporaryDirectory() as directory:
            socket = str(Path(directory) / "tmux.sock")
            command = ["tmux", "-S", socket]
            try:
                subprocess.run(
                    command
                    + [
                        "-f",
                        str(ROOT / "config/tmux/tmux.conf"),
                        "new-session",
                        "-d",
                        "sleep 30",
                    ],
                    check=True,
                    capture_output=True,
                    timeout=5,
                )
                result = subprocess.check_output(
                    command + ["show-option", "-gv", "prefix"], text=True, timeout=5
                )
                self.assertEqual(result.strip(), "C-b")
                bindings = subprocess.check_output(
                    command + ["list-keys", "-T", "root"], text=True, timeout=5
                )
                self.assertNotIn(" C-a ", bindings)
            finally:
                subprocess.run(
                    command + ["kill-server"],
                    capture_output=True,
                    timeout=5,
                    check=False,
                )
