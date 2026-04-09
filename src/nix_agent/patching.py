from pathlib import Path

from nix_agent.models import PatchSet


def apply_patches(patch_set: PatchSet) -> list[str]:
    changed: list[str] = []
    for patch in patch_set.patches:
        target = Path(patch.path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(patch.content)
        changed.append(str(target))
    return changed
