from dataclasses import dataclass
import os
import shutil
import subprocess


@dataclass(frozen=True)
class CommandResult:
    ok: bool
    output: str


def _with_privileged_automation_hint(message: str) -> str:
    if (
        "sudo: a terminal is required" not in message
        and "sudo: a password is required" not in message
    ):
        return message

    hint = (
        "Privileged automation is not configured. Configure passwordless sudo for the specific "
        "nixos-rebuild dry-activate/switch commands used by nix-agent, for example via a narrow "
        "/etc/sudoers.d rule.\n\n"
    )
    return f"{hint}{message}".strip()


def _resolve_nixos_rebuild() -> str:
    command = shutil.which("nixos-rebuild")
    if command is None:
        return "nixos-rebuild"
    return os.path.realpath(command)


def run_dry_activate(flake_uri: str) -> CommandResult:
    nixos_rebuild = _resolve_nixos_rebuild()
    try:
        result = subprocess.run(
            ["sudo", nixos_rebuild, "dry-activate", "--flake", flake_uri],
            check=True,
            capture_output=True,
            text=True,
        )
        return CommandResult(ok=True, output=result.stdout)
    except subprocess.CalledProcessError as exc:
        return CommandResult(
            ok=False,
            output=_with_privileged_automation_hint((exc.stderr or "").strip()),
        )


def run_switch(flake_uri: str) -> str:
    nixos_rebuild = _resolve_nixos_rebuild()
    result = subprocess.run(
        ["sudo", nixos_rebuild, "switch", "--flake", flake_uri],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout
