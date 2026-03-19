# nix-agent
Autonomous agent for managing your NixOS configuration through guided, MCP-driven workflows.

## What the Ops Agent does

- Inspect local system state and managed config files without mutating them.
- Apply structured `PatchSet`s to deterministic targets, run file-appropriate formatters, and validate changes through `nixos-rebuild dry-activate` before triggering any switch.
- Classify risk via an approval blacklist, gate execution when needed, and return compact `OperationResult` summaries for callers.

## Partnering with `mcp-nixos`

`nix-agent` handles inspection, mutation, validation, and activation, while `mcp-nixos` remains the source of truth for package names, option lookups, and attribute discovery. `plan_change()` mirrors that boundary by emitting `requires_mcp_nixos` and notes whenever the goal mentions package installation or option discovery, signaling that the caller must run `mcp-nixos` first before invoking local mutations.

## When to call `mcp-nixos` first

- Any goal that involves installing packages (`install`, `package`, etc.) should be paired with `mcp-nixos` to resolve the attribute path before the Ops Agent touches local files.
- Option discovery requests (anything mentioning `option`, `setting`, or a NixOS module knob) also need `mcp-nixos` answers before `apply_patch_set` runs.
- `plan_change()` embeds these heuristics in the `requires_mcp_nixos` flag and `notes`, so follow that guidance rather than guessing from the request alone.

## Available MCP tools

- `inspect_state(path|target)`: read a single machine-local artifact for conversational inspection.
- `plan_change(goal)`: identify the goal, emit `requires_mcp_nixos`, and describe why package/option lookups belong on the discovery server.
- `apply_patch_set(patch_set)`: write each `Patch` (path + content) and report touched files.
  If any target path is outside the recorded managed roots it will return `status: approval_required` along with `trust_proposals` describing the proposed root, so callers can record the approval before retrying.
- `run_formatters(changed_files)`: invoke `nixpkgs-fmt` for `.nix` files touched by the patch set.
- `dry_activate_system(flake_uri)`: run `nixos-rebuild dry-activate --flake` for validation output.
- `classify_change(changed_files)`: enforce the approval blacklist (paths containing `ssh`, `network`, or `firewall`) and return a `policy_decision` with `approval_required`/`reason`.
- `apply_change(intent, changed_files, flake_uri)`: orchestrate approval checks, dry-activate, and a controlled `nixos-rebuild switch`, returning the `OperationResult` body.
- `get_operation_result(operation_id)`: placeholder view when external tracking is required later.
- `record_managed_root(state_path, root)`: persist an approved managed root to `state_path` so future patch sets treat that tree as managed.

## Approval policy behavior

Approval decisions now come from the config-driven `POLICY_RULES` in `src/nix_agent/policy.py`. Each rule names a set of path patterns, specifies which operations it controls, and tags itself with a risk level. The sensitive categories (`auth-ssh`, `network-core`, `boot-identity`, `secrets-wiring`) always block create/patch/delete/switch operations and surface the matching rule IDs via `matched_rules`. The remaining `user-config` category is treated as low risk and does not require approval.

Operation context matters: `classify_change` defaults to `patch`, matches only the supplied operation against each rule, and blocks the request whenever a sensitive rule applies for that operation. Anything outside the listed operations (create/patch/delete/switch) fails closed, marking `approval_required` as true and returning `policy_decision: blocked` so callers know the request needs review.

## Example requests

- "Install ripgrep": consult `mcp-nixos` for the attribute, then patch your NixOS config, run formatters/validation, and switch.
- "Inspect the firewall rules": call `inspect_state` on the relevant files without altering anything.
- "Add a cava module to Waybar": use `plan_change` to confirm no extra discovery is needed, apply a patch to the Waybar config, format/validate, and activate.

## Safety & scope

- Secret payloads remain out of scope for v1; the agent can edit references or metadata, but it must never write actual secret blobs or credentials to disk.
- Everything runs through patch-and-policy tooling, so the Ops Agent never executes arbitrary shell commands outside the controlled tools above.
- Unknown paths create trust proposals that must be approved and recorded before the patch set can run again.
- Approved roots persist locally (via `record_managed_root`) so the agent remembers that tree is trusted for future writes.
- Managed writes still require drift-safe validation: `apply_patch_set` enforces `expected_content`/`expected_sha256` checks per patch and will report a `conflict` if anything diverges.

## Documentation checklist

- Cover each MCP tool plus its purpose.
- Reiterate the safety model and approval blacklist behavior.
- Provide concrete example requests that match the implementation.
- Explain when `mcp-nixos` must be called before local actions.
