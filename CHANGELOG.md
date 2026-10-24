# Changelog

Notable changes to BTIDE, a portable terminal IDE workspace.

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
