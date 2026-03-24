from nix_agent.server import plan_change


def test_plan_change_marks_package_lookup_as_external_dependency():
    result = plan_change("install ripgrep")

    assert result["requires_mcp_nixos"] is True
    assert "package lookup" in result["notes"].lower()


def test_plan_change_marks_option_style_requests_as_external_dependency():
    result = plan_change("which setting enables openssh?")

    assert result["requires_mcp_nixos"] is True
    assert "option discovery" in result["notes"].lower()


def test_plan_change_marks_module_knob_requests_as_external_dependency():
    result = plan_change("which module knob controls tailscale routing?")

    assert result["requires_mcp_nixos"] is True
    assert "option discovery" in result["notes"].lower()


def test_plan_change_does_not_route_generic_module_edits_to_mcp_nixos():
    result = plan_change("add a cava module to waybar")

    assert result["requires_mcp_nixos"] is False
