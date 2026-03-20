# nix-agent skill testing notes

## Baseline scenarios checked before rewriting the skill

- Installing a package through `nix-agent` plus `mcp-nixos`
- Activating a touched `configuration.nix` after patching
- Direct package-install requests incorrectly detouring into generic brainstorming

## Expected behavior with the skill present

- Skip generic brainstorming for direct NixOS MCP execution tasks
- Start with `plan_change()`
- Respect `requires_mcp_nixos`
- Run formatters before apply
- Stop on `approval_required`
- Treat `nix-agent` as local mutation/validation only

## Why this skill exists

The MCP tools are discoverable without a skill, but the skill makes the workflow explicit and repeatable across agent hosts.

The updated version also pushes direct NixOS operational requests away from generic brainstorming and toward the actual MCP workflow.
