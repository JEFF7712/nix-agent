from pathlib import Path

from nix_agent import runner
from nix_agent.target import TargetError, resolve_target


def _format_with_nixfmt(paths: list[str]) -> dict[str, object]:
    nixfmt = runner.resolve_binary("nixfmt")
    if nixfmt is None:
        return {
            "status": "tool_missing",
            "missing": ["nixfmt"],
            "error": "nixfmt not on PATH",
        }
    nix_paths = [p for p in paths if p.endswith(".nix")]
    skipped = [p for p in paths if not p.endswith(".nix")]
    results = []
    ok = True
    for path in nix_paths:
        result = runner.run([nixfmt, path])
        ok = ok and result.ok
        results.append(
            {"path": path, "ok": result.ok, "output": result.output}
        )
    return {
        "status": "ok" if ok else "failed",
        "formatter": "nixfmt",
        "results": results,
        "skipped": skipped,
    }


def _format_dir_with_nixfmt(flake_dir: str) -> dict[str, object]:
    nixfmt = runner.resolve_binary("nixfmt")
    if nixfmt is None:
        return {
            "status": "tool_missing",
            "missing": ["nixfmt"],
            "error": "nixfmt not on PATH",
        }
    all_nix = sorted(str(p) for p in Path(flake_dir).rglob("*.nix"))
    if not all_nix:
        return {
            "status": "ok",
            "formatter": "nixfmt",
            "results": [],
            "skipped": [],
        }
    result = runner.run([nixfmt, *all_nix])
    return {
        "status": "ok" if result.ok else "failed",
        "formatter": "nixfmt",
        "command": result.command,
        "output": result.output,
        "results": [{"path": p, "ok": result.ok} for p in all_nix],
        "skipped": [],
    }


def format_nix(
    paths: list[str] | None = None,
    flake_uri: str | None = None,
    mode: str = "nixos",
) -> dict[str, object]:
    """Format .nix files. Explicit paths -> nixfmt per file. Whole flake
    -> `nix fmt` (respects the flake's own formatter), falling back to
    nixfmt over every .nix file when the flake defines no formatter."""
    if paths:
        return _format_with_nixfmt(paths)

    try:
        target = resolve_target(flake_uri, mode)
    except TargetError as exc:
        return {"status": "no_target", "error": str(exc)}

    result = runner.run(["nix", "fmt"], cwd=target.flake_dir)
    if result.ok:
        return runner.envelope(
            "ok", target.flake_dir, result, formatter="nix fmt"
        )
    if "does not provide attribute" not in result.output:
        return runner.envelope(
            "failed", target.flake_dir, result, formatter="nix fmt"
        )

    response = _format_dir_with_nixfmt(target.flake_dir)
    response["resolved_target"] = target.flake_dir
    return response
