# Privileged Automation

`nix-agent` can run fully non-interactively on NixOS only if the host allows
the exact `nixos-rebuild` commands it uses to run through `sudo` without
prompting. nix-agent invokes sudo with the **resolved store path** of
`nixos-rebuild`, so NOPASSWD rules must match that argv form (as in the
example below). Standalone Home Manager mode does not use sudo.

Recommended approach: allowlist only these commands for the local trusted user:

- `nixos-rebuild dry-activate --flake ...`
- `nixos-rebuild switch --flake ...`
- `nixos-rebuild switch --rollback`

(`build`, `diff`, and `check("dry-build")` use `nix build` and do not need sudo.)

Example NixOS config:

```nix
security.sudo.extraRules = [
  {
    users = [ "rupan" ];
    commands = [
      {
        command = "${pkgs.nixos-rebuild}/bin/nixos-rebuild dry-activate --flake *";
        options = [ "NOPASSWD" ];
      }
      {
        command = "${pkgs.nixos-rebuild}/bin/nixos-rebuild switch --flake *";
        options = [ "NOPASSWD" ];
      }
      {
        command = "${pkgs.nixos-rebuild}/bin/nixos-rebuild switch --rollback";
        options = [ "NOPASSWD" ];
      }
    ];
  }
];
```

This is intentionally broader than manual approval and should only be used on a trusted local machine.
