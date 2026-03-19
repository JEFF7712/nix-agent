from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from nix_agent.models import ManagedRoot, ManagedState


def load_managed_state(state_path: Path) -> dict[str, Any]:
    if not state_path.exists():
        return {"managed_roots": []}
    return json.loads(state_path.read_text(encoding="utf-8"))


def save_managed_state(state_path: Path, state: ManagedState | dict[str, Any]) -> None:
    normalized = state.to_dict() if isinstance(state, ManagedState) else state
    state_path.parent.mkdir(parents=True, exist_ok=True)
    with state_path.open("w", encoding="utf-8") as fh:
        json.dump(normalized, fh, indent=2)
        fh.write("\n")


def record_managed_root(
    state_path: Path, managed_root: ManagedRoot | dict[str, Any]
) -> dict[str, Any]:
    root = (
        managed_root
        if isinstance(managed_root, ManagedRoot)
        else ManagedRoot.from_dict(managed_root)
    )
    current_state = load_managed_state(state_path)
    managed_state = ManagedState.from_dict(current_state)
    managed_state.managed_roots.append(root)
    save_managed_state(state_path, managed_state)
    return managed_state.to_dict()
