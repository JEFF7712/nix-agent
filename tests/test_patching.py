from pathlib import Path

from nix_agent.patching import replace_file_contents


def test_replace_file_contents_tracks_changed_file(tmp_path: Path):
    target = tmp_path / "configuration.nix"
    target.write_text("services.openssh.enable = false;\n")

    changed = replace_file_contents(target, "services.openssh.enable = true;\n")

    assert changed == [str(target)]
    assert target.read_text() == "services.openssh.enable = true;\n"
