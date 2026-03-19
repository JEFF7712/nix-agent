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
- `run_formatters(changed_files)`: invoke `nixpkgs-fmt` for `.nix` files touched by the patch set.
- `dry_activate_system(flake_uri)`: run `nixos-rebuild dry-activate --flake` for validation output.
- `classify_change(changed_files)`: enforce the approval blacklist (paths containing `ssh`, `network`, or `firewall`) and return a `policy_decision` with `approval_required`/`reason`.
- `apply_change(intent, changed_files, flake_uri)`: orchestrate approval checks, dry-activate, and a controlled `nixos-rebuild switch`, returning the `OperationResult` body.
- `get_operation_result(operation_id)`: placeholder view when external tracking is required later.

## Approval blacklist behavior

The Ops Agent blocks auto-apply (sets `approval_required`) whenever a `changed_files` list includes `ssh`, `network`, or `firewall` in the path: these change types return `policy_decision: blocked` with `reason: matched approval blacklist`. Allow-list safe touches proceed through dry-activate and switch without human approval.

## Example requests

- "Install ripgrep": consult `mcp-nixos` for the attribute, then patch your NixOS config, run formatters/validation, and switch.
- "Inspect the firewall rules": call `inspect_state` on the relevant files without altering anything.
- "Add a cava module to Waybar": use `plan_change` to confirm no extra discovery is needed, apply a patch to the Waybar config, format/validate, and activate.

## Safety & scope

- Secret payloads remain out of scope for v1; the agent can edit references or metadata, but it must never write actual secret blobs or credentials to disk.
- Everything runs through patch-and-policy tooling, so the Ops Agent never executes arbitrary shell commands outside the controlled tools above.

## Documentation checklist

- Cover each MCP tool plus its purpose.
- Reiterate the safety model and approval blacklist behavior.
- Provide concrete example requests that match the implementation.
- Explain when `mcp-nixos` must be called before local actions.
