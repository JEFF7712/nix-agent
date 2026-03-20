from dataclasses import dataclass
import subprocess


@dataclass(frozen=True)
class CommandResult:
    ok: bool
    output: str


def run_dry_activate(flake_uri: str) -> CommandResult:
    try:
        result = subprocess.run(
            ["sudo", "nixos-rebuild", "dry-activate", "--flake", flake_uri],
            check=True,
            capture_output=True,
            text=True,
        )
        return CommandResult(ok=True, output=result.stdout)
    except subprocess.CalledProcessError as exc:
        return CommandResult(ok=False, output=(exc.stderr or "").strip())


def run_switch(flake_uri: str) -> str:
    result = subprocess.run(
        ["sudo", "nixos-rebuild", "switch", "--flake", flake_uri],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout
