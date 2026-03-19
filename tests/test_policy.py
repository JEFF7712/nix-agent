from nix_agent.policy import classify_change


def test_classify_change_requires_approval_for_ssh_config():
    decision = classify_change(["/etc/nixos/ssh.nix"])

    assert decision.approval_required is True
    assert decision.policy_decision == "blocked"
