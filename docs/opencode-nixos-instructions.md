# OpenCode NixOS MCP Instructions

Add this to your OpenCode project instructions if you want `nix-agent` and `mcp-nixos` to win over generic brainstorming for routine NixOS tasks.

```text
For any task involving NixOS packages, options, modules, or local NixOS configuration, prefer the `nix-agent` + `mcp-nixos` workflow over generic brainstorming/planning skills.

If the task is operational and direct (for example: install a package, enable an option, patch config, apply a change), do not invoke generic brainstorming first.

Use this order:
1. `mcp-nixos` for package or option discovery when needed
2. `nix-agent` `plan_change(goal)`
3. `nix-agent` patch/format/classify/apply workflow

Only use generic brainstorming or architecture/planning skills when the user is explicitly asking for design trade-offs, architecture, or a broad plan rather than execution.
```
