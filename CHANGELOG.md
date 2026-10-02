# Changelog

## v0.12.0 - 2026-10-02

- Usage events now record the calling `client` (from `NIX_AGENT_CLIENT`,
  else inferred: opencode / claude-code / codex / cursor / parent process),
  `host`, `cwd`, `session`, the full sanitized request `params`, and
  outcome details (`command` / `op`, `first_error`, `error_message`,
  `failed_drv`, `output_bytes`, truncation flag). `nix-agent usage`
  groups by client with a time span.
- `nix-agent usage --compare-shell` scans interactive shell histories
  (fish, bash, zsh) for direct nix commands and reports MCP tool calls
  vs shell commands with an MCP share, for measuring adoption vs
  shell bypass.
- Examples enable the usage log by default (`NIX_AGENT_USAGE_LOG=1`),
  and the NixOS module grew `programs.nix-agent.usageLog.enable` to set
  it on the wrapped binary.
- The companion skill maps shell commands to their MCP tool (`nixos-rebuild`
  switch to `switch()`, `nix eval` to `eval_config()`, ...),
  with a prefer-MCP hard rule.

## v0.11.0 - 2026-08-22

- First rebuild is `sudo -n` when NOPASSWD already matches; otherwise
  `nix-agent bootstrap-rebuild` (and the installer) stop with one TTY
  command instead of hanging on a password prompt.
- Cursor CLI and Codex have explicit high-trust allowlists
  (`Mcp(nix-agent, …)` / `default_tools_approval_mode = "approve"`).
- CI evaluates the NixOS module's sudoers (`checks.nixos-module`):
  narrowed flake refs, rollback, switch-generation, profile
  `switch-to-configuration`; no `--flake *` and no store-path wildcard.

## v0.10.0 - 2026-08-22

- The documented default is high trust: unprompted `switch` /
  `generations` and narrowed passwordless sudo for this machine's flake.
  Lower trust (host prompts, sudo password) is an opt-down; apply it
  only if the user asked. The Nix option
  `privilegedAutomation.enable` still defaults to false so existing
  configs do not grow sudoers without an explicit user.
- Privileged argv uses `sudo -n` so a missing NOPASSWD rule fails
  immediately with `privilege` instead of hanging on a password prompt.
- When the hostname attr is missing, tools fall back to a unique flake host
  (or a unique prefix/suffix match) and otherwise return `unknown_host`
  with the available names. Explicit `flake_uri#attr` is never rewritten.
- `locate_option` and `eval_config` retry NixOS-mode queries under
  `home-manager.users.<user>.…` when the unprefixed attr is not an option.
- Privileged ops accept `.` / `./` by resolving them to `$NIX_AGENT_FLAKE`
  when the pin is set.
- `switch` returns `status: "degraded"` (with a rollback hint) when
  activation succeeded but systemd units newly failed. The workflow
  default is apply: switch after `diff()` unless the user asked only to
  preview or check. On `degraded`, roll back unless the user asked to
  leave those units failed.

## v0.9.1 - 2026-08-12

- Stop putting `raw_bytes` / `returned_bytes` on MCP tool envelopes.
  Byte accounting stays in the usage log (`NIX_AGENT_USAGE_LOG=1`,
  `nix-agent usage`).

## v0.9.0 - 2026-08-12

- Privileged `switch` / `check("dry-activate")` reject remote flake refs
  and honor `$NIX_AGENT_FLAKE` / `$NIX_AGENT_HM_FLAKE` as an anti-footgun;
  sudoers narrow to `--flake <flake_dir>*` instead of a wildcard flake ref.
- `generations(action="rollback", generation=...)` consumes the recorded
  `rollback_generation` (id, profile path, or store realpath). Bare
  rollback remains previous-generation only. NixOS list entries include
  `path`. Targeted NixOS rollback uses `nix-env --switch-generation` then
  the profile `switch-to-configuration`, never a store-path binary.
- Installer default Claude Code allow list is build/diff/eval/locate/check
  only. Unprompted `switch` / `generations` is a separate ask (default no),
  distinct from passwordless sudo.
- NixOS module: `programs.nix-agent.flake` wraps `NIX_AGENT_FLAKE` into the
  binary; `programs.nix-agent.privilegedAutomation` emits the narrowed
  sudoers. `NIX_AGENT_ALLOW_REMOTE` is documented for humans only.
- Batched `eval_config` is `failed` when every attr failed.
  `locate_option` is documented as the which-file tool (24 KB → 20 KB on
  `environment.systemPackages`), not a firehose cap. nix-darwin is out of
  scope. `inspect-flake` HM classification of `"unknown"` stays
  inconclusive in the init skill.

## v0.8.1 - 2026-08-10

- Add an opt-in local JSONL usage log for MCP tool calls (tool, duration,
  status, byte accounting, target) under `$XDG_STATE_HOME/nix-agent/usage.jsonl`,
  with `nix-agent usage` to summarize. Enable with `NIX_AGENT_USAGE_LOG=1`.

## v0.8.0 - 2026-07-12

- Trim the runtime tool surface from nine tools to seven, split into two
  tiers: an operational core (`build`, `diff`, `switch`, `generations`) and
  config introspection (`eval_config`, `locate_option`, `check`).
- Remove the `format` tool. Format edited files with the flake's own
  formatter (`nix fmt` / `nixfmt`) via the host's shell; the wrapper still
  bundles `nixfmt` for that step.
- Remove `inspect_flake` from the MCP surface. Onboarding now runs it as the
  `nix-agent inspect-flake [flake_uri]` CLI subcommand, which the
  `nix-agent-init` skill drives.
- Drop the `flake` level from `check`; the ladder is now `lint` ->
  `dry-build` -> `dry-activate`. Use `dry-build` for cheap eval/build
  validation.

## v0.7.2 - 2026-07-07

- Add a CI matrix with separate plain Python tests and `nix flake check --system x86_64-linux`.
- Add an MCP stdio smoke test that starts `nix-agent` and lists tools through the protocol.
- Add public tool envelope schema snapshots for representative response shapes.
- Make command timeout configurable with `NIX_AGENT_COMMAND_TIMEOUT`.
- Add this changelog for release history.

## v0.7.1 - 2026-07-07

- Make package imports lazy so parser and runner tests do not require FastMCP.
- Add subprocess timeouts to prevent long Nix commands from hanging indefinitely.
- Make the Nix dev shell and flake checks run pytest without mutating user site-packages.
- Sync install and testing docs for the current tool surface.
