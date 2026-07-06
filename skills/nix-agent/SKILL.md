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

### Picking `mode` (read before any HM change)

`mode` defaults to `"nixos"`. Do NOT reflexively switch to
`"home-manager"` just because the task touches Home Manager options —
that is the most common way to operate on the wrong config.

- **Integrated HM** (Home Manager wired in as a NixOS module via
  `home-manager.nixosModules.home-manager` + `home-manager.users.*`):
  there is no separate `home-manager switch`. HM is built and activated
  as part of the system closure. Use `mode="nixos"` (the default) and
  `switch` the whole system. This is the common laptop/desktop layout.
- **Standalone HM** (its own flake exposing `homeConfigurations.*`,
  applied with `home-manager switch`): use `mode="home-manager"`.

If both a NixOS flake and a standalone `~/.config/home-manager` flake
exist on the machine, the standalone one is often vestigial — confirm
which is actually active (`eval_config` against each, or check what the
running generation was built from) before mutating. When in doubt,
`mode="nixos"` is the safer guess.

For nonstandard or multi-flake layouts, don't rely on auto-resolution:
set `NIX_AGENT_FLAKE` (or `NIX_AGENT_HM_FLAKE`) once, or pass an explicit
`flake_uri` like `/home/you/nixos#host`. Either pins the target and
removes the guesswork entirely.

- `eval_config(attr, flake_uri?, mode?)` — final merged value of any
  config attribute on THIS machine (after all modules/overlays).
  `mcp-nixos` tells you what an option means; this tells you what it is.
  `attr` also takes a list, evaluating each in one call and returning
  per-attr `results`; values above ~2 KB degrade to attr names / length /
  a head slice with `truncated: true`.
- `locate_option(attr, flake_uri?, mode?)` — where this configuration
  sets an option: `declarations` (files declaring it) and `definitions`
  (`{file, value}` per defining file). `status` is `not_an_option` for
  plain config values (use `eval_config` there instead). For integrated
  Home Manager, spell the attr `home-manager.users.<user>.<attr>` with
  `mode="nixos"`.
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

Between discovery and editing, `locate_option` closes the gap `mcp-nixos`
leaves open: it tells you which file to open, not just what the option
means. For integrated Home Manager, spell the attr
`home-manager.users.<user>.<attr>` with `mode="nixos"`: HM options live
under the NixOS options tree, not a separate config.

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
