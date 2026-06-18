# nix-agent

`nix-agent` is a local MCP server that gives AI agents composable NixOS
operations: eval, lint, format, build, diff, switch, generations.

It works alongside [`mcp-nixos`](https://github.com/utensils/mcp-nixos):
- `nix-agent` handles operations on your actual configuration — evaluating, linting, formatting, building, diffing, switching
- `mcp-nixos` handles package and option discovery

## NOTE: This is experimental and a work in progress. Feedback and contributions are very welcome.

## What you get

- a runnable stdio MCP server
- a Nix flake package and app (wrapper bundles statix/deadnix/nixfmt/nvd)
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

All tools auto-resolve the target when `flake_uri` is omitted. Resolution
order: `$NIX_AGENT_FLAKE` (or `$NIX_AGENT_HM_FLAKE` for HM), then the first
existing `flake.nix` among `/etc/nixos`, `~/nixos`, `~/.config/nixos`,
`~/nix-config`, `~/nixos-config` for NixOS (`~/.config/home-manager`,
`~/.config/nixpkgs` for Home Manager). The hostname / `user@host` attribute is
picked automatically. Every result echoes back `resolved_target` and the exact
`command` run. Exception: calling `format` with explicit `paths` returns
per-file `results` instead.

`mode` defaults to `"nixos"`. Use `"home-manager"` only for a **standalone** HM
flake (its own `homeConfigurations`, applied with `home-manager switch`). When
HM is integrated as a NixOS module (built into the system closure), keep
`mode="nixos"` and switch the whole system — there is no separate HM switch. On
a machine that has both a NixOS flake and a leftover `~/.config/home-manager`
flake, pin the target with `$NIX_AGENT_FLAKE` or an explicit `flake_uri` so
resolution can't pick the wrong one. See `skills/nix-agent/SKILL.md` for the
full mode-selection guidance.

| Tool | What it does |
|------|-------------|
| `eval_config(attr, flake_uri?, mode?)` | Final merged value of any config attribute on this machine (after all modules/overlays). `mcp-nixos` tells you what an option means; this tells you what it resolves to. |
| `check(level, flake_uri?, mode?)` | Validation ladder, fast to slow: `"lint"` (statix + deadnix, structured `findings` list), `"flake"`, `"dry-build"`, `"dry-activate"` (NixOS only). |
| `format(paths?, flake_uri?, mode?)` | `nix fmt` / nixfmt. With explicit `paths`, returns per-file `results`. |
| `build(flake_uri?, mode?)` | Build the closure, no activation. |
| `diff(flake_uri?, mode?)` | What a switch would change (package adds/removes/version bumps). Show this to the user before switching. |
| `switch(flake_uri?, mode?, validate?, full_log?)` | Activate. Records `rollback_generation`. Returns a structured `summary` (units changed, derivations built) and trims the log to a tail on success (`full_log=True` for all of it). `validate=True` gates on `check("dry-build")` first; a sudo auth failure returns a `privilege` diagnosis. |
| `generations(action="list"\|"rollback", mode?)` | List or roll back generations. |

## Basic workflow

1. Discovery: query `mcp-nixos` for packages/options; use `eval_config` to see what the user's machine currently resolves.
2. Edit `.nix` files with the agent's native file tools (Read/Edit/Write).
3. `format()` then `check("lint")` — fix findings worth fixing.
4. `check("dry-build")` — catches eval/build errors cheaply.
5. `diff()` — show the user what will change.
6. `switch()` — activate; reports `rollback_generation`.
7. On regret: `generations(action="rollback")`.

Steps 3–5 are judgment calls, not gates — for a trivial change, going straight
to `switch` is fine.

On failure, the response includes a `first_error` field with the first
actionable error line from Nix's output, alongside the full log.

## Design notes

- nix-agent does no file I/O. The host agent's own file tools are better
  at reading and editing; nix-agent only provides the Nix operations
  around them.
- No in-MCP approval gates. Path restrictions belong to the host's
  permission system; rollback safety belongs to Nix generations.
- Every response echoes `resolved_target` and the exact `command` run —
  nothing is silently implicit.
- Do not write secret payloads into configs — reference secrets via
  sops-nix or agenix.
- Fully non-interactive switch requires privileged automation; see
  `docs/privileged-automation.md`.

## More detail

- skill docs: `skills/nix-agent/SKILL.md`
- examples: `examples/`
