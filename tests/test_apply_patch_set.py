from nix_agent.models import Patch, PatchSet
from nix_agent.server import _extract_first_error, apply_patch_set


def test_apply_patch_set_writes_files(tmp_path):
    target = tmp_path / "configuration.nix"
    result = apply_patch_set(PatchSet(patches=[Patch(path=str(target), content="{ }\n")]))

    assert result["status"] == "written"
    assert result["changed_files"] == [str(target)]
    assert target.read_text() == "{ }\n"


def test_apply_patch_set_creates_parent_dirs(tmp_path):
    target = tmp_path / "nested" / "dir" / "f.nix"
    apply_patch_set(PatchSet(patches=[Patch(path=str(target), content="{}\n")]))
    assert target.exists()


def test_apply_patch_set_rejects_unknown_mode(tmp_path):
    target = tmp_path / "f.nix"
    result = apply_patch_set(
        PatchSet(patches=[Patch(path=str(target), content="{}\n")]),
        mode="bogus",
    )
    assert result["status"] == "invalid_mode"
    assert not target.exists()


def test_apply_patch_set_empty_patchset_is_written_noop(tmp_path):
    result = apply_patch_set(PatchSet(patches=[]))
    assert result["status"] == "written"
    assert result["changed_files"] == []
    assert result["formatter_output"] == "no .nix files to format"


def test_extract_first_error_finds_nix_error_line():
    output = (
        "building the system configuration...\n"
        "trace: evaluation warning: foo\n"
        "error: attribute 'floorpx' missing\n"
        "       at /etc/nixos/configuration.nix:42:5\n"
    )
    assert _extract_first_error(output) == "error: attribute 'floorpx' missing"


def test_extract_first_error_returns_none_when_no_error():
    assert _extract_first_error("everything is fine\n") is None
    assert _extract_first_error("") is None


def test_apply_patch_set_home_manager_writes_without_flake(tmp_path):
    target = tmp_path / "home.nix"
    result = apply_patch_set(
        PatchSet(patches=[Patch(path=str(target), content="{ }\n")]),
        mode="home-manager",
    )
    assert result["status"] == "written"
    assert result["mode"] == "home-manager"
    assert target.read_text() == "{ }\n"
