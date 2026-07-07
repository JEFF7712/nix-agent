from pathlib import Path
from stat import S_IXUSR


def test_install_script_exists_and_mentions_supported_hosts():
    script_path = Path("install-skill.sh")
    script_text = script_path.read_text()

    assert script_path.stat().st_mode & S_IXUSR
    assert "codex" in script_text
    assert "opencode" in script_text
    assert "claude" in script_text
    assert '"$skills_dir"/*/' in script_text
    assert ".codex}/skills" in script_text
    assert ".config/opencode/skills" in script_text
    assert ".claude/skills" in script_text


def test_install_script_covers_every_skill_dir():
    script_text = Path("install-skill.sh").read_text()
    skill_dirs = sorted(p.name for p in Path("skills").iterdir() if p.is_dir())

    assert skill_dirs == ["nix-agent", "nix-agent-init"]
    for skill_dir in skill_dirs:
        assert (Path("skills") / skill_dir / "SKILL.md").is_file()
    assert "skills/nix-agent" not in script_text


def test_docs_mention_install_script():
    usage_text = Path("docs/usage.md").read_text()

    assert "./install-skill.sh codex" in usage_text
    assert "./install-skill.sh opencode" in usage_text
    assert "./install-skill.sh claude" in usage_text
