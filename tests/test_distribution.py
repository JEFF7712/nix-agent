from pathlib import Path


def test_flake_exports_package_app_and_nixos_module():
    flake_text = Path("flake.nix").read_text()

    assert "packages.default" in flake_text
    assert "apps.default" in flake_text
    assert "meta.description" in flake_text
    assert "nixosModules.default" in flake_text
    assert "checks.default" in flake_text


def test_flake_package_wraps_nixpkgs_fmt_for_runtime():
    flake_text = Path("flake.nix").read_text()

    assert "makeWrapper" in flake_text
    assert "nixpkgs-fmt" in flake_text
    assert "wrapProgram" in flake_text


def test_nixos_module_exposes_enable_option():
    module_text = Path("nix/module.nix").read_text()

    assert "programs.nix-agent.enable" in module_text
    assert "environment.systemPackages" in module_text


def test_ci_workflow_runs_pytest():
    workflow_text = Path(".github/workflows/ci.yml").read_text()

    assert "pytest" in workflow_text
    assert "nix build .#default" in workflow_text
    assert "nix flake check" in workflow_text
    assert "pull_request" in workflow_text
    assert "push" in workflow_text


def test_opencode_example_uses_packaged_binary():
    example_text = Path("examples/opencode-mcp.json").read_text()

    assert '"command": "nix-agent"' in example_text
