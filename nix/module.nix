{ self }:
{
  config,
  lib,
  pkgs,
  ...
}:

let
  cfg = config.programs.nix-agent;
  flakeDir = if cfg.flake == null then null else lib.removeSuffix "/" (toString cfg.flake);
  wrappedPackage =
    if flakeDir == null then
      cfg.package
    else
      pkgs.runCommand "${cfg.package.pname or "nix-agent"}-pinned"
        {
          nativeBuildInputs = [ pkgs.makeWrapper ];
          meta = cfg.package.meta or { };
        }
        ''
          mkdir -p $out/bin
          makeWrapper ${cfg.package}/bin/nix-agent $out/bin/nix-agent \
            --set NIX_AGENT_FLAKE ${lib.escapeShellArg flakeDir}
        '';
  nixosRebuild = "${pkgs.nixos-rebuild}/bin/nixos-rebuild";
  nixEnv = "${pkgs.nix}/bin/nix-env";
  profileSwitch = "/nix/var/nix/profiles/system/bin/switch-to-configuration switch";
  generationCommands = [
    {
      command = "${nixosRebuild} switch --rollback";
      options = [ "NOPASSWD" ];
    }
    {
      command = "${nixEnv} -p /nix/var/nix/profiles/system --switch-generation *";
      options = [ "NOPASSWD" ];
    }
    {
      command = profileSwitch;
      options = [ "NOPASSWD" ];
    }
  ];
  flakeCommands = lib.optionals (flakeDir != null) [
    {
      command = "${nixosRebuild} dry-activate --flake ${flakeDir}*";
      options = [ "NOPASSWD" ];
    }
    {
      command = "${nixosRebuild} switch --flake ${flakeDir}*";
      options = [ "NOPASSWD" ];
    }
  ];
in
{
  options.programs.nix-agent.enable = lib.mkEnableOption "install the nix-agent MCP server package";

  options.programs.nix-agent.package = lib.mkOption {
    type = lib.types.package;
    default = self.packages.${pkgs.system}.default;
    defaultText = lib.literalExpression "inputs.nix-agent.packages.\${pkgs.system}.default";
    description = "Package that provides the nix-agent MCP server.";
  };

  options.programs.nix-agent.flake = lib.mkOption {
    type = lib.types.nullOr lib.types.path;
    default = null;
    example = lib.literalExpression "/home/alice/nixos";
    description = ''
      Absolute filesystem path of the config flake working tree. When set,
      the module wraps the nix-agent binary so NIX_AGENT_FLAKE is in its
      environment. This pin is an anti-footgun for privileged activation,
      not a security boundary.
    '';
  };

  options.programs.nix-agent.privilegedAutomation.enable = lib.mkEnableOption ''
    passwordless sudo for nix-agent dry-activate, switch, and rollback.
    Off by default. When programs.nix-agent.flake is set, nixos-rebuild
    dry-activate/switch rules are narrowed to that directory. When flake
    is unset, only rollback and generation-switch rules are emitted;
    flake dry-activate/switch still need a pin
  '';

  options.programs.nix-agent.privilegedAutomation.user = lib.mkOption {
    type = lib.types.str;
    example = "alice";
    description = ''
      User granted NOPASSWD for nix-agent privileged operations.
      Required when programs.nix-agent.privilegedAutomation.enable is true.
    '';
  };

  config = lib.mkIf cfg.enable {
    environment.systemPackages = [ wrappedPackage ];

    warnings = lib.optionals (cfg.privilegedAutomation.enable && cfg.flake == null) [
      ''
        programs.nix-agent.privilegedAutomation.enable is true but
        programs.nix-agent.flake is unset. Passwordless nixos-rebuild
        dry-activate/switch from a flake are omitted until the flake
        directory is pinned. Rollback and generation-switch rules are
        still emitted.
      ''
    ];

    security.sudo.extraRules = lib.mkIf cfg.privilegedAutomation.enable [
      {
        users = [ cfg.privilegedAutomation.user ];
        commands = generationCommands ++ flakeCommands;
      }
    ];
  };
}
