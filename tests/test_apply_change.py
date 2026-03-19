from unittest.mock import Mock, patch

from nix_agent.server import apply_change_workflow


@patch("nix_agent.server.run_dry_activate")
@patch("nix_agent.server.classify_change")
def test_apply_change_workflow_stops_when_approval_required(
    mock_classify: Mock, mock_dry: Mock
):
    mock_classify.return_value.policy_decision = "blocked"
    mock_classify.return_value.approval_required = True
    mock_classify.return_value.reason = "matched approval blacklist"

    result = apply_change_workflow(
        "update ssh config", ["/etc/nixos/ssh.nix"], "/etc/nixos#host"
    )

    assert result.approval_required is True
    assert result.apply_result is None


@patch("nix_agent.server.run_switch")
@patch("nix_agent.server.run_dry_activate")
@patch("nix_agent.server.classify_change")
def test_apply_change_workflow_calls_switch_when_allowed(
    mock_classify: Mock, mock_dry: Mock, mock_switch: Mock
):
    mock_classify.return_value.policy_decision = "allowed"
    mock_classify.return_value.approval_required = False
    mock_classify.return_value.reason = "proceed"
    mock_dry.return_value = "dry ok"
    mock_switch.return_value = "switched"

    result = apply_change_workflow(
        "update ssh config", ["/etc/nixos/ssh.nix"], "/etc/nixos#host"
    )

    mock_switch.assert_called_once_with("/etc/nixos#host")
    assert result.apply_result == "switched"
