from pathlib import Path

from nix_agent.inspect import read_target


def test_read_target_returns_file_contents(tmp_path: Path):
    target = tmp_path / "waybar.json"
    target.write_text('{"modules-right": []}')

    result = read_target(target)

    assert result["path"] == str(target)
    assert "modules-right" in result["content"]
