{
  description = "MCP server and companion skill exposing composable NixOS operations";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs =
    {
      self,
      nixpkgs,
      flake-utils,
    }:
    flake-utils.lib.eachDefaultSystem (
      system:
      let
        pkgs = import nixpkgs { inherit system; };
        lib = pkgs.lib;
        python = pkgs.python3;
        nix-agent-package = pkgs.python3Packages.buildPythonApplication {
          pname = "nix-agent";
          version = "0.7.1";
          format = "pyproject";
          src = ./.;
          nativeBuildInputs =
            with pkgs.python3Packages;
            [
              setuptools
              wheel
            ]
            ++ [ pkgs.makeWrapper ];
          propagatedBuildInputs = with pkgs.python3Packages; [ fastmcp ];
          nativeCheckInputs = with pkgs.python3Packages; [ pytestCheckHook ];
          postFixup = ''
            wrapProgram "$out/bin/nix-agent" \
              --prefix PATH : "${
                lib.makeBinPath [
                  pkgs.statix
                  pkgs.deadnix
                  pkgs.nixfmt
                  pkgs.nvd
                ]
              }"
          '';
        };
        devPython = python.withPackages (
          ps: with ps; [
            fastmcp
            pytest
          ]
        );
      in
      {
        packages.default = nix-agent-package;

        checks.default = nix-agent-package;

        apps.default = {
          type = "app";
          program = "${nix-agent-package}/bin/nix-agent";
          meta.description = "Run the nix-agent stdio MCP server";
        };

        devShells.default = pkgs.mkShell {
          buildInputs = [
            devPython
            pkgs.statix
            pkgs.deadnix
            pkgs.nixfmt
            pkgs.nvd
          ];
          shellHook = ''
            export PYTHONNOUSERSITE=1
            export PYTHONPATH="$PWD/src''${PYTHONPATH:+:$PYTHONPATH}"
          '';
        };
      }
    )
    // {
      nixosModules.default = import ./nix/module.nix { inherit self; };
    };
}
