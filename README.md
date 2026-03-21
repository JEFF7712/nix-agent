# nix-agent

`nix-agent` is a local MCP server for trusted NixOS automation.

It works alongside [`mcp-nixos`](https://github.com/utensils/mcp-nixos):
- `nix-agent` handles local inspection, patching, validation, and switching
- `mcp-nixos` handles package and option discovery

## What you get

- a runnable stdio MCP server
- a Nix flake package and app
- a NixOS module at `nixosModules.default`
- a companion agent skill in `skills/nix-agent/`
- example MCP host configs in `examples/`

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

## Basic workflow

1. Call `plan_change(goal)`
2. If it says `requires_mcp_nixos=true`, use `mcp-nixos` first
3. Apply patches with `apply_patch_set(...)`
4. Run `run_formatters(changed_files)`
5. Run `classify_change(changed_files)`
6. If allowed, run `apply_change(intent, changed_files, flake_uri)`

## Verification

```bash
pytest
nix build .#default
nix flake check
```

## Notes

- v1 assumes a trusted local environment
- file writes are intentionally unrestricted in this release
- `get_operation_result()` is only a placeholder in v1
- fully non-interactive apply requires privileged automation; see `docs/privileged-automation.md`

## More detail

- release notes: `docs/releases/v0.1.0.md`
- skill docs: `skills/nix-agent/SKILL.md`
- examples: `examples/`
