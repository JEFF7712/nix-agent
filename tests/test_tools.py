from pathlib import Path
from unittest.mock import Mock, patch

from nix_agent.models import Patch, PatchSet
from nix_agent.server import build_server
from nix_agent.system_apply import CommandResult


def test_build_server_registers_expected_tools():
    server = build_server()
    tool_names = {tool.name for tool in server._tools.values()}

    assert "inspect_state" in tool_names
    assert "plan_change" in tool_names
    assert "apply_change" in tool_names
    assert "get_operation_result" in tool_names
    assert "record_managed_root" not in tool_names


def test_classify_change_tool_contract():
    server = build_server()
    classify_tool = server._tools["classify_change"].fn
    result = classify_tool(
        changed_files=["etc/ssh/sshd_config"],
        operation="patch",
    )

    assert result["policy_decision"] == "blocked"
    assert result["approval_required"] is True
    assert result["reason"] == "SSH/auth changes require approval"
    assert result["risk_level"] == "high"
    assert result["matched_rules"] == ["auth-ssh"]


def test_apply_patch_set_tool_returns_structured_result(tmp_path: Path):
    server = build_server()
    apply_tool = server._tools["apply_patch_set"].fn
    patch_set = PatchSet(
        patches=[
            Patch(
                path=str(tmp_path / "unknown.conf"),
                content="value",
                reason="configure app",
            )
        ]
    )

    result = apply_tool(patch_set=patch_set)

    assert result["status"] == "applied"
    assert result["changed_files"] == [str(tmp_path / "unknown.conf")]
    assert set(result.keys()) == {"status", "changed_files"}


@patch("nix_agent.server.run_dry_activate")
def test_dry_activate_tool_returns_boolean_status(mock_dry: Mock):
    server = build_server()
    dry_tool = server._tools["dry_activate_system"].fn
    mock_dry.return_value = CommandResult(ok=True, output="dry ok")

    result = dry_tool(flake_uri="/etc/nixos#host")

    assert result == {
        "dry_activate_output": "dry ok",
        "validation_ok": True,
    }
