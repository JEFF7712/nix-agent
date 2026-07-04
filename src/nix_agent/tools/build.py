import os
from pathlib import Path

from nix_agent import runner
from nix_agent.target import (
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


def build_closure(target: Target, dry_run: bool = False) -> dict[str, object]:
    """Shared by build(), diff(), and check(level='dry-build')."""
    candidates = attr_candidates(target)
    installable = ""
    result = runner.RunResult(ok=False, command=[], stdout="", stderr="")
    for i, candidate in enumerate(candidates):
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
        if "does not provide attribute" in result.output and i < len(candidates) - 1:
            continue
        break
    extra: dict[str, object] = {}
    info = runner.failed_derivation_info(result.output)
    if info is not None:
        extra["failed_derivation"] = info
    return runner.envelope("failed", installable, result, **extra)


def build(
    flake_uri: str | None = None,
    mode: str = "nixos",
) -> dict[str, object]:
    try:
        target = resolve_target(flake_uri, mode)
    except TargetError as exc:
        return {"status": "no_target", "error": str(exc)}
    return build_closure(target)


def _current_closure(mode: str) -> str | None:
    if mode == "nixos":
        path = Path("/run/current-system")
        return os.path.realpath(path) if path.exists() else None
    return current_hm_profile()


def diff(flake_uri: str | None = None, mode: str = "nixos") -> dict[str, object]:
    """Diff the freshly built closure against the live system."""
    try:
        target = resolve_target(flake_uri, mode)
    except TargetError as exc:
        return {"status": "no_target", "error": str(exc)}

    built = build_closure(target)
    if built["status"] != "ok":
        return built
    new_path = str(built["store_path"])

    current = _current_closure(mode)
    if current is None:
        return {
            "status": "failed",
            "resolved_target": built["resolved_target"],
            "command": built["command"],
            "output": built["output"],
            "error": f"could not locate the current {mode} closure to diff against",
            "store_path": new_path,
        }

    nvd = runner.resolve_binary("nvd")
    if nvd:
        argv = [nvd, "diff", current, new_path]
    else:
        argv = ["nix", "store", "diff-closures", current, new_path]
    result = runner.run(argv)
    status = "ok" if result.ok else "failed"
    return runner.envelope(
        status,
        str(built["resolved_target"]),
        result,
        diff=result.output,
        store_path=new_path,
        current_closure=current,
    )
