# nix-agent skill testing notes

## Test walkthroughs for the new tool surface

### Evaluation and discovery

- Call `eval_config("environment.systemPackages")` to read the live system's resolved package list.
- Compare with `mcp-nixos` discovery for confirmation.

### Linting

- Call `check("lint")` on a configuration with a known deadnix warning (e.g., an unused let binding).
- Verify that `findings` is a structured list with `file`, `line`, `column`, `message` per finding.
- Verify that `commands` echoes the two linters that ran.

### Validation and building

- Touch a `.nix` file (e.g., syntax error or eval error).
- Call `check("dry-build")` and confirm `first_error` surfaces the actionable error line.
- Call `build()` on a working config and verify it completes with a store path.

### Formatting

- Edit a `.nix` file with poor spacing.
- Call `format(paths=["/path/to/file"])` and verify the file is formatted.
- Or call `format()` with no paths to format the entire flake.

### Diffing and switching

- Edit a `.nix` file to add or remove a package.
- Call `diff()` and show the user the changeset before activation.
- Call `switch()` to activate and capture `rollback_generation`.
- Confirm the change on the live system.

### Rollback

- After a switch, call `generations(action="list")` to see the generation history.
- Call `generations(action="rollback")` and verify the system reverts.

## Why this skill exists

The MCP tools are discoverable without a skill, but the skill makes the workflow explicit and repeatable across agent hosts. It also clarifies the division: file I/O stays with native tools, operations go to nix-agent, discovery goes to mcp-nixos.
