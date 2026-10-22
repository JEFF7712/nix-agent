---
name: nix-agent
description: Operate on this machine's NixOS or Home Manager configuration with the nix-agent MCP tools (build, diff, switch, generations, eval_config, locate_option, check). Use when changing packages, options, or modules; diagnosing a failed build or switch; rolling back a generation; or asking what the live config currently resolves to. Requires the nix-agent MCP server (usually alongside mcp-nixos).
---

# Nix Agent

## Overview

`nix-agent` MCP tools do not edit configuration files. They build, diff, switch,
and manage generations (the operational core), and evaluate, locate, and
check the live config (introspection), handing every result back as a
compact JSON envelope. Read the envelope: it already holds what you would
otherwise re-fetch by hand.

Division of labor:
- **Your native tools** (Read/Edit/Write) edit `.nix` files.
- **`mcp-nixos`** discovers packages and options (what exists, what it means).
- **`nix-agent`** operates on the user's actual configuration (what their machine resolves, whether it builds, what a switch would change).

Default is apply for local activation: after a config change, `diff()`
then `switch()` without waiting, unless the user asked to preview or check.
Follow the repository's deployment workflow for coordinated fleet rollout.

## Check tool availability

Inspect the session's exposed tool catalog, or the host's MCP tool-discovery
facility, once for this server's seven tools before planning around them.
This needs no build, check, or activation call. A skill, installed binary,
running server process, or MCP resource listing does not establish that the
tools are callable in this session.

If tools are absent, state that once and use the repository's supported
shell workflow for the missing operations, within its existing permissions
and deployment gates. If a hook blocks those commands, report the unavailable
MCP capability and restore host registration; do not bypass the hook. To
verify a restored connection, evaluate `networking.hostName` for an explicit
known target. Report that evaluation separately from catalog discovery.

## Use MCP tools when available for covered operations

Shelling out for operations below re-pays the context cost this server
exists to remove (raw `nix eval` on `environment.systemPackages` is ~13 KB
the size guard collapses to ~400 bytes). Reach for Bash only for what has
no tool: formatting (`nix fmt`), file edits, and remote-target deploys
(`--target-host`, `--use-remote-sudo`), which privileged tools reject by
design.

The repository's required validation gates remain authoritative. Deploy
hosts requiring fleet coordination through the repository's orchestrator,
including Kubernetes cordon/drain, cluster preflight, readiness checks, and
uncordon. Use SSH, kubectl, and service APIs for hardware and application
runtime probes. `switch` performs local activation and systemd health
checks; it has no fleet orchestration hooks.

Use introspection for specific questions alongside those workflows:
`locate_option("services.openssh.enable", flake_uri="/path/to/flake#worker")`
finds option ownership, and
`eval_config(["networking.hostName", "services.openssh.enable"],
flake_uri="/path/to/flake#worker")` checks merged values. These inspect the
named flake, so remote runtime state still needs remote probes.

| Instead of shell | Call |
|---|---|
| `nixos-rebuild switch/boot/test`, `home-manager switch` (local) | `switch()` |
| `nix build ...toplevel`, `nix build ...activationPackage` | `build()` |
| `nixos-rebuild dry-activate` (local) | `check("dry-activate")` |
| `nix eval <config attr>` | `eval_config(attr)` (batch lists in one call) |
| grepping the tree for where an option is set | `locate_option(attr)` |
| `statix` / `deadnix` directly | `check("lint")` |
| `nvd diff` / `nix store diff-closures` | `diff()` |
| `nix log <drv>` after a failed build | read `failed_derivation.log_tail` |
| `systemctl --failed` after a switch | read `summary.health` |

## Remote activation fallback

Use the repository's fleet deployer for coordinated hosts. Where manual
remote activation is supported by that workflow, or a remote rebuild fails
before activation, follow this recipe on the explicitly selected host:

1. Run the repository's validation and deployment preflight for the exact
   source revision. Keep required drain/readiness orchestration in place.
2. Over SSH, record the realpaths of `/run/current-system` and
   `/nix/var/nix/profiles/system`, generation IDs, and failed systemd units.
   Keep the running closure and profile target separately for rollback.
3. Build that host's `config.system.build.toplevel`. Use MCP `build` and
   poll its job when available; otherwise use the repository's shell build
   recipe or `nix build --no-link --print-out-paths` with the explicit flake
   and quoted host attribute. Keep the resulting store path.
4. Copy the closure with `nix copy --to` and the target's verified SSH store
   URL. Follow its documented store-trust workflow if copying is rejected.
5. On the remote host, compare the recorded running closure and the new
   closure with `nix store diff-closures`, checking the exit status.
   Empty successful output means no reported package changes. Different
   closure paths can still contain changed config or embedded code; inspect
   the intended change and its runtime acceptance criteria.
6. On that host, set the system profile with
   `sudo -n nix-env -p /nix/var/nix/profiles/system --set` and the new store
   path, then run that closure's `bin/switch-to-configuration switch` under
   `sudo -n`. Record each exit status; profile movement alone is not proof
   of activation.
