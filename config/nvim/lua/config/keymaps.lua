-- Keymaps are automatically loaded on the VeryLazy event
-- Default keymaps that are always set: https://github.com/LazyVim/LazyVim/blob/main/lua/lazyvim/config/keymaps.lua
-- Add any additional keymaps here

vim.keymap.set("n", "<C-a>", "ggVG", { desc = "Select all text" })

-- Discard deleted text without changing the clipboard or yank registers.
vim.keymap.set({ "n", "x" }, "d", '"_d', { desc = "Delete without copying" })

vim.keymap.set("n", "<C-f>", "/", { desc = "Find in buffer" })
vim.keymap.set("i", "<C-f>", "<Esc>/", { desc = "Find in buffer" })

vim.keymap.set({ "n", "i" }, "<C-S-f>", function()
  LazyVim.pick("live_grep")()
end, { desc = "Find in project" })

vim.keymap.set({ "n", "i" }, "<C-S-h>", function()
  require("grug-far").open({
    transient = true,
    prefills = { paths = LazyVim.root():gsub(" ", "\\ ") },
  })
end, { desc = "Replace in project" })

-- Leave the cursor in the search field; confirm each replacement.
vim.keymap.set("n", "<C-h>", ":%s///gc<Left><Left><Left><Left>", { desc = "Replace in buffer" })
vim.keymap.set("i", "<C-h>", "<Esc>:%s///gc<Left><Left><Left><Left>", { desc = "Replace in buffer" })
