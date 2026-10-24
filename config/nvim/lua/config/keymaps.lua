-- Keymaps are automatically loaded on the VeryLazy event
-- Default keymaps that are always set: https://github.com/LazyVim/LazyVim/blob/main/lua/lazyvim/config/keymaps.lua
-- Add any additional keymaps here

vim.keymap.set("n", "<C-a>", "ggVG", { desc = "Select all text" })

vim.keymap.set("n", "<C-f>", "/", { desc = "Find in buffer" })
vim.keymap.set("i", "<C-f>", "<Esc>/", { desc = "Find in buffer" })

-- Leave the cursor in the search field; confirm each replacement.
vim.keymap.set("n", "<C-h>", ":%s///gc<Left><Left><Left><Left>", { desc = "Replace in buffer" })
vim.keymap.set("i", "<C-h>", "<Esc>:%s///gc<Left><Left><Left><Left>", { desc = "Replace in buffer" })
