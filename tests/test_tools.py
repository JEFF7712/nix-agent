from nix_agent.server import build_server


def test_build_server_registers_expected_tools():
    server = build_server()
    tool_names = {tool.name for tool in server._tools.values()}

    assert "inspect_state" in tool_names
    assert "plan_change" in tool_names
    assert "apply_change" in tool_names
    assert "get_operation_result" in tool_names


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
