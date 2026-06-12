from dataclasses import dataclass
import os
import pwd
import socket
from pathlib import Path

VALID_MODES = ("nixos", "home-manager")
NIXOS_DEFAULT_DIR = Path("/etc/nixos")


class TargetError(Exception):
    pass


@dataclass(frozen=True)
class Target:
    flake_dir: str
    attr: str | None
    mode: str

    @property
    def flake_ref(self) -> str:
        """For nixos-rebuild/home-manager --flake: those tools pick the
        hostname/user attribute themselves when none is given."""
        if self.attr:
            return f"{self.flake_dir}#{self.attr}"
        return self.flake_dir


def current_user() -> str | None:
    user = os.environ.get("USER")
    if user:
        return user
    try:
        return pwd.getpwuid(os.getuid()).pw_name
    except KeyError:
        return None


def resolve_target(flake_uri: str | None, mode: str) -> Target:
    if mode not in VALID_MODES:
        raise TargetError(
            f"mode must be one of {list(VALID_MODES)}, got {mode!r}"
        )
    if flake_uri is not None:
        dir_part, _, attr = flake_uri.partition("#")
        return Target(flake_dir=dir_part, attr=attr or None, mode=mode)
    if mode == "nixos":
        default_dir = NIXOS_DEFAULT_DIR
    else:
        default_dir = Path.home() / ".config" / "home-manager"
    if not (default_dir / "flake.nix").is_file():
        raise TargetError(
            f"no flake_uri given and {default_dir}/flake.nix does not exist; "
            "pass flake_uri explicitly"
        )
    return Target(flake_dir=str(default_dir), attr=None, mode=mode)


def attr_candidates(target: Target) -> list[str]:
    """Attribute names to try, in order, for nix eval / nix build
    installables (which, unlike nixos-rebuild, need an explicit attr)."""
    if target.attr:
        return [target.attr]
    host = socket.gethostname()
    if target.mode == "nixos":
        return [host]
    user = current_user()
    if not user:
        raise TargetError(
            "could not determine current user for home-manager attribute"
        )
    return [f"{user}@{host}", user]


def config_attr(target: Target, candidate: str) -> str:
    root = (
        "nixosConfigurations"
        if target.mode == "nixos"
        else "homeConfigurations"
    )
    return f'{target.flake_dir}#{root}."{candidate}"'
