---
name: nix-agent
description: Use when a user wants to change NixOS packages, options, modules, or local configuration and the host exposes the nix-agent MCP server (usually alongside mcp-nixos).
---

# Nix Agent

## Overview

`nix-agent` is a pure Nix operations toolbox. It does NOT read or write
files. It evaluates the live config, lints, formats, validates, builds,
diffs, switches, and manages generations, handing every result back as a
compact JSON envelope. Read the envelope: it already holds what you would
otherwise re-fetch by hand.

Division of labor:
- **Your native tools** (Read/Edit/Write) edit `.nix` files.
- **`mcp-nixos`** discovers packages and options (what exists, what it means).
- **`nix-agent`** operates on the user's actual configuration (what their machine resolves, whether it builds, what a switch would change).

## Tool Surface

All tools auto-resolve the target when `flake_uri` is omitted and echo
back what they resolved and ran (`resolved_target` and `command`;
`inspect_flake` reports `flake_dir`), plus `raw_bytes`/`returned_bytes`
accounting (see Token discipline).

- `eval_config(attr, flake_uri?, mode?)`: final merged value of any
  config attribute on THIS machine, after all modules/overlays.
  `mcp-nixos` says what an option means; this says what it is. Pass a
  **list** for `attr` to evaluate many in one call (per-attr `results`).
  Values above ~2 KB degrade to attr names / length / a head slice,
  marked `truncated: true`.
- `locate_option(attr, flake_uri?, mode?)`: which file sets an option,
  as `declarations` and `definitions` (`{file, value}` per file). Use
  this instead of grepping the tree. `status` is `not_an_option` for
  plain config values (use `eval_config` there). For integrated HM,
  spell the attr `home-manager.users.<user>.<attr>` with `mode="nixos"`.
- `check(level, flake_uri?, mode?)`: validation ladder, fast to slow:
  `"lint"` (statix + deadnix, structured `findings`), `"flake"`,
  `"dry-build"`, `"dry-activate"` (NixOS only).
- `format(paths?, flake_uri?, mode?)`: `nix fmt` / nixfmt. Explicit
  `paths` return per-file `results`.
- `build(flake_uri?, mode?)`: build the closure, no activation. A failed
  build carries `failed_derivation`.
- `diff(flake_uri?, mode?)`: what a switch would change (adds/removes/
  version bumps), plus a structured `packages` object when it parses.
  Show this before switching.
- `switch(flake_uri?, mode?, validate?, full_log?)`: activate. Records
  `rollback_generation`, returns a `summary` (units changed, derivations
  built, `packages` vs the rollback generation, `health`), and trims the
  log to a tail on success. `validate=True` gates on `check("dry-build")`.
- `generations(action="list"|"rollback", mode?)`: list or roll back.
- `inspect_flake(flake_uri?)`: structured facts about a config repo in
  one call (hosts, HM integration, module dirs, formatter, lint tools).
  Run it when orienting in an unfamiliar config; it feeds onboarding.

## Picking `mode` (read before any HM change)

`mode` defaults to `"nixos"`. Do NOT reflexively switch to
`"home-manager"` just because the task touches Home Manager options.
That is the most common way to operate on the wrong config.

- **Integrated HM** (wired in as a NixOS module via
  `home-manager.nixosModules.home-manager` + `home-manager.users.*`):
  no separate `home-manager switch`. HM is built and activated as part
  of the system closure, so use `mode="nixos"` (the default) and
  `switch` the whole system. The common laptop/desktop layout.
- **Standalone HM** (its own flake exposing `homeConfigurations.*`,
  applied with `home-manager switch`): use `mode="home-manager"`.

If both a NixOS flake and a standalone `~/.config/home-manager` flake
exist on the machine, the standalone one is often vestigial. Confirm
which is actually active (`eval_config` against each, or check what the
running generation was built from) before mutating. When in doubt,
`mode="nixos"` is the safer guess.

For nonstandard or multi-flake layouts, do not rely on auto-resolution:
set `NIX_AGENT_FLAKE` (or `NIX_AGENT_HM_FLAKE`) once, or pass an explicit
`flake_uri` like `/home/you/nixos#host`. Either pins the target exactly.

**Wrong-host symptom:** a `failed` envelope whose `first_error` names a
missing `nixosConfigurations."<hostname>"` means auto-resolution picked
an attribute this flake does not define. Fix it with an explicit
`flake_uri` (`.../repo#realhost`) or `$NIX_AGENT_FLAKE`, not by retrying.

## Workflow

1. Discovery (if needed): query `mcp-nixos` for packages/options;
   `eval_config` for what the machine currently resolves; `locate_option`
   for which file to open.
2. Edit `.nix` files with your native file tools.
3. `format()` then `check("lint")`: fix findings worth fixing.
4. `check("dry-build")`: catches eval/build errors cheaply.
5. `diff()`: show the user what will change.
6. `switch()`: report the result and `rollback_generation`.
7. On failure at any step: read `first_error`, then `error_detail`, then
   `failed_derivation.log_tail`; fix and retry. On regret after a switch:
   `generations(action="rollback")` to the recorded generation.

Steps 3 through 5 are judgment calls, not gates. For a trivial change,
going straight to `switch` is fine.

## Token discipline: the envelope is the interface

This server pre-digests Nix's firehose. An agent that re-runs `nix log`
or `systemctl` after every operation throws that away. Read the fields;
do not re-fetch.

- **On failure, read three fields in order and stop.** `first_error` is
  the actionable line. `error_detail` is `{message, file, line, column,
  trace}` when Nix emitted an eval error: a direct file:line:column edit
  target. `failed_derivation.log_tail` is the failing builder's log,
  already fetched. Do NOT run `nix log` or re-run with `full_log=True`
  unless these fields are absent.
- **After a switch, read `summary`, do not re-probe.** `summary.health`
  reports units `newly_failed`/`resolved`/`still_failed` with journal
  tails for the first five failures; `summary.packages` reports changes
  vs the rollback generation. These replace running `systemctl --failed`
  or a second `diff()`.
- **Batch attr checks.** `eval_config([...])` answers N questions in one
  call. A `truncated: true` value means eval a child attr for the part
  you need, NOT retry for full output.
- **`locate_option` before grepping.** It answers "which file sets this"
  in one call; a tree-wide grep does not.
- **`raw_bytes`/`returned_bytes`** on every envelope tell you how much log
  the trimming saved. They are diagnostics, not knobs.
- **Escape hatches are deliberate last resorts.** `full_log=True` and the
  raw `output` field exist for the rare case the trimmed view genuinely
  lacks what you need; reaching for them by default defeats the server.

## Onboarding a repo

First time in an unfamiliar config? Run `/nix-agent-init`: it calls
`inspect_flake()` once and generates `AGENT_MAP.md`, `CLAUDE.md`, and
`.mcp.json` from the observed facts, never boilerplate.

## Hard Rules

- Never write secret payloads into config files; reference secrets via
  sops-nix/agenix and only edit references.
- Never call `switch` when the user asked only to check or preview;
  `diff` is the preview.