7. Verify `/run/current-system`, compare failed units with the baseline,
   inspect activation warnings, and perform service/cluster runtime probes.
   If recovery is needed, restore the recorded profile target with
   `nix-env --set` on that profile and activate the recorded previous running
   closure, both under `sudo -n` on the remote host. Verify recovery and
   finish the repository's readiness/uncordon steps.

This recipe creates no local MCP `rollback_generation` or health envelope.
Retain the remote baseline and report the measured activation and health
results explicitly. MCP `diff()` compares against the caller machine's
running closure; a remote deployment needs the remote baseline.

## Tool Surface

Seven tools in two tiers. All auto-resolve the target when `flake_uri` is
omitted and echo back what they resolved and ran (`resolved_target` and
`command`, or `commands` for `check("lint")`).

Operational core:
- `build(flake_uri?, mode?, job_id?, log_offset?)`: start a persistent
  background build, no activation. Keep the returned `job_id` and poll
  `build(job_id=..., log_offset=<previous poll's log_offset>)` for new log
  lines and the final result. `running` means wait; `ok`
  carries `store_path`; a failed builder carries `failed_derivation`.
  Successful output is a short tail with `log_truncated` and `log_paths`
  to the full local logs. Failures retain their capped diagnostics.
  Repeated starts for the same running target reuse its job. Jobs survive
  MCP disconnects and server restarts. `interrupted` means the worker
  exited without a result, not proof that Nix daemon work was cancelled.
- `diff(flake_uri?, mode?)`: what a switch would change (adds/removes/
  version bumps), plus a structured `packages` object when it parses.
  Include this in the reply and switch unless the user asked only to
  preview or check.
- `switch(flake_uri?, mode?, validate?, full_log?)`: activate. Records
  `rollback_generation`, returns a `summary` (units changed, derivations
  built, `packages` vs the rollback generation, `health`), and trims the
  log to a tail on success. `validate=True` gates on `check("dry-build")`.
  `summary.warnings` preserves recognizable warning/error lines from the
  captured switch log, independently of unit health. It deduplicates and
  caps the list; `warnings_truncated` marks omissions or shortened lines.
  Remote refs and pin mismatches exit as `remote_ref_rejected` /
  `target_locked` before sudo or dry-build. `.` / `./` resolve to the
  pin when `$NIX_AGENT_FLAKE` is set. Newly failed units after
  activation are `status: "degraded"`; report `summary.health` and roll
  back unless the user asked to leave those units failed. Privileged
  argv uses `sudo -n`.
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
  All attrs ok → `ok`; mixed → `partial`; every attr failed → `failed`.
  Batches carry `succeeded_count` and `failed_count`; partial and failed
  batches include the first available `first_error`. Values above ~2 KB
  degrade to attr names / length / a head slice, marked `truncated: true`.
  Text fallback and truncation include a `hint` to request narrower leaf
  attributes. Fallback is Nix text and can contain unevaluated option
  errors, so do not treat it as complete structured JSON. A missing hostname
  attr falls back to
  a unique flake host or returns `unknown_host` with `hosts`. In NixOS
  mode, a missing option is retried as `home-manager.users.<user>.<attr>`
  (`hm_rewritten: true`).
- `locate_option(attr, flake_uri?, mode?)`: which file sets an option,
  as `declarations` and `definitions` (`{file, value}` per file). Earns
  its slot as that which-file answer, not as a cap (measured
  `environment.systemPackages` is 24 KB → 20 KB). Use this instead of
  grepping the tree. `status` is `not_an_option` for plain config values
  (use `eval_config` there). For integrated HM, spell the attr
  `home-manager.users.<user>.<attr>` with `mode="nixos"`; if you pass
  the unprefixed attr, the tool retries that spelling (`hm_rewritten`).
  Missing hostname → `unknown_host` with `hosts`.
- `check(level, flake_uri?, mode?)`: validation ladder, fast to slow:
  `"lint"` (statix + deadnix, structured `findings`), `"dry-build"`,
  `"dry-activate"` (NixOS only). Dry-activate uses the same remote/pin
  classifier as `switch` and attaches `privilege` on sudo auth failure.
  Success returns a short output tail with `log_truncated` and `log_paths`
  to full local logs; failures retain their capped diagnostics.

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

**Wrong-host symptom:** `unknown_host` lists `hosts` from the flake. A
`failed` envelope whose `first_error` names a missing
`nixosConfigurations."<hostname>"` means auto-resolution could not
recover; pass an explicit `flake_uri` (`.../repo#realhost`) or
`$NIX_AGENT_FLAKE`, not by retrying the same hostname.

## Workflow

1. Discovery (if needed): query `mcp-nixos` for packages/options;
   `eval_config` for what the machine currently resolves; `locate_option`
   for which file to open.
