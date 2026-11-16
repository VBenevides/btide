# Changelog

Notable changes to BTIDE, a portable terminal IDE workspace.

## [0.2.1] - 2026-11-13

### Features

- Add `btide --prune`. It keeps only the newest backup of each path, deletes backups older than 7 days, and deletes files in `~/.local/share/btide` that the current version does not use. Use `--dry-run` to list the changes. It keeps any entry that a shell startup file refers to, and it does not run while an installation is active.
- Run the pruning quietly in the background each time `btide` starts and after a full install. Errors go to `~/.cache/btide/prune.log`.
- Add `btide --size` to show disk use of the BTIDE data, cache, and state directories per component.
- Add `./uninstall.sh --purge` to delete those three directories and the `~/.local/bin` links that point into them. Configuration and other tools stay.
- Install `maintenance.py` with the launcher so the commands work after the checkout is deleted.

### Bugfixes

- Disable the `markdown-preview.nvim` plugin to save about 57 MB. The installer now runs Lazy clean, so existing installations remove the plugin directory.

### Other

- Add tests for backup rules, leftover removal, locking, symbolic links, quiet mode, the launcher options, purge, and the plugin setting.
- Exclude `maintenance.py` from configuration capture with `update-project.py`.
- Document the disk-use commands in the README.

## [0.1.2] - 2026-10-24

### Features

- Add Ctrl+A in Neovim normal mode to select the entire buffer in linewise visual mode, equivalent to `ggVG`.
- Add Ctrl+Shift+F for project-wide find and Ctrl+Shift+H for project-wide replace in normal and insert modes. Replacement uses Grug Far without file-type restrictions.

### Bugfixes

- Make the `d` operator discard deleted text without changing the clipboard or yank registers. Preserve explicit copy commands, counted deletion, and dot repeat.
- Forward distinct Ctrl+Shift+F and Ctrl+Shift+H key sequences from the bundled Kitty configuration instead of invoking Kitty window actions.

### Other

- Document the new shortcuts, clipboard behavior, terminal requirements, and Grug Far replacement controls.
- Add tests for full-buffer selection, clipboard-safe deletion, project shortcuts, Kitty mappings, and tmux prefix handling.
- Add an optional Grug Far integration test for search and replacement across multiple file types, including project paths with spaces.

### Breaking Changes

- Change the tmux prefix from Ctrl+A to Ctrl+B so Ctrl+A reaches Neovim. Use Ctrl+B for prefix commands.

## [0.1.1] - 2026-10-21

### Features

- Add `btide --update` to install from upstream `main` only when its numeric `MAJOR.MINOR.PATCH` version is newer. Updates use a temporary checkout and standalone copies, back up existing configuration, and retain previously enabled Kitty support.
- Expand `btide --help` and `-h` to describe every launcher option, session requirements, and default launch behavior without starting applications or installing tools.

### Bugfixes

- Keep the outer terminal title set to `BTIDE - <project folder>` across workspace tabs.

### Other

- Install the updater and version metadata alongside the launcher, and exclude these artifacts from configuration capture with `update-project.py`.
- Report update failures and restore the previous version metadata after installation failure so updates remain retryable; partial installation changes are not rolled back.
- Add regression coverage for version ordering, skipped and failed updates, temporary checkout cleanup, launcher help, and terminal titles.

## [0.1.0] - 2026-10-20

### Features

- Introduce a per-project tmux workspace with Neovim, PiG, lazygit, the user's shell, and Ranger. Start Neovim immediately and the other applications on first tab selection.
- Add managed-tab shortcuts, application restarts, shell and Git popups, session reload and close commands, and optional separate Kitty windows.
- Provide isolated tmux and LazyVim configurations without replacing personal defaults or modifying shell startup files. Allow either BTIDE configuration to be disabled independently with `.nouse`.
- Include language servers, debugging tools, formatters, Tree-sitter parsers, Neo-tree actions, and navigation from Neo-tree to the managed Ranger pane.
- Add Linux x86_64 and aarch64 installation with apt, dnf, or pacman prerequisites, checksum-verified runtime downloads, editor provisioning, integrity receipts, offline checks, and configuration-only deployment.
- Support checkout-linked installation and standalone curl installation through a private temporary checkout that is removed on success or failure.
- Add optional Kitty configuration, a bundled Nerd Font, and Ranger image previews. Install PiG through pig-plugins on first use while retaining its normal state paths.
- Back up replaced configuration and launchers with unique timestamps, capture local configuration changes back into the checkout, and provide an uninstall command that retains tools, configuration, backups, and user data.

### Bugfixes

- Remove a trailing NUL byte from the Kitty configuration.
- Install only missing dependencies and reuse existing tools and verified managed releases instead of unnecessarily reinstalling or upgrading them.
- Refresh unmodified Neovim buffers after external file changes, including while idle, without overwriting unsaved edits.

### Other

- Add installation, workspace, configuration, release-integrity, and editor integration tests, plus setup and usage documentation.
- Include the MIT project license and third-party license notices.
