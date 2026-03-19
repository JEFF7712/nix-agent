from nix_agent.policy import POLICY_RULES, classify_change


def test_classify_change_requires_approval_for_ssh_config():
    decision = classify_change(["/etc/nixos/ssh.nix"])

    assert decision.approval_required is True
    assert decision.policy_decision == "blocked"


def test_ssh_path_requires_approval_for_switch():
    decision = classify_change(["/etc/nixos/ssh.nix"], operation="switch")
    assert decision.approval_required is True


def test_network_path_requires_approval_for_patch():
    decision = classify_change(["/etc/nixos/networking.nix"], operation="patch")
    assert decision.approval_required is True


def test_firewall_path_requires_approval_for_switch():
    decision = classify_change(["/etc/nixos/firewall.nix"], operation="switch")
    assert decision.approval_required is True


def test_classify_change_reports_risk_and_matched_rules():
    decision = classify_change(["/etc/nixos/ssh.nix"], operation="patch")

    assert decision.risk_level == "high"
    assert decision.matched_rules == ["auth-ssh"]


def test_policy_rules_include_auth_and_network_categories():
    rule_ids = {rule.id for rule in POLICY_RULES}

    assert "auth-ssh" in rule_ids
    assert "network-core" in rule_ids


def test_inspect_operation_never_requires_approval_for_sensitive_path():
    decision = classify_change(["/etc/nixos/firewall.nix"], operation="inspect")

    assert decision.approval_required is False
    assert decision.policy_decision == "allowed"


def test_high_risk_rule_wins_over_low_risk_rule():
    decision = classify_change(["/etc/nixos/network/firewall.nix"], operation="patch")

    assert decision.approval_required is True
    assert decision.risk_level == "high"


def test_unknown_operation_fails_closed():
    decision = classify_change(["/etc/nixos/configuration.nix"], operation="unknown")

    assert decision.approval_required is True
    assert decision.policy_decision == "blocked"
