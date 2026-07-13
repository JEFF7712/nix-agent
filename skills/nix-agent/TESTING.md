# nix-agent skill testing notes

## Test walkthroughs for the new tool surface

### Evaluation and discovery

- Call `eval_config("environment.systemPackages")` to read the live system's resolved package list.
- Compare with `mcp-nixos` discovery for confirmation.
- Pass a list, e.g. `eval_config(["networking.hostName", "services.openssh.enable"])`, and verify the response carries per-attr `results` and no top-level `value`.
- Evaluate a large attrset and confirm the size guard fires: the value degrades to attr names / length / a head slice with `truncated: true`.

### Locating where an option is set

- Call `locate_option("services.openssh.enable")` and verify `declarations` (files declaring it) and `definitions` (`{file, value}` per defining file).
- Call it on a plain attrset path (e.g. `locate_option("networking")`) and confirm `status` is `not_an_option`.
- For an integrated Home Manager option, spell the attr `home-manager.users.<user>.<attr>` with `mode="nixos"`.

### Inspecting a repo

- Run `nix-agent inspect-flake` on a config repo and verify the JSON fact bundle: `hosts`, `hm_integration`, `module_dirs`, `formatter`, `lint_tools`, and justfile/CI/`.mcp.json` presence.
- Confirm undecidable facts come back `null`/`"unknown"`, never guessed.

### Linting

- Call `check("lint")` on a configuration with a known deadnix warning (e.g., an unused let binding).
- Verify that `findings` is a structured list with `file`, `line`, `column`, `message` per finding.
- Verify that `commands` echoes the two linters that ran.

### Validation and building

- Touch a `.nix` file (e.g., syntax error or eval error).
- Call `check("dry-build")` and confirm `first_error` surfaces the actionable error line, and `error_detail` (`{message, file, line, column, trace}`) is present when the output is an eval error.
- Call `build()` on a working config and verify it completes with a store path.
- Introduce a builder failure (a package whose build phase exits non-zero) and confirm the failed `build()` carries `failed_derivation` (`{drv, log_tail}`) instead of forcing a separate `nix log`.

### Diffing and switching

- Edit a `.nix` file to add or remove a package.
- Call `diff()`, show the user the changeset before activation, and verify the structured `packages` object (`added`/`removed` as `{name, version}`, `changed` as `{name, old, new}`) when the diff parses.
- Call `switch()` to activate and capture `rollback_generation`. Verify `summary` carries `packages` (vs the rollback generation) and `health` (systemd units `newly_failed`/`resolved`/`still_failed`, with journal tails for the first five newly failed units).
- Confirm the change on the live system.

### Rollback

- After a switch, call `generations(action="list")` to see the generation history.
- Call `generations(action="rollback")` and verify the system reverts.

## Why this skill exists

The MCP tools are discoverable without a skill, but the skill makes the workflow explicit and repeatable across agent hosts. It also clarifies the division: file I/O stays with native tools, operations go to nix-agent, discovery goes to mcp-nixos.
