# nix-agent v0.5.0 — Pure Nix Ops Toolbox

**Date:** 2026-06-11
**Status:** Approved

## Goal

Reorient nix-agent from a structured mutation pipeline into a pure enhancement layer for a capable AI agent. The host agent (Claude Code, opencode, etc.) already has superior file read/edit tools; nix-agent stops duplicating them and instead exposes the NixOS-specific operations — evaluation, linting, validation, building, diffing, switching, generation management — as composable, structured tools. Nothing in the server gates or restricts the agent.

## Non-goals

- File I/O tools (`inspect_state`, `apply_patch_set`) — removed, no compat shims.
- In-MCP approval gates or path restrictions — these belong to the host's permission system.
- Package/option *discovery* — stays in `mcp-nixos`.
- VM testing (`nixos-rebuild build-vm`) — out of scope for v0.5.0.

## Tool surface (7 tools)

All tools accept an optional `flake_uri`; tools that touch a system closure also accept `mode: "nixos" | "home-manager"` (default `"nixos"`). Omitted values are auto-resolved (see Target resolution).

### 1. `eval_config(attr, flake_uri=None, mode="nixos")`

Evaluate the final merged value of an attribute in the user's actual configuration:

- nixos: `nix eval <uri>#nixosConfigurations.<host>.config.<attr> --json`
- home-manager: `nix eval <uri>#homeConfigurations.<name>.config.<attr> --json`

Falls back to non-JSON eval when the value is not JSON-serializable (functions, derivations), returning the `--raw`/default rendering and noting the fallback. This complements `mcp-nixos`: that tells you what an option *means*; this tells you what *this machine* resolved it to after all modules and overlays merge.

### 2. `check(level, flake_uri=None, mode="nixos")`

One validation-ladder tool, fast → slow:

- `"lint"` — run `statix check` and `deadnix` over the flake directory. Both emit JSON; parse into structured findings: `[{tool, file, line, column, message, severity}]`.
- `"flake"` — `nix flake check <uri>`.
- `"dry-build"` — build the closure without activating (nixos: `nixos-rebuild dry-build --flake`; home-manager: `home-manager build --flake`).
- `"dry-activate"` — nixos only: `sudo nixos-rebuild dry-activate --flake`. For home-manager mode, return status `not_applicable` with a hint to use `dry-build`.

Unknown level → `status: "invalid_level"` listing valid levels.

### 3. `format(paths=None, flake_uri=None)`

Format `.nix` files. If `paths` is given, format those files; otherwise format the whole flake directory. Formatter preference:

