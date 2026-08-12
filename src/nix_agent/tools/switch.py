import json
import os
import re
from pathlib import Path

from nix_agent import health, runner
from nix_agent.privilege import sudo_diagnosis
from nix_agent.target import (
    TargetError,
    constrain_privileged_target,
    current_hm_profile,
    resolve_target,
)
from nix_agent.tools.build import closure_diff
from nix_agent.tools.check import check

SYSTEM_PROFILE = "/nix/var/nix/profiles/system"

_NIX_ENV_LINE = re.compile(
    r"^\s*(\d+)\s+(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s*(\(current\))?\s*$"
)
_HM_LINE = re.compile(
    r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}) : id (\d+) -> (\S+)(\s+\(current\))?\s*$"
)

# Activation lines emitted by switch-to-configuration. Each lists its units
# comma-separated on one line; the last occurrence wins.
_UNIT_PATTERNS = {
    "stopped": re.compile(r"stopping the following units:\s*(.+)"),
    "started": re.compile(r"^starting the following units:\s*(.+)"),
    "restarted": re.compile(r"restarting the following units:\s*(.+)"),
    "reloaded": re.compile(r"reloading the following units:\s*(.+)"),
    "new": re.compile(r"the following new units were started:\s*(.+)"),
}
_BUILDING = re.compile(r"^\s*building '/nix/store/\S+\.drv'")


def _current_generation(mode: str) -> str | None:
    if mode == "nixos":
        path = Path(SYSTEM_PROFILE)
        return os.path.realpath(path) if path.exists() else None
    return current_hm_profile()


def _summarize_switch(output: str) -> dict[str, object]:
    """Pull the genuinely useful signal out of an activation log: which
    units changed and how many derivations were built."""
    units: dict[str, list[str]] = {}
    built = 0
    for line in output.splitlines():
        stripped = line.strip()
        if _BUILDING.match(line):
            built += 1
        for key, pattern in _UNIT_PATTERNS.items():
            match = pattern.search(stripped)
            if match:
                units[key] = [u.strip() for u in match.group(1).split(",") if u.strip()]
    summary: dict[str, object] = {"derivations_built": built}
    if units:
        summary["units"] = units
    summary["changed"] = bool(units) or built > 0
    return summary


def switch(
    flake_uri: str | None = None,
    mode: str = "nixos",
    validate: bool = False,
    full_log: bool = False,
) -> dict[str, object]:
    """Switch with no implicit validation gate; the agent composes
    check -> diff -> switch itself. rollback_generation is always
    recorded first so a bad switch can be undone.

    validate=True runs check(level='dry-build') first and aborts the
    switch if it does not pass. full_log=True returns the full activation
    log; by default a successful switch returns only a short tail plus a
    structured ``summary`` of the units that changed."""
    try:
        target = resolve_target(flake_uri, mode)
    except TargetError as exc:
        return {"status": "no_target", "error": str(exc)}

    locked = constrain_privileged_target(target, mode=mode)
    if locked is not None:
        return locked

    if validate:
        preflight = check("dry-build", flake_uri=flake_uri, mode=mode)
        if preflight.get("status") != "ok":
            return {
                "status": "preflight_failed",
                "resolved_target": target.flake_ref,
                "stage": "dry-build",
                "preflight": preflight,
                "first_error": preflight.get("first_error"),
            }

    rollback = _current_generation(mode)
    pre_failed, health_note = health.failed_units(mode)
    if mode == "nixos":
        nixos_rebuild = runner.resolve_binary("nixos-rebuild") or "nixos-rebuild"
        argv = ["sudo", nixos_rebuild, "switch", "--flake", target.flake_ref]
    else:
        argv = ["home-manager", "switch", "--flake", target.flake_ref]
    result = runner.run(argv)

    extra: dict[str, object] = {
        "rollback_generation": rollback,
        "current_generation": _current_generation(mode),
    }
    if result.ok:
        summary = _summarize_switch(result.output)
        new_gen = extra["current_generation"]
        if rollback and new_gen and rollback != new_gen:
            # new_gen comes out of a dict[str, object]; cast for typing only
            _, packages = closure_diff(rollback, str(new_gen))
            if packages is not None:
                summary["packages"] = packages
        report = health.health_report(pre_failed, mode)
        if report is not None:
            summary["health"] = report
        else:
            extra["health_note"] = (
                health_note
                or "post-activation systemctl snapshot unavailable; health diff skipped"
            )
        extra["summary"] = summary
        if not full_log:
            extra["output"] = runner.tail(result.output)
            extra["log_truncated"] = extra["output"] != result.output
        return runner.envelope("ok", target.flake_ref, result, **extra)

    diagnosis = sudo_diagnosis(argv, result.output)
    if diagnosis is not None:
        extra["privilege"] = diagnosis
    drv_info = runner.failed_derivation_info(result.output)
    if drv_info is not None:
        extra["failed_derivation"] = drv_info
    return runner.envelope("failed", target.flake_ref, result, **extra)


def _nixos_profile_link(gen_id: object) -> str:
    return f"{SYSTEM_PROFILE}-{gen_id}-link"


