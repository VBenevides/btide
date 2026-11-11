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

-- Compare the saved Git version with the live, editable buffer.
vim.keymap.set("n", "<leader>gd", function()
  require("gitsigns").diffthis("HEAD", { vertical = true })
end, { desc = "Diff against HEAD (side by side)" })
vim.keymap.set("n", "<leader>gD", "<cmd>diffoff!<cr>", { desc = "Leave diff mode" })
vim.keymap.set("n", "<leader>gp", function()
  require("gitsigns").preview_hunk()
end, { desc = "Preview Git hunk" })
vim.keymap.set("n", "<leader>gr", function()
  if vim.fn.confirm("Discard this hunk's unstaged changes?", "&Discard\n&Cancel", 2) == 1 then
    require("gitsigns").reset_hunk()
  end
end, { desc = "Discard Git hunk (confirm)" })

vim.keymap.set("n", "<leader>]", function()
  require("neo-tree.command").execute({ action = "focus", source = "filesystem", dir = LazyVim.root() })
end, { desc = "Open project tree" })
vim.keymap.set("n", "<leader>[", function()
  require("neo-tree.command").execute({ action = "close" })
end, { desc = "Close Neo-tree" })