2. Edit `.nix` files with your native file tools.
3. Format with the flake's formatter (`nix fmt`, or `nixfmt` on the edited files) via Bash, then `check("lint")`: fix findings worth fixing.
4. `check("dry-build")`: catches eval/build errors cheaply.
5. `diff()`: include the changeset in the reply and switch unless the
   user asked only to preview or check.
6. `switch()`: report the result and `rollback_generation`. Keep that
   value. `status: "degraded"` means activation succeeded but units
   newly failed — report `summary.health` and roll back unless the user
   asked to leave those units failed.
7. On failure at any step: read `first_error`, then `error_detail`, then
   `failed_derivation.log_tail`; fix and retry. `status: "preflight_failed"`
   means `switch(validate=True)` never activated — fix the nested
   `preflight` dry-build, do not retry activation. A `privilege` field
   means sudo auth failed, not a Nix error. `unknown_generation`,
   `unknown_host`, `target_locked`, and `remote_ref_rejected` are early
   exits: no command ran. On regret after a switch:
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
- **After a switch, read `summary`, do not re-probe.** `status: "degraded"`
  means units `newly_failed`; treat that as a problem, not success, and
  roll back with
  `generations(action="rollback", generation=<rollback_generation>)`
  unless the user asked to leave those units failed.
  `summary.health` reports units `newly_failed`/`resolved`/`still_failed` with journal
  tails for the first five newly failed units; `summary.packages` reports changes
  vs the rollback generation. These replace running `systemctl --failed`
  or a second `diff()`.
- **Read switch warnings separately.** `summary.warnings` contains
  recognizable warning/error lines such as activation target-creation
  failures. Healthy units alone do not establish clean activation output.
  Interpret those diagnostics before reporting activation acceptance.
- **Batch attr checks.** `eval_config([...])` answers N questions in one
  call. Mixed results have `status: "partial"`; if every attr failed,
  status is `failed`. Check `failed_count`, `first_error`, and each result.
  Successful values remain available. A `truncated: true` value means
  eval a child attr for the part you need, NOT retry for full output.
- **Keep build job IDs.** Poll `build(job_id=...)` while `running`, passing
  back each poll's `log_offset` so repeated polls do not resend the same
  tail. A lost MCP connection does not cancel the worker.
  Repeating the same start retrieves the existing running job; it does
  not start a duplicate. `interrupted` requires inspecting the saved
  logs before retrying.
- **`locate_option` before grepping.** It answers "which file sets this"
  in one call; a tree-wide grep does not. That is why it has a slot, not
  because it caps a firehose (24 KB → 20 KB on
  `environment.systemPackages`).
- **Read empty diffs precisely.** An `ok` response with empty `packages`
  lists means no reported package additions, removals, or version changes.
  Compare `current_closure` and `store_path` to establish whether the
  closure path changed. An empty package diff alone does not establish
  identical configuration or unchanged service behavior.
- **Byte accounting is off the envelope.** `raw_bytes` / `returned_bytes`
  live in the usage log (`NIX_AGENT_USAGE_LOG=1`, then `nix-agent usage`),
  not on the tool response. Do not look for them in MCP results.
- **Escape hatches are deliberate last resorts.** `full_log=True` and the
  raw `output` field exist for the rare case the trimmed view genuinely
  lacks what you need; reaching for them by default defeats the server.

## Onboarding a repo

First time in an unfamiliar config? Run `/nix-agent-init`: it runs
`nix-agent inspect-flake` once and generates `AGENT_MAP.md`, `CLAUDE.md`
(+ an `AGENTS.md` symlink), and `.mcp.json` from the observed facts, never
boilerplate.

## Hard Rules

- When callable, prefer the MCP tools over shell for every covered operation in the map
above. Do not shell out to `nixos-rebuild`, `nix build`, `nix eval`,
`statix`/`deadnix`, `nvd`, or `nix store diff-closures` when a tool covers
it; a hook may block such commands and tell you which tool to call instead.
When tools are unavailable, use the availability fallback above.
- Never write secret payloads into config files; reference secrets via
sops-nix/agenix and only edit references.
- Never call `switch` when the user asked only to check or preview;
  `diff` is the preview. For local activation, the default is apply:
  switch after `diff()` without waiting. Use the repository's orchestrator
  for targets requiring coordinated fleet deployment.
- `status: "degraded"` means activation succeeded but units newly
  failed; report `summary.health` and roll back unless the user asked
  to leave those units failed.
- Host allowlists cannot see `flake_uri`. Privileged tools reject remote
  refs and honor `$NIX_AGENT_FLAKE` / `$NIX_AGENT_HM_FLAKE` as an
  anti-footgun (the HM lock does not fall back to the NixOS pin). Do not
  treat the pin as a security boundary. Sudoers must be narrowed to that
  directory. Default install is unprompted activation plus passwordless
  sudo for this flake. Do not re-ask for confirmation. Lower trust
  (host prompts, sudo password) only if the user asked.
- After `switch`, undo with
  `generations(action="rollback", generation=<rollback_generation>)`.
  Bare rollback is previous-only.
