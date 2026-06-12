import json

from nix_agent import runner
from nix_agent.target import Target, TargetError, resolve_target
from nix_agent.tools.build import build_closure

LEVELS = ("lint", "flake", "dry-build", "dry-activate")


def _parse_statix(stdout: str) -> list[dict[str, object]]:
    if not stdout.strip():
        return []
    try:
        entry = json.loads(stdout)
    except json.JSONDecodeError:
        return [
            {
                "tool": "statix",
                "file": None,
                "line": None,
                "column": None,
                "severity": "unknown",
                "message": "not json: " + stdout.strip(),
            }
        ]
    # statix emits a single object; normalise to list for uniform iteration
    entries = entry if isinstance(entry, list) else [entry]
    findings: list[dict[str, object]] = []
    for ent in entries:
        file = ent.get("file")
        for report in ent.get("report", []):
            note = report.get("note", "")
            severity = report.get("severity", "Warn")
            for diag in report.get("diagnostics", []):
                at = diag.get("at", {}).get("from", {})
                findings.append(
                    {
                        "tool": "statix",
                        "file": file,
                        "line": at.get("line"),
                        "column": at.get("column"),
                        "severity": severity,
                        "message": diag.get("message") or note,
                    }
                )
    return findings


def _parse_deadnix(stdout: str) -> list[dict[str, object]]:
    findings: list[dict[str, object]] = []
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        for item in entry.get("results", []):
            findings.append(
                {
                    "tool": "deadnix",
                    "file": entry.get("file"),
                    "line": item.get("line"),
                    "column": item.get("column"),
                    "severity": "warning",
                    "message": item.get("message"),
                }
            )
    return findings


def _lint(target: Target) -> dict[str, object]:
    statix = runner.resolve_binary("statix")
    deadnix = runner.resolve_binary("deadnix")
    missing = [
        name
        for name, path in (("statix", statix), ("deadnix", deadnix))
        if path is None
    ]
    if missing:
        return {
            "status": "tool_missing",
            "resolved_target": target.flake_dir,
            "missing": missing,
            "error": f"lint tools not on PATH: {', '.join(missing)}",
        }

    findings: list[dict[str, object]] = []
    commands: list[list[str]] = []
    outputs: list[str] = []

    statix_result = runner.run([statix, "check", "-o", "json", target.flake_dir])
    commands.append(statix_result.command)
    outputs.append(statix_result.output)
    findings.extend(_parse_statix(statix_result.stdout))

    deadnix_result = runner.run(
        [deadnix, "--output-format", "json", target.flake_dir]
    )
    commands.append(deadnix_result.command)
    outputs.append(deadnix_result.output)
    findings.extend(_parse_deadnix(deadnix_result.stdout))

    return {
        "status": "ok",
        "resolved_target": target.flake_dir,
        "command": commands,
        "output": "\n".join(o for o in outputs if o),
        "findings": findings,
        "finding_count": len(findings),
    }


def check(
    level: str,
    flake_uri: str | None = None,
    mode: str = "nixos",
) -> dict[str, object]:
    """Validation ladder, fast to slow: lint -> flake -> dry-build ->
    dry-activate. Linters exiting non-zero just means findings exist;
    status stays 'ok' with structured findings attached."""
    if level not in LEVELS:
        return {
            "status": "invalid_level",
            "error": f"level must be one of {list(LEVELS)}, got {level!r}",
        }
    try:
        target = resolve_target(flake_uri, mode)
    except TargetError as exc:
        return {"status": "no_target", "error": str(exc)}

    if level == "lint":
        return _lint(target)

    if level == "flake":
        result = runner.run(["nix", "flake", "check", target.flake_dir])
        return runner.envelope(
            "ok" if result.ok else "failed", target.flake_dir, result
        )

    if level == "dry-build":
        return build_closure(target, dry_run=True)

    # dry-activate
    if target.mode == "home-manager":
        return {
            "status": "not_applicable",
            "resolved_target": target.flake_ref,
            "hint": "home-manager has no dry-activate; use level='dry-build'",
        }
    nixos_rebuild = runner.resolve_binary("nixos-rebuild") or "nixos-rebuild"
    result = runner.run(
        ["sudo", nixos_rebuild, "dry-activate", "--flake", target.flake_ref]
    )
    return runner.envelope(
        "ok" if result.ok else "failed", target.flake_ref, result
    )
