# nix-agent install guide (for coding agents)

This document is the canonical, ordered checklist for installing
[`nix-agent`](https://github.com/JEFF7712/nix-agent) on a NixOS machine and
wiring it into an MCP-capable coding agent (Claude Code, opencode, etc.).

It is written for an autonomous agent. Follow every step in order. Do not
skip steps. Stop and report to the user if any step fails.

---

## 0. Preconditions

Verify all of the following before touching anything:

- The host is NixOS (`test -e /etc/NIXOS`).
- The system is managed by a flake. Locate the flake directory. Common
  locations:
  - `/etc/nixos/flake.nix`
  - `~/nixos-config/flake.nix`
  - ask the user if neither exists.
- The user has `sudo` and is willing to run `nixos-rebuild switch`.
- `git` is available.

Record:

- `FLAKE_DIR` — directory containing `flake.nix`
- `HOSTNAME` — value of `hostname` (must match a key under
  `nixosConfigurations.<host>` in the flake)

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
    })
    # ...existing modules...
  ];
};
```

If the user keeps host config in a separate file (e.g.
`hosts/${HOSTNAME}/default.nix`), add the import and the
`programs.nix-agent.enable = true;` line there instead.

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

`command -v` must print a path. If not, the module did not take effect —
re-check steps 1–3.

---

## 5. Install the companion skill

The skill teaches the host agent the correct workflow. Pick the target
that matches the user's coding agent:

```bash
# From a checkout of the repo:
git clone https://github.com/JEFF7712/nix-agent /tmp/nix-agent-src
cd /tmp/nix-agent-src

# opencode
./install-skill.sh opencode
# or Claude Code
./install-skill.sh claude
```

This copies `skills/nix-agent/` into:

- opencode: `~/.config/opencode/skills/nix-agent`
- Claude Code: `~/.claude/skills/nix-agent`

For other hosts, copy `skills/nix-agent/` into that host's skills
directory manually.

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

If the file already has an `mcpServers` / `mcp` block, merge — do not
overwrite. Reference samples live in `examples/claude-code-mcp.json` and
`examples/opencode-mcp.json` in the repo.

---

## 7. Configure host permissions

`nix-agent` deliberately ships no in-MCP approval gate. Path
restrictions and command gating belong in the host's permission system.
Configure them now so the user gets a sane default without prompting on
every `nixos-rebuild` invocation.

**This step is mandatory for Claude Code.** For other hosts, translate
the same intent into whatever permission mechanism that host provides;
if no equivalent exists, skip.

### Claude Code

Edit `~/.claude/settings.json` (create the file with `{}` if it does
not exist). Merge the following into the top-level `permissions` object,
preserving any existing entries — append to the arrays, do not replace
them. Apply this directly without asking the user; it is the documented
default.

```json
{
  "permissions": {
    "allow": [
      "Bash(sudo nixos-rebuild dry-activate --flake *)",
      "Bash(sudo nixos-rebuild switch --flake *)",
      "Bash(sudo nixos-rebuild switch --rollback)",
      "mcp__nix-agent__inspect_state",
      "mcp__nix-agent__apply_patch_set"
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

- **allow**: the two `nixos-rebuild` commands `nix-agent` drives via
  sudo (so `apply_patch_set` does not prompt on every call), the
  rollback escape hatch, and the two `nix-agent` MCP tools themselves.
- **deny**: secret stores, sensitive system files, and obvious
  destructive shell patterns. `nix-agent` writes to `/etc/nixos/**` —
  that path is intentionally **not** denied.

---

## 8. Smoke test

Restart the host agent so it picks up the new MCP server, then ask it
to call `inspect_state` on a known file, e.g.:

> Use nix-agent's `inspect_state` tool to read `/etc/nixos/flake.nix`
> and show me the first few lines.

A successful call returns the file contents. If the host reports the
tool is missing, the MCP registration in step 6 did not take effect.

---

## 9. Rollback

If anything goes wrong and the user wants to back out:

1. Remove `programs.nix-agent.enable = true;` and the
   `nix-agent.nixosModules.default` entry from the flake.
2. Remove the `nix-agent` input.
3. `sudo nixos-rebuild switch --flake .#${HOSTNAME}`
4. Remove the MCP server entry from the host config file edited in step 6.
5. Remove the `permissions` entries added in step 7.
6. Remove the skill directory installed in step 5.

---

## Done

Report to the user:

- the flake file(s) you edited
- that the rebuild succeeded
- which MCP host config you registered into
- which permission entries you added in step 7
- the result of the smoke test in step 8
