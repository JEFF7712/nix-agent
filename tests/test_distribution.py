from pathlib import Path


def test_flake_exports_package_app_and_nixos_module():
    flake_text = Path("flake.nix").read_text()

    assert "packages.default" in flake_text
    assert "apps.default" in flake_text
    assert "meta.description" in flake_text
    assert "nixosModules.default" in flake_text
    assert "checks.default" in flake_text
    assert "pytestCheckHook" in flake_text


def test_flake_package_wraps_lint_and_diff_tools_for_runtime():
    flake_text = Path("flake.nix").read_text()

    for tool in ("statix", "deadnix", "nixfmt", "nvd"):
        assert tool in flake_text


def test_dev_shell_does_not_pip_install_into_user_site():
    flake_text = Path("flake.nix").read_text()

    assert "fastmcp" in flake_text
    assert "PYTHONPATH" in flake_text
    assert "pip install" not in flake_text
    assert "PYTHONNOUSERSITE=1" in flake_text


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


def test_codex_example_uses_packaged_binary():
    example_text = Path("examples/codex-config.toml").read_text()

    assert 'command = "nix-agent"' in example_text
