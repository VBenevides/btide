-- Autocmds are automatically loaded on the VeryLazy event
-- Default autocmds that are always set: https://github.com/LazyVim/LazyVim/blob/main/lua/lazyvim/config/autocmds.lua
--
-- Add any additional autocmds here
-- with `vim.api.nvim_create_autocmd`
--
-- Or remove existing autocmds by their group name (which is prefixed with `lazyvim_` for the defaults)
-- e.g. vim.api.nvim_del_augroup_by_name("lazyvim_wrap_spell")

-- Focus events are not reliable in every terminal/tmux session. Poll while idle
-- too, without prompting about or overwriting buffers with unsaved edits.
local refresh_group = vim.api.nvim_create_augroup("btide_external_changes", { clear = true })
local function refresh_files()
  if vim.fn.mode() ~= "n" or vim.fn.getcmdwintype() ~= "" then
    return
  end
  for _, buffer in ipairs(vim.api.nvim_list_bufs()) do
    if vim.api.nvim_buf_is_loaded(buffer) and vim.bo[buffer].buftype == "" and not vim.bo[buffer].modified then
      vim.cmd("checktime " .. buffer)
    end
  end
end

vim.api.nvim_create_autocmd({ "FocusGained", "BufEnter" }, {
  group = refresh_group,
  callback = refresh_files,
})

local refresh_timer = vim.fn.timer_start(1000, refresh_files, { ["repeat"] = -1 })
vim.api.nvim_create_autocmd("VimLeavePre", {
  group = refresh_group,
  once = true,
  callback = function()
    vim.fn.timer_stop(refresh_timer)
  end,
})
