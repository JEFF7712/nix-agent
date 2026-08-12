# Proposed changes

Status: shipped in v0.9.0, after a Claude Code review of the
v0.8.1 first-principles draft. This document is the spec that release
implemented. `docs/implementation-plan.md` is the file-by-file plan.

The product thesis stays: a local MCP server that structures NixOS / Home
Manager operations, caps noisy output, and makes rollback a first-class
result. File edits stay with the host agent. Package and option discovery
stay with `mcp-nixos`. There is still no in-MCP "are you sure?" prompt.

What did not hold up is the safety story as written in `CLAUDE.md` and
`docs/usage.md`:

> There is no in-MCP approval gate. Path restrictions belong in the host's
> permission system. Rollback safety belongs to Nix generations.

Those three sentences do not compose. Host MCP allowlists are
tool-name-level, not argument-level, so they cannot restrict `flake_uri`.
`switch` records `rollback_generation` as a store path, but
`generations(action="rollback")` ignores it and always activates the
previous generation. The companion skill tells the agent to roll back
"to the recorded generation." That is not what the tool does.

This spec closes that loop. Residual risks that remain even after these
changes are named at the end; they are accepted, not ignored.

## Principles that stay

- No in-MCP approval gate. Confirmation, if any, stays in the host.
- No file editing or formatting tools. `inspect-flake` stays a CLI
  subcommand, not a runtime tool.
- Do not merge with `mcp-nixos`.
- `check` → `diff` → `switch` stays a composable workflow, not a
  mandatory gate.
- Privileged automation remains an explicit, documented trust decision
  on a local machine. See [privileged-automation.md](privileged-automation.md).
- A tool still has to earn its slot: structure noisy Nix output, cap a
  firehose, or provide a rollback affordance.

## Honesty about what the pin is

`$NIX_AGENT_FLAKE` as a directory lock is an **anti-footgun**, not a
security boundary. The agent can edit the MCP config that supplies the
pin, and it can edit the files inside the pinned directory. The pin
narrows *where* root activation reads from, not *what* those files
contain.

The privilege boundary that actually runs as root is sudoers. Change 2
therefore narrows the sudoers rule to the pin path, and change 3
removes the Bash `nixos-rebuild switch --flake *` allow that would
route around both the MCP classifier and the host prompt.

`target_locked` / `remote_ref_rejected` stop the MCP tools from being
the confused-deputy path. They do not stop a determined agent with
file-edit access.

## 1. Rollback consumes the recorded generation

### Problem

`switch` records `rollback_generation` (realpath of the live profile
before activation). `generations(action="rollback")` ignores it:

- NixOS: `sudo nixos-rebuild switch --rollback` (previous only)
- Home Manager: activate `gens[current_index + 1]`

NixOS `list` returns `{id, date, current}` with no path, so the
recorded store path cannot be resolved against the list. Home Manager
list already has `path`. NixOS rollback also lacks the `privilege`
diagnosis `switch` already returns.

There is no `nixos-rebuild` verb that activates generation *N*.

### Spec

Extend `generations`:

```
generations(action="list"|"rollback", mode?, generation?)
```

**List (NixOS).** Each entry gains `path`: the realpath of
`/nix/var/nix/profiles/system-<id>-link` when that link exists,
otherwise omitted. Ids and dates stay as they are. This is a contract
change; list is not "unchanged."

**List (HM).** Unchanged (`id`, `date`, `path`, `current`).

**Rollback with no `generation`.** Previous generation, as today:
NixOS `sudo <nixos-rebuild> switch --rollback`; HM activates the
entry after current in the list. Attach `privilege` on NixOS sudo
auth failure, same object `switch` produces.

**Rollback with `generation` set.** Resolve against the list for that
mode. Accept:

- an int or digit string matching `id`
- a profile path (`/nix/var/nix/profiles/system-42-link`)
- the realpath of that profile path (the `/nix/store/...` value
  `switch` returns as `rollback_generation`)
- HM: the `path` field already on the list entry

If nothing matches, return `status: "unknown_generation"` (early
exit: no `command`, no `output`, no byte accounting). Do not guess.
Do not run sudo.

**NixOS targeted rollback argv** (this is the mechanism; do not
invent another):

1. `sudo <resolved nix-env> -p /nix/var/nix/profiles/system --switch-generation <id>`
2. `sudo /nix/var/nix/profiles/system/bin/switch-to-configuration switch`

