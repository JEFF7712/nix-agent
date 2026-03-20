import hashlib
from pathlib import Path

from nix_agent.models import OPERATION_DELETE, Patch, PatchSet


def replace_file_contents(path: str | Path, content: str) -> list[str]:
    target = Path(path)
    target.write_text(content)
    return [str(target)]


def apply_patch_set(patch_set: PatchSet) -> dict[str, object]:
    conflict = _find_drift_conflict(patch_set.patches)
    if conflict:
        return {
            "status": "conflict",
            "changed_files": [],
            "conflicts": [conflict],
        }

    if any(patch.operation == OPERATION_DELETE for patch in patch_set.patches):
        return {
            "status": "approval_required",
            "changed_files": [],
        }

    return _execute_patch_set(patch_set.patches)


def _execute_patch_set(patches: list[Patch]) -> dict[str, object]:
    changed_files: list[str] = []
    for patch in patches:
        changed_files.extend(replace_file_contents(patch.path, patch.content))

    return {"status": "applied", "changed_files": changed_files}


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
