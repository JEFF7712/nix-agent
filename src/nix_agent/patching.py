from fnmatch import fnmatch
import hashlib
from pathlib import Path

from nix_agent.models import Patch, PatchSet, TrustProposal


def replace_file_contents(path: str | Path, content: str) -> list[str]:
    target = Path(path)
    target.write_text(content)
    return [str(target)]


def apply_patch_set(
    patch_set: PatchSet, managed_state: dict[str, object] | None = None
) -> dict[str, object]:
    state = managed_state or {}
    managed_roots = state.get("managed_roots", [])

    validation_result = _validate_patch_set(patch_set, managed_roots)
    if validation_result is not None:
        return validation_result

    return _execute_patch_set(patch_set.patches)


def _validate_patch_set(
    patch_set: PatchSet, managed_roots: object
) -> dict[str, object] | None:
    unknown_targets: list[TrustProposal] = []
    for patch in patch_set.patches:
        target = Path(patch.path)
        if _is_managed_target(patch, managed_roots):
            continue
        unknown_targets.append(
            TrustProposal(
                path=str(target),
                proposed_managed_root=str(target.parent),
                file_pattern=f"*{target.suffix}" if target.suffix else target.name,
                operation=patch.operation,
                reason=patch.reason,
            )
        )

    if unknown_targets:
        return {
            "status": "approval_required",
            "trust_proposals": [proposal.to_dict() for proposal in unknown_targets],
            "changed_files": [],
        }

    conflict = _find_drift_conflict(patch_set.patches)
    if conflict:
        return {
            "status": "conflict",
            "trust_proposals": [],
            "changed_files": [],
            "conflicts": [conflict],
        }

    return None


def _execute_patch_set(patches: list[Patch]) -> dict[str, object]:
    changed_files: list[str] = []
    for patch in patches:
        changed_files.extend(replace_file_contents(patch.path, patch.content))

    return {"status": "applied", "changed_files": changed_files, "trust_proposals": []}


def _is_managed_target(patch: Patch, managed_roots: object) -> bool:
    if not isinstance(managed_roots, list):
        return False

    resolved_target = Path(patch.path).resolve(strict=False)
    for root in managed_roots:
        root_path: str | None = None
        allowed_operations: list[str] = []
        allowed_patterns: list[str] = []

        if isinstance(root, dict):
            candidate = root.get("root")
            if isinstance(candidate, str):
                root_path = candidate
            operations = root.get("allowed_operations")
            if isinstance(operations, list):
                allowed_operations = [
                    str(op).lower() for op in operations if isinstance(op, str)
                ]
            patterns = root.get("allowed_file_patterns")
            if isinstance(patterns, list):
                allowed_patterns = [
                    str(pattern) for pattern in patterns if isinstance(pattern, str)
                ]
        elif isinstance(root, str):
            root_path = root
        else:
            continue

        if not root_path:
            continue

        managed_root = Path(root_path).resolve(strict=False)
        try:
            relative_path = resolved_target.relative_to(managed_root)
        except ValueError:
            continue

        if allowed_operations and patch.operation.lower() not in allowed_operations:
            continue

        if allowed_patterns:
            relative_str = relative_path.as_posix()
            name = resolved_target.name
            if not any(
                fnmatch(name, pattern) or fnmatch(relative_str, pattern)
                for pattern in allowed_patterns
            ):
                continue

        return True

    return False


def _find_drift_conflict(patches: list[Patch]) -> dict[str, str] | None:
    for patch in patches:
        conflict = _check_patch_drift(patch)
        if conflict:
            return conflict
    return None


def _check_patch_drift(patch: Patch) -> dict[str, str] | None:
    if patch.expected_content is None and patch.expected_sha256 is None:
        return None

    target = Path(patch.path)
    if target.exists():
        actual_bytes = target.read_bytes()
        actual_text = actual_bytes.decode("utf-8", errors="replace")
    else:
        actual_bytes = b""
        actual_text = ""

    if patch.expected_content is not None and actual_text != patch.expected_content:
        return {
            "path": str(target),
            "type": "content_mismatch",
            "expected": patch.expected_content,
            "actual": actual_text,
        }

    if patch.expected_sha256 is not None:
        actual_sha = hashlib.sha256(actual_bytes).hexdigest()
        if actual_sha != patch.expected_sha256:
            return {
                "path": str(target),
                "type": "sha_mismatch",
                "expected": patch.expected_sha256,
                "actual": actual_sha,
            }

    return None
