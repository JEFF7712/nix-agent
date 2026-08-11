"""Local usage logging for evaluating nix-agent value while dogfooding.

Off by default. Set NIX_AGENT_USAGE_LOG=1 to append one JSON line per MCP
tool call under XDG state (no network). Override the path with
NIX_AGENT_USAGE_LOG_PATH.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import time
from typing import Any, Mapping

ENABLED_ENV = "NIX_AGENT_USAGE_LOG"
PATH_ENV = "NIX_AGENT_USAGE_LOG_PATH"
DEFAULT_RELATIVE = Path("nix-agent") / "usage.jsonl"

_TRUTHY = frozenset({"1", "true", "yes", "on"})

# Request kwargs worth keeping in the event (paths/names only, no secrets).
_KWARG_KEYS = (
    "mode",
    "flake_uri",
    "level",
    "action",
    "validate",
    "full_log",
)


def enabled() -> bool:
    raw = os.environ.get(ENABLED_ENV)
    if raw is None:
        return False
    return raw.strip().lower() in _TRUTHY


def log_path() -> Path:
    override = os.environ.get(PATH_ENV)
    if override:
        return Path(override).expanduser()
    state_home = os.environ.get("XDG_STATE_HOME")
    root = Path(state_home) if state_home else Path.home() / ".local" / "state"
    return root / DEFAULT_RELATIVE


def _attr_summary(attr: object) -> object | None:
    if isinstance(attr, str):
        return attr
    if isinstance(attr, list):
        return {"count": len(attr), "attrs": [str(a) for a in attr]}
    return None


def event_from_call(
    *,
    tool: str,
    duration_ms: float,
    response: Mapping[str, Any] | None,
    error: str | None,
    kwargs: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    event: dict[str, Any] = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "tool": tool,
        "duration_ms": round(duration_ms, 1),
    }
    if error is not None:
        event["error"] = error
    if response is not None:
        status = response.get("status")
        if status is not None:
            event["status"] = status
        target = response.get("resolved_target")
        if target is not None:
            event["resolved_target"] = target
        raw = response.get("raw_bytes")
        returned = response.get("returned_bytes")
        if isinstance(raw, int):
            event["raw_bytes"] = raw
        if isinstance(returned, int):
            event["returned_bytes"] = returned
        if isinstance(raw, int) and isinstance(returned, int):
            event["bytes_saved"] = raw - returned
    if kwargs:
        for key in _KWARG_KEYS:
            if key in kwargs and kwargs[key] is not None:
                event[key] = kwargs[key]
        if "attr" in kwargs and kwargs["attr"] is not None:
            summary = _attr_summary(kwargs["attr"])
            if summary is not None:
                event["attr"] = summary
    return event


def record(event: Mapping[str, Any]) -> None:
    """Append one JSONL event. Never raises; logging must not break tools."""
    if not enabled():
        return
    try:
        path = log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(dict(event), ensure_ascii=False, default=str)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except OSError:
        return


def record_call(
    *,
    tool: str,
    duration_ms: float,
    response: Mapping[str, Any] | None = None,
    error: str | None = None,
    kwargs: Mapping[str, Any] | None = None,
) -> None:
    record(
        event_from_call(
            tool=tool,
            duration_ms=duration_ms,
            response=response,
            error=error,
            kwargs=kwargs,
        )
    )


def load_events(path: Path | None = None) -> list[dict[str, Any]]:
    target = path if path is not None else log_path()
    if not target.is_file():
        return []
    events: list[dict[str, Any]] = []
    for line in target.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            events.append(parsed)
    return events


def summarize(events: list[dict[str, Any]]) -> dict[str, Any]:
    by_tool: dict[str, dict[str, Any]] = {}
    total_raw = 0
    total_returned = 0
    accounted = 0
    ok = 0
    failed = 0
    errors = 0

    for event in events:
        tool = str(event.get("tool") or "unknown")
        bucket = by_tool.setdefault(
            tool,
            {
                "calls": 0,
                "ok": 0,
                "failed": 0,
                "errors": 0,
                "duration_ms_total": 0.0,
                "raw_bytes": 0,
                "returned_bytes": 0,
                "bytes_saved": 0,
                "accounted_calls": 0,
            },
        )
        bucket["calls"] += 1
        duration = event.get("duration_ms")
        if isinstance(duration, (int, float)):
            bucket["duration_ms_total"] += float(duration)

        if event.get("error"):
            bucket["errors"] += 1
            errors += 1
        status = event.get("status")
        if status == "ok":
            bucket["ok"] += 1
            ok += 1
        elif status is not None:
            bucket["failed"] += 1
            failed += 1

        raw = event.get("raw_bytes")
        returned = event.get("returned_bytes")
        if isinstance(raw, int) and isinstance(returned, int):
            bucket["raw_bytes"] += raw
            bucket["returned_bytes"] += returned
            saved = event.get("bytes_saved")
            bucket["bytes_saved"] += (
                int(saved) if isinstance(saved, int) else raw - returned
            )
            bucket["accounted_calls"] += 1
            total_raw += raw
            total_returned += returned
            accounted += 1

    tools_out: dict[str, Any] = {}
    for tool, bucket in sorted(by_tool.items()):
        calls = bucket["calls"]
        entry = {
            "calls": calls,
            "ok": bucket["ok"],
            "failed": bucket["failed"],
            "errors": bucket["errors"],
            "avg_duration_ms": (
                round(bucket["duration_ms_total"] / calls, 1) if calls else 0.0
            ),
        }
        if bucket["accounted_calls"]:
            entry["raw_bytes"] = bucket["raw_bytes"]
            entry["returned_bytes"] = bucket["returned_bytes"]
            entry["bytes_saved"] = bucket["bytes_saved"]
        tools_out[tool] = entry

    return {
        "events": len(events),
        "ok": ok,
        "failed": failed,
        "errors": errors,
        "raw_bytes": total_raw,
        "returned_bytes": total_returned,
        "bytes_saved": total_raw - total_returned if accounted else 0,
        "accounted_calls": accounted,
        "by_tool": tools_out,
    }


def format_summary(summary: Mapping[str, Any], *, path: Path) -> str:
    lines = [
        f"usage log: {path}",
        f"events: {summary['events']}  ok: {summary['ok']}  "
        f"failed: {summary['failed']}  errors: {summary['errors']}",
    ]
    if summary.get("accounted_calls"):
        lines.append(
            f"bytes: raw={summary['raw_bytes']}  returned={summary['returned_bytes']}  "
            f"saved={summary['bytes_saved']}  (over {summary['accounted_calls']} calls)"
        )
    by_tool = summary.get("by_tool") or {}
    if by_tool:
        lines.append("by tool:")
        for tool, entry in by_tool.items():
            parts = [
                f"  {tool}: calls={entry['calls']}",
                f"ok={entry['ok']}",
                f"failed={entry['failed']}",
                f"avg_ms={entry['avg_duration_ms']}",
            ]
            if "bytes_saved" in entry:
                parts.append(f"saved={entry['bytes_saved']}")
            lines.append("  ".join(parts))
    else:
        lines.append("no events yet")
    return "\n".join(lines) + "\n"
