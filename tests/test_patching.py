from pathlib import Path
import hashlib

from nix_agent.models import Patch, PatchSet
from nix_agent.patching import apply_patch_set, replace_file_contents


def test_apply_patch_set_allows_creating_new_file_by_default(tmp_path):
    target = tmp_path / "new.conf"
    patch_set = PatchSet(patches=[Patch(path=str(target), content="value")])

    result = apply_patch_set(patch_set)

    assert result["status"] == "applied"
    assert target.read_text() == "value"


def test_replace_file_contents_tracks_changed_file(tmp_path: Path):
    target = tmp_path / "configuration.nix"
    target.write_text("services.openssh.enable = false;\n")

    changed = replace_file_contents(target, "services.openssh.enable = true;\n")

    assert changed == [str(target)]
    assert target.read_text() == "services.openssh.enable = true;\n"


def test_patch_can_carry_expected_content():
    patch = Patch(path="/tmp/example", content="new", expected_content="old")

    assert patch.expected_content == "old"


def test_apply_patch_set_writes_file(tmp_path):
    target = tmp_path / "waybar.json"
    patch_set = PatchSet(patches=[Patch(path=str(target), content="{}")])

    result = apply_patch_set(patch_set)

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

    result = apply_patch_set(patch_set)

    assert result["status"] == "conflict"
    assert target.read_text() == "old"


def test_apply_patch_set_blocks_when_expected_sha256_does_not_match(tmp_path):
    target = tmp_path / "config.nix"
    target.write_text("old")
    patch_set = PatchSet(
        patches=[
            Patch(
                path=str(target),
                content="new",
                expected_sha256=hashlib.sha256(b"different").hexdigest(),
            )
        ]
    )

    result = apply_patch_set(patch_set)

    assert result["status"] == "conflict"
    assert target.read_text() == "old"


def test_apply_patch_set_requires_approval_for_delete(tmp_path):
    target = tmp_path / "delete-me.txt"
    target.write_text("bye")
    patch_set = PatchSet(
        patches=[Patch(path=str(target), content="", operation="delete")]
    )

    result = apply_patch_set(patch_set)

    assert result["status"] == "approval_required"
    assert target.exists()
