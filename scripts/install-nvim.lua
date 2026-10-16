-- Full bootstrap provisioning only. --check never starts Neovim or installers.
local function main()
  local config = require("lazy.core.config")
  local manage = require("lazy.manage")
  local function verify_plugins()
    for name, plugin in pairs(config.plugins) do
      if not plugin._.installed or vim.fn.isdirectory(plugin.dir) ~= 1 then
        error("Missing Neovim plugin: " .. name)
      end
      for _, task in ipairs(plugin._.tasks or {}) do
        if task:has_errors() then
          error("Neovim plugin failed: " .. name .. ": " .. task:output(vim.log.levels.ERROR))
        end
      end
    end
  end
  manage.install({ wait = true, show = false, concurrency = 4 })
  verify_plugins()
  manage.update({ wait = true, show = false, concurrency = 4 })
  verify_plugins()

  require("lazy").load({ plugins = { "mason.nvim" } })
  local registry = require("mason-registry")
  local refreshed, refresh_ok = false, false
  registry.refresh(function(ok)
    refresh_ok, refreshed = ok, true
  end)
  if not vim.wait(60000, function() return refreshed end, 50) or not refresh_ok then
    error("Mason registry refresh failed or timed out; see :MasonLog")
  end
  local packages = vim.json.decode(table.concat(vim.fn.readfile(vim.env.PORTABLE_IDE_NVIM_TOOLS), "\n"))
  local pending = vim.tbl_keys(packages)
  table.sort(pending)
  local active, complete = 0, 0
  local failures = {}
  local total = #pending
  local function usable(name, package)
    if not package:is_installed() then return false end
    if not package:get_receipt():is_present() then return false end
    for _, binary in ipairs(packages[name]) do
      if vim.fn.executable(vim.fn.stdpath("data") .. "/mason/bin/" .. binary) ~= 1 then return false end
    end
    return true
  end
  local function advance()
    while active < 4 and #pending > 0 do
      local name = table.remove(pending, 1)
      local package = registry.get_package(name)
      active = active + 1
      local function finished(success, detail)
        if not success or not usable(name, package) then
          table.insert(failures, name)
          io.stderr:write("Mason installation failed: " .. name .. ": " .. tostring(detail) .. "; see :MasonLog\n")
        end
        active, complete = active - 1, complete + 1
        vim.schedule(advance)
      end
      if package:is_installing() then
        package:once("install:success", function() finished(true) end)
        package:once("install:failed", function(err) finished(false, err) end)
      else
        package:install({ force = true }, vim.schedule_wrap(finished))
      end
    end
  end
  advance()
  if not vim.wait(900000, function() return complete == total end, 100) then
    error("Mason package installation timed out after 15 minutes")
  end
  if #failures > 0 then
    error("Mason packages failed: " .. table.concat(failures, ", "))
  end
  local parser_options = LazyVim.opts("nvim-treesitter")
  local parsers = parser_options.ensure_installed
  if type(parsers) ~= "table" or #parsers == 0 then error("Missing configured Tree-sitter parsers") end
  -- Own the bounded install below rather than racing LazyVim's automatic job.
  parser_options.ensure_installed = {}
  require("lazy").load({ plugins = { "nvim-treesitter" } })
  local treesitter = require("nvim-treesitter")
  local options = { max_jobs = 4, summary = true }
  if not treesitter.install(parsers, options):wait(180000)
    or not treesitter.update(parsers, options):wait(180000) then
    error("Tree-sitter parser installation failed; inspect :TSLog")
  end
  local parser_dir = vim.fn.stdpath("data") .. "/site/parser/"
  for _, language in ipairs(parsers) do
    local library = parser_dir .. language .. ".so"
    if vim.fn.filereadable(library) ~= 1 then error("Missing parser library: " .. language) end
    vim.treesitter.language.add(language, { path = library })
    if not vim.treesitter.language.inspect(language) then error("Cannot load parser: " .. language) end
  end
  local result = { plugins = {}, parsers = parsers }
  for name, plugin in pairs(config.plugins) do
    if plugin.url then
      local commit = vim.fn.system({ "git", "-C", plugin.dir, "rev-parse", "HEAD" })
      if vim.v.shell_error ~= 0 then error("Cannot verify plugin commit: " .. name) end
      result.plugins[name] = { directory = plugin.dir, commit = vim.trim(commit) }
    end
  end
  vim.fn.writefile({ vim.json.encode(result) }, vim.env.PORTABLE_IDE_NVIM_REPORT)
  print("LazyVim plugins, " .. total .. " Mason packages and " .. #parsers .. " parsers installed")
end

vim.schedule(function()
  local ok, err = xpcall(main, debug.traceback)
  if not ok then
    io.stderr:write(tostring(err) .. "\n")
    vim.cmd("cquit 1")
  else
    vim.cmd("qa!")
  end
end)
