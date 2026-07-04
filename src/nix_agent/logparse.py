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
        start = 0
        for i in range(message_idx - 1, -1, -1):
            if lines[i].strip().startswith("error:"):
                start = i + 1
                # the at line directly under an error line is that error's
                # location, not context for the current one
                if start < message_idx and _AT_LINE.match(lines[start]):
                    start += 1
                break
        for line in lines[start:message_idx]:
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


_BUILDER_FAILED = re.compile(r"builder for '(/nix/store/\S+\.drv)' failed")


def extract_failed_drvs(output: str | None) -> list[str]:
    """Leaf builder failures ('builder for ... failed'), deduped, in order.
    Dependency-chain errors name aggregate drvs; the builder lines are the
    actual failures."""
    seen: list[str] = []
    for match in _BUILDER_FAILED.finditer(output or ""):
        drv = match.group(1)
        if drv not in seen:
            seen.append(drv)
    return seen


def tail_lines(text: str, n: int = LOG_TAIL_LINES) -> str:
    lines = text.splitlines()
    if len(lines) <= n:
        return text
    omitted = len(lines) - n
    return f"... [nix-agent: {omitted} leading lines omitted] ...\n" + "\n".join(
        lines[-n:]
    )


_NVD_SECTIONS = {
    "Version changes:": "changed",
    "Added packages:": "added",
    "Removed packages:": "removed",
}
_NVD_ENTRY = re.compile(r"^\[[^\]]+\]\s+#\d+\s+(\S+)\s+(.+)$")
_ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;]*m")
_DIFF_CLOSURES = re.compile(r"^(\S+): (.+?) → (.+?)(?:, [+-]?[\d.]+\s+\S+)?$")


def parse_nvd(text: str) -> dict[str, list[dict[str, str]]] | None:
    """nvd diff output to structured package changes. Returns the empty
    lists when the output is recognizably nvd but shows no package changes;
    None when the text is not recognizable nvd output, or when a known
    section header appeared but no entry anywhere parsed (nvd never prints
    a section header with zero entries, so that combination signals output
    format drift rather than a genuine empty diff)."""
    packages: dict[str, list[dict[str, str]]] = {
        "added": [],
        "removed": [],
        "changed": [],
    }
    section = None
    matched = False
    saw_section_header = False
    entry_count = 0
    for line in text.splitlines():
        stripped = line.strip()
        if stripped in _NVD_SECTIONS:
            section = _NVD_SECTIONS[stripped]
            matched = True
            saw_section_header = True
            continue
        if stripped.startswith("Closure size:"):
            matched = True
            continue
        if stripped.endswith(":") and not _NVD_ENTRY.match(stripped):
            # unknown section header (e.g. "Selection state changes:");
            # reset so its entries cannot leak into the previous section
            section = None
            continue
        entry = _NVD_ENTRY.match(stripped)
        if section is None or entry is None:
            continue
        matched = True
        entry_count += 1
        name, rest = entry.group(1), entry.group(2).strip()
        if section == "changed":
            old, _, new = rest.partition("->")
            packages["changed"].append(
                {"name": name, "old": old.strip(), "new": new.strip()}
            )
        else:
            packages[section].append({"name": name, "version": rest})
    if saw_section_header and entry_count == 0:
        return None
    return packages if matched else None


def parse_diff_closures(text: str) -> dict[str, list[dict[str, str]]] | None:
    """`nix store diff-closures` output to structured package changes.
    The empty-set character marks an absent side (added/removed). Size
    deltas are always ANSI-colored (no --no-color / NO_COLOR escape hatch),
    so strip escape codes before matching. Identical closures print
    nothing at all, so callers must treat empty input as an empty diff
    themselves; None here means only that no line was recognizable."""
    packages: dict[str, list[dict[str, str]]] = {
        "added": [],
        "removed": [],
        "changed": [],
    }
    matched = False
    for line in text.splitlines():
        entry = _DIFF_CLOSURES.match(_ANSI_ESCAPE.sub("", line).strip())
        if entry is None:
            continue
        matched = True
        name = entry.group(1)
        old = entry.group(2).strip()
        new = entry.group(3).strip()
        if old == "∅":
            packages["added"].append({"name": name, "version": new})
        elif new == "∅":
            packages["removed"].append({"name": name, "version": old})
        else:
            packages["changed"].append({"name": name, "old": old, "new": new})
    return packages if matched else None
