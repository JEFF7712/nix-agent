from nix_agent.server import build_server


def test_build_server_registers_expected_tools():
    server = build_server()
    tool_names = {tool.name for tool in server._tools.values()}

    assert "inspect_state" in tool_names
    assert "plan_change" in tool_names
    assert "apply_change" in tool_names
    assert "get_operation_result" in tool_names
