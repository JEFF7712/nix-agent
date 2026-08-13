# Implementation plan

This file assigns work, names argv and statuses, and lists files. Do
not invent a different NixOS activation mechanism.

TDD: write or extend the failing tests first, then the code.

Do not commit. Do not bump the package version. Add a `CHANGELOG.md`
entry under a new `## Unreleased` heading.

## Shared contracts

### New early-exit statuses

`unknown_generation`, `target_locked`, `remote_ref_rejected`

Shape: `{status, error, ...}` with no `command`, no `output`, no
`raw_bytes` / `returned_bytes`. Add them to the early-exit lists in
`docs/usage.md` and `skills/nix-agent/SKILL.md`.

`target_locked` also includes `pin` (the env value).
`remote_ref_rejected` hint must not mention `NIX_AGENT_ALLOW_REMOTE`.

### Privilege object

Move `_sudo_diagnosis` from `src/nix_agent/tools/switch.py` to
`src/nix_agent/privilege.py` (or `runner.py` if a new module feels
heavy). Use it from `switch`, NixOS `generations` rollback, and
`check("dry-activate")`.

### NixOS targeted rollback argv

```
sudo <realpath nix-env> -p /nix/var/nix/profiles/system --switch-generation <id>
sudo /nix/var/nix/profiles/system/bin/switch-to-configuration switch
```

Never `sudo /nix/store/.../bin/switch-to-configuration`.

Untargeted NixOS rollback stays:

```
sudo <realpath nixos-rebuild> switch --rollback
```

### Classifier

New helpers in `src/nix_agent/target.py`:

- `is_remote_flake_ref(dir_part: str) -> bool`
- `constrain_privileged_target(target, *, mode) -> dict | None`
  returns an early-exit envelope or `None` to proceed.

`NIX_AGENT_ALLOW_REMOTE` uses the same truthy set as
`NIX_AGENT_USAGE_LOG`.

Pin lock: NixOS uses `NIX_AGENT_FLAKE` only. HM uses
`NIX_AGENT_HM_FLAKE` only (no fallback to the NixOS pin for locking).
Resolution when `flake_uri` is omitted still falls back as today.

---

## Workstream A — core Python

Own: `src/nix_agent/**`, tool unit tests, envelope snapshot test.

Do not edit `docs/agent-install.md`, `docs/privileged-automation.md`,
`nix/module.nix`, or `skills/**` except if a test import requires it
(it should not).

### A1. Privilege helper

- Add `src/nix_agent/privilege.py` with `sudo_diagnosis(argv, output)`.
- Point `switch` at it. Add the same attachment on NixOS rollback
  failure and `check("dry-activate")` failure.
- Tests in `tests/test_switch_generations.py` and `tests/test_check.py`.

### A2. Generation list paths + targeted rollback

`src/nix_agent/tools/switch.py`:

- `_list_nixos` / `_list_nixos_nix_env`: add `path` =
  `os.path.realpath(f"/nix/var/nix/profiles/system-{id}-link")` when
  that path exists.
- `generations(action, mode="nixos", generation=None)`.
- Resolve `generation` against the list (id, profile path, realpath).
- No match → `unknown_generation`.
- Targeted NixOS: the two-step argv above. If step 1 fails, skip step
  2. If step 1 ok and step 2 fails, include
  `current_generation` and a `note`.
- Untargeted NixOS: `--rollback` plus `privilege` on sudo failure.
- Targeted HM: activate matched `path`. Untargeted HM: previous, as
  today.

Tests (`tests/test_switch_generations.py`), monkeypatch filesystem
links if needed (`tmp_path` + patched `SYSTEM_PROFILE` or a helper
that builds the path):

- list includes `path`
- targeted id / store-path / profile-path all select gen 41, not
  `--rollback`
- unknown generation: no `run` calls that sudo
- sudo-no-tty on untargeted and targeted rollback → `privilege`
- HM targeted by id and by path
- two-step: step 1 fail → step 2 not run
- two-step: step 1 ok, step 2 fail → `note` present

Update `src/nix_agent/server.py` `generations` description to mention
`generation` and that bare rollback is previous-only.

### A3. Local-target constraint

`src/nix_agent/target.py` helpers as above.

Call `constrain_privileged_target` at the start of `switch` (before
validate/dry-build) and of `check` when `level == "dry-activate"`
(after resolving the target, before sudo).

Tests in `tests/test_target.py` and `tests/test_switch_generations.py`
/ `tests/test_check.py`:

- github ref → `remote_ref_rejected`, no sudo
- pin lock → `target_locked`
- same dir, different attr → proceeds
- NixOS pin does not lock HM switch
- `NIX_AGENT_ALLOW_REMOTE=1` allows github unless pin conflicts
- relative `.` → rejected for privileged ops
- `~/nixos` expands and realpaths
- `switch(validate=True)` on a remote ref does not call `check`

### A4. Batched eval

`src/nix_agent/tools/eval.py`: if every batched result is failed,
top-level `status: "failed"` and `first_error` from the first failed
entry that has one.

Keep partial success as `ok`.

Test in `tests/test_eval_config.py`.

### A5. inspect-flake HM + darwin dirs

`classify_hm`: change signature as needed. Lock file alone →
`"unknown"`, not `"integrated"`. Integrated only when flake.nix text
has `home-manager.nixosModules` or `home-manager.users`.

Drop `darwin` and `modules/darwin` from `MODULE_DIR_CANDIDATES`.

Update `tests/test_inspect_flake.py` (`test_hm_integration_classification`
and `test_inspect_flake_integrated_hm` — the latter must put the
stronger signal in `flake.nix`, not only the lock).

