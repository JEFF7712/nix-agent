from pathlib import Path


def test_install_script_exists_and_mentions_supported_hosts():
    script_text = Path("install-skill.sh").read_text()

    assert "opencode" in script_text
    assert "claude" in script_text
    assert "skills/nix-agent" in script_text
    assert ".config/opencode/skills" in script_text
    assert ".claude/skills" in script_text


def test_readme_mentions_install_script():
    readme_text = Path("README.md").read_text()

    assert "./install-skill.sh opencode" in readme_text
