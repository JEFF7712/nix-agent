# nix-agent

`nix-agent` is a local MCP server for NixOS changes, plus a companion skill that teaches agents how to use it safely.

## What this repo ships

- An MCP server that exposes tools for local inspection, patching, formatting, policy checks, validation, and controlled `nixos-rebuild switch`.
- A companion skill at `skills/nix-agent/SKILL.md` for Claude Code, OpenCode, or other skill-aware agents.
- Example MCP host config snippets in `examples/`.

## Product boundary

`nix-agent` handles local machine inspection, file mutation, formatting, policy checks, dry activation, and switching.

`mcp-nixos` remains the discovery side: package lookup, option lookup, and attribute discovery. Start with `plan_change()` and obey `requires_mcp_nixos` when it is `true`.

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

### 1. Install dependencies

You need:

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

See `examples/claude-code-mcp.json` and `examples/opencode-mcp.json`.

### 4. Install the companion skill

Copy `skills/nix-agent/` into your agent's skill directory, or adapt the contents into your agent's project instructions.

### 5. Add it to NixOS with the flake module

Import the module from this flake and enable it:

```nix
{
  imports = [ inputs.nix-agent.nixosModules.default ];

  programs.nix-agent.enable = true;
}
```

That adds the `nix-agent` command to `environment.systemPackages`.

### 6. Run it directly from the flake

```bash
nix run .#default
```

## Companion skill

The skill exists to teach workflow, not tool discovery. MCP makes tools visible; the skill teaches:

- when to call `mcp-nixos` first
- the required tool order
- when to stop on approval-required responses
- that `apply_change()` assumes formatting already happened
- what not to do with secrets and unsafe assumptions

## Verification

Run the test suite:

```bash
pytest
```

CI also runs `pytest` on push and pull request via `.github/workflows/ci.yml`.

## Files to start with

- `src/nix_agent/server.py`
- `src/nix_agent/policy.py`
- `src/nix_agent/system_apply.py`
- `skills/nix-agent/SKILL.md`
- `examples/claude-code-mcp.json`
- `examples/opencode-mcp.json`
- `nix/module.nix`
- `.github/workflows/ci.yml`
