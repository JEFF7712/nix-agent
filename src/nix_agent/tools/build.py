import os
from pathlib import Path

from nix_agent import hostattr, logparse, runner
from nix_agent.target import (
    VALID_MODES,
    Target,
    TargetError,
    attr_candidates,
    config_attr,
    current_hm_profile,
    resolve_target,
)


def closure_installable(target: Target, candidate: str) -> str:
    if target.mode == "nixos":
        return f"{config_attr(target, candidate)}.config.system.build.toplevel"
    return f"{config_attr(target, candidate)}.activationPackage"


@runner.logged_operation
def build_closure(target: Target, dry_run: bool = False) -> dict[str, object]:
    """Shared by build(), diff(), and check(level='dry-build')."""
    pending = list(attr_candidates(target))
    tried: list[str] = []
    installable = ""
    result = runner.RunResult(ok=False, command=[], stdout="", stderr="")
    idx = 0
    while idx < len(pending):
        candidate = pending[idx]
        tried.append(candidate)
        installable = closure_installable(target, candidate)
        argv = ["nix", "build", "--no-link"]
        if dry_run:
            argv.append("--dry-run")
        else:
            argv.append("--print-out-paths")
        argv.append(installable)
        result = runner.run(argv)
        if result.ok:
            if dry_run:
                return runner.envelope("ok", installable, result)
            lines = result.stdout.strip().splitlines()
            if not lines:
                return runner.envelope("failed", installable, result)
            return runner.envelope("ok", installable, result, store_path=lines[-1])
        if hostattr.missing_flake_attr(result.output):
            if idx < len(pending) - 1:
                idx += 1
                continue
            more, unknown = hostattr.extra_hosts_or_unknown(target, tried)
            if more:
                pending.extend(more)
                idx += 1
                continue
            if unknown is not None:
                return unknown
        break
    extra: dict[str, object] = {}
    drv_info = runner.failed_derivation_info(result.output)
    if drv_info is not None:
        extra["failed_derivation"] = drv_info
    return runner.envelope("failed", installable, result, **extra)


def build(
    flake_uri: str | None = None,
    mode: str = "nixos",
    job_id: str | None = None,
    log_offset: int | None = None,
) -> dict[str, object]:
    from nix_agent import jobs

    if job_id is not None:
        return jobs.status(job_id, log_offset=log_offset)
    try:
        target = resolve_target(flake_uri, mode)
    except TargetError as exc:
        return {"status": "no_target", "error": str(exc)}
    return jobs.start(target)


def _current_closure(mode: str) -> str | None:
    if mode == "nixos":
        path = Path("/run/current-system")
        return os.path.realpath(path) if path.exists() else None
    return current_hm_profile()


def closure_diff(
    old_path: str, new_path: str
) -> tuple[runner.RunResult, dict[str, list[dict[str, str]]] | None]:
    """Diff two closures; structured packages when the output parses.
    diff-closures prints nothing for identical closures, so whitespace-only
    output counts as an empty diff rather than a parse failure. In practice
    this rule only fires for diff-closures: nvd always prints at least a
    header, so it never hits the whitespace-only path, and treating it the
    same way is harmless."""
    nvd = runner.resolve_binary("nvd")
    if nvd:
        argv = [nvd, "diff", old_path, new_path]
        parse = logparse.parse_nvd
    else:
        argv = ["nix", "store", "diff-closures", old_path, new_path]
        parse = logparse.parse_diff_closures
    result = runner.run(argv)
    if not result.ok:
        return result, None
    if not result.output.strip():
        return result, {"added": [], "removed": [], "changed": []}
    return result, parse(result.output)


def diff(
    flake_uri: str | None = None,
    mode: str = "nixos",
    store_path: str | None = None,
    against: str | None = None,
) -> dict[str, object]:
    """Diff a built closure (or freshly built target closure) against the
    live system or an explicit ``against`` baseline closure."""
    if mode not in VALID_MODES:
        return {
            "status": "no_target",
            "error": f"mode must be one of {list(VALID_MODES)}, got {mode!r}",
        }

    built: dict[str, object] | None = None
    build_raw_bytes = 0
    if store_path is not None:
        if not store_path.strip() or not os.path.exists(store_path):
            return {
                "status": "failed",
                "error": f"store_path does not exist: {store_path!r}",
                "store_path": store_path,
            }
        new_path = os.path.realpath(store_path)
        resolved_target = flake_uri if flake_uri is not None else new_path
    else:
        try:
            target = resolve_target(flake_uri, mode)
        except TargetError as exc:
            return {"status": "no_target", "error": str(exc)}

        built = build_closure(target)
        if built["status"] != "ok":
            return built
        new_path = str(built["store_path"])
        resolved_target = str(built["resolved_target"])
        if isinstance(built.get("raw_bytes"), int):
            build_raw_bytes = int(built["raw_bytes"])  # type: ignore[arg-type]

    if against is not None:
        if not against.strip() or not os.path.exists(against):
            return {
                "status": "failed",
                "resolved_target": resolved_target,
                "error": f"baseline closure does not exist: {against!r}",
                "store_path": new_path,
            }
        current: str | None = os.path.realpath(against)
    else:
        current = _current_closure(mode)
        if current is None:
            failure: dict[str, object] = {
                "status": "failed",
                "resolved_target": resolved_target,
                "error": f"could not locate the current {mode} closure to diff against",
                "store_path": new_path,
            }
            if built is not None:
                failure["command"] = built["command"]
                failure["output"] = built["output"]
            return failure

    result, packages = closure_diff(current, new_path)
    diff_raw_bytes = (
        result.raw_bytes
        if result.raw_bytes is not None
        else len(result.stdout) + len(result.stderr)
    )
    extra: dict[str, object] = {"store_path": new_path, "current_closure": current}
    if not result.ok:
        response = runner.envelope("failed", resolved_target, result, **extra)
        response["raw_bytes"] = build_raw_bytes + diff_raw_bytes
        return runner.account(response)
    if packages is None:
        extra["diff"] = result.output
    else:
        extra["packages"] = packages
        closure_size = _closure_size(result.output)
        if closure_size is not None:
            extra["closure_size"] = closure_size
    response = runner.envelope("ok", resolved_target, result, **extra)
    # The parsed packages (or the raw diff) already carry the output.
    del response["output"]
    response["raw_bytes"] = build_raw_bytes + diff_raw_bytes
    return runner.account(response)


def _closure_size(output: str) -> str | None:
    for line in reversed(output.splitlines()):
        stripped = line.strip()
        if stripped.startswith("Closure size:"):
            return stripped.removeprefix("Closure size:").strip()
    return None