### A6. Envelope snapshots

Extend `tests/test_envelope_schemas.py` and
`tests/snapshots/tool_envelopes.json` with the shapes listed in spec
§5. Reuse existing monkeypatches from `test_switch_generations.py` /
`test_build_diff.py` / `test_locate_option.py`. Include the three new
early exits.

---

## Workstream B — docs, installer, module, skills

Own: `docs/**` except this plan. `skills/**`, `nix/module.nix`,
`flake.nix` wrapper only if the module
needs a new option plumbed through the package, `CHANGELOG.md`,
`CLAUDE.md`, `tests/test_public_content.py`, `tests/test_distribution.py`.

Do not change tool Python except `nix/module.nix` / flake packaging.

### B1. Privileged automation doc

Rewrite `docs/privileged-automation.md`:

- Narrow `--flake <flake_dir>*` not `*`
- Add nix-env `--switch-generation` and profile
  `switch-to-configuration` rules
- Never wildcard `/nix/store/*/bin/switch-to-configuration`
- Document `NIX_AGENT_ALLOW_REMOTE` here only, as a human trust
  decision
- State that the pin is an anti-footgun; sudoers is the root boundary
- Point at `programs.nix-agent.privilegedAutomation`

### B2. Agent install

`docs/agent-install.md` step 7–8 per spec §3. Default allow JSON
block: five MCP tools, no Bash switch/dry-activate/rollback.

Ask (default no) for unprompted activation MCP + narrowed Bash.

Step 8: prefer module options; pasted sudoers must match B1.

Fix every sentence that says "the seven nix-agent MCP tools" in the
permissions intent.

### B3. Usage, skill, CLAUDE.md, init skill

- Tool table: `generations(..., generation?)`
- Workflow: pass `rollback_generation` into rollback
- Early-exit list includes the three new statuses
- Batched eval all-failed → `failed`
- `locate_option` slot justification (which file, not a cap); mention
  the 24 KB → 20 KB case
- nix-darwin out of scope
- Safety model paragraph: host allowlists cannot see `flake_uri`;
  privileged tools reject remote refs and honor the pin as an
  anti-footgun; sudoers must be narrowed; rollback takes `generation`
- Init skill: hard HM mode rule only for integrated/standalone; unknown
  stays inconclusive
- `skills/nix-agent/TESTING.md` rollback walkthrough uses targeted
  generation

### B4. NixOS module

`nix/module.nix`:

```nix
programs.nix-agent.flake          # nullOr path, default null
programs.nix-agent.privilegedAutomation.enable  # bool, default false
programs.nix-agent.privilegedAutomation.user    # str, default config.users.users that... 
```

Keep `user` simple: a string option, required when privileged
automation is enabled (no silent default to "rupan").

When `flake != null`, wrap the package (or use
`environment.variables.NIX_AGENT_FLAKE` plus a wrapped extra package)
so the MCP binary sees the pin. Wrapping via `cfg.package` override in
the module is enough; do not have to change `flake.nix` if the module
can `pkgs.symlinkJoin` / `wrapProgram`.

When `privilegedAutomation.enable`:

- if `flake != null`, emit narrowed nixos-rebuild rules plus nix-env
  and profile switch-to-configuration
- if `flake == null`, emit only `--rollback`, nix-env
  `--switch-generation`, and profile switch-to-configuration (no
  `--flake *` rebuild/switch rules). Document that dry-activate/switch
  from a flake still need a pin.

Use `${pkgs.nixos-rebuild}` and `${pkgs.nix}/bin/nix-env` (or
`pkgs.nix-env` if that attr exists — it is `pkgs.nix`).

### B5. Content tests

Rewrite `test_agent_install_matches_current_tool_surface_and_sudo_needs`
so it:

- parses the default allow JSON block in agent-install.md
- asserts the five tools are in it
- asserts `switch` and `generations` are not in that block
- asserts no `Bash(sudo nixos-rebuild switch` in that block
- still allows those strings in the optional-ask section
- drops the assertion `"the seven \`nix-agent\` MCP tools" in install`

Update `test_distribution.py` for new module option names.

`CHANGELOG.md`: `## Unreleased` summarizing the user-visible contract.

---

## Workstream C — tiny-flake CI step

Own: `tests/fixtures/tiny-flake/`, `.github/workflows/ci.yml`.

Do not put Nix calls in the `python-tests` job.

`tests/fixtures/tiny-flake/flake.nix`:

```nix
{
  description = "nix-agent quoting fixture; no inputs";
  outputs = { self }: {
    nixosConfigurations.fixture = {
      config.networking.hostName = "fixture";
    };
  };
}
```

CI `nix-flake-check` job, after `nix flake check`:

```bash
nix eval ./tests/fixtures/tiny-flake#nixosConfigurations.\"fixture\".config.networking.hostName --json
```

Expect `"fixture"`. This locks the quoted installable form.

Optional: `tests/test_fixture_quoting.py` that only asserts the
fixture file contains that attrpath shape, so python-tests still
guards the fixture without invoking Nix. Keep it small.

---

## Integration (parent agent)

After A, B, and C return:

1. `python -m pytest` in the repo (venv or nix develop).
2. Fix conflicts (docs vs tests vs snapshots).
3. Grep for stale claims: "rollback to the recorded generation",
   `--flake *`, "the seven `nix-agent` MCP tools",
   `classify_hm(True, []) == "integrated"`.
4. Do not commit unless asked.

## Out of this implementation

- Removing envelope byte accounting
- Live `switch` / full NixOS module eval in CI
- Version bump
