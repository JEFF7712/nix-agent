from dataclasses import dataclass


@dataclass
class PolicyDecision:
    policy_decision: str
    approval_required: bool
    reason: str


def classify_change(changed_files: list[str]) -> PolicyDecision:
    for path in changed_files:
        if "ssh" in path or "network" in path or "firewall" in path:
            return PolicyDecision("blocked", True, "matched approval blacklist")
    return PolicyDecision("allowed", False, "no blacklist match")
