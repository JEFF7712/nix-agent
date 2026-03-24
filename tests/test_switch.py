from unittest.mock import Mock, patch

from nix_agent.system_apply import run_switch


@patch("nix_agent.system_apply.subprocess.run")
def test_run_switch_returns_stdout(mock_run: Mock):
    mock_run.return_value.stdout = "switched"
    mock_run.return_value.stderr = ""

    result = run_switch("/etc/nixos#host")

    assert result == "switched"
