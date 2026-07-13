# Changelog

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
