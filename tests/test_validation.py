from pathlib import Path

from nix_agent.validation import needs_nix_format


def test_needs_nix_format_matches_nix_files(tmp_path: Path):
    nix_file = tmp_path / "flake.nix"
    json_file = tmp_path / "waybar.json"

    assert needs_nix_format(nix_file) is True
    assert needs_nix_format(json_file) is False
