"""Failed-unit snapshots around a switch. Everything degrades to a note;
health probing must never fail a switch envelope."""

import json

from nix_agent import runner

JOURNAL_LINES = 20


def _systemctl(mode: str) -> list[str]:
    if mode == "home-manager":
        return ["systemctl", "--user"]
    return ["systemctl"]


def failed_units(mode: str) -> tuple[list[str] | None, str | None]:
    """Sorted names of currently failed units, or (None, note) when
    undetectable."""
    result = runner.run(_systemctl(mode) + ["--failed", "--output=json", "--no-pager"])
    if result.ok:
        try:
            entries = json.loads(result.stdout or "[]")
            return sorted(str(e["unit"]) for e in entries), None
        except (json.JSONDecodeError, TypeError, KeyError):
            pass
    result = runner.run(
        _systemctl(mode) + ["--failed", "--no-pager", "--plain", "--no-legend"]
    )
    if not result.ok:
        return None, "systemctl --failed unavailable; health check skipped"
    units = [line.split()[0] for line in result.stdout.splitlines() if line.split()]
    return sorted(units), None


def journal_tail(unit: str, mode: str) -> str:
    argv = ["journalctl"]
    if mode == "home-manager":
        argv.append("--user")
    argv += ["-u", unit, "-n", str(JOURNAL_LINES), "--no-pager"]
    result = runner.run(argv)
    if result.ok and result.stdout.strip():
        return result.stdout
    return "journal unavailable (permission denied or empty)"


def health_report(before: list[str] | None, mode: str) -> dict[str, object] | None:
    """Diff failed units against a pre-switch snapshot. None when either
    snapshot was undetectable; callers surface a note instead."""
    if before is None:
        return None
    after, _ = failed_units(mode)
    if after is None:
        return None
    before_set, after_set = set(before), set(after)
    return {
        "newly_failed": [
            {"unit": unit, "log_tail": journal_tail(unit, mode)}
            for unit in sorted(after_set - before_set)
        ],
        "resolved": sorted(before_set - after_set),
        "still_failed": sorted(before_set & after_set),
    }
