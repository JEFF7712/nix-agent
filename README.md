# nix-agent

`nix-agent` is a local MCP server for NixOS changes, plus a companion skill that teaches agents how to use it safely.

This project is intended for trusted local automation on a NixOS machine. It is not a generic remote deployment service and it does not replace `mcp-nixos`.

## What this repo ships

- An MCP server that exposes tools for local inspection, patching, formatting, policy checks, validation, and controlled `nixos-rebuild switch`.
- A companion skill at `skills/nix-agent/SKILL.md` for Claude Code, OpenCode, or other skill-aware agents.
- Example MCP host config snippets in `examples/`.

## Product boundary

`nix-agent` handles local machine inspection, file mutation, formatting, policy checks, dry activation, and switching.

`mcp-nixos` remains the discovery side: package lookup, option lookup, and attribute discovery. Start with `plan_change()` and obey `requires_mcp_nixos` when it is `true`.

## Who this is for

- You run NixOS locally and want an MCP server that can inspect and mutate your machine-local configuration.
- You already use an MCP-capable agent host such as Claude Code or OpenCode.
- You are comfortable granting the agent access to `sudo`, `nixos-rebuild`, and unrestricted local file writes in a trusted environment.

This is probably not the right tool if you want untrusted multi-user access, remote orchestration, or secret material management.

## MCP tools

- `inspect_state(path|target)` - read a local file.
- `plan_change(goal)` - decide whether `mcp-nixos` should be used first.
- `apply_patch_set(patch_set)` - write file replacements and report touched files.
- `run_formatters(changed_files)` - run `nixpkgs-fmt` for touched `.nix` files.
- `dry_activate_system(flake_uri)` - run `nixos-rebuild dry-activate --flake` and report success/failure.
- `classify_change(changed_files, operation)` - evaluate approval policy.
- `apply_change(intent, changed_files, flake_uri)` - classify for `switch`, dry-activate, then switch if validation succeeds.
- `get_operation_result(operation_id)` - placeholder for future async tracking.

## Required workflow

The server exposes separate tools on purpose. The intended flow is:

1. `plan_change(goal)`
2. If `requires_mcp_nixos` is `true`, query `mcp-nixos`
3. `apply_patch_set(patch_set)`
4. If `apply_patch_set()` returns `status="approval_required"`, stop and ask for approval
5. `run_formatters(changed_files)`
6. `classify_change(changed_files)`
7. If approval is not required, `apply_change(intent, changed_files, flake_uri)`

`apply_change()` does not run formatters for you.

## Policy behavior

- Deletes always require approval.
- Matching high-risk paths like SSH, networking, and hardware configuration require approval for covered operations.
- Rules are defined in `src/nix_agent/policy.py`.
- `classify_change()` respects operation-specific rule matching.

## Safety and limits

- `apply_change()` stops before `switch` if dry activation fails.
- Secret payload editing is out of scope.
- File writes are intentionally unrestricted in this version because the operator may manage files outside a fixed root. Use this MCP only in trusted agent environments.
- This repo does not replace `mcp-nixos`; it complements it.

## Quick start

### Fastest install for Nix users

If you just want the MCP server binary available on your NixOS machine, add this flake input and module:

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

After that, point your MCP host at:

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

### 1. Install dependencies

You need:

- NixOS
- Python 3.11+
- `fastmcp`
- `nixpkgs-fmt`
- `sudo`
- `nixos-rebuild`

With the dev shell:

```bash
nix develop
```

Or with Python directly:

```bash
python -m pip install -e .
```

The Python install path creates the `nix-agent` console script defined in `pyproject.toml`.

### 2. Run the MCP server

```bash
nix-agent
```

Or:

```bash
python -m nix_agent
```

The server uses stdio transport by default.

### 3. Connect your MCP host

Minimal host config:

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

Ready-to-copy examples live in `examples/claude-code-mcp.json` and `examples/opencode-mcp.json`.

### 4. Install the companion skill

Copy `skills/nix-agent/` into your agent's skill directory, or adapt the contents into your agent's project instructions.

The MCP server exposes tools. The skill teaches the correct workflow for using them safely.

### 5. Add it to NixOS with the flake module

Import the module from this flake and enable it:

```nix
{
  inputs.nix-agent.url = "github:JEFF7712/nix-agent";

  imports = [ inputs.nix-agent.nixosModules.default ];

  programs.nix-agent.enable = true;
}
```

That adds the `nix-agent` command to `environment.systemPackages`.

### 6. Run it directly from the flake

```bash
nix run .#default
```

If you consume this repo as a flake input from another configuration, you can also run:

```bash
nix run github:JEFF7712/nix-agent#default
```

## First-use example

Typical request flow for a package install:

1. The user asks the agent to install a package such as `ripgrep`.
2. The agent calls `plan_change("install ripgrep")`.
3. `nix-agent` returns `requires_mcp_nixos=true`.
4. The agent queries `mcp-nixos` for the correct package attribute.
5. The agent builds a `PatchSet` and calls `apply_patch_set(...)`.
6. The agent calls `run_formatters(changed_files)`.
7. The agent calls `classify_change(changed_files)`.
8. If approval is not required, the agent calls `apply_change(intent, changed_files, flake_uri)`.

Typical request flow for a local config edit that does not need discovery:

1. The user asks the agent to edit an existing NixOS file.
2. The agent calls `plan_change(...)` and sees `requires_mcp_nixos=false`.
3. The agent applies the patch, formats, classifies, and then applies the change.

## Companion skill

The skill exists to teach workflow, not tool discovery. MCP makes tools visible; the skill teaches:

- when to call `mcp-nixos` first
- the required tool order
- when to stop on approval-required responses
- that `apply_change()` assumes formatting already happened
- what not to do with secrets and unsafe assumptions

If you skip the skill, the MCP is still usable, but the agent has less guidance about tool order and the `mcp-nixos` boundary.

## Known limitations in v1

- `get_operation_result(operation_id)` is only a placeholder for future async tracking.
- File writes are unrestricted by design in this release.
- Secret payloads are out of scope.
- Approval decisions are path-based and intentionally simple.
- `nix flake check` validates the current system by default; use `--all-systems` if you need broader flake validation.

## Verification

Run the full local verification used for this repo:

```bash
pytest
nix build .#default
nix flake check
```

CI also runs `pytest` on push and pull request via `.github/workflows/ci.yml`.

## Release checklist

- `git status` is clean
- `pytest` passes
- `nix build .#default` passes
- `nix flake check` passes
- MCP host config has been tested with the installed `nix-agent` binary
- Companion skill is installed or documented for the target agent host

## Files to start with

- `src/nix_agent/server.py`
- `src/nix_agent/policy.py`
- `src/nix_agent/system_apply.py`
- `skills/nix-agent/SKILL.md`
- `examples/claude-code-mcp.json`
- `examples/opencode-mcp.json`
- `nix/module.nix`
- `.github/workflows/ci.yml`
