# 💤 LazyVim

A starter template for [LazyVim](https://github.com/LazyVim/LazyVim).
Refer to the [documentation](https://lazyvim.github.io/installation) to get started.

Neo-tree stays closed on startup. Open it with `Space e`. Dotfiles and Git-ignored files are visible by default. Press `H` in the explorer to hide or show them.

In Neo-tree, use `Space ga` to copy the selected file or folder's absolute path,
`Space gr` to copy its path relative to Neovim's current working directory, and
`Space gn` to copy its name (including the extension for files). These mappings
copy to the system clipboard.

In Neo-tree, `Space o` opens the selected folder in the desktop file manager
with `xdg-open`. `Space r` navigates the existing managed Ranger pane in window
5 of the same tmux IDE session and switches to it. Start Ranger once with Alt+5 first. Selecting a file opens its
parent folder instead. These mappings apply only inside Neo-tree.

Desktop opening requires a graphical session and a file-manager association.
Ranger opening requires tmux, `ps`, and an idle Ranger in the managed pane;
it refuses missing panes, other foreground applications and paths containing
terminal control characters. It cancels any open Ranger console before
navigating. It does not restart Ranger or create another instance.

To reopen the editor when only Neo-tree remains, select a file and press Enter;
the editor opens on the right. Use `:rightbelow vnew` for an empty editor split.
