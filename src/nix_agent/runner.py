from dataclasses import dataclass
import json
import os
import shutil
import subprocess

from nix_agent import logparse

OUTPUT_CAP = 64_000
TAIL_CAP = 2_000


@dataclass(frozen=True)
class RunResult:
    ok: bool
    command: list[str]
    stdout: str
    stderr: str
    raw_bytes: int | None = None

    @property
    def output(self) -> str:
        parts = [p for p in (self.stdout.strip(), self.stderr.strip()) if p]
        return "\n".join(parts)


def resolve_binary(name: str) -> str | None:
    """Realpath of a binary on PATH, or None. Sudo NOPASSWD rules match
    the resolved store path, not the PATH name, so sudo'd commands must
    use this."""
    found = shutil.which(name)
    if found is None:
        return None
    return os.path.realpath(found)


def truncate_output(text: str, cap: int = OUTPUT_CAP) -> str:
    if len(text) <= cap:
        return text
    half = cap // 2
    if half == 0:
        return text[:cap]
    omitted = len(text) - cap
    return (
        text[:half]
        + f"\n... [nix-agent: {omitted} bytes truncated] ...\n"
        + text[-half:]
    )


def tail(text: str, cap: int = TAIL_CAP) -> str:
    """Last `cap` chars, for surfacing the end of an otherwise-noisy log
    (e.g. a successful activation) without spending tokens on the whole thing."""
    if len(text) <= cap:
        return text
    return (
        f"... [nix-agent: {len(text) - cap} leading bytes omitted] ...\n" + text[-cap:]
    )


def run(argv: list[str], cwd: str | None = None) -> RunResult:
    try:
        proc = subprocess.run(
            argv, capture_output=True, text=True, errors="replace", cwd=cwd
        )
    except FileNotFoundError:
        stderr = f"{argv[0]}: command not found"
        return RunResult(
            ok=False,
            command=list(argv),
            stdout="",
            stderr=stderr,
            raw_bytes=len(stderr),
        )
    raw = len((proc.stdout or "").encode()) + len((proc.stderr or "").encode())
    return RunResult(
        ok=proc.returncode == 0,
        command=list(argv),
        stdout=truncate_output(proc.stdout or ""),
        stderr=truncate_output(proc.stderr or ""),
        raw_bytes=raw,
    )


def extract_first_error(output: str) -> str | None:
    """First line of Nix stderr that looks like an error; the actionable
    signal in an otherwise verbose log."""
    if not output:
        return None
    for line in output.splitlines():
        stripped = line.strip()
        if (
            stripped.startswith("error:")
            or stripped.startswith("error (")
            or stripped.startswith("error[")
        ):
            return stripped
    return None


def envelope(
    status: str,
    resolved_target: str,
    result: RunResult,
    **extra: object,
) -> dict[str, object]:
    response: dict[str, object] = dict(extra)
    response.update(
        status=status,
        resolved_target=resolved_target,
        command=result.command,
    )
    # Callers may pre-set a trimmed `output` (e.g. switch's success tail);
    # only fill in the full log when they did not.
    response.setdefault("output", result.output)
    if status == "failed":
        response["first_error"] = extract_first_error(result.output)
        detail = logparse.extract_error_detail(result.output)
        if detail is not None:
            response["error_detail"] = detail
    response["raw_bytes"] = (
        result.raw_bytes
        if result.raw_bytes is not None
        else len(result.stdout) + len(result.stderr)
    )
    return account(response)


def account(response: dict[str, object]) -> dict[str, object]:
    """Attach returned_bytes: the serialized size of the envelope minus
    the accounting fields themselves."""
    body = {
        k: v for k, v in response.items() if k not in ("raw_bytes", "returned_bytes")
    }
    response["returned_bytes"] = len(json.dumps(body))
    return response


def failed_derivation_info(output: str) -> dict[str, object] | None:
    """For a failed build log: the first failing .drv plus the tail of its
    builder log via `nix log`, replacing the agent's manual follow-up call."""
    drvs = logparse.extract_failed_drvs(output)
    if not drvs:
        return None
    drv = drvs[0]
    result = run(["nix", "log", drv])
    if result.ok and result.stdout.strip():
        return {"drv": drv, "log_tail": logparse.tail_lines(result.stdout)}
    return {"drv": drv, "note": "nix log unavailable for this derivation"}
