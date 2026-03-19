from unittest.mock import Mock, patch

from nix_agent.system_apply import run_dry_activate


@patch("nix_agent.system_apply.subprocess.run")
def test_run_dry_activate_returns_stdout(mock_run: Mock):
    mock_run.return_value.stdout = "ok"
    mock_run.return_value.stderr = ""

    result = run_dry_activate("/etc/nixos#host")

    assert result == "ok"
