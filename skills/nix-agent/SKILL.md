---
name: nix-agent
description: Operate on this machine's NixOS or Home Manager configuration with the nix-agent MCP tools (build, diff, switch, generations, eval_config, locate_option, check). Use when changing packages, options, or modules; diagnosing a failed build or switch; rolling back a generation; or asking what the live config currently resolves to. Requires the nix-agent MCP server (usually alongside mcp-nixos).
---

# Nix Agent

## Overview

`nix-agent` MCP tools do NOT read or write files. They build, diff, switch,
and manage generations (the operational core), and evaluate, locate, and
check the live config (introspection), handing every result back as a
compact JSON envelope. Read the envelope: it already holds what you would
otherwise re-fetch by hand.

Division of labor:
- **Your native tools** (Read/Edit/Write) edit `.nix` files.
- **`mcp-nixos`** discovers packages and options (what exists, what it means).
- **`nix-agent`** operates on the user's actual configuration (what their machine resolves, whether it builds, what a switch would change).

## Tool Surface

Seven tools in two tiers. All auto-resolve the target when `flake_uri` is
omitted and echo back what they resolved and ran (`resolved_target` and
`command`, or `commands` for `check("lint")`), plus `raw_bytes`/
`returned_bytes` accounting when present (see Token discipline).

Operational core:
- `build(flake_uri?, mode?)`: build the closure, no activation. A failed
  build carries `failed_derivation`.
- `diff(flake_uri?, mode?)`: what a switch would change (adds/removes/
  version bumps), plus a structured `packages` object when it parses.
  Show this before switching.
- `switch(flake_uri?, mode?, validate?, full_log?)`: activate. Records
  `rollback_generation`, returns a `summary` (units changed, derivations
  built, `packages` vs the rollback generation, `health`), and trims the
  log to a tail on success. `validate=True` gates on `check("dry-build")`.
  Remote refs and pin mismatches exit as `remote_ref_rejected` /
  `target_locked` before sudo or dry-build.
- `generations(action="list"|"rollback", mode?, generation?)`: list or
  roll back. NixOS list entries include `path` when the profile link
  exists. After `switch`, call
  `generations(action="rollback", generation=<rollback_generation or id>)`.
  Bare `generations(action="rollback")` is previous-generation only.
  Unknown ids return `unknown_generation` and run no command.

Config introspection:
- `eval_config(attr, flake_uri?, mode?)`: final merged value of any
  config attribute on THIS machine, after all modules/overlays.
  `mcp-nixos` says what an option means; this says what it is. Pass a
  **list** for `attr` to evaluate many in one call (per-attr `results`).
  All attrs ok or mixed → `ok` (failures in `results`); every attr
  failed → `failed` with `first_error` from the first failed entry that
  has one. Values above ~2 KB degrade to attr names / length / a head
  slice, marked `truncated: true`.
- `locate_option(attr, flake_uri?, mode?)`: which file sets an option,
  as `declarations` and `definitions` (`{file, value}` per file). Earns
  its slot as that which-file answer, not as a cap (measured
  `environment.systemPackages` is 24 KB → 20 KB). Use this instead of
  grepping the tree. `status` is `not_an_option` for plain config values
  (use `eval_config` there). For integrated HM, spell the attr
  `home-manager.users.<user>.<attr>` with `mode="nixos"`.
- `check(level, flake_uri?, mode?)`: validation ladder, fast to slow:
  `"lint"` (statix + deadnix, structured `findings`), `"dry-build"`,
  `"dry-activate"` (NixOS only). Dry-activate uses the same remote/pin
  classifier as `switch` and attaches `privilege` on sudo auth failure.

Formatting is not a tool: format edited files with the flake's own
formatter (`nix fmt`, or `nixfmt` on the files) via your Bash tool. Repo
onboarding is the `nix-agent inspect-flake` CLI subcommand, not a tool; the
`nix-agent-init` skill drives it.

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
set `NIX_AGENT_FLAKE` once (or `NIX_AGENT_HM_FLAKE` for standalone HM,
which falls back to `NIX_AGENT_FLAKE`), or pass an explicit `flake_uri`
like `/home/you/nixos#host`. Either pins the target exactly.

