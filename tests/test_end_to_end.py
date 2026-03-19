from unittest.mock import Mock, patch

from nix_agent.server import apply_change_workflow


@patch("nix_agent.server.run_switch")
@patch("nix_agent.server.run_dry_activate")
@patch("nix_agent.server.classify_change")
def test_apply_change_workflow_switches_allowed_change(
    mock_classify: Mock, mock_dry: Mock, mock_switch: Mock
):
    mock_classify.return_value.policy_decision = "allowed"
    mock_classify.return_value.approval_required = False
    mock_classify.return_value.reason = "no blacklist match"
    mock_dry.return_value = "dry ok"
    mock_switch.return_value = "switch ok"

    result = apply_change_workflow(
        "add waybar cava",
        ["/home/user/.config/waybar/config.jsonc"],
        "/etc/nixos#host",
    )

    assert result.approval_required is False
    assert result.apply_result == "switch ok"
