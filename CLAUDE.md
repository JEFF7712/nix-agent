# CLAUDE Operational Notes

1. **Purpose** – `nix-agent` is the local mutation and validation half of the two-server workflow. It reads machine state, edits managed files through structured patches, formats/validates `.nix` content, and gates apply actions via a simple approval blacklist. Package/option discovery stays in `mcp-nixos`.
2. **Tool recipe** –
   - Start with `plan_change(goal)`; obey the `requires_mcp_nixos` flag and `notes`. If true, run `mcp-nixos` to resolve packages or options before performing any local mutation.
   - Construct the necessary `PatchSet` of `Patch(path, content)` edits and invoke `apply_patch_set`. Track the returned `changed_files` list.
   - Call `run_formatters(changed_files)` so touched `.nix` files are formatted before validation.
   - Run `classify_change(changed_files)` to check the approval blacklist. If `approval_required` is true, halt and describe the `reason` (paths containing `ssh`, `network`, or `firewall`).
   - If classification allows it, call `apply_change(intent, changed_files, flake_uri)` to run the dry-activate and switch path and report the `OperationResult`.
   - Use `inspect_state` and `get_operation_result` for extra context as needed.
3. **Approval & safety** – The policy blocks any edit whose file path includes `ssh`, `network`, or `firewall`. `apply_change` will stop at classification and mark `approval_required` until a human explicitly approves. All actual activation runs through `nixos-rebuild dry-activate` followed by a controlled `switch` when allowed.
4. **Secret handling** – Editing secret payloads is out of scope for v1. You may adjust references/metadata, but never write secret blobs or credentials through the Ops Agent surface.
