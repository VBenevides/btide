# BTIDE

A tmux workspace for Neovim, [PiG](https://github.com/VBenevides/pig-plugins), lazygit, a terminal, and Ranger. Each application has its own tab; only Neovim starts immediately.

## Install

Supported platforms: Linux x86_64 and aarch64, including WSL. Requires Bash and Python 3.10+. Run as your normal user, not root.

```bash
git clone https://github.com/VBenevides/BTIDE.git ~/Projects/BTIDE
cd ~/Projects/BTIDE
./install.sh
```

Keep the checkout in place: the launcher and configuration are symlinked to it.
`./install.sh --version` prints `VERSION` without installing anything.

The installer puts an executable `btide` at `~/.local/bin/btide` and configuration under `~/.config/btide/`. It does not replace your normal `~/.tmux.conf`, `~/.config/nvim`, or Kitty configuration. It does not modify shell startup files or your login shell. BTIDE uses your default shell without installing shell frameworks or extensions.

Kitty and Ranger image previews are opt-in:

```bash
./install.sh --include kitty
```

Ensure `~/.local/bin` is already on your PATH, or invoke `~/.local/bin/btide` directly. The executable works from Bash, zsh, Fish, and other shells without sourcing a script.

### Existing installations and backups

Installation replaces BTIDE's active configuration links and the launcher. Each existing destination is first renamed beside the original as `old_name.ext.TIMESTAMP.bak`, for example:

```text
~/.config/btide/tmux.conf.1792151943108503224.bak
~/.local/bin/btide.1792151943115442652.bak
```

Timestamps use nanoseconds; existing backup names are never reused. Symlinks are backed up as symlinks, without changing their referents. This also applies when a previously installed configuration link already matches. No backup flag is required; `--backup-existing` remains accepted for compatibility.

Symlinked installation parent directories are refused. Runtime replacements are staged and verified before the previous installation is backed up. Unchanged verified runtime downloads can be reused.

```bash
./bootstrap.sh --config-only  # Deploy configuration and launcher without downloads
./bootstrap.sh --check        # Verify installed tools, editor artifacts, and configuration
```

Old installations may have links at `~/.tmux.conf` or `~/.config/nvim`. These are not automatically removed or restored; review their backups if you want to restore your previous configuration. Old shell-function installations are not automatically removed from startup files either. In Bash/zsh, `unset -f btide btide_reload btide_close` clears functions that could shadow the executable.

### Dependencies

Every full installation installs missing system prerequisites using apt, dnf, or pacman, with sudo for package installation only. No `--install-deps` flag is needed; it remains accepted for compatibility. Dependencies include terminal/editor tools, compilers, build libraries, and Python with venv/ensurepip. Neither zsh nor Fish is required. `--include kitty` additionally installs Kitty, fontconfig, Pillow, and the bundled font. Previously enabled Kitty support is retained on reinstall. Installation failures stop the installer; missing dependencies are not silently skipped.

Full bootstrap resolves stable upstream releases for Go, Node.js, Neovim, tmux, and lazygit. Distribution tools at least as new as the current release are reused where supported; otherwise managed runtimes are installed under `~/.local/share/btide/` and linked into `~/.local/bin`. Release downloads use upstream SHA-256 checksums. Minimum versions are recorded in `versions.json`.

Full bootstrap also updates BTIDE's LazyVim plugins, configured Mason tools, and Tree-sitter parsers and initializes Ranger's text-preview script. Disabled BTIDE Neovim configurations are not provisioned. Plugin and toolchain receipts are checked before reporting success. Failed downloads, builds, and verification remain errors. `--check` is offline and does not repair or install anything. `--config-only` deploys links without installing dependencies or downloading tools.

PiG installation and plugin configuration are handled by pig-plugins on first use, not by bootstrap. PiG continues to use its normal `~/.pig` installation/state; BTIDE does not redirect it into `~/.config/btide`. Private credentials and session state are not copied or overwritten.

## Installed paths

| Repository source | Destination |
| --- | --- |
| `config/btide.sh` | `~/.local/bin/btide` executable symlink |
| `config/nvim/` | `~/.config/btide/nvim.conf` directory symlink |
| `config/tmux/tmux.conf` | `~/.config/btide/tmux.conf` symlink |
| `config/kitty/kitty.conf` | `~/.config/btide/kitty.conf` symlink, only with `--include kitty` |
| `config/misc/MesloLGSNerdFontMono-Regular.ttf` | `~/.local/share/fonts/btide/`, only with `--include kitty` |

Configuration edits through these symlinks change the checkout. Runtime, editor cache, and integrity receipts stay machine-local. BTIDE Neovim uses `NVIM_APPNAME=btide/nvim.conf`, keeping its data, cache, and state separate from normal Neovim.

### Use your normal tmux or Neovim configuration

Rename either BTIDE configuration to disable it independently:

```bash
mv ~/.config/btide/tmux.conf ~/.config/btide/tmux.conf.nouse
mv ~/.config/btide/nvim.conf ~/.config/btide/nvim.conf.nouse
```

- Without `tmux.conf`, BTIDE loads `~/.tmux.conf` on the next server start.
- Without the `nvim.conf` directory, the next managed Neovim launch uses `~/.config/nvim`.
- Reinstallation preserves `.nouse` choices instead of recreating the disabled configuration.
- Rename `.nouse` back to the original name to enable the BTIDE configuration again.

BTIDE uses its own tmux server (`tmux -L btide`), leaving ordinary tmux sessions alone. tmux reads its startup configuration only when the server starts. To change configuration sources, close all BTIDE sessions first. Alternatively, `tmux -L btide kill-server` stops **all BTIDE sessions and their running applications**; use it only after saving your work. Disabling the tmux config also disables its styling and extra bindings; the launcher still installs its managed-tab bindings.

## Launch and shortcuts

```bash
cd /path/to/project
btide
```

| Shortcut | Tab | Startup |
| --- | --- | --- |
| Alt+1 | Code: Neovim only, explorer closed | Immediate |
| Alt+2 | PiG | First selection |
| Alt+3 | Git: lazygit | First selection |
| Alt+4 | Shell: user's default (`$SHELL`, or `/bin/sh` if unset) | First selection |
| Alt+5 | Ranger | First selection |

PiG checks executable paths in order:

1. `~/.local/bin/pig-plugins`
2. `~/pig/bin/pig-plugins`
3. If neither exists, download and run `https://raw.githubusercontent.com/VBenevides/pig-plugins/main/scripts/install.sh` with `sh`, then check both paths again.

The download must succeed before execution. Installation failures remain visible in the PiG pane; restart it with prefix + `x` to retry explicitly. Review the upstream installer before first use.

Managed applications restart when they exit. The configured tmux prefix is Ctrl+a; Ctrl+b shows hints and enters prefix mode. Prefix + `x` restarts the current pane, `d` detaches, and `X` confirms closing the whole session. Alt+g and Alt+s open temporary lazygit and shell popups; Alt+z zooms a pane.

```bash
btide --reload  # Inside tmux: restore missing tabs without restarting live applications
btide --close   # Inside tmux: destroy the current session
btide --help
```

Existing sessions keep their running layout. Start a fresh session to apply layout changes. Project session names derive from the sanitized directory basename, so projects with the same basename share a session.

By default BTIDE attaches in the current terminal. First launch creates `~/.config/btide/config.yml`:

```yaml
open_separate_window: false
```

After installing with `--include kitty`, set this to `true` to open a separate Kitty window in graphical sessions. Inside the BTIDE tmux server, BTIDE switches sessions instead. From another tmux server, it attaches to BTIDE's separate server. Headless sessions attach in the current terminal. Only unquoted `true`/`false`, blank lines, and comments are accepted; duplicate or invalid settings stop launch.

Ranger image previews are disabled by default, even if your personal Ranger config enables them. `--include kitty` enables them; they need a Kitty-compatible terminal and tmux 3.3+ passthrough. Ordinary browsing supports tmux 3.2a. Optional PDF/archive/media preview helpers are not installed.

## Neovim

Neo-tree stays closed on startup; use `Space e` to open it. Dotfiles and Git-ignored files are initially visible; `H` toggles them. `Space r` in Neo-tree navigates an idle managed Ranger pane in tab 5; start Ranger once with Alt+5 first.

Included language servers: `bashls`, `gopls`, `jsonls`, `lua_ls`, `marksman`, `pyright`, and `ruff`. Go and Python debugging use Delve and debugpy. Formatters and other tools are listed in `config/nvim-tools.json`. Inspect them with `:Lazy`, `:Mason`, `:LspInfo`, and `:ConformInfo`; add extras with `:LazyExtras`.

Ctrl+f searches the current buffer; Ctrl+h opens a whole-buffer substitution with confirmation. See `config/nvim/README.md` for explorer actions.

## Capture local configuration

```bash
./update-project.py --dry-run
./update-project.py
```

Use `--home /path/to/home` for another home directory. The command copies mapped configuration and launcher changes back to the checkout, skipping unchanged content and common private/runtime paths. Symlinked source parents and nested configuration links are rejected. Independent valid changes still proceed if another item fails; failures return a nonzero status. Review the diff before distributing changes.

## Uninstall

```bash
./uninstall.sh
```

This removes this checkout's `~/.local/bin/btide` symlink. Backups, tools, configuration, private data, shell startup files, and running tmux sessions are retained. Repeating uninstall is safe. Foreign launcher files or links and symlinked launcher parent directories are refused.

## Validation

```bash
python3 -m unittest discover -s tests -v
bash -n bootstrap.sh install.sh uninstall.sh config/btide.sh
shellcheck -S warning config/btide.sh
```

Tests use isolated homes and mocked downloads; tmux/editor integration tests run when prerequisites are available. Full network provisioning, real distribution package transactions, authenticated PiG sessions, and aarch64 execution require separate validation.

## License

[MIT](LICENSE). Third-party components retain their licenses; see [THIRD-PARTY-NOTICE.md](THIRD-PARTY-NOTICE.md).
