{ self }:
{ config, lib, pkgs, ... }:

let
  cfg = config.programs.nix-agent;
in {
  options.programs.nix-agent.enable = lib.mkEnableOption "install the nix-agent MCP server package";

  options.programs.nix-agent.package = lib.mkOption {
    type = lib.types.package;
    default = self.packages.${pkgs.system}.default;
    defaultText = lib.literalExpression "inputs.nix-agent.packages.${pkgs.system}.default";
    description = "Package that provides the nix-agent MCP server.";
  };

  config = lib.mkIf cfg.enable {
    environment.systemPackages = [ cfg.package ];
  };
}
