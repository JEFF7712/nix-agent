from fastmcp import FastMCP
from fastmcp.tools.tool import Tool

from nix_agent.tools.build import build, diff
from nix_agent.tools.check import check
from nix_agent.tools.eval import eval_config
from nix_agent.tools.fmt import format_nix
from nix_agent.tools.inspect_flake import inspect_flake
from nix_agent.tools.locate import locate_option
from nix_agent.tools.switch import generations, switch

_TOOLS = [
    (
        eval_config,
        "eval_config",
        "Evaluate the final merged value of an attribute in the user's "
        "actual NixOS/Home Manager configuration via `nix eval` "
        "(e.g. attr='services.openssh.enable'). flake_uri and mode "
        "auto-resolve when omitted. Pass a list of attrs to batch several "
        "evals into one call, returning per-attr results. Values above the "
        "size guard degrade to attr names / length / a head slice "
        "(truncated: true).",
    ),
    (
        check,
        "check",
        "Validation ladder for the configuration, fast to slow: "
        "level='lint' (statix+deadnix; returns a structured findings "
        "list — lint only), 'flake' (nix flake check), 'dry-build' "
        "(evaluate and plan the closure build), 'dry-activate' (NixOS "
        "only, shows what activation would change).",
    ),
    (
        format_nix,
        "format",
        "Format .nix files. With paths: nixfmt per file. Without: "
        "`nix fmt` in the flake directory, falling back to nixfmt on "
        "all .nix files when the flake defines no formatter.",
    ),
    (
        build,
        "build",
        "Build the full system/HM closure without activating it. "
        "Returns the output store path.",
    ),
    (
        diff,
        "diff",
        "Build the new closure and diff it against the running system "
        "(nvd, falling back to nix store diff-closures): package "
        "additions, removals, version changes. Use before switch.",
    ),
    (
        switch,
        "switch",
        "Activate the configuration (sudo nixos-rebuild switch / "
        "home-manager switch). Records rollback_generation first. Returns a "
        "structured 'summary' (units changed, derivations built) plus gen "
        "before/after; on success the raw log is trimmed to a tail (pass "
        "full_log=True for all of it). No implicit validation by default; "
        "pass validate=True to gate on check('dry-build') first. On a sudo "
        "auth failure returns a 'privilege' diagnosis.",
    ),
    (
        generations,
        "generations",
        "action='list': enumerate system/HM generations with dates and "
        "current marker. action='rollback': revert to the previous "
        "generation. Pass mode='home-manager' for HM generations.",
    ),
    (
        locate_option,
        "locate_option",
        "Where does this configuration set an option: files declaring it "
        "and every file defining it, with each contributed value "
        "(e.g. attr='services.openssh.enable'). The bridge from mcp-nixos "
        "discovery to editing the right file. For integrated Home Manager, "
        "query the NixOS config with attr='home-manager.users.<user>.<attr>'.",
    ),
    (
        inspect_flake,
        "inspect_flake",
        "Structured facts about the config repo in one call: hosts, "
        "homeConfigurations, integrated-vs-standalone Home Manager, module "
        "dirs, auto-import mechanism, formatter, lint tools, justfile/CI/"
        ".mcp.json presence. Run this before onboarding a repo or when "
        "orienting in an unfamiliar config; facts that cannot be determined "
        "are null/'unknown'.",
    ),
]


def build_server() -> FastMCP:
    server = FastMCP("nix-agent")
    for fn, name, description in _TOOLS:
        server.add_tool(Tool.from_function(fn, name=name, description=description))
    return server