Step 1 moves the profile pointer. Step 2 activates through the
**profile path**, which after step 1 points at the chosen generation.
If step 1 fails, do not run step 2; return `failed` (and `privilege`
if sudo auth failed). If step 1 succeeds and step 2 fails, return
`failed` with `current_generation` reflecting the moved pointer and
`note` that the profile advanced but activation did not.

Never execute `/nix/store/<hash>/bin/switch-to-configuration` under
sudo. Never emit a sudoers wildcard over `/nix/store/*/bin/...`.

**HM targeted rollback.** ` <matched path>/activate `, as today, but
matching the requested id/path rather than `current_index + 1`. No
sudo.

**`generations` has no `flake_uri`.** The local-ref classifier in
change 2 does not apply to this tool. Safety here is: resolve
`generation` against the local profile list; only run the argv above;
never sudo a store path.

Update skill, `CLAUDE.md`, and usage:

1. After `switch`, keep `rollback_generation`.
2. To undo that switch, call
   `generations(action="rollback", generation=<that path or id>)`.
3. Bare `generations(action="rollback")` is previous generation, and
   is only the right default when nothing else has switched since.

### Sudoers additions

Document and emit (module option, installer step 8) these additional
NOPASSWD forms, using resolved store paths for the binaries and the
profile path for activation:

- `<nix-env> -p /nix/var/nix/profiles/system --switch-generation *`
- `/nix/var/nix/profiles/system/bin/switch-to-configuration switch`

Keep `nixos-rebuild switch --rollback` for the untargeted path.

### Acceptance

- List NixOS entries include `path` when the profile link exists.
- Rollback with `generation=41` (or that generation's path / store
  realpath) runs `--switch-generation 41` then profile
  `switch-to-configuration`, not `--rollback`.
- `generation` that matches nothing returns `unknown_generation` and
  runs no command.
- NixOS rollback (targeted or not) on sudo-no-tty includes
  `privilege`.
- No test or doc suggests sudoing a `/nix/store/.../switch-to-configuration`.
- Skill and usage describe both rollback forms without claiming they
  are the same.

## 2. Privileged flake operations get a local-target constraint

### Problem

`resolve_target` accepts any string, including remote flake refs.
Host MCP allowlists cannot restrict `flake_uri`. The recommended
sudoers rule is `nixos-rebuild switch --flake *`. Together that is
unattended root activation of an arbitrary flake.

`$NIX_AGENT_FLAKE` is a default, not a constraint.

### Spec

Classifier applies only to operations that take `flake_uri` and then
activate or dry-activate:

- `switch`
- `check(level="dry-activate")`

Not `generations` (no flake ref). Not `build`, `diff`,
`check("lint"|"dry-build")`, `eval_config`, `locate_option`.

Run the classifier **before** `switch(validate=True)`'s dry-build
preflight so a rejected target does not pay for a build.

**Local ref.** After splitting on `#`, the directory part must be a
filesystem path, not a flake URL. Reject (prefix / shape):

- `github:`, `gitlab:`, `sourcehut:`, `git+`, `http://`, `https://`,
  `ssh://`, `flake:`

Expand `~`. Reject relative paths (including `.` and `..`) for these
two operations: the MCP server's cwd is usually some other project.
Require an absolute path (after `~` expansion) whose realpath is a
directory containing `flake.nix`.

Compare pin and request with `os.path.realpath` on both sides so
`/pin/../pin`, trailing slashes, and symlinks do not false-reject or
false-allow.

**Pin (anti-footgun).**

- NixOS mode: if `$NIX_AGENT_FLAKE` is set, the resolved directory
  must equal that pin's directory. Attribute-only changes
  (`/same/dir#otherhost`) are allowed. A different directory returns
  `target_locked` naming the pin.
- Home Manager mode: if `$NIX_AGENT_HM_FLAKE` is set, lock to that
  pin the same way. **Do not** fall back to `$NIX_AGENT_FLAKE` for
  this lock. A machine with only the NixOS pin must still be able to
  `switch(..., mode="home-manager")` against a local standalone HM
  flake. (Resolution fallback for *finding* a flake when `flake_uri`
  is omitted stays as it is; only the lock ignores the NixOS pin.)
- HM `switch` is not root, but it still activates. Remote refs are
  still rejected. Directory lock only applies when the HM pin is set.

**Remote refs.** `status: "remote_ref_rejected"`. Hint: clone locally
and pin. **Do not** mention `NIX_AGENT_ALLOW_REMOTE` in the tool
envelope; the reader is the agent. Document the escape hatch for
humans in `privileged-automation.md` only.

