{
  description = "MCP server and companion skill for local NixOS changes";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = import nixpkgs { inherit system; };
        lib = pkgs.lib;
        python = pkgs.python3;
        nix-agent-package = pkgs.python3Packages.buildPythonApplication {
          pname = "nix-agent";
          version = "0.1.2";
          format = "pyproject";
          src = ./.;
          nativeBuildInputs = with pkgs.python3Packages; [ setuptools wheel ] ++ [ pkgs.makeWrapper ];
          propagatedBuildInputs = with pkgs.python3Packages; [ fastmcp ];
          postFixup = ''
            wrapProgram "$out/bin/nix-agent" \
              --prefix PATH : "${lib.makeBinPath [ pkgs.nixpkgs-fmt ]}"
          '';
        };
      in {
        packages.default = nix-agent-package;

        checks.default = nix-agent-package;

        apps.default = {
          type = "app";
          program = "${nix-agent-package}/bin/nix-agent";
          meta.description = "Run the nix-agent stdio MCP server";
        };

        devShells.default = pkgs.mkShell {
          buildInputs = [
            python
            pkgs.python3Packages.pytest
            pkgs.nixpkgs-fmt
          ];
          shellHook = ''
            export PYTHONNOUSERSITE=0
            python -m pip install --break-system-packages --force-reinstall --upgrade --editable . pytest
          '';
        };
      })
    // {
      nixosModules.default = import ./nix/module.nix { inherit self; };
    };
}
