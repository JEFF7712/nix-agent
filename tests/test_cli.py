from pathlib import Path


def test_module_entrypoint_exists():
    assert Path("src/nix_agent/__main__.py").exists()


def test_skill_exists_with_expected_name():
    skill_path = Path("skills/nix-agent/SKILL.md")

    assert skill_path.exists()
    assert "name: nix-agent" in skill_path.read_text()