**Escape hatch.** `NIX_AGENT_ALLOW_REMOTE=1` (same truthy set as the
usage log) skips the remote-ref rejection. It does not skip
`target_locked`. Off by default.

Do not silently rewrite a `flake_uri` to the pin. Reject and explain.

**Sudoers narrowing.** When a flake directory is known (module option
or installer-recorded `FLAKE_DIR`), the NOPASSWD `nixos-rebuild`
rules are:

- `dry-activate --flake <flake_dir>*`
- `switch --flake <flake_dir>*`

not `--flake *`. Untargeted `--rollback` and the profile
`switch-to-configuration` / `nix-env --switch-generation` rules do
not take a flake ref and stay as in change 1.

If no flake directory is configured, do not emit `--flake *`
NOPASSWD rules. Tell the user to set the path or skip privileged
automation.

### Acceptance

- `switch(flake_uri="github:example/nixos#host")` →
  `remote_ref_rejected`, no sudo, hint does not mention
  `NIX_AGENT_ALLOW_REMOTE`.
- With `NIX_AGENT_FLAKE=/home/me/nixos#laptop`,
  `switch(flake_uri="/tmp/other#host")` → `target_locked`.
- Same pin, `switch(flake_uri="/home/me/nixos#other")` proceeds.
- Same pin, `switch(flake_uri="/home/me/.config/home-manager#me", mode="home-manager")` proceeds (NixOS pin does not lock HM).
- `eval_config(..., flake_uri="github:example/nixos#host")` is not
  rejected by nix-agent.
- `NIX_AGENT_ALLOW_REMOTE=1` lets the github ref through to
  `nixos-rebuild` unless a pin also conflicts.
- `switch(validate=True, flake_uri="github:...")` does not run
  dry-build.
- `target_locked`, `remote_ref_rejected`, `unknown_generation` omit
  byte accounting and are listed with the other early exits in usage
  and the skill.

## 3. Installer stops auto-allowing activation

### Problem

Step 7 auto-allows all seven MCP tools, including `switch` and
`generations`, without asking. It also allows
`Bash(sudo nixos-rebuild switch --flake *)`. With step 8's NOPASSWD
rule, an agent denied the MCP tool shells out and activates any flake
with no host prompt, no sudo prompt, and no classifier from change 2.

### Spec

**Default MCP allow** (apply without asking):

- `mcp__nix-agent__build`
- `mcp__nix-agent__diff`
- `mcp__nix-agent__eval_config`
- `mcp__nix-agent__locate_option`
- `mcp__nix-agent__check`

**Default Bash allow:** do **not** include `nixos-rebuild switch`,
`dry-activate`, or `switch --rollback`. Those are the bypass.

**Ask, default no,** whether to allow unprompted activation:

- `mcp__nix-agent__switch`
- `mcp__nix-agent__generations`
- matching Bash `sudo nixos-rebuild` forms, narrowed to `FLAKE_DIR`
  as in change 2 (not `*`)

This is a separate question from step 8 (passwordless sudo). Unprompted
non-interactive switch needs both yeses.

Rewrite the intent paragraph. It must not say "the seven nix-agent
MCP tools." `tests/test_public_content.py` currently asserts that
phrase and that every `mcp__nix-agent__<tool>` appears *somewhere* in
the file; change the test to parse the **default allow JSON block**
and fail if `switch` or `generations` are in it. Mentions in the
optional-ask section are fine.

Step 8 sudo snippet uses the narrowed `--flake <FLAKE_DIR>*` forms
plus the change 1 `nix-env` / profile `switch-to-configuration`
rules. Prefer `programs.nix-agent.privilegedAutomation` (change 6)
over a pasted `extraRules` block when the module is already imported.

### Acceptance

- Default allow JSON block in `docs/agent-install.md` does not
  contain `mcp__nix-agent__switch`, `mcp__nix-agent__generations`, or
  `Bash(sudo nixos-rebuild switch`.
- A test parses that block, not a whole-file substring.
- Step 8 still asks about sudo; the activation-allow question is
  separate and defaults to no.

## 4. Batched `eval_config` status reflects total failure

Unchanged from the draft, except the skill mentions it.

- All attrs ok → `ok`
- Mix → `ok`, failures in `results`
- Every attr failed → `failed`, `results` unchanged,
  `first_error` from the first failed entry that has one

Do not change lint-with-findings or switch-with-newly-failed-units.

## 5. Tests lock the envelopes that matter

