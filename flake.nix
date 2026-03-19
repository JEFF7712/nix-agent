{
  description = "Scaffolding for nix-agent";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = import nixpkgs { inherit system; };
        python = pkgs.python311;
      in {
        devShells.default = pkgs.mkShell {
          buildInputs = [
            python
            pkgs.python311Packages.pytest
            pkgs.nixpkgs-fmt
          ];
          shellHook = ''
export PYTHONNOUSERSITE=0
python -m pip install --break-system-packages --force-reinstall --upgrade --editable . pytest
'';
        };
      });
}
