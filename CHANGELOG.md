# Changelog

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
