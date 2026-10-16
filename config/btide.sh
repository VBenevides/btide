#!/usr/bin/env bash

# ============================================================================
# ~/.local/bin/btide
#
# BTIDE project tmux workspace:
#
#   1. Code (Neovim only)
#   2. PiG (lazy)
#   3. Git (lazy)
#   4. Shell (lazy)
#   5. Ranger (lazy; image previews require --include kitty)
#
#
# Managed applications automatically restart when they exit:
#
#   :q in Neovim   -> Neovim reopens
#   PiG exits      -> PiG reopens
#   q in LazyGit   -> LazyGit reopens
#   exit / Ctrl+D  -> User's default shell reopens
#   q in Ranger    -> Ranger reopens
#
#
# Commands:
#
#   btide
#       Create/repair/attach to project session.
#
#   btide_reload
#       Repair the current project session.
#
#   btide_close
#       Destroy the entire project session.
#
#
# tmux bindings installed by btide:
#
#   Ctrl+b x
#       Restart current pane.
#
#   Ctrl+b &
#       Block destruction of managed IDE windows.
#
#   Ctrl+b X
#       Confirm and destroy the entire session.
#
#   Ctrl+b d
#       Normal detach.
#
#   Ctrl+b ?
#       Shows the bindings above with descriptions.
# ============================================================================

# ----------------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------------

# Delay before restarting an application that exits.
#
# This prevents an accidental high-CPU loop if an executable is missing or
# repeatedly crashes immediately.
_TM_RESTART_DELAY="0.20"

# Bump this whenever the Ranger invocation changes.
_TM_RANGER_VERSION="optional-kitty-v4"

# ----------------------------------------------------------------------------
# Managed commands
#
# IMPORTANT:
#
# Do NOT use "exec" here.
#
# The outer shell is deliberately kept alive and restarts the application
# whenever the application exits.
# ----------------------------------------------------------------------------

_TM_EDITOR_CMD='
while :; do
    if [ -d "$HOME/.config/btide/nvim.conf" ]; then
        env -u XDG_DATA_HOME -u XDG_CACHE_HOME -u XDG_STATE_HOME \
            XDG_CONFIG_HOME="$HOME/.config" NVIM_APPNAME=btide/nvim.conf nvim
    else
        env -u NVIM_APPNAME XDG_CONFIG_HOME="$HOME/.config" nvim
    fi
    sleep 0.20
done
'

_TM_PI_CMD='
pig=""
for candidate in "$HOME/.local/bin/pig-plugins" "$HOME/pig/bin/pig-plugins"; do
    if [ -x "$candidate" ]; then pig="$candidate"; break; fi
done
if [ -z "$pig" ]; then
    installer=$(mktemp) || exit 1
    if ! curl -fsSL https://raw.githubusercontent.com/VBenevides/pig-plugins/main/scripts/install.sh -o "$installer"; then
        rm -f "$installer"
        echo "PiG installer download failed" >&2
        exit 1
    fi
    sh "$installer"
    install_status=$?
    rm -f "$installer"
    [ "$install_status" -eq 0 ] || exit "$install_status"
    for candidate in "$HOME/.local/bin/pig-plugins" "$HOME/pig/bin/pig-plugins"; do
        if [ -x "$candidate" ]; then pig="$candidate"; break; fi
    done
    if [ -z "$pig" ]; then echo "PiG executable not found after installation" >&2; exit 1; fi
fi
while :; do
    "$pig"
    sleep 0.20
done
'

_TM_GIT_CMD="
while :; do
    lazygit
    sleep $_TM_RESTART_DELAY
done
"

_TM_SHELL_CMD="
while :; do
    \"\${SHELL:-/bin/sh}\"
    sleep $_TM_RESTART_DELAY
done
"

_TM_RANGER_CMD='
while :; do
    if [ -f "$HOME/.config/btide/kitty.conf" ]; then
        ranger --cmd="set preview_files true" --cmd="set use_preview_script true" \
            --cmd="set preview_images true" --cmd="set preview_images_method kitty"
    else
        ranger --cmd="set preview_images false"
    fi
    sleep 0.20
done
'

# ============================================================================
# tmux server configuration
# ============================================================================

# Use a separate server so BTIDE never changes ordinary tmux sessions.
tmux() {
  local socket="${BTIDE_TMUX_SOCKET:-btide}"
  if [[ -f "$HOME/.config/btide/tmux.conf" ]]; then
    command tmux -L "$socket" -f "$HOME/.config/btide/tmux.conf" "$@"
  elif [[ -f "$HOME/.tmux.conf" ]]; then
    command tmux -L "$socket" -f "$HOME/.tmux.conf" "$@"
  else
    command tmux -L "$socket" "$@"
  fi
}

_tm_enable_kitty_passthrough() {
  [[ -f "$HOME/.config/btide/kitty.conf" ]] || return 0
  # The server MUST already exist before this function is called.
  #
  # Prefer "all" when supported. Fall back to "on".
  tmux set-option -g allow-passthrough all >/dev/null 2>&1 ||
    tmux set-option -g allow-passthrough on >/dev/null 2>&1 ||
    true
}

_tm_install_keybindings() {
  tmux bind-key -n M-1 select-window -t Code
  tmux bind-key -n M-2 select-window -t PiG
  tmux bind-key -n M-3 select-window -t Git
  tmux bind-key -n M-4 select-window -t Shell
  tmux bind-key -n M-5 select-window -t Ranger
  # ------------------------------------------------------------------------
  # Prefix + x
  #
  # Restart the existing pane instead of destroying it.
  #
  # respawn-pane -k kills its current command and starts the command that
  # originally created / last respawned the pane.
  # ------------------------------------------------------------------------

  tmux bind-key \
    -N "Restart current pane" \
    x \
    respawn-pane -k \; run-shell 'tmux wait-for -S #{pane_id}'

  # ------------------------------------------------------------------------
  # Prefix + &
  #
  # Don't destroy individual windows in this IDE.
  #
  # The complete project should instead be closed with Prefix + X.
  # ------------------------------------------------------------------------

  tmux bind-key \
    -N "Protected IDE window - use X to close session" \
    '&' \
    display-message \
    "IDE windows are protected - use Prefix+X to close the session"

  # ------------------------------------------------------------------------
  # Prefix + Shift+X
  #
  # "X" means Shift+x in tmux's prefix key table.
  # ------------------------------------------------------------------------

  tmux bind-key \
    -N "Kill current IDE session" \
    X \
    confirm-before \
    -p "Kill entire session #S? (y/n)" \
    kill-session
}

# ============================================================================
# General helpers
# ============================================================================

_tm_window_exists() {
  local name="$1"
  local window="$2"

  tmux list-windows \
    -t "$name" \
    -F '#{window_name}' \
    2>/dev/null |
    grep -Fxq "$window"
}

_tm_first_pane() {
  local target="$1"

  tmux list-panes \
    -t "$target" \
    -F '#{pane_id}' \
    2>/dev/null |
    head -n1
}

_tm_mark_window_protected() {
  local target="$1"

  tmux set-option \
    -w \
    -t "$target" \
    @tm_ide_protected 1
}

# ============================================================================
# Create Code
# ============================================================================

_tm_create_code_window() {
  local name="$1"
  local cwd="$2"

  tmux new-window \
    -d \
    -t "$name:1" \
    -n "Code" \
    -c "$cwd" \
    /bin/sh -c "$_TM_EDITOR_CMD"

  local editor
  editor="$(
    tmux list-panes \
      -t "$name:Code" \
      -F '#{pane_id}' |
      head -n1
  )"

  tmux set-option \
    -p \
    -t "$editor" \
    @role editor


  _tm_mark_window_protected "$name:Code"
}

# ============================================================================
# Create Git
# ============================================================================

_tm_create_git_window() {
  local name="$1"
  local cwd="$2"

  tmux new-window \
    -d \
    -t "$name:3" \
    -n "Git" \
    -c "$cwd" \
    /bin/sh -c 'tmux wait-for "$TMUX_PANE"; '"$_TM_GIT_CMD"

  local pane
  pane="$(_tm_first_pane "$name:Git")"

  if [[ -n "$pane" ]]; then
    tmux set-option \
      -p \
      -t "$pane" \
      @role git
  fi

  _tm_mark_window_protected "$name:Git"
}

# ============================================================================
# Create Shell
# ============================================================================

_tm_create_shell_window() {
  local name="$1"
  local cwd="$2"

  tmux new-window \
    -d \
    -t "$name:4" \
    -n "Shell" \
    -c "$cwd" \
    /bin/sh -c 'tmux wait-for "$TMUX_PANE"; '"$_TM_SHELL_CMD"

  local pane
  pane="$(_tm_first_pane "$name:Shell")"

  if [[ -n "$pane" ]]; then
    tmux set-option \
      -p \
      -t "$pane" \
      @role shell
  fi

  _tm_mark_window_protected "$name:Shell"
}

# ============================================================================
# Create Ranger
# ============================================================================

_tm_create_ranger_window() {
  local name="$1"
  local cwd="$2"

  tmux new-window \
    -d \
    -t "$name:5" \
    -n "Ranger" \
    -c "$cwd" \
    /bin/sh -c 'tmux wait-for "$TMUX_PANE"; '"$_TM_RANGER_CMD"

  local ranger_pane
  ranger_pane="$(_tm_first_pane "$name:Ranger")"

  if [[ -n "$ranger_pane" ]]; then
    tmux set-option \
      -p \
      -t "$ranger_pane" \
      @role ranger

    tmux set-option \
      -p \
      -t "$ranger_pane" \
      @tm_ranger_version "$_TM_RANGER_VERSION"
  fi

  _tm_mark_window_protected "$name:Ranger"
}

# Deferred panes wait on their unique pane ID until first selection.
_tm_create_pi_window() {
  local name="$1" cwd="$2" pane
  tmux new-window -d -t "$name:2" -n PiG -c "$cwd" \
    /bin/sh -c 'tmux wait-for "$TMUX_PANE"; '"$_TM_PI_CMD" || return 1
  pane="$(_tm_first_pane "$name:PiG")"
  tmux set-option -p -t "$pane" @role pi
  tmux set-option -w -t "$name:PiG" remain-on-exit on
  _tm_mark_window_protected "$name:PiG"
}

_tm_install_lazy_hook() {
  tmux set-hook -t "$1" after-select-window \
    'run-shell "tmux wait-for -S #{pane_id}"'
}

_tm_repair_session() {
  local name="$1" cwd="$2"
  _tm_enable_kitty_passthrough
  _tm_install_keybindings
  tmux set-option -t "$name" renumber-windows off
  # Never kill or respawn applications in an existing session.
  # Old split layouts can be replaced by closing the session explicitly.
  if [[ "$(tmux show-options -qv -t "$name" @tm_layout)" != "lazy-v2" ]]; then
    printf '%s\n' 'Existing layout preserved; start a fresh session for the five-tab layout.' >&2
    return 0
  fi
  _tm_install_lazy_hook "$name"
  _tm_window_exists "$name" Code || _tm_create_code_window "$name" "$cwd"
  _tm_window_exists "$name" PiG || _tm_create_pi_window "$name" "$cwd"
  _tm_window_exists "$name" Git || _tm_create_git_window "$name" "$cwd"
  _tm_window_exists "$name" Shell || _tm_create_shell_window "$name" "$cwd"
  _tm_window_exists "$name" Ranger || _tm_create_ranger_window "$name" "$cwd"
}

