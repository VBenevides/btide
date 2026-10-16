return {
  {
    "nvim-treesitter/nvim-treesitter",
    opts = function(_, opts)
      -- JSON5 supports comments; Tree-sitter has no separate jsonc parser.
      vim.treesitter.language.register("json5", "jsonc")
      local parsers, seen = {}, {}
      for _, language in ipairs(opts.ensure_installed or {}) do
        language = language == "jsonc" and "json5" or language
        if not seen[language] then
          seen[language] = true
          parsers[#parsers + 1] = language
        end
      end
      opts.ensure_installed = parsers
    end,
  },
}
