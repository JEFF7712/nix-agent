import subprocess
from pathlib import Path

from fastmcp import FastMCP
from fastmcp.tools.tool import Tool

from nix_agent.inspect import read_target
from nix_agent.models import PatchSet
from nix_agent.patching import apply_patches
from nix_agent.system_apply import (
    get_current_generation,
    get_current_hm_generation,
    run_dry_activate,
    run_hm_build,
    run_hm_switch,
    run_switch,
)


VALID_MODES = {"nixos", "home-manager"}


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
    return "\n".join(messages) if messages else "no .nix files to format"


def _extract_first_error(output: str) -> str | None:
    """Return the first line of `output` that looks like a Nix error.

    Nix stderr is verbose; the first `error:` line is usually the
    actionable signal. Returns None if no such line exists.
    """
    if not output:
        return None
    for line in output.splitlines():
        stripped = line.strip()
        if stripped.startswith("error:") or stripped.startswith("error ("):
            return stripped
    return None


def apply_patch_set(
    patch_set: PatchSet,
    flake_uri: str | None = None,
    mode: str = "nixos",
) -> dict[str, object]:
    """Write patches, format, and (if flake_uri given) validate + switch.

    mode="nixos" runs `nixos-rebuild dry-activate` then `nixos-rebuild
    switch` (sudo). mode="home-manager" runs `home-manager build` then
    `home-manager switch` (no sudo). In both cases the response includes
    a `rollback_generation` pointer so a bad switch can be recovered:

      - nixos:        `sudo nixos-rebuild switch --rollback`
      - home-manager: `<rollback_generation>/activate`
    """
    if mode not in VALID_MODES:
        return {
            "status": "invalid_mode",
            "error": f"mode must be one of {sorted(VALID_MODES)}, got {mode!r}",
        }

    changed = apply_patches(patch_set)
    formatter_output = _format_nix_files(changed)

    response: dict[str, object] = {
        "status": "written",
        "mode": mode,
        "changed_files": changed,
        "formatter_output": formatter_output,
    }

    if flake_uri is None:
        return response

    if mode == "nixos":
        rollback = get_current_generation()
        validate = run_dry_activate(flake_uri)
        validate_key = "dry_activate_output"
        switch_fn = run_switch
        current_fn = get_current_generation
    else:  # home-manager
        rollback = get_current_hm_generation()
        validate = run_hm_build(flake_uri)
        validate_key = "build_output"
        switch_fn = run_hm_switch
        current_fn = get_current_hm_generation

    response["rollback_generation"] = rollback
    response[validate_key] = validate.output
    if not validate.ok:
        response["status"] = "validation_failed"
        response["first_error"] = _extract_first_error(validate.output)
        return response

    switch = switch_fn(flake_uri)
    response["switch_output"] = switch.output
    if switch.ok:
        response["status"] = "applied"
    else:
        response["status"] = "switch_failed"
        response["first_error"] = _extract_first_error(switch.output)
    response["current_generation"] = current_fn()
    return response


def build_server() -> FastMCP:
    server = FastMCP("nix-agent")

    def inspect_state(path: str | Path) -> dict[str, str]:
        return read_target(path)

    def apply_patch_set_tool(
        patch_set: PatchSet,
        flake_uri: str | None = None,
        mode: str = "nixos",
    ) -> dict[str, object]:
        return apply_patch_set(patch_set, flake_uri=flake_uri, mode=mode)

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
                    "and—if flake_uri is provided—validate then switch. "
                    "mode='nixos' (default) runs `nixos-rebuild dry-activate` "
                    "then `switch` (sudo). mode='home-manager' runs "
                    "`home-manager build` then `switch` (no sudo). Returns "
                    "rollback_generation so a bad switch can be undone."
                ),
            )
        ),
    }
    return server