# ============================================================================
# Reload / repair current project
# ============================================================================

_tm_in_btide_server() {
  [[ -n "${TMUX:-}" ]] || return 1
  local current_socket btide_socket
  current_socket="$(command tmux display-message -p '#{socket_path}')" || return 1
  btide_socket="$(tmux display-message -p '#{socket_path}')" || return 1
  [[ "$current_socket" == "$btide_socket" ]]
}

btide_reload() {
  if ! _tm_in_btide_server; then
    echo "btide_reload must be run inside a BTIDE tmux session." >&2
    return 1
  fi

  local name
  name="$(tmux display-message -p '#S')"

  local cwd
  cwd="$(
    tmux show-options \
      -t "$name" \
      -v \
      @project_cwd \
      2>/dev/null
  )"

  if [[ -z "$cwd" ]]; then
    cwd="$(
      tmux display-message \
        -p \
        '#{pane_current_path}'
    )"

    tmux set-option \
      -t "$name" \
      @project_cwd "$cwd"
  fi

  _tm_repair_session "$name" "$cwd"

  tmux display-message \
    "IDE bindings reloaded; start a fresh session to apply layout changes"
}

# ============================================================================
# Close current project completely
# ============================================================================

btide_close() {
  if ! _tm_in_btide_server; then
    echo "btide_close must be run inside a BTIDE tmux session." >&2
    return 1
  fi

  local name
  name="$(tmux display-message -p '#S')"

  tmux kill-session \
    -t "$name"
}

# ============================================================================
# Main launcher
# ============================================================================

_tm_open_separate_window() {
  local config="$HOME/.config/btide/config.yml"
  if [[ ! -e "$config" && ! -L "$config" ]]; then
    mkdir -p "${config%/*}" || return 1
    ( set -C; printf 'open_separate_window: false\n' > "$config" ) || return 1
  fi
  if [[ ! -f "$config" || ! -r "$config" ]]; then
    printf 'Cannot read BTIDE configuration: %s\n' "$config" >&2
    return 1
  fi
  local line value=false seen=0
  local blank='^[[:space:]]*(#.*)?$'
  local setting='^[[:space:]]*open_separate_window:[[:space:]]*(true|false)[[:space:]]*(#.*)?$'
  while IFS= read -r line || [[ -n "$line" ]]; do
    if [[ "$line" =~ $blank ]]; then
      continue
    elif [[ "$line" =~ $setting && "$seen" == 0 ]]; then
      seen=1
      line="${line#*:}"
      line="${line%%#*}"
      line="${line//[[:space:]]/}"
      value="$line"
    else
      printf 'Invalid BTIDE configuration in %s; expected open_separate_window: true or false\n' "$config" >&2
      return 1
    fi
  done < "$config"
  printf '%s\n' "$value"
}

