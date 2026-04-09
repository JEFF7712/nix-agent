from dataclasses import dataclass
import os
import shutil
import subprocess


@dataclass(frozen=True)
class CommandResult:
    ok: bool
    output: str


def _resolve(binary: str) -> str:
    found = shutil.which(binary)
    if found is None:
        return binary
    return os.path.realpath(found)


# --- NixOS ----------------------------------------------------------------


def get_current_generation() -> str | None:
    try:
        result = subprocess.run(
            ["readlink", "/nix/var/nix/profiles/system"],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip() or None
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def run_dry_activate(flake_uri: str) -> CommandResult:
    nixos_rebuild = _resolve("nixos-rebuild")
    try:
        result = subprocess.run(
            ["sudo", nixos_rebuild, "dry-activate", "--flake", flake_uri],
            check=True,
            capture_output=True,
            text=True,
        )
        return CommandResult(ok=True, output=result.stdout)
    except subprocess.CalledProcessError as exc:
        return CommandResult(ok=False, output=(exc.stderr or "").strip())


def run_switch(flake_uri: str) -> CommandResult:
    nixos_rebuild = _resolve("nixos-rebuild")
    try:
        result = subprocess.run(
            ["sudo", nixos_rebuild, "switch", "--flake", flake_uri],
            check=True,
            capture_output=True,
            text=True,
        )
        return CommandResult(ok=True, output=result.stdout)
    except subprocess.CalledProcessError as exc:
        return CommandResult(ok=False, output=(exc.stderr or "").strip())


# --- Home Manager ---------------------------------------------------------


def get_current_hm_generation() -> str | None:
    user = os.environ.get("USER") or ""
    if not user:
        return None
    try:
        result = subprocess.run(
            ["readlink", f"/nix/var/nix/profiles/per-user/{user}/home-manager"],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip() or None
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def run_hm_build(flake_uri: str) -> CommandResult:
    """Home Manager has no `dry-activate`; `build` is the closest equivalent.

    It evaluates and builds the activation package without activating it.
    """
    home_manager = _resolve("home-manager")
    try:
        result = subprocess.run(
            [home_manager, "build", "--flake", flake_uri],
            check=True,
            capture_output=True,
            text=True,
        )
        return CommandResult(ok=True, output=result.stdout)
    except subprocess.CalledProcessError as exc:
        return CommandResult(ok=False, output=(exc.stderr or "").strip())


def run_hm_switch(flake_uri: str) -> CommandResult:
    home_manager = _resolve("home-manager")
    try:
        result = subprocess.run(
            [home_manager, "switch", "--flake", flake_uri],
            check=True,
            capture_output=True,
            text=True,
        )
        return CommandResult(ok=True, output=result.stdout)
    except subprocess.CalledProcessError as exc:
        return CommandResult(ok=False, output=(exc.stderr or "").strip())
