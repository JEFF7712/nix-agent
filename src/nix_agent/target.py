from dataclasses import dataclass
import os
import pwd
import socket
from pathlib import Path

VALID_MODES = ("nixos", "home-manager")
NIXOS_DEFAULT_DIR = Path("/etc/nixos")
ALLOW_REMOTE_ENV = "NIX_AGENT_ALLOW_REMOTE"
_TRUTHY = frozenset({"1", "true", "yes", "on"})
_REMOTE_PREFIXES = (
    "github:",
    "gitlab:",
    "sourcehut:",
    "git+",
    "http://",
    "https://",
    "ssh://",
    "flake:",
)

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
        return os.environ.get("NIX_AGENT_HM_FLAKE") or os.environ.get("NIX_AGENT_FLAKE")
    return os.environ.get("NIX_AGENT_FLAKE")


def flake_search_dirs(mode: str) -> list[Path]:
    home = Path.home()
    if mode == "nixos":
        return [NIXOS_DEFAULT_DIR, *(home / d for d in NIXOS_FALLBACK_DIRNAMES)]
    return [home / d for d in HM_FALLBACK_DIRNAMES]


def resolve_target(flake_uri: str | None, mode: str) -> Target:
    if mode not in VALID_MODES:
        raise TargetError(f"mode must be one of {list(VALID_MODES)}, got {mode!r}")
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
        raise TargetError("could not determine current user for home-manager attribute")
    return [f"{user}@{host}", user]


def matched_hosts(guess: str, hosts: list[str]) -> list[str]:
    """Flake config names to try after `guess` was missing.

    Unique flake name, or a unique prefix/suffix/FQDN match. Empty means
    ambiguous or none — callers should surface `unknown_host`.
    """
    if not hosts:
        return []
    if guess in hosts:
        return [guess]
    if len(hosts) == 1:
        return [hosts[0]]
    needle = guess.lower()
    hits: list[str] = []
    for host in hosts:
        hay = host.lower()
        if (
            hay.startswith(needle)
            or needle.startswith(hay)
            or hay.endswith(needle)
            or needle.endswith(hay)
            or hay.split(".", 1)[0] == needle
            or needle.split(".", 1)[0] == hay
        ):
            hits.append(host)
    if len(hits) == 1:
        return hits
    return []


def unknown_host_envelope(
    *,
    hostname: str,
    hosts: list[str],
    flake_dir: str,
    mode: str,
) -> dict[str, object]:
    root = "nixosConfigurations" if mode == "nixos" else "homeConfigurations"
    example = hosts[0] if hosts else "host"
    return {
        "status": "unknown_host",
        "error": f"flake {flake_dir!r} has no {root} matching {hostname!r}",
        "hostname": hostname,
        "hosts": hosts,
        "hint": (
            f"pass flake_uri with an explicit attribute "
            f"(e.g. '{flake_dir}#{example}') or set $NIX_AGENT_FLAKE"
        ),
    }


def hm_user_attr(attr: str) -> str | None:
    """NixOS-mode rewrite of an HM option onto home-manager.users.<user>."""
    if attr.startswith("home-manager.users."):
        return None
    user = current_user()
    if not user:
        return None
    return f"home-manager.users.{user}.{attr}"


def current_hm_profile() -> str | None:
    user = current_user()
    candidates = []
    if user:
        candidates.append(Path(f"/nix/var/nix/profiles/per-user/{user}/home-manager"))
    candidates.append(
        Path.home() / ".local" / "state" / "nix" / "profiles" / "home-manager"
    )
    for path in candidates:
        if path.exists():
            return os.path.realpath(path)
    return None


def config_attr(target: Target, candidate: str) -> str:
    root = "nixosConfigurations" if target.mode == "nixos" else "homeConfigurations"
    return f'{target.flake_dir}#{root}."{candidate}"'


def is_remote_flake_ref(dir_part: str) -> bool:
    return dir_part.startswith(_REMOTE_PREFIXES)


def _allow_remote() -> bool:
    raw = os.environ.get(ALLOW_REMOTE_ENV)
    if raw is None:
        return False
    return raw.strip().lower() in _TRUTHY


def _lock_pin(mode: str) -> str | None:
    if mode == "home-manager":
        return os.environ.get("NIX_AGENT_HM_FLAKE")
    return os.environ.get("NIX_AGENT_FLAKE")


_DOT_REFS = frozenset({".", "./"})


def prepare_privileged_target(target: Target, *, mode: str) -> Target | dict:
    """Absolute local target for switch / dry-activate, or an early-exit
    envelope. Resolves `.` / `./` to the pin directory when one is set."""
    dir_part = target.flake_dir
    remote = is_remote_flake_ref(dir_part)
    if remote and not _allow_remote():
        return {
            "status": "remote_ref_rejected",
            "error": (
                f"privileged operations do not accept remote flake refs ({dir_part!r})"
            ),
            "hint": "clone the repository locally and pin that directory",
        }

    pin = _lock_pin(mode)
    pin_resolved = None
    if pin:
        pin_dir, _, _ = pin.partition("#")
        pin_resolved = os.path.realpath(os.path.expanduser(pin_dir))

    if remote:
        resolved = dir_part
    else:
        expanded = os.path.expanduser(dir_part)
        if not os.path.isabs(expanded):
            if pin_resolved is not None and dir_part in _DOT_REFS:
                resolved = pin_resolved
            else:
                resolved = os.path.realpath(expanded)
                if pin_resolved is None:
                    search = {
                        os.path.realpath(str(candidate))
                        for candidate in flake_search_dirs(mode)
                        if candidate.is_dir()
                    }
                    if resolved not in search:
                        return {
                            "status": "no_target",
                            "error": (
                                "privileged operations require an absolute flake "
                                f"path, got {dir_part!r}"
                            ),
                            "hint": (
                                "set $NIX_AGENT_FLAKE or pass an absolute flake_uri"
                            ),
                        }
        else:
            resolved = os.path.realpath(expanded)

    if pin_resolved is not None and pin_resolved != resolved:
        return {
            "status": "target_locked",
            "error": f"privileged operations are locked to {pin}",
            "pin": pin,
        }

    if not remote:
        flake_nix = os.path.join(resolved, "flake.nix")
        if not os.path.isdir(resolved) or not os.path.isfile(flake_nix):
            return {
                "status": "no_target",
                "error": f"{resolved} is not a directory containing flake.nix",
            }

    if resolved == dir_part:
        return target
    return Target(flake_dir=resolved, attr=target.attr, mode=target.mode)


def constrain_privileged_target(target: Target, *, mode: str) -> dict | None:
    """Early-exit envelope for switch / dry-activate, or None to proceed."""
    prepared = prepare_privileged_target(target, mode=mode)
    if isinstance(prepared, Target):
        return None
    return prepared