btide() {
  local cwd="$PWD"
  local open_separate_window
  open_separate_window="$(_tm_open_separate_window)" || return 1
  local launch_kitty=0
  if [[ "$open_separate_window" == true && -z "${TMUX:-}" &&
        ( -n "${DISPLAY:-}" || -n "${WAYLAND_DISPLAY:-}" ) ]]; then
    if [[ ! -f "$HOME/.config/btide/kitty.conf" ]]; then
      printf '%s\n' 'Separate windows require Kitty support. Run ./install.sh --include kitty.' >&2
      return 1
    fi
    if ! command -v kitty >/dev/null 2>&1; then
      printf '%s\n' 'Kitty is missing. Run ./install.sh --include kitty.' >&2
      return 1
    fi
    launch_kitty=1
  fi

  local name
  name="$(basename "$PWD")"

  # Sanitize characters which are inconvenient in tmux target names.
  name="${name//./_}"
  name="${name//:/_}"
  name="${name// /_}"

  # ------------------------------------------------------------------------
  # IMPORTANT:
  #
  # has-session is the ONLY tmux operation we perform before knowing whether
  # the tmux server exists.
  #
  # stderr is discarded intentionally when there is no server.
  # ------------------------------------------------------------------------

  if ! tmux has-session \
    -t "=$name" \
    2>/dev/null; then
    # --------------------------------------------------------------------
    # Create the first session/window.
    #
    # This also starts the tmux server.
    # --------------------------------------------------------------------

    tmux new-session \
      -d \
      -s "$name" \
      -n "Code" \
      -c "$cwd" \
      /bin/sh -c "$_TM_EDITOR_CMD" ||
      return 1

    # --------------------------------------------------------------------
    # The server now exists.
    # --------------------------------------------------------------------

    _tm_enable_kitty_passthrough
    _tm_install_keybindings

    tmux set-option \
      -t "$name" \
      @project_cwd "$cwd"

    tmux set-option \
      -t "$name" \
      base-index 1

    tmux set-option \
      -t "$name" \
      renumber-windows off

    # --------------------------------------------------------------------
    # Ensure the first Code window is index 1.
    # --------------------------------------------------------------------

    local code_index
    code_index="$(
      tmux display-message \
        -p \
        -t "$name:Code" \
        '#{window_index}'
    )"

    if [[ "$code_index" != "1" ]]; then
      tmux move-window \
        -s "$name:Code" \
        -t "$name:1"
    fi

    # --------------------------------------------------------------------
    # Mark initial editor pane.
    # --------------------------------------------------------------------

    local editor
    editor="$(
      tmux list-panes \
        -t "$name:Code" \
        -F '#{pane_id}' |
        head -n1
    )"

    tmux set-option \
      -p \
      -t "$editor" \
      @role editor

    _tm_install_lazy_hook "$name"
    _tm_create_pi_window "$name" "$cwd"

    _tm_mark_window_protected "$name:Code"

    # --------------------------------------------------------------------
    # Fixed remaining windows.
    # --------------------------------------------------------------------

    _tm_create_git_window \
      "$name" \
      "$cwd"

    _tm_create_shell_window \
      "$name" \
      "$cwd"

    _tm_create_ranger_window \
      "$name" \
      "$cwd"

    tmux set-option -t "$name" @tm_layout lazy-v2
  else
    # --------------------------------------------------------------------
    # Existing session.
    # --------------------------------------------------------------------

    tmux set-option \
      -t "$name" \
      @project_cwd "$cwd"

    _tm_repair_session \
      "$name" \
      "$cwd"
  fi

  # ------------------------------------------------------------------------
  # Select Code + editor.
  # ------------------------------------------------------------------------

  tmux select-window \
    -t "$name:Code"

  local editor_pane
  editor_pane="$(
    tmux list-panes \
      -t "$name:Code" \
      -F '#{pane_id} #{@role}' |
      awk '$2 == "editor" { print $1; exit }'
  )"

  if [[ -n "$editor_pane" ]]; then
    tmux select-pane \
      -t "$editor_pane"
  fi

  # ------------------------------------------------------------------------
  # Attach or switch.
  # ------------------------------------------------------------------------

  if _tm_in_btide_server; then
    tmux switch-client -t "=$name"
  elif [[ "$launch_kitty" == 1 ]]; then
    kitty --config "$HOME/.config/btide/kitty.conf" --directory "$cwd" \
      tmux -L "${BTIDE_TMUX_SOCKET:-btide}" attach-session -t "=$name"
  else
    TMUX='' tmux attach-session -t "=$name"
  fi
}

if [ -n "${BASH_VERSION:-}" ] && [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  export PATH="$HOME/.local/bin:$PATH"
  case "${1:-}" in
    '') btide ;;
    --reload) btide_reload ;;
    --close) btide_close ;;
    --help|-h) printf '%s\n' 'Usage: btide [--reload|--close|--help]' ;;
    *) printf 'Unknown option: %s\n' "$1" >&2; exit 1 ;;
  esac
fi
