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

    def test_delete_preserves_clipboard_and_explicit_copy(self):
        self.run_lua(
            f"dofile({json.dumps(str(KEYMAPS))})\n"
            + r"""
local clipboard = { "keep this clipboard" }
local writes = 0
local function copy(lines) clipboard = vim.deepcopy(lines); writes = writes + 1 end
local function paste() return { vim.deepcopy(clipboard), "V" } end
vim.g.clipboard = {
  name = "test clipboard",
  copy = { ["+"] = copy, ["*"] = copy },
  paste = { ["+"] = paste, ["*"] = paste },
  cache_enabled = 0,
}
vim.opt.clipboard = "unnamedplus"
local function keys(input)
  vim.api.nvim_feedkeys(vim.api.nvim_replace_termcodes(input, true, false, true), "xt", false)
end
for _, input in ipairs({ "dd", "2dd", "Vd", "Vjd", "dw" }) do
  vim.api.nvim_buf_set_lines(0, 0, -1, false, { "one", "two", "three", "four" })
  vim.api.nvim_win_set_cursor(0, { 1, 0 })
  keys(input)
  assert(vim.api.nvim_get_current_line() ~= "one", "Expected deletion: " .. input)
  assert(writes == 0, "Deletion wrote to clipboard: " .. input)
  assert(clipboard[1] == "keep this clipboard")
end
vim.api.nvim_buf_set_lines(0, 0, -1, false, { "one", "two", "three" })
vim.api.nvim_win_set_cursor(0, { 1, 0 })
keys("dd.")
assert(vim.api.nvim_buf_line_count(0) == 1, "Dot repeat must delete another line")
assert(writes == 0, "Dot repeat wrote to clipboard")
keys("yy")
assert(writes > 0 and clipboard[1] == "three", "Explicit yank must copy")
keys('"+yy')
assert(clipboard[1] == "three", "Explicit clipboard yank must copy")
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

    def test_tree_shortcuts_expand_and_close_nodes_only(self):
        spec = ROOT / "config/nvim/lua/plugins/neo-tree.lua"
        self.run_lua(
            f"dofile({json.dumps(str(KEYMAPS))})\n"
            f"local spec = dofile({json.dumps(str(spec))})\n"
            + r"""
assert(vim.fn.maparg("<leader>]", "n") == "")
assert(vim.fn.maparg("<leader>[", "n") == "")
local mappings = spec[1].opts.window.mappings
local expanded, parent = false, "parent"
local node = {
  type = "directory",
  is_expanded = function() return expanded end,
  get_parent_id = function() return parent end,
}
local opened, closed = 0, 0
local state = { tree = { get_node = function() return node end }, commands = {} }
state.commands.toggle_node = function(s)
  assert(s == state)
  opened = opened + 1
  expanded = not expanded
end
state.commands.close_node = function(s)
  assert(s == state)
  closed = closed + 1
  expanded = false
end
local open = mappings["<leader>]"][1]
local close = mappings["<leader>["][1]
open(state)
open(state)
assert(opened == 1 and expanded, "Repeated expansion must not collapse the folder")
close(state)
close(state)
assert(closed == 2, "Collapsed folders must use Neo-tree's parent action")
node.type = "file"
open(state)
assert(opened == 1, "Expansion must not open files")
close(state)
assert(closed == 3)
parent = nil
close(state)
assert(closed == 3, "A collapsed root must be a safe no-op")
node = nil
open(state)
close(state)
assert(opened == 1 and closed == 3)
"""
        )

    def test_middle_click_closes_clicked_buffer_without_force(self):
        spec = ROOT / "config/nvim/lua/plugins/bufferline.lua"
        self.run_lua(
            f"local spec = dofile({json.dumps(str(spec))})\n"
            + r"""
assert(spec[1][1] == "akinsho/bufferline.nvim")
local target = vim.api.nvim_create_buf(true, false)
assert(target ~= vim.api.nvim_get_current_buf())
local closed
Snacks = { bufdelete = function(buffer) closed = buffer end }
spec[1].opts.options.middle_mouse_command(target)
assert(closed == target, "Must close clicked buffer, not current buffer, without force options")
"""
        )

    def test_git_diff_shortcuts_and_confirmed_rollback(self):
        self.run_lua(
            f"dofile({json.dumps(str(KEYMAPS))})\n"
            + r"""
local calls = { reset = 0, preview = 0 }
package.loaded.gitsigns = {
  diffthis = function(base, opts)
    assert(base == "HEAD" and opts.vertical == true)
    calls.diff = true
  end,
  preview_hunk = function() calls.preview = calls.preview + 1 end,
  reset_hunk = function() calls.reset = calls.reset + 1 end,
}
vim.fn.maparg("<leader>gd", "n", false, true).callback()
vim.fn.maparg("<leader>gp", "n", false, true).callback()
assert(calls.diff and calls.preview == 1)
local reset = vim.fn.maparg("<leader>gr", "n", false, true).callback
vim.fn.confirm = function(_, _, default) assert(default == 2); return 2 end
reset()
assert(calls.reset == 0, "Cancel must not discard changes")
vim.fn.confirm = function() return 1 end
reset()
assert(calls.reset == 1)
vim.cmd.vsplit()
vim.cmd("windo diffthis")
vim.api.nvim_feedkeys(vim.api.nvim_replace_termcodes(
  vim.fn.maparg("<leader>gD", "n"), true, false, true), "xt", false)
for _, win in ipairs(vim.api.nvim_list_wins()) do
  assert(not vim.wo[win].diff, "Exit must disable diff in every split")
end
"""
        )

    @unittest.skipUnless(
        os.environ.get("BTIDE_NVIM_PLUGINS"),
        "Plugin integration requires BTIDE_NVIM_PLUGINS",
    )
    def test_real_gitsigns_opens_head_and_editable_working_buffer(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)

            def git(*args):
                subprocess.run(
                    ["git", *args], cwd=project, check=True, capture_output=True
                )

            git("init", "-q")
            file = project / "tracked.txt"
            file.write_text("before\n")
            git("add", ".")
            git(
                "-c",
                "user.name=Test",
                "-c",
                "user.email=test@example.invalid",
                "commit",
                "-qm",
                "initial",
            )
            file.write_text("after\n")
            plugin = Path(os.environ["BTIDE_NVIM_PLUGINS"]) / "gitsigns.nvim"
            self.run_lua(
                f"vim.opt.rtp:prepend({json.dumps(str(plugin))})\n"
                + f"vim.cmd.cd({json.dumps(directory)})\n"
                + f"vim.cmd.edit({json.dumps(str(file))})\n"
                + f"dofile({json.dumps(str(KEYMAPS))})\n"
                + r"""
local messages = {}
vim.notify = function(msg) messages[#messages + 1] = tostring(msg) end
require("gitsigns").setup()
assert(vim.wait(5000, function() return require("gitsigns").get_hunks() ~= nil end), "Git attachment failed")
local working = vim.api.nvim_get_current_buf()
vim.fn.maparg("<leader>gd", "n", false, true).callback()
assert(vim.wait(5000, function() return #vim.api.nvim_list_wins() == 2 end),
  "Diff did not open: " .. table.concat(messages, "; ") .. vim.api.nvim_exec2("messages", { output = true }).output)
local saw_before = false
for _, win in ipairs(vim.api.nvim_list_wins()) do
  assert(vim.wo[win].diff)
  local buf = vim.api.nvim_win_get_buf(win)
  if buf ~= working then
    assert(vim.api.nvim_buf_get_lines(buf, 0, 1, false)[1] == "before")
    saw_before = true
  end
end
assert(saw_before and vim.bo[working].modifiable)
vim.api.nvim_buf_set_lines(working, 0, -1, false, { "edited" })
assert(vim.api.nvim_buf_get_lines(working, 0, 1, false)[1] == "edited")
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
                # The prefix is disabled so that the root C-b binding can show hints
                # and then enter the prefix table.
                self.assertEqual(result.strip(), "None")
                bindings = subprocess.check_output(
                    command + ["list-keys", "-T", "root"], text=True, timeout=5
                )
                self.assertNotIn(" C-a ", bindings)
                self.assertIn(" C-b ", bindings)
            finally:
                subprocess.run(
                    command + ["kill-server"],
                    capture_output=True,
                    timeout=5,
                    check=False,
                )
