import subprocess
from pathlib import Path

from fastmcp import FastMCP
from fastmcp.tools.tool import Tool

from nix_agent.inspect import read_target
from nix_agent.models import PatchSet
from nix_agent.patching import apply_patches
from nix_agent.system_apply import (
    get_current_generation,
    run_dry_activate,
    run_switch,
)


def _format_nix_files(paths: list[str]) -> str:
    messages: list[str] = []
    for path in paths:
        if Path(path).suffix != ".nix":
            continue
        try:
            result = subprocess.run(
                ["nixpkgs-fmt", path], capture_output=True, text=True
            )
            messages.append(
                f"{path}: {(result.stdout or result.stderr).strip() or 'formatted'}"
            )
        except FileNotFoundError:
            messages.append(f"{path}: nixpkgs-fmt not installed, skipped")
    return "\n".join(messages) if messages else "no nix files"


def apply_patch_set(
    patch_set: PatchSet, flake_uri: str | None = None
) -> dict[str, object]:
    """Write patches, format, and (if flake_uri given) dry-activate + switch.

    Returns rollback_generation so callers can `nixos-rebuild switch
    --rollback` or boot a prior generation if anything looks wrong.
    """
    changed = apply_patches(patch_set)
    formatter_output = _format_nix_files(changed)

    response: dict[str, object] = {
        "status": "written",
        "changed_files": changed,
        "formatter_output": formatter_output,
    }

    if flake_uri is None:
        return response

    rollback_generation = get_current_generation()
    response["rollback_generation"] = rollback_generation

    dry = run_dry_activate(flake_uri)
    response["dry_activate_output"] = dry.output
    if not dry.ok:
        response["status"] = "validation_failed"
        return response

    switch = run_switch(flake_uri)
    response["switch_output"] = switch.output
    response["status"] = "applied" if switch.ok else "switch_failed"
    response["current_generation"] = get_current_generation()
    return response


def build_server() -> FastMCP:
    server = FastMCP("nix-agent")

    def inspect_state(path: str | Path) -> dict[str, str]:
        return read_target(path)

    def apply_patch_set_tool(
        patch_set: PatchSet, flake_uri: str | None = None
    ) -> dict[str, object]:
        return apply_patch_set(patch_set, flake_uri=flake_uri)

    server._tools = {  # type: ignore[attr-defined]
        "inspect_state": server.add_tool(
            Tool.from_function(
                inspect_state,
                name="inspect_state",
                description="Read a local file and return its contents.",
            )
        ),
        "apply_patch_set": server.add_tool(
            Tool.from_function(
                apply_patch_set_tool,
                name="apply_patch_set",
                description=(
                    "Write a set of file replacements, format any .nix files, "
                    "and—if flake_uri is provided—run nixos-rebuild dry-activate "
                    "then switch. Returns rollback_generation so a bad switch "
                    "can be undone via `nixos-rebuild switch --rollback`."
                ),
            )
        ),
    }
    return server