**Wrong-host symptom:** a `failed` envelope whose `first_error` names a
missing `nixosConfigurations."<hostname>"` means auto-resolution picked
an attribute this flake does not define. Fix it with an explicit
`flake_uri` (`.../repo#realhost`) or `$NIX_AGENT_FLAKE`, not by retrying.

## Workflow

1. Discovery (if needed): query `mcp-nixos` for packages/options;
   `eval_config` for what the machine currently resolves; `locate_option`
   for which file to open.
2. Edit `.nix` files with your native file tools.
3. Format with the flake's formatter (`nix fmt`, or `nixfmt` on the edited files) via Bash, then `check("lint")`: fix findings worth fixing.
4. `check("dry-build")`: catches eval/build errors cheaply.
5. `diff()`: show the user what will change.
6. `switch()`: report the result and `rollback_generation`. Keep that
   value.
7. On failure at any step: read `first_error`, then `error_detail`, then
   `failed_derivation.log_tail`; fix and retry. `status: "preflight_failed"`
   means `switch(validate=True)` never activated — fix the nested
   `preflight` dry-build, do not retry activation. A `privilege` field
   means sudo auth failed, not a Nix error. `unknown_generation`,
   `target_locked`, and `remote_ref_rejected` are early exits: no
   command ran. On regret after a switch:
   `generations(action="rollback", generation=<rollback_generation or id>)`.
   Bare `generations(action="rollback")` is previous-generation only,
   and is only the right default when nothing else has switched since.

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
  tails for the first five newly failed units; `summary.packages` reports changes
  vs the rollback generation. These replace running `systemctl --failed`
  or a second `diff()`.
- **Batch attr checks.** `eval_config([...])` answers N questions in one
  call. Mixed results stay `ok` with failures in `results`; if every
  attr failed, top-level `status` is `failed` with `first_error` from
  the first failed entry that has one. A `truncated: true` value means
  eval a child attr for the part you need, NOT retry for full output.
- **`locate_option` before grepping.** It answers "which file sets this"
  in one call; a tree-wide grep does not. That is why it has a slot, not
  because it caps a firehose (24 KB → 20 KB on
  `environment.systemPackages`).
- **`raw_bytes`/`returned_bytes`** when present tell you how much log
  the trimming saved. They are diagnostics, not knobs. Early-exit
  statuses (`no_target`, `invalid_attr`, `invalid_action`,
  `invalid_level`, `not_an_option`, `tool_missing`, `not_applicable`,
  `preflight_failed`, `unknown_generation`, `target_locked`,
  `remote_ref_rejected`) omit them. `target_locked` includes `pin`.
  `remote_ref_rejected` means clone the flake locally and pin it; do
  not retry the remote ref.
- **Escape hatches are deliberate last resorts.** `full_log=True` and the
  raw `output` field exist for the rare case the trimmed view genuinely
  lacks what you need; reaching for them by default defeats the server.

## Onboarding a repo

First time in an unfamiliar config? Run `/nix-agent-init`: it runs
`nix-agent inspect-flake` once and generates `AGENT_MAP.md`, `CLAUDE.md`
(+ an `AGENTS.md` symlink), and `.mcp.json` from the observed facts, never
boilerplate.

## Hard Rules

- Never write secret payloads into config files; reference secrets via
  sops-nix/agenix and only edit references.
- Never call `switch` when the user asked only to check or preview;
  `diff` is the preview.
- Host allowlists cannot see `flake_uri`. Privileged tools reject remote
  refs and honor `$NIX_AGENT_FLAKE` / `$NIX_AGENT_HM_FLAKE` as an
  anti-footgun (the HM lock does not fall back to the NixOS pin). Do not
  treat the pin as a security boundary. Sudoers must be narrowed to that
  directory.
- After `switch`, undo with
  `generations(action="rollback", generation=<rollback_generation>)`.
  Bare rollback is previous-only.
