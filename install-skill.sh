#!/usr/bin/env bash

set -euo pipefail

repo_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
source_dir="$repo_root/skills/nix-agent"

target=${1:-opencode}

case "$target" in
  opencode)
    skills_root="$HOME/.config/opencode/skills"
    ;;
  claude)
    skills_root="$HOME/.claude/skills"
    ;;
  *)
    printf 'Usage: %s [opencode|claude]\n' "$(basename "$0")" >&2
    exit 1
    ;;
esac

dest_dir="$skills_root/nix-agent"

mkdir -p "$skills_root"
rm -rf "$dest_dir"
cp -R "$source_dir" "$dest_dir"

printf 'Installed nix-agent skill to %s\n' "$dest_dir"
