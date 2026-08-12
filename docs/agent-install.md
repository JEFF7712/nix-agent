# nix-agent install guide (for coding agents)

This document is the canonical, ordered checklist for installing
[`nix-agent`](https://github.com/JEFF7712/nix-agent) on a NixOS machine and
wiring it into an MCP-capable coding agent (Codex, Claude Code, opencode, Cursor, etc.).

It is written for an autonomous agent. Follow every step in order. Do not
skip steps. Stop and report to the user if any step fails.

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
    })
    # ...existing modules...
  ];
};
```

`programs.nix-agent.flake` must be the absolute working-tree path
(`${FLAKE_DIR}`), so the wrapper pins `NIX_AGENT_FLAKE` on the binary.
That pin is an anti-footgun, not a security boundary.

If the user keeps host config in a separate file (e.g.
`hosts/${HOSTNAME}/default.nix`), add the import, the
`programs.nix-agent.enable = true;` line, and the `flake` pin there
instead.

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
allowlists are tool-name-level and cannot see `flake_uri`. Configure
permissions now so inspection, build, diff, and check do not prompt,
while activation stays behind a host prompt unless the user opts in.

**This step is mandatory for Claude Code.** For other hosts, translate
the same intent into whatever permission mechanism that host provides;
if no equivalent exists, skip.

### Claude Code

Edit `~/.claude/settings.json` (create the file with `{}` if it does
not exist). Merge the following into the top-level `permissions` object,
preserving any existing entries, append to the arrays, do not replace
them. Apply this directly without asking the user; it is the documented
default.

```json
{
  "permissions": {
    "allow": [
      "mcp__nix-agent__build",
      "mcp__nix-agent__diff",
      "mcp__nix-agent__eval_config",
      "mcp__nix-agent__locate_option",
      "mcp__nix-agent__check"
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

- **allow** (default, no prompt): the read/build/diff/check MCP tools
  (`build`, `diff`, `eval_config`, `locate_option`, `check`). Do **not**
  auto-allow `switch`, `generations`, or Bash `sudo nixos-rebuild`
  dry-activate / switch / `switch --rollback`. Those are the activation
  bypass; they stay prompted unless the user opts in below.
- **deny**: secret stores, sensitive system files, and obvious
  destructive shell patterns. Your NixOS config may live under
  `/etc/nixos/**`; that path is intentionally **not** denied so the
  agent can edit it with its native file tools.

### Unprompted activation (ask, default no)

This is a separate question from passwordless sudo (step 8). Unprompted
non-interactive switch needs both yeses.

**Ask the user this question verbatim and wait for an answer:**

> By default I will still ask before activating or rolling back a NixOS
> generation (`switch` / `generations`, and matching `sudo nixos-rebuild`
> Bash commands). I can allow those without a host prompt, narrowed to
> this machine's flake directory. Passwordless sudo is a separate yes
> (next step). Allow unprompted activation? (yes / no, default no)

### If the user says no, or does not answer yes

- Record "unprompted activation: skipped".
- Do not add `mcp__nix-agent__switch`, `mcp__nix-agent__generations`, or
  Bash `nixos-rebuild` switch / dry-activate / rollback allows.
- Continue to step 8.

### If the user says yes

Append these entries to `permissions.allow` (string-equality dedupe),
substituting the absolute `${FLAKE_DIR}` recorded in step 0. Do not use
a wildcard flake ref.

```json
{
  "permissions": {
    "allow": [
      "Bash(sudo nixos-rebuild dry-activate --flake ${FLAKE_DIR}*)",
      "Bash(sudo nixos-rebuild switch --flake ${FLAKE_DIR}*)",
      "Bash(sudo nixos-rebuild switch --rollback)",
      "mcp__nix-agent__switch",
      "mcp__nix-agent__generations"
    ]
  }
}
```

If `${FLAKE_DIR}` is unknown, do not add the `--flake` Bash rules.
MCP-driven `switch` still needs passwordless sudo (step 8) to avoid a
sudo password hang inside the MCP server process; Claude's Bash allows
do not cover that.

---

## 8. Enable passwordless privileged commands (ask the user first)

`nix-agent`'s `check("dry-activate")`, `switch`, and
`generations(action="rollback")` tools shell out to `sudo`.
(`build`, `diff`, and `check("dry-build")` use `nix build` and do not
need sudo.) If the user has not configured passwordless sudo for those
exact commands, every privileged invocation will hang on a password
prompt the agent cannot answer.

This is a separate question from unprompted activation in step 7.

**Ask the user this question verbatim and wait for an answer:**

> nix-agent can run `nixos-rebuild dry-activate`, `nixos-rebuild
> switch`, `nixos-rebuild switch --rollback`, and targeted generation
> switch non-interactively if I add a narrow passwordless-sudo rule for
> just those commands (scoped to your user and this flake directory).
> Without it, every dry-activate, switch, or rollback will pause waiting
> for your sudo password. Do you want me to configure this now?
> (yes / no)

### If the user says no

- Record "privileged automation: skipped".
- Warn the user that `check("dry-activate")`, `switch`, and
  `generations(action="rollback")` will require them to enter their
  sudo password in the terminal where the MCP server runs, and continue
  to the next step.
- Do not edit anything.

### If the user says yes

1. Ask for `USERNAME` (default to `whoami` on the host).
2. Prefer the module options already imported in step 2 over a pasted
   `security.sudo.extraRules` block. Add (or extend) the same module
   snippet, substituting `${USERNAME}` and `${FLAKE_DIR}`:

   ```nix
   ({ ... }: {
     programs.nix-agent.enable = true;
     programs.nix-agent.flake = ${FLAKE_DIR};
     programs.nix-agent.privilegedAutomation.enable = true;
     programs.nix-agent.privilegedAutomation.user = "${USERNAME}";
   })
   ```

   That emits NOPASSWD rules narrowed to `${FLAKE_DIR}` for
   `dry-activate` / `switch`, plus `switch --rollback`,
   `nix-env -p /nix/var/nix/profiles/system --switch-generation *`,
   and `/nix/var/nix/profiles/system/bin/switch-to-configuration switch`.
   If `${FLAKE_DIR}` is unknown, omit `programs.nix-agent.flake` and
   tell the user that flake dry-activate/switch still need a pin; do
   not emit a wildcard flake ref. Never wildcard
   `/nix/store/*/bin/switch-to-configuration`.

   Equivalent raw `extraRules` (only if the module cannot be used) are
   in `docs/privileged-automation.md`.

3. Rebuild:

   ```bash
   sudo nixos-rebuild switch --flake .#${HOSTNAME}
   ```

4. Verify the rule took effect. nix-agent invokes sudo with the
   **resolved store path** of `nixos-rebuild`, so check that form:

   ```bash
   NIXOS_REBUILD="$(realpath "$(command -v nixos-rebuild)")"
   sudo -n "$NIXOS_REBUILD" dry-activate --flake "${FLAKE_DIR}#${HOSTNAME}" >/dev/null && echo OK
   ```

   If this prints `OK`, record "privileged automation: enabled" and
   continue. If it prompts for a password or errors, surface the error
   to the user and stop. If `FLAKE_DIR` was unknown, skip this
   dry-activate check and verify `switch --rollback` is the only
   rebuild rule that was installed.

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
5. Remove the `permissions` entries added in step 7 (default allow and
   any unprompted-activation allows).
6. Remove any leftover `security.sudo.extraRules` block from step 8
   (the module options in item 1 already drop the generated sudoers).
7. Remove the skill directory installed in step 5.

---

## Done

Report to the user:

- the flake file(s) you edited
- that the rebuild succeeded
- which MCP host config you registered into
- which permission entries you added in step 7, and whether unprompted
  activation was allowed (default no) or skipped
- whether passwordless privileged commands were enabled in step 8 (and
  for which user) or skipped
- the result of the smoke test in step 9
