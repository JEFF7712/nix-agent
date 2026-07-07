#!/usr/bin/env bash

set -euo pipefail

repo_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
skills_dir="$repo_root/skills"

target=${1:-opencode}

case "$target" in
  codex)
    skills_root="${CODEX_HOME:-$HOME/.codex}/skills"
    ;;
  opencode)
    skills_root="$HOME/.config/opencode/skills"
    ;;
  claude)
    skills_root="$HOME/.claude/skills"
    ;;
  *)
    printf 'Usage: %s [codex|opencode|claude]\n' "$(basename "$0")" >&2
    exit 1
    ;;
esac

mkdir -p "$skills_root"

for source_dir in "$skills_dir"/*/; do
  skill_name=$(basename "$source_dir")
  dest_dir="$skills_root/$skill_name"
  rm -rf "$dest_dir"
  cp -R "$source_dir" "$dest_dir"
  printf 'Installed %s skill to %s\n' "$skill_name" "$dest_dir"
done
