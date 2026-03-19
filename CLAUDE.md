# CLAUDE Operational Notes

1. **Purpose** – `nix-agent` is the local mutation and validation half of the two-server workflow. It reads machine state, edits managed files through structured patches, formats/validates `.nix` content, and gates apply actions via a simple approval blacklist. Package/option discovery stays in `mcp-nixos`.
2. **Tool recipe** –
   - Start with `plan_change(goal)`; obey the `requires_mcp_nixos` flag and `notes`. If true, run `mcp-nixos` to resolve packages or options before performing any local mutation.
   - Construct the necessary `PatchSet` of `Patch(path, content)` edits and invoke `apply_patch_set`. Track the returned `changed_files` list.
      - If `apply_patch_set` returns `approval_required`, inspect the supplied `trust_proposals`, call `record_managed_root(state_path, root)` to persist the new root, and retry the patch set with the updated `managed_state`.
   - Call `run_formatters(changed_files)` so touched `.nix` files are formatted before validation.
   - Run `classify_change(changed_files)` to check the approval blacklist. If `approval_required` is true, halt and describe the `reason` (paths containing `ssh`, `network`, or `firewall`).
   - If classification allows it, call `apply_change(intent, changed_files, flake_uri)` to run the dry-activate and switch path and report the `OperationResult`.
   - Use `inspect_state` and `get_operation_result` for extra context as needed.
3. **Approval & safety** – Approval decisions are config-driven via `POLICY_RULES` in `src/nix_agent/policy.py`. Sensitive rule categories (`auth-ssh`, `network-core`, `boot-identity`, `secrets-wiring`) always block create/patch/delete/switch paths and report the matching rule IDs, while lower-risk user/application config (`user-config`) remains approval-free.

   Operation context matters: `classify_change` defaults to `patch`, enforces only the listed operations, and fails closed for anything outside create/patch/delete/switch (blocked with `approval_required`). `apply_change` still stops at classification when approval is required, and every allowed change is validated via `nixos-rebuild dry-activate` before a controlled `switch`.
   Unknown paths create trust proposals that must be recorded before the root can be treated as managed.
   Approved roots persist locally via the `record_managed_root` helper so future patch sets can run without re-approval.
   Managed writes still require drift-safe validation; each patch that supplies `expected_content` or `expected_sha256` is rechecked and any divergence results in a `conflict` response.
4. **Secret handling** – Editing secret payloads is out of scope for v1. You may adjust references/metadata, but never write secret blobs or credentials through the Ops Agent surface.
