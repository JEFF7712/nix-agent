# Privileged Automation

The documented default for autonomous use is passwordless sudo for the
narrow nix-agent commands, scoped to one user and one flake directory.
nix-agent invokes `sudo -n` with the **resolved store path** of
`nixos-rebuild` and `nix-env`, so a missing NOPASSWD rule fails
immediately with a `privilege` diagnosis instead of hanging on a
password prompt. NOPASSWD rules must match that argv form (the command
after `sudo -n`, as in the examples below). Standalone Home Manager mode
does not use sudo.

To lower trust (sudo password, or host prompts on activation), see
[Lower trust](#lower-trust). Do not grant a wildcard flake ref.

`$NIX_AGENT_FLAKE` (and the module option that wraps it into the binary) is
an **anti-footgun**, not a security boundary. The agent can still edit the
pinned tree and, if it can edit MCP config, the pin in `.mcp.json`. The
privilege boundary that actually runs as root is sudoers. Narrow those rules
to the pinned flake directory. Do not grant a wildcard flake ref.

The autonomous install enables this. Prefer the NixOS module over a
pasted `extraRules` block when `nixosModules.default` is already imported:

```nix
programs.nix-agent.enable = true;
programs.nix-agent.flake = /home/alice/nixos; # absolute working-tree path
programs.nix-agent.privilegedAutomation.enable = true;
programs.nix-agent.privilegedAutomation.user = "alice";
```

When `programs.nix-agent.flake` is set, the module wraps the binary so
`NIX_AGENT_FLAKE` is in its environment, and emits NOPASSWD rules narrowed
to that directory. When privileged automation is enabled but `flake` is
unset, the module emits only rollback / generation-switch rules (no
rebuild or switch from a flake). Set the flake path, or skip privileged
automation; do not widen the flake argument.

## Commands to allow

Allowlist only these commands for the local trusted user.

Flake-scoped (only when the flake directory is known; substitute that
absolute path, no trailing slash):

- `nixos-rebuild dry-activate --flake <flake_dir>*`
- `nixos-rebuild switch --flake <flake_dir>*`

Generation / rollback (no flake ref):

- `nixos-rebuild switch --rollback`
- `nix-env -p /nix/var/nix/profiles/system --switch-generation *`
- `/nix/var/nix/profiles/system/bin/switch-to-configuration switch`

(`build`, `diff`, and `check("dry-build")` use `nix build` and do not need sudo.)

Activate through the **profile path**
(`/nix/var/nix/profiles/system/bin/switch-to-configuration`). Never grant
NOPASSWD on a store-path binary, and never write a sudoers wildcard over
`/nix/store/*/bin/switch-to-configuration`.

## Equivalent `extraRules`

If you are wiring sudoers by hand instead of
`programs.nix-agent.privilegedAutomation`, the same narrowed rules look
like this. Replace `/home/alice/nixos` with the real flake directory.

```nix
security.sudo.extraRules = [
  {
    users = [ "alice" ];
    commands = [
      {
        command = "${pkgs.nixos-rebuild}/bin/nixos-rebuild dry-activate --flake /home/alice/nixos*";
        options = [ "NOPASSWD" ];
      }
      {
        command = "${pkgs.nixos-rebuild}/bin/nixos-rebuild switch --flake /home/alice/nixos*";
        options = [ "NOPASSWD" ];
      }
      {
        command = "${pkgs.nixos-rebuild}/bin/nixos-rebuild switch --rollback";
        options = [ "NOPASSWD" ];
      }
      {
        command = "${pkgs.nix}/bin/nix-env -p /nix/var/nix/profiles/system --switch-generation *";
        options = [ "NOPASSWD" ];
      }
      {
        command = "/nix/var/nix/profiles/system/bin/switch-to-configuration switch";
        options = [ "NOPASSWD" ];
      }
    ];
  }
];
```

If the flake directory is unknown, omit the two `--flake` rebuild/switch
rules entirely. Keep only `--rollback`, `nix-env --switch-generation`, and
the profile `switch-to-configuration` rule.

This is intentionally broader than per-command host prompts and is the
default for a trusted local machine. It is not a reason to widen the
flake argument or to wildcard `/nix/store/*/bin/switch-to-configuration`.

## Lower trust

Keep `programs.nix-agent.enable` and the flake pin. Then:

- **Sudo password:** omit `programs.nix-agent.privilegedAutomation` (the
  Nix option defaults to off) or set `enable = false`. Privileged MCP
  tools fail fast with `privilege` (`sudo -n`) until a human authenticates.
- **Host prompts on activation:** omit `switch` / `generations` (and
  matching Bash `nixos-rebuild` switch / dry-activate / rollback) from
  the host allow list. See [agent-install.md](agent-install.md) § Lower
  trust. Do this only when the user asked for human-in-the-loop guards.

## Remote flake refs (humans only)

Privileged MCP tools (`switch` and `check("dry-activate")`) reject remote
flake refs (`github:`, `git+`, `https://`, …) and, when a pin is set, refuse
a different local directory (`target_locked`). That classifier is an
anti-footgun so the MCP server is not the confused-deputy path to root
activation. It does not make the pinned tree trusted.

`NIX_AGENT_ALLOW_REMOTE=1` (same truthy set as `NIX_AGENT_USAGE_LOG`:
`1` / `true` / `yes` / `on`) skips the remote-ref rejection only. It does
not skip `target_locked`. Off by default. Set it yourself in the MCP
server environment if you understand the trust decision; do not ask an
agent to enable it, and do not put it in tool-envelope hints.
