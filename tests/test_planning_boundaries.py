from nix_agent.server import plan_change


def test_plan_change_marks_package_lookup_as_external_dependency():
    result = plan_change("install ripgrep")

    assert result["requires_mcp_nixos"] is True
    assert "package lookup" in result["notes"].lower()
