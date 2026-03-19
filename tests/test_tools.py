from pathlib import Path

from nix_agent.models import Patch, PatchSet
from nix_agent.server import build_server


def test_build_server_registers_expected_tools():
    server = build_server()
    tool_names = {tool.name for tool in server._tools.values()}

    assert "inspect_state" in tool_names
    assert "plan_change" in tool_names
    assert "apply_change" in tool_names
    assert "get_operation_result" in tool_names
    assert "record_managed_root" in tool_names


def test_classify_change_tool_contract():
    server = build_server()
    classify_tool = server._tools["classify_change"].fn
    result = classify_tool(
        changed_files=["etc/ssh/sshd_config"],
        operation="patch",
    )

    assert result["policy_decision"] == "blocked"
    assert result["approval_required"] is True
    assert result["reason"] == "matched approval blacklist"
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

    assert result["status"] == "approval_required"
    assert result["changed_files"] == []
    assert result["trust_proposals"]
    proposal = result["trust_proposals"][0]
    assert proposal["path"].endswith("unknown.conf")


def test_recorded_managed_root_retries_managed_patch(tmp_path: Path):
    server = build_server()
    assert "record_managed_root" in server._tools
    record_tool = server._tools["record_managed_root"].fn
    state_path = tmp_path / "managed-state.json"
    root = {
        "root": str(tmp_path),
        "allowed_operations": ["patch"],
        "allowed_file_patterns": ["*.json"],
    }

    recorded = record_tool(state_path=str(state_path), root=root)
    assert recorded["managed_state"]["managed_roots"][0]["root"] == str(tmp_path)
    assert state_path.exists()

    target = tmp_path / "config.json"
    patch_set = PatchSet(patches=[Patch(path=str(target), content="{}")])
    apply_tool = server._tools["apply_patch_set"].fn
    result = apply_tool(
        patch_set=patch_set,
        managed_state=recorded["managed_state"],
    )

    assert result["status"] == "applied"
    assert target.read_text() == "{}"
