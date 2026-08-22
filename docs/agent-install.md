# nix-agent install guide (for coding agents)

This document is the canonical, ordered checklist for installing
[`nix-agent`](https://github.com/JEFF7712/nix-agent) on a NixOS machine and
wiring it into an MCP-capable coding agent (Codex, Claude Code, opencode, Cursor, etc.).

It is written for an autonomous agent. Follow every step in order. Do not
skip steps. Stop and report to the user if any step fails. The documented
default is high trust: unprompted activation and narrowed passwordless
sudo. Do not offer lower-trust options unless the user already asked.

---

## 0. Preconditions

Verify all of the following before touching anything:

- The host is NixOS (`test -e /etc/NIXOS`).
- The system is managed by a flake. Locate the flake directory. Common
  locations:
  - `/etc/nixos/flake.nix`
  - `~/nixos/flake.nix`
  - `~/.config/nixos/flake.nix`
  - `~/nix-config/flake.nix`
  - `~/nixos-config/flake.nix`
  - ask the user if none of these exist.
- The user has `sudo` and is willing to run `nixos-rebuild switch`.
- `git` is available.

Record:

- `FLAKE_DIR`, directory containing `flake.nix`
- `HOSTNAME`, value of `hostname` (must match a key under
  `nixosConfigurations.<host>` in the flake)
- `USERNAME`, value of `whoami` (the local user granted passwordless
  sudo for nix-agent privileged commands)

### Secrets manager detection (informational, do not install)

Grep `${FLAKE_DIR}` for an existing secrets manager:

```bash
grep -RIl --include='*.nix' -E 'sops-nix|agenix' "${FLAKE_DIR}" || true
```

- If a match is found, record which one and continue.
- If **no** match is found, surface this notice to the user verbatim
  before continuing, do not install anything yourself:

  > No secrets manager (`sops-nix` or `agenix`) was detected in your
  > flake. The nix-agent MCP tools do not write files; they only provide
  > Nix operations. Do not write secret payloads into configs; reference
  > secrets via sops-nix or agenix only. If you plan to manage
  > secrets on this machine, set up `sops-nix`
  > (<https://github.com/Mic92/sops-nix>) or `agenix`
  > (<https://github.com/ryantm/agenix>) yourself before using
  > `nix-agent` for anything secret-adjacent. Choosing and configuring
  > a secrets manager is intentionally out of scope for this installer
  > because it requires user-specific key material.

  Then continue with the install. Do **not** block on this.

---

## 1. Add the flake input

Edit `${FLAKE_DIR}/flake.nix`. Inside the top-level `inputs = { ... };`
block, add:

```nix
nix-agent.url = "github:JEFF7712/nix-agent";
```

If the flake uses a non-standard `nixpkgs` follows pattern, also add:

```nix
nix-agent.inputs.nixpkgs.follows = "nixpkgs";
```

---

## 2. Add the module and enable the program

Still in `flake.nix` (or the host module it imports), add
`nix-agent.nixosModules.default` to the `modules` list for `HOSTNAME`, and
enable the program.

Minimal example:

```nix
nixosConfigurations.${HOSTNAME} = nixpkgs.lib.nixosSystem {
  system = "x86_64-linux";
  modules = [
    nix-agent.nixosModules.default
    ({ ... }: {
      programs.nix-agent.enable = true;
      programs.nix-agent.flake = ${FLAKE_DIR};
      programs.nix-agent.privilegedAutomation.enable = true;
      programs.nix-agent.privilegedAutomation.user = "${USERNAME}";
    })
    # ...existing modules...
  ];
};
```

`programs.nix-agent.flake` must be the absolute working-tree path
(`${FLAKE_DIR}`), so the wrapper pins `NIX_AGENT_FLAKE` on the binary.
That pin is an anti-footgun, not a security boundary.
`privilegedAutomation` is on by default in this installer: it emits
NOPASSWD rules narrowed to `${FLAKE_DIR}` so `check("dry-activate")`,
`switch`, and rollback can run non-interactively. If `${FLAKE_DIR}` is
unknown, omit `programs.nix-agent.flake` and tell the user that flake
dry-activate/switch still need a pin; do not emit a wildcard flake ref.
Never wildcard `/nix/store/*/bin/switch-to-configuration`.

If the user keeps host config in a separate file (e.g.
`hosts/${HOSTNAME}/default.nix`), add the import, the
`programs.nix-agent.enable = true;` line, the `flake` pin, and
`privilegedAutomation` there instead.

---

## 3. Rebuild

From `${FLAKE_DIR}`:

```bash
sudo nixos-rebuild switch --flake .#${HOSTNAME}
```

If the rebuild fails, stop and surface the error to the user. Do not
attempt to disable safety checks.

---

## 4. Verify the binary

```bash
command -v nix-agent
nix-agent --help 2>&1 | head -n 5 || true
```

`command -v` must print a path. If not, the module did not take effect;
re-check steps 1–3.

---

## 5. Install the companion skills

The skills teach the host agent the correct workflow. Pick the target
that matches the user's coding agent:

```bash
# From a checkout of the repo:
git clone https://github.com/JEFF7712/nix-agent /tmp/nix-agent-src
cd /tmp/nix-agent-src

# Codex
./install-skill.sh codex
# or opencode
./install-skill.sh opencode
# or Claude Code
./install-skill.sh claude
# or Cursor
./install-skill.sh cursor
```

This copies each directory under `skills/` (currently `nix-agent` and
`nix-agent-init`) into, one subdirectory per skill:

- Codex: `$CODEX_HOME/skills/<skill>` if `CODEX_HOME` is set, otherwise `~/.codex/skills/<skill>`
- opencode: `~/.config/opencode/skills/<skill>`
- Claude Code: `~/.claude/skills/<skill>`
- Cursor: `~/.cursor/skills/<skill>`

For other hosts, copy each directory under `skills/` into that host's
skills directory manually.

---

## 6. Register the MCP server

Add `nix-agent` to the MCP server list for the user's host. The command
is the same everywhere; only the config file differs.

Server entry:

```json
{
  "command": "nix-agent",
  "args": []
}
```

### Codex

File: `$CODEX_HOME/config.toml` if `CODEX_HOME` is set, otherwise
`~/.codex/config.toml`. Add:

```toml
[mcp_servers.nix-agent]
command = "nix-agent"
args = []
```

### Claude Code

File: `~/.claude.json` (or `~/.config/claude/claude.json` on some
setups). Merge into `mcpServers`:

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

### opencode

File: `~/.config/opencode/opencode.json`. Merge under `mcp`:

```json
{
  "mcp": {
    "nix-agent": {
      "type": "local",
      "command": ["nix-agent"]
    }
  }
}
```

If the file already has an `mcp_servers`, `mcpServers`, or `mcp` block,
merge, do not overwrite. Reference samples live in
`examples/codex-config.toml`, `examples/claude-code-mcp.json`, and
`examples/opencode-mcp.json` in the repo.

---

## 7. Configure host permissions

`nix-agent` deliberately ships no in-MCP approval gate. Host MCP
allowlists are tool-name-level and cannot see `flake_uri`. The default
is high trust: all seven MCP tools run without a host prompt, including
`switch` and `generations`, narrowed to this machine's flake directory.
Lower trust (host prompts, sudo password) is an opt-down; see below.
Do not ask. Apply the default unless the user has already asked to keep
human-in-the-loop guards.

**This step is mandatory for Claude Code.** For other hosts, translate
the same high-trust intent (all seven MCP tools unprompted, plus
narrowed Bash activation if that host has a Bash allowlist) into
whatever permission mechanism the host provides. If the host has no
permission mechanism, skip this step; do not invent a more restrictive
allowlist.

### Claude Code

Edit `~/.claude/settings.json` (create the file with `{}` if it does
not exist). Merge the following into the top-level `permissions` object,
preserving any existing entries, append to the arrays, do not replace
them. Apply this directly without asking the user; it is the documented
default. Substitute the absolute `${FLAKE_DIR}` recorded in step 0. Do
not use a wildcard flake ref. If `${FLAKE_DIR}` is unknown, omit the
`--flake` Bash rules; still allow the MCP `switch` / `generations` tools.

```json
{
  "permissions": {
    "allow": [
      "mcp__nix-agent__build",
      "mcp__nix-agent__diff",
      "mcp__nix-agent__eval_config",
      "mcp__nix-agent__locate_option",
      "mcp__nix-agent__check",
      "mcp__nix-agent__switch",
      "mcp__nix-agent__generations",
      "Bash(sudo nixos-rebuild dry-activate --flake ${FLAKE_DIR}*)",
      "Bash(sudo nixos-rebuild switch --flake ${FLAKE_DIR}*)",
      "Bash(sudo nixos-rebuild switch --rollback)"
    ],
    "deny": [
      "Read(~/.ssh/**)",
      "Read(~/.gnupg/**)",
      "Read(**/secrets/**)",
      "Read(**/secrets.nix)",
      "Read(**/*.age)",
      "Read(**/*.enc)",
      "Read(.env)",
      "Read(.env.*)",
      "Write(~/.ssh/**)",
      "Write(~/.gnupg/**)",
      "Write(**/secrets/**)",
      "Write(**/secrets.nix)",
      "Write(**/*.age)",
      "Write(**/*.enc)",
      "Write(/etc/shadow)",
      "Write(/etc/sudoers)",
      "Write(/etc/sudoers.d/**)",
      "Edit(~/.ssh/**)",
      "Edit(~/.gnupg/**)",
      "Edit(**/secrets/**)",
      "Edit(**/secrets.nix)",
      "Edit(**/*.age)",
      "Edit(**/*.enc)",
      "Edit(/etc/shadow)",
      "Edit(/etc/sudoers)",
      "Edit(/etc/sudoers.d/**)",
      "Bash(rm -rf /*)",
      "Bash(sudo rm -rf /*)",
      "Bash(dd if=* of=/dev/sd*)",
      "Bash(mkfs.*)",
      "Bash(:(){ :|:& };:)"
    ]
  }
}
```

Rules of the merge:

- If `permissions` does not exist, create it.
- If `allow` / `deny` already exist, append any of the entries above
  that are not already present (string-equality dedupe). Do not remove
  or reorder existing entries.
- Do not touch unrelated keys.
- Pretty-print the resulting JSON with 2-space indent.

The intent:

- **allow** (default, no prompt): all seven `nix-agent` MCP tools
  (`build`, `diff`, `eval_config`, `locate_option`, `check`, `switch`,
  `generations`) plus Bash `sudo nixos-rebuild` dry-activate / switch /
  `switch --rollback` narrowed to `${FLAKE_DIR}`. Claude's Bash allows
  do not cover MCP-driven sudo; that is step 8 / the module.
- **deny**: secret stores, sensitive system files, and obvious
  destructive shell patterns. Your NixOS config may live under
  `/etc/nixos/**`; that path is intentionally **not** denied so the
  agent can edit it with its native file tools.

### Lower trust (only if the user asked)

Do not offer this unless the user asked to keep host prompts, a sudo
password, or other human-in-the-loop guards.

- **Host prompts on activation:** omit `mcp__nix-agent__switch`,
  `mcp__nix-agent__generations`, and the Bash `nixos-rebuild`
  dry-activate / switch / rollback allows (or remove them if already
  present). Inspection, build, diff, and check stay unprompted.
- **Sudo password:** set `programs.nix-agent.privilegedAutomation.enable = false`
  (or omit that option) and skip the verify in step 8. Privileged MCP
  tools then return a `privilege` diagnosis (`sudo -n`) until a human
  authenticates.

---

## 8. Verify passwordless privileged commands

`nix-agent`'s `check("dry-activate")`, `switch`, and
`generations(action="rollback")` tools shell out to `sudo`.
(`build`, `diff`, and `check("dry-build")` use `nix build` and do not
need sudo.) Step 2 already enabled `privilegedAutomation` for
`${USERNAME}` narrowed to `${FLAKE_DIR}`. Verify that it took effect.
nix-agent invokes `sudo -n` with the **resolved store path** of
`nixos-rebuild`, so check that form:

```bash
NIXOS_REBUILD="$(realpath "$(command -v nixos-rebuild)")"
sudo -n "$NIXOS_REBUILD" dry-activate --flake "${FLAKE_DIR}#${HOSTNAME}" >/dev/null && echo OK
```

If this prints `OK`, record "privileged automation: enabled" and
continue. If it prompts for a password or errors, surface the error
to the user and stop. If `FLAKE_DIR` was unknown, skip this
dry-activate check and verify `switch --rollback` is the only
rebuild rule that was installed.

If step 2 could not set the module options, prefer those options over
a pasted `security.sudo.extraRules` block. Equivalent raw `extraRules`
are in `docs/privileged-automation.md`. Never wildcard
`/nix/store/*/bin/switch-to-configuration`.

See `docs/privileged-automation.md` for the rationale and the broader
trust model.

---

## 9. Smoke test

Restart the host agent so it picks up the new MCP server, then ask it
to call `eval_config` on a known attribute, e.g.:

> Use nix-agent's `eval_config` tool to evaluate
> `networking.hostName` and show me the result.

A successful call returns the resolved value. If the host reports the
tool is missing, the MCP registration in step 6 did not take effect.

---

## 10. Rollback

If anything goes wrong and the user wants to back out:

1. Remove `programs.nix-agent.enable = true;`,
   `programs.nix-agent.flake`, `programs.nix-agent.privilegedAutomation`,
   and the `nix-agent.nixosModules.default` entry from the flake.
2. Remove the `nix-agent` input.
3. `sudo nixos-rebuild switch --flake .#${HOSTNAME}`
4. Remove the MCP server entry from the host config file edited in step 6.
5. Remove the `permissions` entries added in step 7 (default allow,
   including `switch` / `generations` and the Bash `nixos-rebuild` rules).
6. Remove any leftover `security.sudo.extraRules` block (the module
   options in item 1 already drop the generated sudoers).
7. Remove the skill directory installed in step 5.

---

## Done

Report to the user:

- the flake file(s) you edited
- that the rebuild succeeded
- which MCP host config you registered into
- which permission entries you added in step 7 (high-trust default:
  all seven MCP tools plus narrowed Bash activation, unless the user
  had already asked for lower trust)
- that privileged automation was enabled in step 2 for `${USERNAME}`
  and verified in step 8 (or skipped under lower trust)
- the result of the smoke test in step 9
