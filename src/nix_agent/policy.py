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


SAFE_OPERATIONS = {"inspect"}


POLICY_RULES = [
    PolicyRule(
        id="auth-ssh",
        path_patterns=["ssh", "sshd_config", "authorized_keys"],
        operations=["create", "patch", "delete", "switch"],
        risk_level="high",
        approval_required=True,
        reason="SSH/auth-related changes must be reviewed",
    ),
    PolicyRule(
        id="network-core",
        path_patterns=[
            "network",
            "interfaces",
            "firewall",
            "networking.nix",
            "firewall.nix",
        ],
        operations=["create", "patch", "delete", "switch"],
        risk_level="high",
        approval_required=True,
        reason="Core networking rules require approval",
    ),
    PolicyRule(
        id="boot-identity",
        path_patterns=["boot", "hostname", "system-id"],
        operations=["create", "patch", "delete"],
        risk_level="medium",
        approval_required=True,
        reason="Boot and identity changes affect system stability",
    ),
    PolicyRule(
        id="secrets-wiring",
        path_patterns=["secrets", "vault", "credentials"],
        operations=["create", "patch", "delete"],
        risk_level="high",
        approval_required=True,
        reason="Secrets wiring must always be reviewed",
    ),
    PolicyRule(
        id="user-config",
        path_patterns=["users", "accounts", "services", "profiles"],
        operations=["create", "patch", "delete"],
        risk_level="medium",
        approval_required=False,
        reason="User and app config has broader tolerance",
    ),
]


def classify_change(
    changed_files: list[str], operation: str | None = None
) -> PolicyDecision:
    effective_operation = operation or "patch"
    known_operations = {op for rule in POLICY_RULES for op in rule.operations}
    known_operations.update(SAFE_OPERATIONS)

    if operation and operation not in known_operations:
        return PolicyDecision(
            policy_decision="blocked",
            approval_required=True,
            reason=f"unknown operation: {operation}",
            risk_level="high",
            matched_rules=["unknown-operation"],
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

    if matched_rules:
        return PolicyDecision(
            policy_decision="blocked",
            approval_required=True,
            reason="matched approval blacklist",
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