def _attach_nixos_path(entry: dict[str, object]) -> dict[str, object]:
    gen_id = entry.get("id")
    if gen_id is None:
        return entry
    link = _nixos_profile_link(gen_id)
    if os.path.exists(link):
        entry["path"] = os.path.realpath(link)
    return entry


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
                _attach_nixos_path(
                    {
                        "id": entry.get("generation"),
                        "date": entry.get("date"),
                        "current": bool(entry.get("current")),
                    }
                )
                for entry in entries
            ]
            return runner.envelope("ok", SYSTEM_PROFILE, result, generations=gens)
    return _list_nixos_nix_env()


def _list_nixos_nix_env() -> dict[str, object]:
    """Fallback for nixos-rebuild too old for list-generations; nix-env
    needs a readable profile dir, which may require privileges."""
    result = runner.run(["nix-env", "--list-generations", "-p", SYSTEM_PROFILE])
    if not result.ok:
        return runner.envelope("failed", SYSTEM_PROFILE, result)
    gens = []
    for line in result.stdout.splitlines():
        match = _NIX_ENV_LINE.match(line)
        if match:
            gens.append(
                _attach_nixos_path(
                    {
                        "id": int(match.group(1)),
                        "date": match.group(2),
                        "current": match.group(3) is not None,
                    }
                )
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
    envelope = runner.envelope("ok", "home-manager profile", result, generations=gens)
    return envelope, gens


def _generation_id(generation: object) -> int | None:
    if isinstance(generation, bool):
        return None
    if isinstance(generation, int):
        return generation
    if isinstance(generation, str) and generation.isdigit():
        return int(generation)
    return None


def _match_generation(
    gens: list[dict[str, object]], generation: object
) -> dict[str, object] | None:
    want_id = _generation_id(generation)
    wanted = str(generation)
    for entry in gens:
        if want_id is not None and entry.get("id") == want_id:
            return entry
        if entry.get("path") == wanted:
            return entry
        gen_id = entry.get("id")
        if gen_id is None:
            continue
        link = _nixos_profile_link(gen_id)
        if wanted == link:
            return entry
        if os.path.lexists(link) and os.path.realpath(link) == wanted:
            return entry
        if os.path.lexists(wanted) and os.path.realpath(wanted) == entry.get("path"):
            return entry
    return None


def _unknown_generation(generation: object) -> dict[str, object]:
    return {
        "status": "unknown_generation",
        "error": f"generation {generation!r} does not match any listed generation",
    }


def _rollback_nixos_untargeted() -> dict[str, object]:
    nixos_rebuild = runner.resolve_binary("nixos-rebuild") or "nixos-rebuild"
    argv = ["sudo", nixos_rebuild, "switch", "--rollback"]
    result = runner.run(argv)
    extra: dict[str, object] = {
        "current_generation": _current_generation("nixos"),
    }
    if not result.ok:
        diagnosis = sudo_diagnosis(argv, result.output)
        if diagnosis is not None:
            extra["privilege"] = diagnosis
    return runner.envelope(
        "ok" if result.ok else "failed",
        SYSTEM_PROFILE,
        result,
        **extra,
    )


def _rollback_nixos_targeted(matched: dict[str, object]) -> dict[str, object]:
    nix_env = runner.resolve_binary("nix-env") or "nix-env"
    step1 = [
        "sudo",
        nix_env,
        "-p",
        SYSTEM_PROFILE,
        "--switch-generation",
        str(matched["id"]),
    ]
    result1 = runner.run(step1)
    if not result1.ok:
        extra: dict[str, object] = {}
        diagnosis = sudo_diagnosis(step1, result1.output)
        if diagnosis is not None:
            extra["privilege"] = diagnosis
        return runner.envelope("failed", SYSTEM_PROFILE, result1, **extra)

    step2 = [
        "sudo",
        f"{SYSTEM_PROFILE}/bin/switch-to-configuration",
        "switch",
    ]
    result2 = runner.run(step2)
    extra = {"current_generation": _current_generation("nixos")}
    if not result2.ok:
        extra["note"] = "profile advanced but activation did not"
        diagnosis = sudo_diagnosis(step2, result2.output)
        if diagnosis is not None:
            extra["privilege"] = diagnosis
        return runner.envelope("failed", SYSTEM_PROFILE, result2, **extra)
    return runner.envelope("ok", SYSTEM_PROFILE, result2, **extra)


def _rollback_hm(
    gens: list[dict[str, object]], generation: int | str | None
) -> dict[str, object]:
    if generation is not None:
        matched = _match_generation(gens, generation)
        if matched is None:
            return _unknown_generation(generation)
        previous = matched
    else:
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


def generations(
    action: str = "list",
    mode: str = "nixos",
    generation: int | str | None = None,
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
        if generation is None:
            return _rollback_nixos_untargeted()
        listed = _list_nixos()
        if listed.get("status") != "ok":
            return listed
        gens = list(listed.get("generations") or [])
        matched = _match_generation(gens, generation)
        if matched is None:
            return _unknown_generation(generation)
        return _rollback_nixos_targeted(matched)

    envelope, gens = _list_hm()
    if envelope.get("status") != "ok":
        return envelope
    return _rollback_hm(gens, generation)
