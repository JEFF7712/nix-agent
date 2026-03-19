from pathlib import Path

from nix_agent.models import Patch, PatchSet
from nix_agent.patching import apply_patch_set, replace_file_contents


def test_replace_file_contents_tracks_changed_file(tmp_path: Path):
    target = tmp_path / "configuration.nix"
    target.write_text("services.openssh.enable = false;\n")

    changed = replace_file_contents(target, "services.openssh.enable = true;\n")

    assert changed == [str(target)]
    assert target.read_text() == "services.openssh.enable = true;\n"


def test_patch_can_carry_expected_content():
    patch = Patch(path="/tmp/example", content="new", expected_content="old")

    assert patch.expected_content == "old"


def test_apply_patch_set_returns_trust_proposal_for_unknown_path(tmp_path: Path):
    patch_set = PatchSet(
        patches=[
            Patch(
                path=str(tmp_path / "unknown.conf"),
                content="value",
                reason="configure app",
            )
        ]
    )

    result = apply_patch_set(patch_set, managed_state={"managed_roots": []})

    assert result["status"] == "approval_required"
    assert result["trust_proposals"][0]["path"].endswith("unknown.conf")


def test_apply_patch_set_writes_file_inside_managed_root(tmp_path):
    target = tmp_path / "waybar.json"
    patch_set = PatchSet(patches=[Patch(path=str(target), content="{}")])
    managed_state = {
        "managed_roots": [
            {
                "root": str(tmp_path),
                "allowed_operations": ["patch"],
                "allowed_file_patterns": ["*.json"],
            }
        ]
    }

    result = apply_patch_set(patch_set, managed_state=managed_state)

    assert result["status"] == "applied"
    assert target.read_text() == "{}"


def test_apply_patch_set_blocks_when_expected_content_does_not_match(tmp_path):
    target = tmp_path / "config.nix"
    target.write_text("old")
    patch_set = PatchSet(
        patches=[
            Patch(path=str(target), content="new", expected_content="something-else")
        ]
    )
    managed_state = {
        "managed_roots": [
            {
                "root": str(tmp_path),
                "allowed_operations": ["patch"],
                "allowed_file_patterns": ["*.nix"],
            }
        ]
    }

    result = apply_patch_set(patch_set, managed_state=managed_state)

    assert result["status"] == "conflict"
    assert target.read_text() == "old"


def test_apply_patch_set_is_atomic_when_one_patch_is_unknown(tmp_path):
    known = tmp_path / "known.json"
    unknown = tmp_path / "other.txt"
    patch_set = PatchSet(
        patches=[
            Patch(path=str(known), content="{}"),
            Patch(path=str(unknown), content="x"),
        ]
    )
    managed_state = {
        "managed_roots": [
            {
                "root": str(tmp_path),
                "allowed_operations": ["patch"],
                "allowed_file_patterns": ["*.json"],
            }
        ]
    }

    result = apply_patch_set(patch_set, managed_state=managed_state)

    assert result["status"] == "approval_required"
    assert not known.exists()