1. `nix fmt` in the flake directory (respects the flake's own `formatter` output) — used when formatting the whole directory and the flake defines a formatter.
2. `nixfmt` on individual files otherwise.

Response reports which formatter ran and per-file results.

### 4. `build(flake_uri=None, mode="nixos")`

Full closure build (no activation):

- nixos: `nix build --no-link --print-out-paths <uri>#nixosConfigurations.<host>.config.system.build.toplevel` (no sudo, no `./result` symlink littered in cwd, store path comes straight from stdout)
- home-manager: `home-manager build --flake <uri>` (output path parsed from the `./result` link it creates)

Returns the output store path plus `first_error` on failure.

### 5. `diff(flake_uri=None, mode="nixos")`

Build the new closure (reusing the `build` path), then diff against the live system:

- nixos: `nvd diff /run/current-system <new-toplevel>`
- home-manager: `nvd diff <current-hm-generation> <new-generation>`

Falls back to `nix store diff-closures` when `nvd` is unavailable. Returns the rendered diff (package additions, removals, version changes) so the agent can show the user what a switch would do before doing it.

### 6. `switch(flake_uri=None, mode="nixos")`

1. Record `rollback_generation` (current generation before switching).
2. nixos: `sudo nixos-rebuild switch --flake <uri>`; home-manager: `home-manager switch --flake <uri>`.
3. Return `rollback_generation`, `current_generation`, full output, `first_error` on failure.

No implicit validation. The agent composes `check` → `diff` → `switch` itself; the companion skill teaches that ladder.

### 7. `generations(action="list", mode="nixos")`

- `"list"` — enumerate generations with number, date, and a current marker. nixos: `nixos-rebuild list-generations` (or `nix-env --list-generations -p /nix/var/nix/profiles/system` fallback); home-manager: `home-manager generations`.
- `"rollback"` — nixos: `sudo nixos-rebuild switch --rollback`; home-manager: activate the previous generation's `activate` script. Returns the resulting current generation.

## Target resolution

When `flake_uri` is omitted:

- **nixos:** `/etc/nixos` if it contains `flake.nix`, attribute `#<hostname>`.
- **home-manager:** `~/.config/home-manager` if it contains `flake.nix`, attribute `#<user>@<hostname>`, falling back to `#<user>` (matching existing v0.4 USER-fallback behavior).

If resolution fails (no flake.nix found), return `status: "no_target"` explaining what was looked for, so the agent can pass an explicit `flake_uri`.

Every response echoes:

- `resolved_target` — the final flake URI + attribute used.
- `command` — the exact argv that ran.

Nothing is silently implicit; there is no session state.

## Response shape

Uniform envelope across tools:

```json
{
  "status": "ok | failed | not_applicable | invalid_level | no_target | tool_missing",
  "resolved_target": "...",
  "command": ["..."],
  "output": "...",
  "first_error": "...",        // on failure, existing extraction logic
  ...tool-specific fields       // findings, store_path, generations, diff, ...
}
```

Full output is returned. Past a generous cap (~64 KB), truncate the middle (keep head + tail) and note the truncation in the output.

Missing external binary (statix, deadnix, nvd, nixfmt) → `status: "tool_missing"` naming the binary — but see Packaging: the flake bundles them, so this only occurs in non-flake installs.

## Packaging

- The flake's package wraps the `nix-agent` binary with **statix, deadnix, nixfmt (rfc-style), and nvd** on PATH. Linting and diffing work out of the box.
- `nix/module.nix` unchanged in spirit (installs the wrapped package).
- Version bump to 0.5.0 (breaking).

## Deletions

- Tools: `inspect_state`, `apply_patch_set`.
- Code: `models.py` (`Patch`, `PatchSet`), `patching.py`, `inspect.py`, the patch-pipeline half of `server.py`.
- `system_apply.py` is refactored: generation helpers and command runners survive into the new per-tool modules.

## Module layout

```
src/nix_agent/
  server.py      # FastMCP tool registration only
  target.py      # flake URI / attribute resolution
  runner.py      # subprocess wrapper: argv, output capture, truncation, first_error
  tools/
    eval.py      # eval_config
    check.py     # check (lint parsers for statix/deadnix JSON live here)
    fmt.py       # format
    build.py     # build, diff
    switch.py    # switch, generations
```

Each tool module exposes one plain function returning the response dict; `server.py` registers them. Functions are unit-testable without MCP.

## Docs & skill

- Rewrite `skills/nix-agent/SKILL.md`: the agent edits files with its **native** tools, then composes nix-agent: `format` → `check("lint")` → `check("dry-build")` (or `eval_config` for targeted verification) → `diff` → `switch`; `generations("rollback")` on regret. Secrets guidance (sops-nix/agenix references only) carries over.
- Update README tool table, CLAUDE.md operational notes, `docs/agent-install.md`, examples.

## Testing

- Per-tool unit tests with `subprocess.run` mocked: argv construction, status mapping, mode handling.
- Parser tests with captured real statix/deadnix JSON and generation-list output as fixtures.
- Target-resolution tests (env/hostname mocked): defaults, fallbacks, `no_target`.
- Output truncation and `first_error` extraction tests (extraction logic is kept from v0.4).
- Existing `test_apply_patch_set.py` is deleted; `test_cli.py` / `test_distribution.py` / `test_imports.py` updated for the new surface.
