from dataclasses import dataclass
import os
import pwd
import socket
from pathlib import Path

VALID_MODES = ("nixos", "home-manager")
NIXOS_DEFAULT_DIR = Path("/etc/nixos")

# Searched, in order, after the env override and before erroring. Covers the
# common flake-in-$HOME layouts. cwd walk-up is deliberately NOT searched: an
# MCP server's cwd is usually the caller's project dir (which may carry an
# unrelated flake.nix), so it is a wrong-flake hazard. Point a nonstandard
# config at NIX_AGENT_FLAKE / NIX_AGENT_HM_FLAKE instead.
NIXOS_FALLBACK_DIRNAMES = ("nixos", ".config/nixos", "nix-config", "nixos-config")
HM_FALLBACK_DIRNAMES = (".config/home-manager", ".config/nixpkgs")


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


def _env_override(mode: str) -> str | None:
    if mode == "home-manager":
        return os.environ.get("NIX_AGENT_HM_FLAKE") or os.environ.get(
            "NIX_AGENT_FLAKE"
        )
    return os.environ.get("NIX_AGENT_FLAKE")


def flake_search_dirs(mode: str) -> list[Path]:
    home = Path.home()
    if mode == "nixos":
        return [NIXOS_DEFAULT_DIR, *(home / d for d in NIXOS_FALLBACK_DIRNAMES)]
    return [home / d for d in HM_FALLBACK_DIRNAMES]


def resolve_target(flake_uri: str | None, mode: str) -> Target:
    if mode not in VALID_MODES:
        raise TargetError(
            f"mode must be one of {list(VALID_MODES)}, got {mode!r}"
        )
    ref = flake_uri if flake_uri is not None else _env_override(mode)
    if ref is not None:
        dir_part, _, attr = ref.partition("#")
        return Target(flake_dir=dir_part, attr=attr or None, mode=mode)

    searched = flake_search_dirs(mode)
    for candidate in searched:
        if (candidate / "flake.nix").is_file():
            return Target(flake_dir=str(candidate), attr=None, mode=mode)

    env_name = "NIX_AGENT_HM_FLAKE" if mode == "home-manager" else "NIX_AGENT_FLAKE"
    searched_str = ", ".join(str(d) for d in searched)
    raise TargetError(
        f"no flake_uri given and no flake.nix found in any of: {searched_str}. "
        f"Pass flake_uri (e.g. '/home/you/nixos#host') or set ${env_name}."
    )


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


def current_hm_profile() -> str | None:
    user = current_user()
    candidates = []
    if user:
        candidates.append(
            Path(f"/nix/var/nix/profiles/per-user/{user}/home-manager")
        )
    candidates.append(
        Path.home() / ".local" / "state" / "nix" / "profiles" / "home-manager"
    )
    for path in candidates:
        if path.exists():
            return os.path.realpath(path)
    return None


def config_attr(target: Target, candidate: str) -> str:
    root = (
        "nixosConfigurations"
        if target.mode == "nixos"
        else "homeConfigurations"
    )
    return f'{target.flake_dir}#{root}."{candidate}"'
