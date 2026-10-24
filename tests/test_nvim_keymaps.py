"""Exercise BTIDE keymaps in an isolated Neovim process."""

import json
import os
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

    def test_project_shortcuts_preserve_buffer_search(self):
        self.run_lua(
            f"dofile({json.dumps(str(KEYMAPS))})\n"
            + r"""
local calls = {}
LazyVim = {
  root = function() return "/project with spaces" end,
  pick = function(command)
    assert(command == "live_grep")
    return function() calls.find = (calls.find or 0) + 1 end
  end,
}
package.loaded["grug-far"] = { open = function(opts)
  assert(opts.transient == true)
  assert(opts.prefills.paths == "/project\\ with\\ spaces")
  assert(opts.prefills.filesFilter == nil, "Must not restrict file types")
  calls.replace = (calls.replace or 0) + 1
end }
for _, mode in ipairs({ "n", "i" }) do
  local find = vim.fn.maparg("<C-S-f>", mode, false, true)
  local replace = vim.fn.maparg("<C-S-h>", mode, false, true)
  assert(type(find.callback) == "function")
  assert(type(replace.callback) == "function")
  find.callback()
  replace.callback()
  assert(vim.fn.maparg("<C-f>", mode):match("/$"))
  assert(vim.fn.maparg("<C-h>", mode):find("%%s///gc"))
end
assert(calls.find == 2 and calls.replace == 2)
"""
        )

    @unittest.skipUnless(
        os.environ.get("BTIDE_NVIM_PLUGINS"),
        "Set BTIDE_NVIM_PLUGINS for plugin integration",
    )
    def test_global_replace_across_project_files(self):
        plugins = Path(os.environ["BTIDE_NVIM_PLUGINS"])
        with tempfile.TemporaryDirectory(prefix="btide project ") as directory:
            project = Path(directory)
            (project / "nested").mkdir()
            files = [project / "first.txt", project / "nested/second.py"]
            for file in files:
                file.write_text("before\n")
            self.run_lua(
                f"vim.opt.rtp:prepend({json.dumps(str(plugins / 'grug-far.nvim'))})\n"
                + f"local project = {json.dumps(directory)}\n"
                + f"dofile({json.dumps(str(KEYMAPS))})\n"
                + r"""
vim.cmd.cd(vim.fn.fnameescape(project .. "/nested"))
LazyVim = { root = function() return project end }
local grug = require("grug-far")
grug.setup({ icons = { enabled = false }, startInInsertMode = false })
vim.fn.maparg("<C-S-h>", "n", false, true).callback()
local instance = grug.get_instance()
local ready = false
instance:when_ready(function() ready = true end)
assert(vim.wait(5000, function() return ready end), "Replace panel did not become ready")
instance:update_input_values({ search = "before", replacement = "after" }, false)
instance:search()
assert(vim.wait(5000, function()
  local info = instance:get_status_info()
  return info.stats and info.stats.files == 2
end), "Expected search results in both project files")
instance:replace()
assert(vim.wait(5000, function()
  return vim.fn.readfile(project .. "/first.txt")[1] == "after"
    and vim.fn.readfile(project .. "/nested/second.py")[1] == "after"
end), "Expected replacements in both project files")
"""
            )
            for file in files:
                self.assertEqual(file.read_text(), "after\n")

    def test_kitty_preserves_shift_for_project_shortcuts(self):
        config = (ROOT / "config/kitty/kitty.conf").read_text()
        self.assertIn(r"map ctrl+shift+f send_text all \x1b[102;6u", config)
        self.assertIn(r"map ctrl+shift+h send_text all \x1b[104;6u", config)

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
