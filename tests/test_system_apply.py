from unittest.mock import Mock, patch

import subprocess

from nix_agent.system_apply import CommandResult, run_dry_activate, run_switch


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


@patch("nix_agent.system_apply.subprocess.run")
def test_run_dry_activate_adds_privileged_automation_hint(mock_run: Mock):
    mock_run.side_effect = subprocess.CalledProcessError(
        1,
        ["sudo", "nixos-rebuild", "dry-activate", "--flake", "/etc/nixos#host"],
        stderr="sudo: a terminal is required to read the password\nsudo: a password is required",
    )

    result = run_dry_activate("/etc/nixos#host")

    assert result.ok is False
    assert "Privileged automation is not configured" in result.output
    assert "sudoers" in result.output


@patch("nix_agent.system_apply.os.path.realpath")
@patch("nix_agent.system_apply.shutil.which")
@patch("nix_agent.system_apply.subprocess.run")
def test_run_dry_activate_uses_resolved_nixos_rebuild_path(
    mock_run: Mock, mock_which: Mock, mock_realpath: Mock
):
    mock_which.return_value = "/run/current-system/sw/bin/nixos-rebuild"
    mock_realpath.return_value = "/nix/store/abc/bin/nixos-rebuild"
    mock_run.return_value.stdout = "ok"
    mock_run.return_value.stderr = ""

    run_dry_activate("/etc/nixos#host")

    mock_run.assert_called_once_with(
        [
            "sudo",
            "/nix/store/abc/bin/nixos-rebuild",
            "dry-activate",
            "--flake",
            "/etc/nixos#host",
        ],
        check=True,
        capture_output=True,
        text=True,
    )


@patch("nix_agent.system_apply.os.path.realpath")
@patch("nix_agent.system_apply.shutil.which")
@patch("nix_agent.system_apply.subprocess.run")
def test_run_switch_uses_resolved_nixos_rebuild_path(
    mock_run: Mock, mock_which: Mock, mock_realpath: Mock
):
    mock_which.return_value = "/run/current-system/sw/bin/nixos-rebuild"
    mock_realpath.return_value = "/nix/store/abc/bin/nixos-rebuild"
    mock_run.return_value.stdout = "switched"

    result = run_switch("/etc/nixos#host")

    assert result == "switched"
    mock_run.assert_called_once_with(
        [
            "sudo",
            "/nix/store/abc/bin/nixos-rebuild",
            "switch",
            "--flake",
            "/etc/nixos#host",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
