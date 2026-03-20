from unittest.mock import Mock, patch

import subprocess

from nix_agent.system_apply import CommandResult, run_dry_activate


@patch("nix_agent.system_apply.subprocess.run")
def test_run_dry_activate_returns_stdout(mock_run: Mock):
    mock_run.return_value.stdout = "ok"
    mock_run.return_value.stderr = ""

    result = run_dry_activate("/etc/nixos#host")

    assert result == CommandResult(ok=True, output="ok")


@patch("nix_agent.system_apply.subprocess.run")
def test_run_dry_activate_returns_failed_result(mock_run: Mock):
    mock_run.side_effect = subprocess.CalledProcessError(
        1,
        ["sudo", "nixos-rebuild", "dry-activate", "--flake", "/etc/nixos#host"],
        stderr="build failed",
    )

    result = run_dry_activate("/etc/nixos#host")

    assert result == CommandResult(ok=False, output="build failed")
