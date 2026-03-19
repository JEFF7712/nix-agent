from pathlib import Path

from nix_agent.managed_state import load_managed_state, save_managed_state


def test_save_and_load_managed_state_round_trip(tmp_path: Path):
    state_path = tmp_path / "managed-state.json"
    state = {
        "managed_roots": [
            {
                "root": "/etc/nixos",
                "allowed_operations": ["patch", "inspect"],
                "allowed_file_patterns": ["*.nix"],
            }
        ]
    }

    save_managed_state(state_path, state)

    assert load_managed_state(state_path) == state
