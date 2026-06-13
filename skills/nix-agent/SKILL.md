---
name: nix-agent
description: Use when a user wants to change NixOS packages, options, modules, or local configuration and the host exposes the nix-agent MCP server (usually alongside mcp-nixos).
---

# Nix Agent

## Overview

`nix-agent` is a pure Nix operations toolbox. It does NOT read or write
files — use your own file tools (Read/Edit/Write) for that. It gives you
the NixOS-specific operations: evaluate the live config, lint, format,
validate, build, diff, switch, and manage generations.

Division of labor:
- **Your native tools** — read and edit `.nix` files.
- **`mcp-nixos`** — discover packages and options (what exists, what it means).
- **`nix-agent`** — operate on the user's actual configuration (what their machine resolves, whether it builds, what a switch would change).

## Tool Surface

All tools auto-resolve the target when `flake_uri` is omitted
(`/etc/nixos` for NixOS, `~/.config/home-manager` for Home Manager; the
hostname / `user@host` attribute is picked automatically) and echo back
`resolved_target` and the exact `command` run. Exception: calling
`format` with explicit `paths` returns per-file `results` instead.
Pass `mode="home-manager"` for HM configs.

- `eval_config(attr, flake_uri?, mode?)` — final merged value of any
  config attribute on THIS machine (after all modules/overlays).
  `mcp-nixos` tells you what an option means; this tells you what it is.
- `check(level, flake_uri?, mode?)` — validation ladder, fast to slow:
  `"lint"` (statix + deadnix, structured `findings` list), `"flake"`,
  `"dry-build"`, `"dry-activate"` (NixOS only).
- `format(paths?, flake_uri?, mode?)` — `nix fmt` / nixfmt.
- `build(flake_uri?, mode?)` — build the closure, no activation.
- `diff(flake_uri?, mode?)` — what a switch would change (package
  adds/removes/version bumps). Show this to the user before switching.
- `switch(flake_uri?, mode?)` — activate. Records `rollback_generation`.
- `generations(action="list"|"rollback", mode?)` — list or roll back.

## Recommended Workflow

1. Discovery (if needed): query `mcp-nixos` for packages/options;
   `eval_config` to see what the user's machine currently resolves.
2. Edit `.nix` files with your native file tools.
3. `format()` then `check("lint")` — fix findings worth fixing.
4. `check("dry-build")` — catches eval/build errors cheaply. On failure,
   `first_error` has the actionable line.
5. `diff()` — show the user what will change.
6. `switch()` — report the result and `rollback_generation`.
7. On regret: `generations(action="rollback")`.

Steps 3–5 are judgment calls, not gates — for a trivial change, going
straight to `switch` is fine. Compose what the situation needs.

## Failure Handling

- `status="failed"` — read `first_error` first, full `output` second.
  Fix the config and retry; don't retry blindly.
- `status="no_target"` — pass an explicit `flake_uri`.
- `status="tool_missing"` — the named binary isn't on PATH (only
  happens outside the flake-packaged install).

## Hard Rules

- Never write secret payloads into config files; reference secrets via
  sops-nix/agenix and only edit references.
- Never call `switch` when the user asked only to check or preview;
  `diff` is the preview.
