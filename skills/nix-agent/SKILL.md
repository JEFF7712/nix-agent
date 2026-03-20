---
name: nix-agent
description: Use when modifying local NixOS configuration through the nix-agent MCP, especially when package lookup or option discovery may require mcp-nixos first.
---

# Nix Agent

## Overview

Use this skill when an agent needs to inspect, patch, validate, or apply NixOS configuration through the `nix-agent` MCP. Core principle: let `mcp-nixos` handle discovery and let `nix-agent` handle local mutation and activation.

## When to Use

- A user wants to edit local NixOS config through MCP tools.
- The request mentions installing a package, looking up an option, or finding a module setting.
- The agent needs a safe, repeatable tool sequence before `nixos-rebuild switch`.
- The host exposes `nix-agent` MCP tools but does not explain their order.

Do not use this skill for imperative package installs or writing secret payloads.

## Quick Reference

- `plan_change(goal)` first
- if `requires_mcp_nixos` is `true`, query `mcp-nixos`
- `apply_patch_set(patch_set)`
- `run_formatters(changed_files)`
- `classify_change(changed_files)`
- if approval is not required, `apply_change(intent, changed_files, flake_uri)`

## Required Workflow

1. Start with `plan_change(goal)`.
2. If the response says `requires_mcp_nixos=true`, stop local mutation and use `mcp-nixos` to resolve the package, option, or module knob first.
3. Build a `PatchSet` and call `apply_patch_set(patch_set)`.
4. If `apply_patch_set()` returns `status="approval_required"`, stop and report that approval is needed before proceeding.
5. Use the returned `changed_files` with `run_formatters(changed_files)`.
6. Call `classify_change(changed_files)`.
7. If `approval_required` is `true`, stop and report the reason.
8. Only then call `apply_change(intent, changed_files, flake_uri)`.

## Common Mistakes

- Skipping `plan_change()` and guessing whether `mcp-nixos` is needed.
- Calling `apply_change()` right after patching without `run_formatters()`.
- Ignoring `approval_required` and continuing anyway.
- Assuming this MCP should resolve package names or option paths itself.
- Writing secret material through patches.

## Example

User asks: `Install ripgrep on NixOS`

1. `plan_change("install ripgrep on NixOS")`
2. See `requires_mcp_nixos=true`
3. Query `mcp-nixos` for the correct package attribute
4. Patch the relevant NixOS file with `apply_patch_set(...)`
5. `run_formatters(changed_files)`
6. `classify_change(changed_files)`
7. If allowed, `apply_change("install ripgrep", changed_files, flake_uri)`
