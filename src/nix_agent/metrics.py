"""Local usage logging for evaluating nix-agent value while dogfooding.

Off by default. Set NIX_AGENT_USAGE_LOG=1 to append one JSON line per MCP
tool call under XDG state (no network). Override the path with
NIX_AGENT_USAGE_LOG_PATH. Set NIX_AGENT_CLIENT to tag events with the
calling agent; otherwise the client is inferred from host env vars.
"""

from __future__ import annotations

import json
import os
import socket
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any

ENABLED_ENV = "NIX_AGENT_USAGE_LOG"
PATH_ENV = "NIX_AGENT_USAGE_LOG_PATH"
CLIENT_ENV = "NIX_AGENT_CLIENT"
SESSION_ENV = "NIX_AGENT_SESSION"
DEFAULT_RELATIVE = Path("nix-agent") / "usage.jsonl"

_TRUTHY = frozenset({"1", "true", "yes", "on"})

# Request kwargs worth keeping top-level in the event (paths/names only,
# no secrets). The full sanitized params land under "params".
_KWARG_KEYS = (
    "mode",
    "flake_uri",
    "level",
    "action",
    "generation",
    "validate",
    "full_log",
)

# Shell commands that overlap nix-agent's tool surface. Used by
# scan_shell_history to estimate MCP use vs direct-shell bypass.
SHELL_PATTERNS = (
    "nixos-rebuild",
    "home-manager",
    "nix build",
    "nix eval",
    "nix store",
    "nix log",
    "statix",
    "deadnix",
    "nixfmt",
    "nvd",
)

_TRUNCATION_MARKER = "[nix-agent:"


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


def _parent_comm() -> str | None:
    try:
        comm = Path(f"/proc/{os.getppid()}/comm").read_text().strip()
        return comm or None
    except OSError:
        return None


def detect_client() -> str:
    """Which agent host is calling. Explicit NIX_AGENT_CLIENT wins,
    otherwise infer from host env vars, falling back to the parent
    process name so unattributed calls still group somewhere."""
    override = os.environ.get(CLIENT_ENV)
    if override and override.strip():
        return override.strip()[:64]
    env = os.environ
    if env.get("OPENCODE") or env.get("OPENCODE_PID"):
        return "opencode"
    if env.get("CLAUDECODE") or env.get("CLAUDE_CODE_ENTRYPOINT"):
        return "claude-code"
    if env.get("CODEX_HOME") or any(k.startswith("CODEX_") for k in env):
        return "codex"
    if any(k.startswith("CURSOR_") for k in env):
        return "cursor"
    parent = _parent_comm()
    if parent:
        return f"proc:{parent}"[:64]
    return "unknown"


def _session_id() -> str | None:
    for key in (SESSION_ENV, "OPENCODE_PID", "CODEX_SESSION_ID", "TMUX"):
        value = os.environ.get(key)
        if value and value.strip():
            return value.strip()[:128]
    return None


def _sanitize(value: Any, depth: int = 0) -> Any:
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return value if len(value) <= 500 else value[:500] + "…"
    if depth >= 2:
        return str(value)[:200]
    if isinstance(value, Mapping):
        return {str(k)[:64]: _sanitize(v, depth + 1) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_sanitize(v, depth + 1) for v in list(value)[:50]]
    return str(value)[:200]


def _op_summary(response: Mapping[str, Any]) -> dict[str, Any]:
    """Outcome details worth keeping: what ran and how it failed."""
    out: dict[str, Any] = {}
    command = response.get("command")
    if isinstance(command, list) and command:
        out["command"] = [str(a) for a in command][:12]
        out["op"] = " ".join(str(a) for a in command[:3])[:128]
    commands = response.get("commands")
    if isinstance(commands, list) and commands:
        out["op"] = "+".join(
            str(c[0]) if isinstance(c, list) and c else str(c) for c in commands[:4]
        )[:128]
    for key in ("first_error", "health_note"):
        value = response.get(key)
        if isinstance(value, str) and value:
            out[key] = value[:500]
    detail = response.get("error_detail")
    if isinstance(detail, Mapping):
        message = detail.get("message")
        if isinstance(message, str) and message:
            out["error_message"] = message[:500]
    failed = response.get("failed_derivation")
    if isinstance(failed, Mapping):
        drv = failed.get("drv")
        if isinstance(drv, str) and drv:
            out["failed_drv"] = drv
    output = response.get("output")
    if isinstance(output, str):
        out["output_bytes"] = len(output.encode())
        if _TRUNCATION_MARKER in output:
            out["output_truncated"] = True
    summary = response.get("summary")
    if isinstance(summary, Mapping):
        out["summary"] = _sanitize(dict(summary))
    return out


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
        "client": detect_client(),
    }
    try:
        event["host"] = socket.gethostname()
    except OSError:
        pass
    try:
        event["cwd"] = os.getcwd()
    except OSError:
        pass
    session = _session_id()
    if session is not None:
        event["session"] = session
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
        event.update(_op_summary(response))
    if kwargs:
        params: dict[str, Any] = {}
        for key, value in kwargs.items():
            if key in _KWARG_KEYS and value is not None:
                event[key] = value
            if not key.startswith("_"):
                params[str(key)] = _sanitize(value)
        if "attr" in kwargs and kwargs["attr"] is not None:
            summary = _attr_summary(kwargs["attr"])
            if summary is not None:
                event["attr"] = summary
        if params:
            event["params"] = params
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
    by_client: dict[str, int] = {}
    total_raw = 0
    total_returned = 0
    accounted = 0
    ok = 0
    failed = 0
    errors = 0
    first_ts: str | None = None
    last_ts: str | None = None

    for event in events:
        tool = str(event.get("tool") or "unknown")
        client = str(event.get("client") or "unknown")
        by_client[client] = by_client.get(client, 0) + 1
        ts = event.get("ts")
        if isinstance(ts, str) and ts:
            if first_ts is None or ts < first_ts:
                first_ts = ts
            if last_ts is None or ts > last_ts:
                last_ts = ts
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
        "by_client": dict(sorted(by_client.items(), key=lambda kv: -kv[1])),
        "first_ts": first_ts,
        "last_ts": last_ts,
    }


