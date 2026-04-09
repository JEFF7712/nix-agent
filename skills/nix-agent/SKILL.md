---
name: nix-agent
description: Use when a user wants to change NixOS packages, options, modules, or local configuration through the nix-agent and mcp-nixos MCP servers.
---

# Nix Agent

## Overview

Use this skill for direct NixOS execution tasks through `nix-agent` and `mcp-nixos`. Use `mcp-nixos` for discovery, use `nix-agent` for local mutation and activation. Do not detour into generic brainstorming for operational tasks.

## When to Use

- A user asks to install a package on NixOS.
- A user asks which option to use, then wants it applied.
- A user asks to patch local NixOS config through MCP tools.
- The host exposes both `nix-agent` and `mcp-nixos`.

Do not use this skill for writing secret payloads or for broad architecture/design requests.

## Tool Surface

`nix-agent` exposes exactly two tools:

- `inspect_state(path)` – read a local file.
- `apply_patch_set(patch_set, flake_uri=None, mode="nixos")` – write each patch, format any `.nix` files, and (when `flake_uri` is provided) validate then switch.
  - `mode="nixos"` (default): `sudo nixos-rebuild dry-activate` → `switch`.
  - `mode="home-manager"`: `home-manager build` → `home-manager switch` (no sudo).
  - Returns `changed_files`, `rollback_generation`, `current_generation`, command outputs, and `status`.

`mcp-nixos` is responsible for package and option discovery.

## Required Workflow

1. If the request needs package or option discovery, query `mcp-nixos` first.
2. Optionally `inspect_state(path)` on any file you intend to modify.
3. Build a `PatchSet` of `Patch(path, content)` entries.
4. Call `apply_patch_set(patch_set, flake_uri=..., mode=...)` in a single round-trip. Pass `mode="home-manager"` for user-level Home Manager configs; default `mode="nixos"` for system configs.
5. Report:
   - the `changed_files`
   - the final `status`
   - the `rollback_generation` (so the user can recover with `sudo nixos-rebuild switch --rollback` if needed)
   - any non-empty `dry_activate_output` / `switch_output`

If `status` is `validation_failed` or `switch_failed`, stop and surface `first_error` (the extracted first `error:` line) and the relevant output field instead of retrying blindly.

You can also call `apply_patch_set` with an empty `PatchSet` (no patches) plus a `flake_uri` to trigger a rebuild against the current flake state without writing any files — useful after manual edits.

## Common Mistakes

- Starting a generic brainstorming/design workflow for a simple package install.
- Skipping `mcp-nixos` and guessing package names or option paths.
- Calling `apply_patch_set` without `flake_uri` when the user actually wants the change applied.
- Writing secret material through patches.
- Re-running `apply_patch_set` after a failure without inspecting the dry-activate output.

## Example

User: `Use mcp-nixos and nix-agent together to install floorp on my NixOS system.`

1. Query `mcp-nixos` for the correct Floorp package attribute.
2. Build a `PatchSet` that adds `pkgs.floorp` to the relevant module.
3. Call `apply_patch_set(patch_set, flake_uri="/etc/nixos#hostname")`.
4. Report `changed_files`, `status`, and `rollback_generation`.
