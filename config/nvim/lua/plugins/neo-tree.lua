local function copy_path(modifier)
  return function(state)
    local node = state.tree:get_node()
    if not node or (node.type ~= "file" and node.type ~= "directory") then
      vim.notify("Select a file or folder to copy its path", vim.log.levels.WARN)
      return
    end
    local path = node.path
    if modifier == ":." then
      path = vim.uv.fs_realpath(path) or path
    end
    local text = vim.fn.fnamemodify(path, modifier)
    vim.fn.setreg("+", text)
    vim.notify("Copied: " .. text)
  end
end

local function selected_directory(state)
  local node = state.tree:get_node()
  if not node or (node.type ~= "file" and node.type ~= "directory") then
    error("Select a file or folder first", 0)
  end
  local path = vim.fn.fnamemodify(node.path, ":p")
  if node.type == "file" then
    path = vim.fn.fnamemodify(path, ":h")
  end
  if vim.fn.isdirectory(path) ~= 1 then
    error("Folder no longer exists: " .. path, 0)
  end
  return path
end

local function folder_action(action)
  return function(state)
    local ok, err = pcall(function()
      action(selected_directory(state))
    end)
    if not ok then
      vim.notify(tostring(err), vim.log.levels.ERROR)
    end
  end
end

local function open_desktop(path)
  vim.system({ "xdg-open", path }, { detach = true }, function(result)
    if result.code ~= 0 then
      vim.schedule(function()
        vim.notify("xdg-open failed: " .. (result.stderr or tostring(result.code)), vim.log.levels.ERROR)
      end)
    end
  end)
end

local function command(args)
  local result = vim.system(args, { text = true }):wait(3000)
  if result.code ~= 0 then
    error(args[1] .. " failed: " .. (result.stderr or tostring(result.code)), 0)
  end
  return vim.trim(result.stdout or "")
end

local function open_ranger(path)
  if not vim.env.TMUX or not vim.env.TMUX_PANE then
    error("Open Ranger requires Neovim inside the tmux IDE", 0)
  end
  if path:find("[%c]") then
    error("Ranger navigation does not support control characters in paths", 0)
  end
  local session = command({ "tmux", "display-message", "-p", "-t", vim.env.TMUX_PANE, "#{session_id}" })
  local panes = command({
    "tmux",
    "list-panes",
    "-s",
    "-t",
    session,
    "-F",
    "#{window_index}\t#{pane_id}\t#{pane_tty}\t#{@role}",
  })
  local pane, tty
  for line in panes:gmatch("[^\n]+") do
    local index, id, terminal, role = line:match("^(%d+)\t(%%%d+)\t([^\t]+)\t(.*)$")
    if index == "5" and role == "ranger" then
      if pane then
        error("Multiple Ranger panes found in tmux window 5", 0)
      end
      pane, tty = id, terminal
    end
  end
  if not pane then
    error("No managed Ranger pane in window 5 of this tmux session; start a fresh btide session", 0)
  end
  -- The managed restart loop can make tmux report bash instead of ranger.
  -- Inspect the terminal's foreground process group before sending console input.
  local processes = command({ "ps", "-t", tty, "-o", "pid=,ppid=,pgid=,tpgid=,stat=,comm=" })
  local rows, ranger = {}, nil
  for line in processes:gmatch("[^\n]+") do
    local pid, parent, group, foreground, status, name =
      line:match("^%s*(%d+)%s+(%d+)%s+(%d+)%s+(%-?%d+)%s+(%S+)%s+(.+)$")
    if pid then
      rows[pid] = { parent = parent, group = group, foreground = foreground, status = status, name = name }
      if group == foreground and name == "ranger" and not status:find("[TZ]") then
        if ranger then
          error("Multiple foreground Ranger processes in target pane", 0)
        end
        ranger = pid
      end
    end
  end
  if not ranger then
    error("Ranger is not running in the target pane", 0)
  end
  local ancestors, parent = {}, rows[ranger].parent
  while rows[parent] and not ancestors[parent] do
    ancestors[parent] = true
    parent = rows[parent].parent
  end
  for pid, process in pairs(rows) do
    if process.group == process.foreground and pid ~= ranger and not ancestors[pid] then
      error("Ranger pane is busy with another foreground application", 0)
    end
  end
  -- Ranger's cd takes the raw remainder, not shell-quoted arguments.
  -- Double percent signs to prevent Ranger console macro expansion.
  command({ "tmux", "send-keys", "-t", pane, "C-c", ";", "send-keys", "-t", pane, ":" })
  -- Ranger clears queued keys when it opens its console; wait for the prompt
  -- before typing the path, rather than losing input sent in the same batch.
  local ready = vim.wait(1000, function()
    return command({ "tmux", "capture-pane", "-p", "-t", pane }):match("\n:%s*$") ~= nil
  end, 20)
  if not ready then
    error("Ranger console did not become ready", 0)
  end
  command({
    "tmux",
    "send-keys",
    "-t",
    pane,
    "-l",
    "cd " .. path:gsub("%%", "%%%%"),
    ";",
    "send-keys",
    "-t",
    pane,
    "Enter",
    ";",
    "select-window",
    "-t",
    pane,
    ";",
    "select-pane",
    "-t",
    pane,
  })
end

return {
  {
    "nvim-neo-tree/neo-tree.nvim",
    opts = {
      window = {
        mappings = {
          ["<leader>ga"] = { copy_path(":p"), desc = "Copy absolute path" },
          ["<leader>gr"] = { copy_path(":."), desc = "Copy relative path" },
          ["<leader>gn"] = { copy_path(":t"), desc = "Copy file or folder name" },
          ["<leader>o"] = { folder_action(open_desktop), desc = "Open folder in desktop file manager" },
          ["<leader>r"] = { folder_action(open_ranger), desc = "Open folder in Ranger (tmux window 5)" },
        },
      },
      filesystem = {
        filtered_items = {
          visible = true,
          hide_dotfiles = true,
          hide_gitignored = true,
        },
      },
    },
  },
}
