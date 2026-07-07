import json

from nix_agent import runner
from nix_agent.target import Target, TargetError, resolve_target
from nix_agent.tools.build import build_closure

LEVELS = ("lint", "flake", "dry-build", "dry-activate")


def _parse_statix(stdout: str) -> list[dict[str, object]]:
    text = stdout.strip()
    if not text:
        return []
    decoder = json.JSONDecoder()
    entries: list[object] = []
    idx = 0
    while idx < len(text):
        try:
            obj, end = decoder.raw_decode(text, idx)
        except json.JSONDecodeError:
            break
        entries.extend(obj if isinstance(obj, list) else [obj])
        idx = end
        while idx < len(text) and text[idx].isspace():
            idx += 1
    if not entries:
        return [
            {
                "tool": "statix",
                "file": None,
                "line": None,
                "column": None,
                "severity": "unknown",
                "message": text,
            }
        ]
    findings: list[dict[str, object]] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        file = entry.get("file")
        for report in entry.get("report", []):
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
    crashed: list[str] = []
    raw_total = 0

    for name, argv, parse in (
        ("statix", [statix, "check", "-o", "json", target.flake_dir], _parse_statix),
        (
            "deadnix",
            [deadnix, "--output-format", "json", target.flake_dir],
            _parse_deadnix,
        ),
    ):
        result = runner.run(argv)
        commands.append(result.command)
        outputs.append(result.output)
        raw_total += (
            result.raw_bytes
            if result.raw_bytes is not None
            else len(result.stdout) + len(result.stderr)
        )
        if not result.ok and not result.stdout.strip():
            crashed.append(name)
            continue
        findings.extend(parse(result.stdout))

    output = "\n".join(o for o in outputs if o)
    if crashed:
        return runner.account(
            {
                "status": "failed",
                "resolved_target": target.flake_dir,
                "commands": commands,
                "output": output,
                "error": (
                    f"linter crashed (non-zero exit, no output): {', '.join(crashed)}"
                ),
                "first_error": runner.extract_first_error(output),
                "findings": findings,
                "finding_count": len(findings),
                "raw_bytes": raw_total,
            }
        )
    return runner.account(
        {
            "status": "ok",
            "resolved_target": target.flake_dir,
            "commands": commands,
            "output": output,
            "findings": findings,
            "finding_count": len(findings),
            "raw_bytes": raw_total,
        }
    )


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
    return runner.envelope("ok" if result.ok else "failed", target.flake_ref, result)
