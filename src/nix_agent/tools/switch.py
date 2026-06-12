import os
import re
from pathlib import Path

from nix_agent import runner
from nix_agent.target import TargetError, current_user, resolve_target

SYSTEM_PROFILE = "/nix/var/nix/profiles/system"

_NIX_ENV_LINE = re.compile(
    r"^\s*(\d+)\s+(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s*(\(current\))?\s*$"
)
_HM_LINE = re.compile(
    r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}) : id (\d+) -> (\S+)$"
)


def _current_generation(mode: str) -> str | None:
    if mode == "nixos":
        path = Path(SYSTEM_PROFILE)
        return os.path.realpath(path) if path.exists() else None
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


def switch(
    flake_uri: str | None = None, mode: str = "nixos"
) -> dict[str, object]:
    """Switch with no implicit validation gate; the agent composes
    check -> diff -> switch itself. rollback_generation is always
    recorded first so a bad switch can be undone."""
    try:
        target = resolve_target(flake_uri, mode)
    except TargetError as exc:
        return {"status": "no_target", "error": str(exc)}

    rollback = _current_generation(mode)
    if mode == "nixos":
        nixos_rebuild = runner.resolve_binary("nixos-rebuild") or "nixos-rebuild"
        argv = ["sudo", nixos_rebuild, "switch", "--flake", target.flake_ref]
    else:
        argv = ["home-manager", "switch", "--flake", target.flake_ref]
    result = runner.run(argv)
    return runner.envelope(
        "ok" if result.ok else "failed",
        target.flake_ref,
        result,
        rollback_generation=rollback,
        current_generation=_current_generation(mode),
    )


def _list_nixos() -> dict[str, object]:
    result = runner.run(
        ["nix-env", "--list-generations", "-p", SYSTEM_PROFILE]
    )
    if not result.ok:
        return runner.envelope("failed", SYSTEM_PROFILE, result)
    gens = []
    for line in result.stdout.splitlines():
        match = _NIX_ENV_LINE.match(line)
        if match:
            gens.append(
                {
                    "id": int(match.group(1)),
                    "date": match.group(2),
                    "current": match.group(3) is not None,
                }
            )
    return runner.envelope("ok", SYSTEM_PROFILE, result, generations=gens)


def _list_hm() -> tuple[dict[str, object], list[dict[str, object]]]:
    result = runner.run(["home-manager", "generations"])
    if not result.ok:
        return runner.envelope("failed", "home-manager profile", result), []
    gens = []
    for i, line in enumerate(result.stdout.splitlines()):
        match = _HM_LINE.match(line.strip())
        if match:
            gens.append(
                {
                    "id": int(match.group(2)),
                    "date": match.group(1),
                    "path": match.group(3),
                    "current": i == 0,
                }
            )
    envelope = runner.envelope(
        "ok", "home-manager profile", result, generations=gens
    )
    return envelope, gens


def generations(
    action: str = "list", mode: str = "nixos"
) -> dict[str, object]:
    if action not in ("list", "rollback"):
        return {
            "status": "invalid_action",
            "error": f"action must be 'list' or 'rollback', got {action!r}",
        }
    if mode not in ("nixos", "home-manager"):
        return {
            "status": "no_target",
            "error": f"mode must be 'nixos' or 'home-manager', got {mode!r}",
        }

    if action == "list":
        if mode == "nixos":
            return _list_nixos()
        envelope, _ = _list_hm()
        return envelope

    if mode == "nixos":
        nixos_rebuild = runner.resolve_binary("nixos-rebuild") or "nixos-rebuild"
        result = runner.run(["sudo", nixos_rebuild, "switch", "--rollback"])
        return runner.envelope(
            "ok" if result.ok else "failed",
            SYSTEM_PROFILE,
            result,
            current_generation=_current_generation(mode),
        )
    _, gens = _list_hm()
    if len(gens) < 2:
        return {
            "status": "failed",
            "resolved_target": "home-manager profile",
            "error": "no previous home-manager generation to roll back to",
        }
    previous = gens[1]
    result = runner.run([f"{previous['path']}/activate"])
    return runner.envelope(
        "ok" if result.ok else "failed",
        "home-manager profile",
        result,
        activated_generation=previous,
    )
