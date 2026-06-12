import json
import os
import re
from pathlib import Path

from nix_agent import runner
from nix_agent.target import TargetError, current_hm_profile, resolve_target

SYSTEM_PROFILE = "/nix/var/nix/profiles/system"

_NIX_ENV_LINE = re.compile(
    r"^\s*(\d+)\s+(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s*(\(current\))?\s*$"
)
_HM_LINE = re.compile(
    r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}) : id (\d+) -> (\S+)(\s+\(current\))?\s*$"
)


def _current_generation(mode: str) -> str | None:
    if mode == "nixos":
        path = Path(SYSTEM_PROFILE)
        return os.path.realpath(path) if path.exists() else None
    return current_hm_profile()


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
    nixos_rebuild = runner.resolve_binary("nixos-rebuild") or "nixos-rebuild"
    result = runner.run([nixos_rebuild, "list-generations", "--json"])
    if result.ok:
        try:
            entries = json.loads(result.stdout)
        except json.JSONDecodeError:
            entries = None
        if isinstance(entries, list):
            gens = [
                {
                    "id": entry.get("generation"),
                    "date": entry.get("date"),
                    "current": bool(entry.get("current")),
                }
                for entry in entries
            ]
            return runner.envelope(
                "ok", SYSTEM_PROFILE, result, generations=gens
            )
    return _list_nixos_nix_env()


def _list_nixos_nix_env() -> dict[str, object]:
    """Fallback for nixos-rebuild too old for list-generations; nix-env
    needs a readable profile dir, which may require privileges."""
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
    for line in result.stdout.splitlines():
        match = _HM_LINE.match(line.strip())
        if match:
            gens.append(
                {
                    "id": int(match.group(2)),
                    "date": match.group(1),
                    "path": match.group(3),
                    "current": match.group(4) is not None,
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
    current_index = next((i for i, g in enumerate(gens) if g["current"]), 0)
    if current_index + 1 >= len(gens):
        return {
            "status": "failed",
            "resolved_target": "home-manager profile",
            "error": "no previous home-manager generation to roll back to",
        }
    previous = gens[current_index + 1]
    result = runner.run([f"{previous['path']}/activate"])
    return runner.envelope(
        "ok" if result.ok else "failed",
        "home-manager profile",
        result,
        activated_generation=previous,
    )
