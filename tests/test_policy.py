from nix_agent.policy import classify_change


def test_non_blacklisted_patch_allowed():
    decision = classify_change(
        ["/home/user/.config/waybar/config.jsonc"], operation="patch"
    )

    assert decision.approval_required is False
    assert decision.policy_decision == "allowed"


def test_hardware_configuration_requires_approval():
    decision = classify_change(
        ["/etc/nixos/hardware-configuration.nix"], operation="patch"
    )

    assert decision.approval_required is True
    assert decision.policy_decision == "blocked"
    assert "hardware-configuration" in decision.matched_rules


def test_delete_operation_always_requires_approval():
    decision = classify_change(["/etc/nixos/configuration.nix"], operation="delete")

    assert decision.approval_required is True
    assert decision.policy_decision == "blocked"
    assert decision.matched_rules == ["delete-operation"]


def test_inspect_operation_ignores_blacklist():
    decision = classify_change(
        ["/etc/nixos/hardware-configuration.nix"], operation="inspect"
    )

    assert decision.approval_required is False
    assert decision.policy_decision == "allowed"