Expand `tests/snapshots/tool_envelopes.json` (same `_schema` helper)
to include representative shapes for:

- `switch` success with `summary.units`, `summary.health`,
  `rollback_generation`
- `switch` failure with `privilege`
- `switch` failure with `failed_derivation`
- `diff` success with `packages`
- `locate_option` success with `definitions`
- `generations` list success (NixOS entries include `path`)
- `unknown_generation`, `target_locked`, `remote_ref_rejected`

**Live fixture.** `python-tests` CI has no Nix; a check derivation
cannot talk to the daemon. Do not put live eval in pytest-on-GitHub
Python or inside `pytestCheckHook`.

Add `tests/fixtures/tiny-flake/` with **no inputs**: a stub
`nixosConfigurations.fixture.config.networking.hostName = "fixture"`.
In the `nix-flake-check` CI job, as a **plain step after**
`nix flake check` (outside a derivation), run `nix eval` of the
quoted installable nix-agent would build
(`...#nixosConfigurations."fixture".config.networking.hostName --json`).
That locks quoting. Do not eval a full NixOS module system. Do not
run `switch` in CI.

## 6. Follow-ups in this implementation

**`check("dry-activate")` privilege diagnosis.** Share `_sudo_diagnosis`
(move to `runner.py` or a tiny `privilege.py`) and attach it on
dry-activate sudo auth failure, same as `switch` and rollback.

**`inspect-flake` HM classification.** Lock-file presence alone is
not `"integrated"`.

- `homeConfigurations` non-empty → `"standalone"`
- `flake.nix` text contains `home-manager.nixosModules` or
  `home-manager.users` → `"integrated"`
- else if `home-manager` is in the lock → `"unknown"`
- else → `"none"`

Init skill: write a hard mode rule only for `"integrated"` or
`"standalone"`. For `"unknown"`, say the facts were inconclusive.

**`locate_option` docs.** Earns its slot as "which file sets this."
The measured `environment.systemPackages` case is 24 KB → 20 KB.
Say that. Do not promise a firehose cap the per-entry guard does not
provide.

**NixOS module.** Keep it from writing MCP host config or skills.
Add:

- `programs.nix-agent.flake` (null or path): wraps the binary with
  `NIX_AGENT_FLAKE` set. This is the pin that does not live in
  agent-editable `.mcp.json`.
- `programs.nix-agent.privilegedAutomation.enable` (default false):
  emits the sudoers rules from changes 1–2, narrowed to
  `programs.nix-agent.flake` when that is set. Refuse to enable
  `--flake *` if flake is unset (assert or `mkIf` with a warning and
  no rebuild/switch flake rules).

Installer step 8 should prefer these options.

**nix-darwin.** Out of scope. Drop `darwin` and `modules/darwin` from
`MODULE_DIR_CANDIDATES`. One sentence in usage.

**Byte accounting off the hot path.** Deferred. `event_from_call`
reads those fields off the envelope; removing them without a new
channel also blanks the usage log. Do not do this in this pass.

## Suggested order

1. Change 3 (installer / Bash allow) **with** change 1. Targeted
   rollback makes `generations` more powerful; do not leave it
   auto-allowed.
2. Change 2 (classifier + sudoers narrowing) in the same pass as 1
   and 3: one sudoers story, one installer story.
3. Change 4 (batched eval). Independent.
4. Change 5 (snapshots + tiny-flake CI step).
5. Change 6 items listed above, except deferred byte accounting.

## Out of scope

- In-MCP approval prompts, diffs-as-approval, or `switch(confirm=)`.
- Restoring a `format` tool, or putting `inspect-flake` back on MCP.
- Merging with `mcp-nixos`.
- Mandatory `check` → `diff` → `switch`.
- Removing `build`.
- nix-darwin support.
- Teaching the NixOS module to write Claude/Codex/opencode MCP config.
- Live `switch` in CI.
- Changing lint-with-findings or switch-with-newly-failed-units
  away from `ok`.
- Removing `raw_bytes` / `returned_bytes` from envelopes (deferred).

## Residual risks (accepted)

- A local pin does not make the pinned tree trusted. The agent edits
  those files.
- `build` and `diff` of a remote ref still evaluate Nix and run
  sandboxed builders. Only activation/dry-activate are locked.
- `NIX_AGENT_ALLOW_REMOTE` and the pin in `.mcp.json` are
  agent-editable. The module wrapper pin is the harder-to-reach copy.
- Two-step NixOS targeted rollback can move the profile pointer and
  then fail activation. The envelope must say so.