def format_summary(summary: Mapping[str, Any], *, path: Path) -> str:
    lines = [
        f"usage log: {path}",
        f"events: {summary['events']}  ok: {summary['ok']}  "
        f"failed: {summary['failed']}  errors: {summary['errors']}",
    ]
    first_ts = summary.get("first_ts")
    last_ts = summary.get("last_ts")
    if first_ts and last_ts:
        lines.append(f"span: {first_ts} .. {last_ts}")
    if summary.get("accounted_calls"):
        lines.append(
            f"bytes: raw={summary['raw_bytes']}  returned={summary['returned_bytes']}  "
            f"saved={summary['bytes_saved']}  (over {summary['accounted_calls']} calls)"
        )
    by_client = summary.get("by_client") or {}
    if by_client:
        lines.append(
            "by client: "
            + ", ".join(f"{name}={count}" for name, count in by_client.items())
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


def _fish_history_commands(path: Path) -> list[str]:
    """Parse fish_history `- cmd: ...` entries. Best effort; skips decode
    errors so one bad line never breaks the comparison."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    commands: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("- cmd:"):
            commands.append(stripped[len("- cmd:") :].strip())
        elif stripped.startswith("cmd:"):
            commands.append(stripped[len("cmd:") :].strip())
    return commands


def _plain_history_commands(path: Path, *, skip_prefix: str | None = None) -> list[str]:
    """bash/zsh plain-history files: one command per line, optionally
    skipping extended-history timestamp lines."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    commands: list[str] = []
    for line in text.splitlines():
        if skip_prefix and line.startswith(skip_prefix):
            continue
        stripped = line.strip()
        if stripped:
            commands.append(stripped)
    return commands


def shell_history_paths() -> list[Path]:
    home = Path.home()
    candidates = [
        home / ".local" / "share" / "fish" / "fish_history",
        home / ".bash_history",
        home / ".zsh_history",
    ]
    return [p for p in candidates if p.is_file()]


def scan_shell_history(paths: list[Path] | None = None) -> dict[str, Any]:
    """Count shell-history lines that overlap nix-agent's tool surface.

    This only sees interactive shells, not agent Bash tool calls, so it
    estimates *your* shell bypass, not agent bypass. Agent bypass needs
    host-side hooks; see docs/usage.md.
    """
    targets = paths if paths is not None else shell_history_paths()
    by_pattern: dict[str, int] = {pattern: 0 for pattern in SHELL_PATTERNS}
    total = 0
    files = 0
    for path in targets:
        if path.name == "fish_history":
            commands = _fish_history_commands(path)
        elif path.name == ".zsh_history":
            commands = _plain_history_commands(path, skip_prefix=":")
        else:
            commands = _plain_history_commands(path)
        if commands:
            files += 1
        for command in commands:
            matched = False
            for pattern in SHELL_PATTERNS:
                if pattern in command:
                    by_pattern[pattern] += 1
                    matched = True
            if matched:
                total += 1
    return {
        "shell_nix_commands": total,
        "files_scanned": files,
        "by_pattern": {k: v for k, v in by_pattern.items() if v},
    }


def format_comparison(summary: Mapping[str, Any], shell: Mapping[str, Any]) -> str:
    mcp = int(summary.get("events") or 0)
    direct = int(shell.get("shell_nix_commands") or 0)
    lines = [
        f"mcp tool calls: {mcp}  vs  shell nix commands: {direct}",
    ]
    if mcp or direct:
        share = (100.0 * mcp / (mcp + direct)) if (mcp + direct) else 0.0
        lines.append(f"mcp share: {share:.0f}% of recorded nix operations")
    lines.append(
        f"(shell history covers {shell.get('files_scanned', 0)} file(s); "
        "interactive shells only, not agent Bash tool calls)"
    )
    by_pattern = shell.get("by_pattern") or {}
    if by_pattern:
        lines.append(
            "shell by pattern: "
            + ", ".join(f"{name}={count}" for name, count in by_pattern.items())
        )
    return "\n".join(lines) + "\n"
