{
  description = "MCP server and companion skills exposing composable NixOS and Home Manager operations";

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
        sourceFilter =
          _root: path: _type:
          let
            name = baseNameOf path;
          in
          !(
            builtins.elem name [
              ".git"
              ".direnv"
              ".mypy_cache"
              ".next"
              ".pytest_cache"
              ".ruff_cache"
              ".superpowers"
              ".venv"
              "__pycache__"
              "coverage"
              "node_modules"
              "out"
              "research_nextjs_static_3d"
              "research_nix_snowflake_ascii"
              "result"
            ]
            || lib.hasSuffix ".tsbuildinfo" name
          );
        cleanSource =
          root:
          lib.cleanSourceWith {
            src = root;
            filter = sourceFilter root;
          };
        packageSource = cleanSource ./.;
        siteSource = cleanSource ./site;
        nix-agent-package = pkgs.python3Packages.buildPythonApplication {
          pname = "nix-agent";
          version = "0.8.0";
          format = "pyproject";
          src = packageSource;
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
        sourceFilterContract =
          assert !(sourceFilter ./. "${./.}/research_nextjs_static_3d" "directory");
          assert !(sourceFilter ./. "${./.}/.venv" "directory");
          assert !(sourceFilter ./. "${./.}/.direnv" "directory");
          assert !(sourceFilter ./site "${./site}/node_modules" "directory");
          assert !(sourceFilter ./site "${./site}/coverage" "directory");
          assert !(sourceFilter ./site "${./site}/tsconfig.tsbuildinfo" "regular");
          assert sourceFilter ./site "${./site}/public/nix-snowflake.svg" "regular";
          assert sourceFilter ./site "${./site}/app/fonts/ibm-plex-mono-latin-400-normal.woff2" "regular";
          assert sourceFilter ./site "${./site}/__tests__/page.test.tsx" "regular";
          assert sourceFilter ./site "${./site}/pnpm-lock.yaml" "regular";
          assert sourceFilter ./. "${./.}/src/nix_agent/server.py" "regular";
          assert sourceFilter ./. "${./.}/tests/test_server.py" "regular";
          pkgs.runCommand "nix-agent-source-filter-contract" { } ''
            touch "$out"
          '';
        sitePnpmDeps = pkgs.fetchPnpmDeps {
          pname = "nix-agent-site";
          version = "0.1.0";
          src = siteSource;
          pnpm = pkgs.pnpm_11;
          fetcherVersion = 4;
          hash = "sha256-jv6vDHJadvFN/83et5EhAajW7VDearhst8mZ9xilox0=";
        };
        siteDocsInputs = pkgs.runCommand "nix-agent-site-docs-inputs" { } ''
          mkdir -p "$out/site" "$out/docs" "$out/assets"
          cp -a ${siteSource}/. "$out/site/"
          cp ${./README.md} "$out/README.md"
          cp ${./docs/usage.md} "$out/docs/usage.md"
          cp ${./docs/agent-install.md} "$out/docs/agent-install.md"
          cp ${./docs/privileged-automation.md} "$out/docs/privileged-automation.md"
          cp ${./assets/banner.png} "$out/assets/banner.png"
        '';
        siteCheck = pkgs.stdenvNoCC.mkDerivation {
          pname = "nix-agent-site-check";
          version = "0.1.0";
          src = siteDocsInputs;
          dontUnpack = true;
          pnpmDeps = sitePnpmDeps;
          CI = "true";
          NEXT_TELEMETRY_DISABLED = "1";
          nativeBuildInputs = [
            pkgs.nodejs_24
            pkgs.pnpm_11
            pkgs.pnpmConfigHook
          ];
          preConfigure = ''
            cp -a "$src/." repo
            chmod -R u+w repo
            export NIX_AGENT_REPO_ROOT="$PWD/repo"
            cd repo/site
          '';
          buildPhase = ''
            runHook preBuild
            pnpm lint
            pnpm test
            pnpm typecheck
            pnpm build
            runHook postBuild
          '';
          installPhase = ''
            runHook preInstall
            mkdir -p "$out"
            cp -r out "$out/site"
            runHook postInstall
          '';
        };
      in
      {
        packages.default = nix-agent-package;

        checks.default = nix-agent-package;
        checks.source-filter = sourceFilterContract;
        checks.site = siteCheck;

        apps.default = {
          type = "app";
          program = "${nix-agent-package}/bin/nix-agent";
          meta.description = "Run the nix-agent stdio MCP server";
        };

        devShells.default = pkgs.mkShell {
          buildInputs = [
            devPython
            pkgs.nodejs_24
            pkgs.pnpm_11
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
