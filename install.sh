#!/usr/bin/env bash
set -euo pipefail
root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
version="$(cat "$root/VERSION")"
if [[ $# -eq 1 && "$1" == --version ]]; then
    printf '%s\n' "$version"
    exit 0
fi
printf 'BTIDE %s\n' "$version"
exec "$root/bootstrap.sh" "$@"
