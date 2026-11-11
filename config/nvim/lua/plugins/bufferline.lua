return {
  {
    "akinsho/bufferline.nvim",
    opts = {
      options = {
        middle_mouse_command = function(buffer)
          Snacks.bufdelete(buffer)
        end,
      },
    },
  },
}
