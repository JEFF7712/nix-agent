"""Guard the tiny-flake quoting fixture without invoking Nix."""

from pathlib import Path

FIXTURE = Path(__file__).parent / "fixtures" / "tiny-flake" / "flake.nix"


def test_tiny_flake_has_quoted_installable_attrpath():
    text = FIXTURE.read_text()
    assert "nixosConfigurations.fixture" in text
    assert 'config.networking.hostName = "fixture"' in text
    assert "outputs = { self }:" in text
