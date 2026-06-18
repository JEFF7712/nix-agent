<p align="center">
  <img src="assets/banner.png" alt="nix-agent: composable NixOS operations for AI agents" width="100%">
</p>

# nix-agent

A local MCP server that gives AI agents composable NixOS / Home Manager
operations: eval, lint, format, build, diff, switch, generations.

It pairs with [`mcp-nixos`](https://github.com/utensils/mcp-nixos): nix-agent
operates on your actual configuration, `mcp-nixos` handles package and option
discovery.

> **Experimental and a work in progress.** Feedback and contributions welcome.

## Install

Paste this to a coding agent (Claude Code, opencode, …) and it does the install:

```
Read https://raw.githubusercontent.com/JEFF7712/nix-agent/main/docs/agent-install.md and follow every step to install nix-agent on this NixOS system, install the companion skill, and register nix-agent in my MCP settings for this machine.
```

Or do it by hand, see [docs/usage.md](docs/usage.md#install).

## Docs

- [docs/usage.md](docs/usage.md): install, MCP host config, tool surface, workflow, design notes
- [docs/agent-install.md](docs/agent-install.md): one-shot agent install guide
- [docs/privileged-automation.md](docs/privileged-automation.md): non-interactive switch
- [skills/nix-agent/SKILL.md](skills/nix-agent/SKILL.md): companion agent skill

---

The banner uses the Nix snowflake from [NixOS/nixos-artwork](https://github.com/NixOS/nixos-artwork), licensed [CC-BY 4.0](https://creativecommons.org/licenses/by/4.0/).
