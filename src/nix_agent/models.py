from dataclasses import dataclass, field

from nix_agent.policy import PolicyDecision

# Re-export the policy decision type so callers can import it from this module.


OPERATION_PATCH = "patch"
OPERATION_DELETE = "delete"


@dataclass
class OperationResult:
    intent: str
    changed_files: list[str] = field(default_factory=list)
    policy_decision: str = "allowed"
    approval_required: bool = False
    validation_result: str | None = None
    apply_result: str | None = None
    rollback_target: str | None = None


@dataclass
class Patch:
    path: str
    content: str
    expected_content: str | None = None
    expected_sha256: str | None = None
    operation: str = OPERATION_PATCH
    reason: str | None = None


@dataclass
class PatchSet:
    patches: list[Patch] = field(default_factory=list)


__all__ = [
    "OperationResult",
    "Patch",
    "PatchSet",
    "PolicyDecision",
    "OPERATION_PATCH",
    "OPERATION_DELETE",
]
