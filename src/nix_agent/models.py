from dataclasses import dataclass, field
from typing import Any

from nix_agent.policy import PolicyDecision

# Re-export the policy decision type so callers can import it from this module.


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
    operation: str = "patch"
    reason: str | None = None


@dataclass
class PatchSet:
    patches: list[Patch] = field(default_factory=list)


@dataclass
class ManagedRoot:
    root: str
    allowed_operations: list[str] = field(default_factory=list)
    allowed_file_patterns: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, list[str] | str]:
        return {
            "root": self.root,
            "allowed_operations": list(self.allowed_operations),
            "allowed_file_patterns": list(self.allowed_file_patterns),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ManagedRoot":
        return cls(
            root=data["root"],
            allowed_operations=[str(op) for op in data.get("allowed_operations", [])],
            allowed_file_patterns=[
                str(pattern) for pattern in data.get("allowed_file_patterns", [])
            ],
        )


@dataclass
class ManagedState:
    managed_roots: list[ManagedRoot] = field(default_factory=list)

    def to_dict(self) -> dict[str, list[dict[str, Any]]]:
        return {"managed_roots": [root.to_dict() for root in self.managed_roots]}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ManagedState":
        roots = data.get("managed_roots", [])
        return cls(managed_roots=[ManagedRoot.from_dict(root) for root in roots])


@dataclass
class TrustProposal:
    path: str
    proposed_managed_root: str
    file_pattern: str
    operation: str
    reason: str | None = None

    def to_dict(self) -> dict[str, str | None]:
        return {
            "path": self.path,
            "proposed_managed_root": self.proposed_managed_root,
            "file_pattern": self.file_pattern,
            "operation": self.operation,
            "reason": self.reason,
        }


__all__ = [
    "OperationResult",
    "Patch",
    "PatchSet",
    "PolicyDecision",
    "ManagedRoot",
    "ManagedState",
    "TrustProposal",
]
