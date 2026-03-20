# nix-agent skill testing notes

## Baseline scenarios checked before writing the skill

- Installing a package through `nix-agent` plus `mcp-nixos`
- Activating a touched `configuration.nix` after patching

## Expected behavior with the skill present

- Start with `plan_change()`
- Respect `requires_mcp_nixos`
- Run formatters before apply
- Stop on `approval_required`
- Treat `nix-agent` as local mutation/validation only

## Why this skill exists

The MCP tools are discoverable without a skill, but the skill makes the workflow explicit and repeatable across agent hosts.
