# Privileged Automation

`nix-agent` can run fully non-interactively only if the host allows the exact `nixos-rebuild` commands it uses to run through `sudo` without prompting.

Recommended approach: allowlist only these commands for the local trusted user:

- `nixos-rebuild dry-activate --flake ...`
- `nixos-rebuild switch --flake ...`

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
    ];
  }
];
```

This is intentionally broader than manual approval and should only be used on a trusted local machine.
