"""Verify external file changes without requiring editor input or focus events."""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which('nvim'), 'Neovim required')
class NvimReloadTests(unittest.TestCase):
    def test_idle_reload_preserves_unsaved_edits(self):
        with tempfile.TemporaryDirectory() as temporary:
            script = Path(temporary) / 'reload.lua'
            script.write_text('''
local path = vim.fn.tempname()
vim.fn.writefile({ "original" }, path)
vim.cmd.edit(path)
dofile(''' + json.dumps(str(ROOT / 'config/nvim/lua/config/options.lua')) + ''')
dofile(''' + json.dumps(str(ROOT / 'config/nvim/lua/config/autocmds.lua')) + ''')
local ok, err = pcall(function()
  vim.fn.writefile({ "external replacement" }, path)
  assert(vim.wait(3500, function()
    return vim.api.nvim_buf_get_lines(0, 0, 1, false)[1] == "external replacement"
  end, 50), "idle buffer did not reload")
  vim.api.nvim_buf_set_lines(0, 0, -1, false, { "unsaved edit" })
  vim.fn.writefile({ "another external replacement" }, path)
  vim.wait(2200, function() return false end, 50)
  assert(vim.api.nvim_buf_get_lines(0, 0, 1, false)[1] == "unsaved edit",
    "unsaved edit was overwritten")
  assert(vim.bo.modified, "buffer lost modified state")
end)
vim.fn.delete(path)
if not ok then
  print(err)
  vim.cmd("cquit 1")
end
vim.cmd("qa!")
''')
            result = subprocess.run(
                ['nvim', '--headless', '-u', 'NONE', '-c',
                 'lua dofile(' + json.dumps(str(script)) + ')'],
                text=True, capture_output=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
