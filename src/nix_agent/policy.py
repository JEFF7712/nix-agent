from dataclasses import dataclass


@dataclass
class PolicyDecision:
    policy_decision: str
    approval_required: bool
    reason: str
    risk_level: str
    matched_rules: list[str]


@dataclass
class PolicyRule:
    id: str
    path_patterns: list[str]
    operations: list[str]
    risk_level: str
    approval_required: bool
    reason: str


POLICY_RULES = [
    PolicyRule(
        id="auth-ssh",
        path_patterns=["ssh", "sshd_config", "authorized_keys", "ssh.nix"],
        operations=["create", "patch", "switch"],
        risk_level="high",
        approval_required=True,
        reason="SSH/auth changes require approval",
    ),
    PolicyRule(
        id="network-core",
        path_patterns=["network", "interfaces", "firewall", "networking.nix"],
        operations=["create", "patch", "switch"],
        risk_level="high",
        approval_required=True,
        reason="Core networking changes require approval",
    ),
    PolicyRule(
        id="hardware-configuration",
        path_patterns=["hardware-configuration.nix"],
        operations=["create", "patch", "switch"],
        risk_level="high",
        approval_required=True,
        reason="Hardware configuration edits require approval",
    ),
]


KNOWN_OPERATIONS = {"create", "patch", "delete", "switch", "inspect"}


def classify_change(
    changed_files: list[str], operation: str | None = None
) -> PolicyDecision:
    effective_operation = operation or "patch"

    if operation and operation not in KNOWN_OPERATIONS:
        return PolicyDecision(
            policy_decision="blocked",
            approval_required=True,
            reason=f"unknown operation: {operation}",
            risk_level="high",
            matched_rules=["unknown-operation"],
        )

    if effective_operation == "delete":
        return PolicyDecision(
            policy_decision="blocked",
            approval_required=True,
            reason="delete operations always require approval",
            risk_level="high",
            matched_rules=["delete-operation"],
        )

    matched_rules: list[str] = []
    highest_risk = "low"
    risk_order = {"low": 0, "medium": 1, "high": 2}

    for path in changed_files:
        for rule in POLICY_RULES:
            if effective_operation not in rule.operations:
                continue
            if not any(pattern in path for pattern in rule.path_patterns):
                continue
            if rule.id not in matched_rules:
                matched_rules.append(rule.id)
            if risk_order[rule.risk_level] > risk_order[highest_risk]:
                highest_risk = rule.risk_level
                highest_reason = rule.reason

    highest_reason = locals().get("highest_reason", "matched approval blacklist")

    if matched_rules and effective_operation != "inspect":
        return PolicyDecision(
            policy_decision="blocked",
            approval_required=True,
            reason=highest_reason,
            risk_level=highest_risk,
            matched_rules=matched_rules,
        )

    return PolicyDecision(
        policy_decision="allowed",
        approval_required=False,
        reason="no blacklist match",
        risk_level="low",
        matched_rules=[],
    )
