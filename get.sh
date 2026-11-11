#!/bin/sh
# Install from a disposable checkout; installed configuration is copied, not linked.
set -eu

for command in git bash python3 make mktemp; do
    if ! command -v "$command" >/dev/null 2>&1; then
        printf 'BTIDE installer requires %s. Install it and retry.\n' "$command" >&2
        exit 1
    fi
done

temporary_root="${TMPDIR:-/tmp}/btide"
python3 - "$temporary_root" <<'PY'
import os
from pathlib import Path
import stat
import sys

root = Path(sys.argv[1])
root.mkdir(mode=0o700, exist_ok=True)
info = root.lstat()
if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
    sys.exit('Refusing unsafe temporary directory: ' + str(root))
PY
checkout=$(mktemp -d "$temporary_root/install.XXXXXXXX")
trap 'rm -rf -- "$checkout"' 0
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

git clone --depth 1 -- https://github.com/VBenevides/btide.git "$checkout/repo" </dev/null
INSTALL_ARGS=$(python3 -c 'import shlex, sys; print(shlex.join(sys.argv[1:]))' --copy-config "$@")
export INSTALL_ARGS
make -C "$checkout/repo" install </dev/null
