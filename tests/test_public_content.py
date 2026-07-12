import re
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
README = (REPOSITORY_ROOT / "README.md").read_text()
BANNER = (REPOSITORY_ROOT / "assets/banner.svg").read_text()
USAGE = (REPOSITORY_ROOT / "docs/usage.md").read_text()
INSTALL_PROMPT_COMPONENT = (
    REPOSITORY_ROOT / "site/components/InstallPrompt.tsx"
).read_text()

EXPECTED_TOOLS = {
    "eval_config",
    "locate_option",
    "check",
    "format",
    "build",
    "diff",
    "switch",
    "generations",
    "inspect_flake",
}


def _readme_install_prompt() -> str:
    install_section = README.split("## Install", 1)[1].split("## Docs", 1)[0]
    return re.search(r"```\n(.+?)\n```", install_section, re.DOTALL).group(1)


def _typescript_install_prompt() -> str:
    return re.search(
        r'export const INSTALL_PROMPT\s*=\s*"([^"]+)";',
        INSTALL_PROMPT_COMPONENT,
    ).group(1)


def _usage_section(title: str) -> str:
    return USAGE.split(f"## {title}", 1)[1].split("\n## ", 1)[0]


def _paragraph_containing(section: str, text: str) -> str:
    return next(paragraph for paragraph in section.split("\n\n") if text in paragraph)


def test_install_prompts_stay_in_sync_and_install_both_skills():
    readme_prompt = _readme_install_prompt()
    typescript_prompt = _typescript_install_prompt()

    assert readme_prompt == typescript_prompt
    assert "install the companion skills" in readme_prompt


def test_readme_banner_describes_both_configuration_types():
    banner = re.search(r'<img src="assets/banner\.png"[^>]+>', README).group(0)

    assert "NixOS" in banner
    assert "Home Manager" in banner


def test_svg_banner_covers_the_public_scope_and_exact_tool_surface():
    tool_line = re.search(r">(eval_config .+ generations)</text>", BANNER).group(1)
    documented_tools = set(tool_line.split(" · "))

    assert "NixOS and Home Manager" in BANNER
    assert documented_tools == EXPECTED_TOOLS
    assert "\u2014" not in BANNER


def test_usage_documents_runtime_dependencies_and_timeout_boundaries():
    what_you_get = _usage_section("What you get")
    wrapper = _paragraph_containing(what_you_get, "packaged wrapper")
    host = _paragraph_containing(what_you_get, "host must supply")
    timeout = _paragraph_containing(what_you_get, "`NIX_AGENT_COMMAND_TIMEOUT`")

    for tool in ("statix", "deadnix", "nixfmt", "nvd"):
        assert f"`{tool}`" in wrapper
        assert f"`{tool}`" not in host
    for command in (
        "Nix",
        "nixos-rebuild",
        "home-manager",
        "sudo",
        "systemctl",
        "journalctl",
    ):
        assert command in host
    assert "positive number of seconds" in timeout
    assert "30 minutes" in timeout
    assert "invalid or nonpositive" in timeout
    assert "falls back" in timeout


def test_usage_documents_output_caps_and_full_switch_log_escape_hatch():
    failure_envelopes = _usage_section("Basic workflow")
    runtime = _paragraph_containing(failure_envelopes, "`full_log=True`")

    assert "each stdout and stderr stream" in runtime
    assert "64,000 Python characters" in runtime
    assert "2,000-character tail" in runtime
    assert "successful `switch`" in runtime
    assert "`full_log=True`" in runtime
    assert "64 KB" not in runtime


def test_usage_qualifies_inspection_as_best_effort_and_file_access_precisely():
    tool_surface = _usage_section("Tool surface")
    inspect_entry = next(
        line for line in tool_surface.splitlines() if line.startswith("| `inspect_flake")
    )
    inspect_entry_lower = inspect_entry.lower()
    design_notes = _usage_section("Design notes")

    assert "flake-show fails" in inspect_entry
    assert "evaluated facts" in inspect_entry_lower
    assert "`null` or `\"unknown\"`" in inspect_entry
    assert "best-effort presence/absence heuristics" in inspect_entry
    assert "repository layout" in inspect_entry_lower
    assert "auto-import" in inspect_entry_lower
    assert "integrated home manager detection" in inspect_entry_lower
    assert "unreadable or unmatched files as absence" in inspect_entry
    assert "never guessed" not in inspect_entry
    assert "no general-purpose file reading or editing" in design_notes
    assert "`format` writes" in design_notes
    assert "`inspect_flake` reads" in design_notes
    assert "nix-agent does no file I/O" not in USAGE
