# nix-agent

`nix-agent` is a local MCP server for trusted NixOS automation.

It works alongside [`mcp-nixos`](https://github.com/utensils/mcp-nixos):
- `nix-agent` handles local inspection, patching, validation, and switching
- `mcp-nixos` handles package and option discovery

## NOTE: This is experimental and a work in progress. Feedback and contributions are very welcome.

## What you get

- a runnable stdio MCP server
- a Nix flake package and app
- a NixOS module at `nixosModules.default`
- a companion agent skill in `skills/nix-agent/`
- example MCP host configs in `examples/`

## One-shot agent install

Paste this to a coding agent (Claude Code, opencode, etc.) and it will do the install for you:

```
Read https://raw.githubusercontent.com/JEFF7712/nix-agent/main/docs/agent-install.md and follow every step to install nix-agent on this NixOS system, install the companion skill, and register nix-agent in my MCP settings for this machine.
```
## Fast install

Add this flake input and module to your NixOS config:

```nix
{
  inputs.nix-agent.url = "github:JEFF7712/nix-agent";

  outputs = { nixpkgs, nix-agent, ... }: {
    nixosConfigurations.my-host = nixpkgs.lib.nixosSystem {
      system = "x86_64-linux";
      modules = [
        nix-agent.nixosModules.default
        ({ ... }: {
          programs.nix-agent.enable = true;
        })
      ];
    };
  };
}
```

Then rebuild:

```bash
sudo nixos-rebuild switch --flake .#my-host
```

That installs the `nix-agent` binary.

## MCP host config

Point your MCP host at:

```json
{
  "mcpServers": {
    "nix-agent": {
      "command": "nix-agent",
      "args": []
    }
  }
}
```

See `examples/claude-code-mcp.json` and `examples/opencode-mcp.json`.

## Companion skill

Install or copy `skills/nix-agent/` into your agent's skill directory.

Quick install:

```bash
./install-skill.sh opencode
```

The MCP exposes the tools. The skill teaches the correct workflow.

## Tool surface

`nix-agent` exposes two tools:

- `inspect_state(path)` — read a local file.
- `apply_patch_set(patch_set, flake_uri=None)` — write each `Patch(path, content)`, format any `.nix` files, and (when `flake_uri` is given) run `nixos-rebuild dry-activate` then `switch`. Returns `changed_files`, `rollback_generation`, `current_generation`, command outputs, and a `status`.

`mcp-nixos` handles package and option discovery.

## Basic workflow

1. If you need package or option info, query `mcp-nixos` first.
2. Build a `PatchSet` of `Patch(path, content)` entries.
3. Call `apply_patch_set(patch_set, flake_uri="/etc/nixos#hostname")`.
4. If anything looks wrong, recover with `sudo nixos-rebuild switch --rollback`. The response includes `rollback_generation` for reference.

## Design notes

- `nix-agent` deliberately does **not** ship an in-MCP approval gate. Path restrictions belong in the host's permission system (e.g. Claude Code's allow/deny lists), and rollback safety belongs to Nix generations. Re-implementing either inside the MCP just adds friction without improving safety.
- Do not write secret payloads through patches — reference secrets via `sops-nix` or `agenix`.
- v1 assumes a trusted local environment.
- Fully non-interactive apply requires privileged automation; see `docs/privileged-automation.md`.

## More detail

- release notes: `docs/releases/v0.1.0.md`
- skill docs: `skills/nix-agent/SKILL.md`
- examples: `examples/`
