# nix-agent usage

`nix-agent` is a local stdio MCP server that gives AI agents composable
NixOS / Home Manager operations: build, diff, switch, and generations for the
operational core, plus eval, locate, and check for config introspection. It
works alongside [`mcp-nixos`](https://github.com/utensils/mcp-nixos):
nix-agent operates on your actual configuration; `mcp-nixos` handles package
and option discovery.

## What you get

- a runnable stdio MCP server
- a Nix flake package and app (wrapper bundles statix/deadnix/nixfmt/nvd)
- a NixOS module at `nixosModules.default`
- companion agent skills in `skills/nix-agent/` (workflow) and `skills/nix-agent-init/` (onboarding)
- example MCP host configs in `examples/`

The packaged wrapper supplies `statix`, `deadnix`, `nixfmt`, and `nvd`.

The host must supply Nix and the commands needed by the operations it uses:
`nixos-rebuild` for NixOS, `home-manager` for standalone Home Manager,
`sudo` for privileged activation, and `systemctl`/`journalctl` for
post-activation health reporting and logs.

Commands time out after 30 minutes by default. Set
`NIX_AGENT_COMMAND_TIMEOUT` to a positive number of seconds to override that
limit; an unset, invalid or nonpositive value falls back to the 30-minute
default.

## Install

Add the flake input and module to your NixOS config:

```nix
{
  inputs.nix-agent.url = "github:JEFF7712/nix-agent";

  outputs = { nixpkgs, nix-agent, ... }: {
    nixosConfigurations.my-host = nixpkgs.lib.nixosSystem {
      system = "x86_64-linux";
      modules = [
        nix-agent.nixosModules.default
        ({ ... }: {
          programs.nix-agent.enable = true;
        })
      ];
    };
  };
}
```

Then rebuild:

```bash
sudo nixos-rebuild switch --flake .#my-host
```

That installs the `nix-agent` binary.

Prefer to let an agent do it? See [agent-install.md](agent-install.md) for the
one-shot install prompt.

## MCP host config

Point your MCP host at:

```json
{
  "mcpServers": {
    "nix-agent": {
      "command": "nix-agent",
      "args": []
    }
  }
}
```

See `examples/codex-config.toml`, `examples/claude-code-mcp.json`, and
`examples/opencode-mcp.json`.

## Companion skills

The MCP exposes the tools; the skills teach the correct workflow. The
installer copies every directory under `skills/` (the `nix-agent` workflow
skill and the `nix-agent-init` onboarding skill) into your agent's skill
directory:

```bash
./install-skill.sh codex
./install-skill.sh opencode
./install-skill.sh claude
```

## Tool surface

All tools auto-resolve the target when `flake_uri` is omitted. Resolution
order: `$NIX_AGENT_FLAKE` (for Home Manager: `$NIX_AGENT_HM_FLAKE`, falling
back to `$NIX_AGENT_FLAKE`), then the first existing `flake.nix` among
`/etc/nixos`, `~/nixos`, `~/.config/nixos`, `~/nix-config`, `~/nixos-config`
for NixOS (`~/.config/home-manager`, `~/.config/nixpkgs` for Home Manager).
The hostname / `user@host` attribute is picked automatically. Single-command
results echo back `resolved_target` and the exact `command` run. Exceptions:
a batched `eval_config` folds its per-attr commands into `results`;
`check("lint")` returns `commands` (the statix and deadnix argv list)
instead of a single `command`.

`mode` defaults to `"nixos"`. Use `"home-manager"` only for a **standalone** HM
flake (its own `homeConfigurations`, applied with `home-manager switch`). When
HM is integrated as a NixOS module (built into the system closure), keep
`mode="nixos"` and switch the whole system, there is no separate HM switch. On
a machine that has both a NixOS flake and a leftover `~/.config/home-manager`
flake, pin the target with `$NIX_AGENT_FLAKE` or an explicit `flake_uri` so
resolution can't pick the wrong one. See `skills/nix-agent/SKILL.md` for the
full mode-selection guidance.

The surface is two tiers. The **operational core** produces structured
operational signal and rollback safety that ad-hoc shell cannot reproduce
reliably. **Config introspection** tools each earn their slot by capping or
structuring Nix output the host would otherwise pay for in raw context.

Operational core:

| Tool | What it does |
|------|-------------|
| `build(flake_uri?, mode?)` | Build the closure, no activation. A failed build carries `failed_derivation` (`{drv, log_tail}`). |
| `diff(flake_uri?, mode?)` | What a switch would change (package adds/removes/version bumps). Also returns a structured `packages` object alongside the human-readable diff, when the diff output parses: `added` and `removed` entries are `{name, version}`, `changed` entries are `{name, old, new}`. Show this to the user before switching. |
| `switch(flake_uri?, mode?, validate?, full_log?)` | Activate. Records `rollback_generation`. Returns a structured `summary` (units changed, derivations built, a `packages` object with package-level changes vs the rollback generation, and a `health` object with systemd units that newly failed, resolved, or are still failing after activation) and trims the log to a tail on success (`full_log=True` for all of it). `validate=True` gates on `check("dry-build")` first; a sudo auth failure returns a `privilege` diagnosis. |
| `generations(action="list"\|"rollback", mode?)` | List or roll back generations. |

Config introspection:

| Tool | What it does |
|------|-------------|
| `eval_config(attr, flake_uri?, mode?)` | Final merged value of any config attribute on this machine (after all modules/overlays). `mcp-nixos` tells you what an option means; this tells you what it resolves to. `attr` also takes a list, evaluating each in one call and returning per-attr `results`. Values above ~2 KB degrade to attr names / length / a head slice with `truncated: true`. |
| `locate_option(attr, flake_uri?, mode?)` | Where this configuration sets an option: `declarations` (files declaring it) and `definitions` (`{file, value}` entries, one per file defining it; large values degrade under the same size guard as `eval_config`, marked `truncated: true` per entry). For non-options, `status` is `not_an_option`. For integrated Home Manager, spell the attr `home-manager.users.<user>.<attr>` with `mode="nixos"`. |
| `check(level, flake_uri?, mode?)` | Validation ladder, fast to slow: `"lint"` (statix + deadnix, structured `findings` list), `"dry-build"`, `"dry-activate"` (NixOS only). |

Repo onboarding is a CLI subcommand, not a runtime tool: `nix-agent
inspect-flake [flake_uri]` prints structured facts about a config repo as JSON
(`hosts`, `home_configurations`, integrated-vs-standalone Home Manager
(`hm_integration`), `module_dirs`, `auto_import` mechanism, `formatter`,
`lint_tools`, and justfile/CI/`.mcp.json` presence). Evaluated facts become
`null` or `"unknown"` when flake-show fails; repository layout, auto-import,
and integrated Home Manager detection are best-effort presence/absence
heuristics that may reflect unreadable or unmatched files as absence. The
`skills/nix-agent-init/` skill invokes it during onboarding.

`summary.health` reports post-activation unit status and is success-only by
design: a switch that leaves units newly failed still returns `status: "ok"`
(activation succeeded), with the failures surfaced in
`summary.health.newly_failed` for the agent to act on. Each newly failed unit
carries a `log_tail` (last 20 journal lines); to stay compact under mass
failures, only the first 5 newly failed units (sorted) include a tail, the
rest list the unit name alone. When systemctl probing is unavailable, a
top-level `health_note` replaces `summary.health`.

## Basic workflow

1. Discovery: query `mcp-nixos` for packages/options; use `eval_config` to see what the user's machine currently resolves.
2. Edit `.nix` files with the agent's native file tools (Read/Edit/Write).
3. Format with the flake's formatter (`nix fmt`, or `nixfmt` on the edited files) then `check("lint")`, fix findings worth fixing.
4. `check("dry-build")`, catches eval/build errors cheaply.
5. `diff()`, show the user what will change.
6. `switch()`, activate; reports `rollback_generation`.
7. On regret: `generations(action="rollback")`.

Steps 3–5 are judgment calls, not gates. For a trivial change, going straight
to `switch` is fine.

### Onboarding a repo

First time in an unfamiliar config? Run `nix-agent inspect-flake` once to get
its hosts, HM mode, module layout, and tooling in one shot, then hand those
facts to the `skills/nix-agent-init/` skill. It generates `AGENT_MAP.md`,
`CLAUDE.md` (+ an `AGENTS.md` symlink), and a `.mcp.json`, all derived from
what `inspect-flake` actually observed, never boilerplate. Re-runs only touch
the marked sections it owns, and it refuses to clobber a hand-written file
that lacks its marker, proposing a diff instead.

### Failure envelopes

On failure, the response carries the full log plus:

- `first_error`: the first actionable error line from Nix's output. Present on failure envelopes produced through the standard path (most failures).
- `error_detail`: `{message, file, line, column, trace}` when the output matched Nix's eval-error shape, a direct file:line:column edit target. Omitted otherwise.
- `failed_derivation`: on a failed build, diff, or switch, `{drv, log_tail}` with the last 40 lines of the failing builder's `nix log` (or `{drv, note}` when the log is unavailable). Omitted when the failure has no failing derivation (a pure eval error or a sudo auth failure, for example).

`switch(validate=True)` is a special case: if the dry-build preflight fails, the
envelope status is `preflight_failed` (not `failed`), with the check result
nested under `preflight` and no activation attempted.

The command runner truncates each stdout and stderr stream independently at
64,000 Python characters. A successful `switch` is more compact: it returns a
2,000-character tail of the activation log by default. Pass `full_log=True` to
return the full successful switch log, still subject to the runner's
per-stream limit.

### Byte accounting

Every response that ran a command carries `raw_bytes` and `returned_bytes`
so the token savings are visible per call, not just claimed (early-exit
statuses listed below are the exception):

- `raw_bytes` is the underlying command output size (combined
  stdout+stderr, in bytes, before any truncation). Tools whose work is
  several co-equal runs sum them: `check("lint")` sums statix+deadnix,
  batched `eval_config` sums the per-attr evals. Tools with auxiliary probes
  count only the primary operation: `switch`'s post-activation
  health/diff probes are not included.
- `returned_bytes` is the serialized size of the envelope actually handed
  back, computed last, and excludes the ~30 bytes of the two accounting
  fields themselves.
- Early-exit statuses
  (`no_target`, `invalid_attr`, `invalid_action`, `invalid_level`,
  `not_an_option`, `tool_missing`, `not_applicable`, `preflight_failed`)
  omit both `raw_bytes` and `returned_bytes`.

### Measured on a real config

Captured 2026-07-07 on a NixOS laptop, Nix 2.34, running real read-only
operations against a live config (`/home/rupan/nixos#laptop`):

| Operation | raw bytes | returned bytes | note |
|---|---|---|---|
| `diff` | 338 | 1431 | the underlying package diff was tiny (one internal package removed); envelope metadata and the structured `packages` breakout dominate on a near-empty diff, the win grows with the diff |
| `eval_config("environment.systemPackages")` | 13,500 | 394 | the raw value is a huge list of store paths; the size guard collapses it to a length + head slice instead of returning it whole |
| `locate_option("environment.systemPackages")` | 24,066 | 20,396 | 95 defining files, each already close to its per-entry size guard; savings here are modest because the option is genuinely defined in many places |

`switch` carries the same `raw_bytes`/`returned_bytes` pair on its envelope;
its log is trimmed to a tail on success by design, so the win there tracks
the same shape as the numbers above rather than a fifth number worth
quoting in isolation.

The failure path shows a different kind of win, not a smaller
`returned_bytes` (failure envelopes keep the full output on purpose, so
`returned_bytes` can exceed `raw_bytes`): building a scratch flake with a
builder that does `exit 1` gave `raw_bytes: 7187`, `returned_bytes: 7975`,
and a populated `failed_derivation: {drv: ".../boom.drv", log_tail:
"failing to build\n"}`. That field is the actual saving: it names the one
failing `.drv` and its last log line directly, instead of the agent running
a separate `nix log` and scanning a much longer derivation log by hand.

## Design notes

- The nix-agent MCP tools do no file editing or formatting. Use the host
  agent's own file tools for reading and editing `.nix` files, and the flake's
  formatter (`nix fmt` / `nixfmt`) to format them. The one reader is the
  `nix-agent inspect-flake` CLI subcommand, which reads flake metadata and
  repository layout for its best-effort onboarding inspection.
- No in-MCP approval gates. Path restrictions belong to the host's
  permission system; rollback safety belongs to Nix generations.
- Responses that resolve a target and run one command echo
  `resolved_target` and the exact `command` run, so nothing is silently
  implicit. Multi-command tools differ by design: a batched `eval_config`
  reports the resolved target once with individual commands folded into
  its per-attr `results`; `check("lint")` returns `commands` for the two
  linters.
- Do not write secret payloads into configs, reference secrets via
  sops-nix or agenix.
- Fully non-interactive NixOS dry-activate, switch, and rollback require
  privileged automation; see
  [privileged-automation.md](privileged-automation.md). Standalone Home
  Manager activation does not use sudo.
