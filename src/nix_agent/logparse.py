"""Pure parsers over captured nix/systemd text. No imports from nix_agent:
runner and tools import this module, never the reverse."""

import re

TRACE_CAP = 5
LOG_TAIL_LINES = 40

_ERROR_LINE = re.compile(r"^\s*error:\s*(.+)$")
_AT_LINE = re.compile(r"^\s*at (/\S+?):(\d+):(\d+):?\s*$")
_TRACE_LINE = re.compile(r"^\s*…\s*(while .+|from call site.*)\s*$")


def extract_error_detail(output: str | None) -> dict[str, object] | None:
    """Structured form of a Nix eval error: deepest message, its source
    location, and up to TRACE_CAP trace frames. None unless both a message
    and a location are found; never guessed."""
    if not output:
        return None
    lines = output.splitlines()
    message: str | None = None
    message_idx = -1
    for i, line in enumerate(lines):
        match = _ERROR_LINE.match(line)
        if match and match.group(1).strip():
            message = match.group(1).strip()
            message_idx = i
    if message is None:
        return None

    at = None
    for line in lines[message_idx + 1 :]:
        match = _AT_LINE.match(line)
        if match:
            at = match
            break
    if at is None:
        for line in lines[:message_idx]:
            match = _AT_LINE.match(line)
            if match:
                at = match
    if at is None:
        return None

    trace = []
    for line in lines:
        match = _TRACE_LINE.match(line)
        if match:
            trace.append(match.group(1).strip())
            if len(trace) == TRACE_CAP:
                break
    return {
        "message": message,
        "file": at.group(1),
        "line": int(at.group(2)),
        "column": int(at.group(3)),
        "trace": trace,
    }
