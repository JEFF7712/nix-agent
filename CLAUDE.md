# CLAUDE Operational Notes

1. **Purpose** – `nix-agent` is the local operations half of the two-server workflow. It evaluates, lints, formats, builds, diffs, switches, and manages generations for NixOS/Home Manager configs. The agent edits files with its own tools; package/option discovery stays in `mcp-nixos`. Rollback is delegated to Nix generations.
2. **Tool surface** – seven tools:
   - `eval_config(attr, flake_uri?, mode?)` – final merged value of any config attribute on this machine.
   - `check(level, flake_uri?, mode?)` – validation ladder: `"lint"` (statix + deadnix), `"flake"`, `"dry-build"`, `"dry-activate"` (NixOS only).
   - `format(paths?, flake_uri?, mode?)` – run `nix fmt` / nixfmt; with explicit `paths`, returns per-file results.
   - `build(flake_uri?, mode?)` – build the closure, no activation.
   - `diff(flake_uri?, mode?)` – show package adds/removes/version bumps before switching.
   - `switch(flake_uri?, mode?)` – activate; records `rollback_generation`.
   - `generations(action="list"|"rollback", mode?)` – list or roll back generations.
   All tools auto-resolve the target when `flake_uri` is omitted. Pass `mode="home-manager"` for HM configs.
3. **Workflow** – Discovery (if needed): query `mcp-nixos` / `eval_config`. Edit `.nix` files with native file tools. Then: `format()` → `check("lint")` → `check("dry-build")` → `diff()` → `switch()`. On failure, surface `first_error` and `rollback_generation`; use `generations(action="rollback")` to recover. Steps are composable judgment calls, not mandatory gates.
4. **Safety model** – There is no in-MCP approval gate. Path restrictions belong in the host's permission system (e.g. Claude Code's allow/deny lists). Rollback safety belongs to Nix generations. `nix-agent` deliberately does not re-implement either.
5. **Secret handling** – Do not write secret payloads through patches. Reference secrets via `sops-nix` / `agenix`; only edit references and metadata.
