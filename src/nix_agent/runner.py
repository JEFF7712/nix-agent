import functools
import json
import os
import shutil
import signal
import subprocess
import tempfile
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from typing import ParamSpec

from nix_agent import logparse

OUTPUT_CAP = 64_000
TAIL_CAP = 2_000
COMMAND_TIMEOUT = 30 * 60
COMMAND_TIMEOUT_ENV = "NIX_AGENT_COMMAND_TIMEOUT"
_LOG_DIR: ContextVar[Path | None] = ContextVar("build_log_dir", default=None)
_PARAMS = ParamSpec("_PARAMS")


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


def command_timeout() -> float:
    configured = os.environ.get(COMMAND_TIMEOUT_ENV)
    if configured is None:
        return COMMAND_TIMEOUT
    try:
        timeout = float(configured)
    except ValueError:
        return COMMAND_TIMEOUT
    return timeout if timeout > 0 else COMMAND_TIMEOUT


@contextmanager
def log_to(directory: Path) -> Iterator[None]:
    token = _LOG_DIR.set(directory)
    try:
        yield
    finally:
        _LOG_DIR.reset(token)


def state_dir() -> Path:
    state = os.environ.get("XDG_STATE_HOME")
    return (
        (Path(state) if state else Path.home() / ".local/state") / "nix-agent"
    ).absolute()


@contextmanager
def operation_logs() -> Iterator[Path]:
    directory = _LOG_DIR.get()
    if directory is None:
        root = state_dir() / "logs"
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        directory = Path(tempfile.mkdtemp(prefix="operation-", dir=root))
        for name in ("stdout.log", "stderr.log"):
            (directory / name).touch(mode=0o600)
    with log_to(directory):
        yield directory


def logged_operation(
    function: Callable[_PARAMS, dict[str, object]],
) -> Callable[_PARAMS, dict[str, object]]:
    @functools.wraps(function)
    def wrapper(*args: _PARAMS.args, **kwargs: _PARAMS.kwargs) -> dict[str, object]:
        with operation_logs() as directory:
            response = function(*args, **kwargs)
        output = response.get("output")
        if not isinstance(output, str):
            return response
        response["log_paths"] = {
            "stdout": str(directory / "stdout.log"),
            "stderr": str(directory / "stderr.log"),
        }
        if response.get("status") == "ok" and "log_truncated" not in response:
            compact = tail(output)
            response["output"] = compact
            response["log_truncated"] = compact != output
        return account(response)

    return wrapper


def _logged_output(path: Path, offset: int) -> tuple[str, int]:
    with path.open("rb") as stream:
        size = max(0, os.fstat(stream.fileno()).st_size - offset)
        stream.seek(offset)
        if size <= OUTPUT_CAP * 4:
            data = stream.read(size)
            text = data.decode("utf-8", errors="replace")
        else:
            head = stream.read(OUTPUT_CAP * 2).decode("utf-8", errors="replace")
            stream.seek(offset + size - OUTPUT_CAP * 2)
            end = stream.read(OUTPUT_CAP * 2).decode("utf-8", errors="replace")
            text = head + "\n... [nix-agent: log truncated] ...\n" + end
    return truncate_output(text), size


def _run_logged(
    argv: list[str], cwd: str | None, timeout: float, directory: Path
) -> RunResult:
    stdout_path = directory / "stdout.log"
    stderr_path = directory / "stderr.log"
    with stdout_path.open("ab") as stdout, stderr_path.open("ab") as stderr:
        stdout_offset, stderr_offset = stdout.tell(), stderr.tell()
        try:
            proc = subprocess.Popen(
                argv,
                stdin=subprocess.DEVNULL,
                stdout=stdout,
                stderr=stderr,
                cwd=cwd,
                start_new_session=True,
            )
        except FileNotFoundError:
            stderr.write(f"{argv[0]}: command not found\n".encode())
            ok = False
        else:
            try:
                ok = proc.wait(timeout=timeout) == 0
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                proc.wait()
                stderr.write(
                    f"\n{argv[0]}: timed out after {timeout} seconds\n".encode()
                )
                ok = False
    out, out_bytes = _logged_output(stdout_path, stdout_offset)
    err, err_bytes = _logged_output(stderr_path, stderr_offset)
    return RunResult(ok, list(argv), out, err, out_bytes + err_bytes)


def run(
    argv: list[str],
    cwd: str | None = None,
    timeout: float | None = None,
) -> RunResult:
    effective_timeout = command_timeout() if timeout is None else timeout
    directory = _LOG_DIR.get()
    if directory is not None:
        return _run_logged(argv, cwd, effective_timeout, directory)
    try:
        proc = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            errors="replace",
            cwd=cwd,
            timeout=effective_timeout,
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
    except subprocess.TimeoutExpired as exc:
        stdout = (exc.stdout or b"").decode("utf-8", errors="replace")
        captured_stderr = (exc.stderr or b"").decode("utf-8", errors="replace")
        stderr = "\n".join(
            part
            for part in (
                captured_stderr,
                f"{argv[0]}: timed out after {exc.timeout} seconds",
            )
            if part
        )
        return RunResult(
            ok=False,
            command=list(argv),
            stdout=truncate_output(stdout),
            stderr=truncate_output(stderr),
            raw_bytes=len(stdout.encode()) + len(stderr.encode()),
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
    signal in an otherwise verbose log.

    If the error line is a bare 'error:' header with no inline message
    (common in multiline Nix diagnostics and evaluation traces), this looks
    for a subsequent concrete error line or formats the next non-empty line.
    """
    if not output:
        return None
    lines = output.splitlines()
    _ERROR_STARTS = ("error:", "error (", "error[")
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith(_ERROR_STARTS):
            if stripped == "error:":
                for next_line in lines[i + 1 :]:
                    next_stripped = next_line.strip()
                    if (
                        next_stripped.startswith(_ERROR_STARTS)
                        and next_stripped != "error:"
                    ):
                        return next_stripped
                for next_line in lines[i + 1 :]:
                    next_stripped = next_line.strip()
                    if next_stripped:
                        return f"error: {next_stripped}"
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


_ACCOUNTING_KEYS = ("raw_bytes", "returned_bytes")


def account(response: dict[str, object]) -> dict[str, object]:
    """Attach returned_bytes: the serialized size of the envelope minus
    the accounting fields themselves. MCP instrument strips both before
    the model sees the envelope; the usage log reads them first."""
    body = {k: v for k, v in response.items() if k not in _ACCOUNTING_KEYS}
    response["returned_bytes"] = len(json.dumps(body))
    return response


def strip_accounting(response: dict[str, object]) -> dict[str, object]:
    """Remove usage-log byte fields from a tool envelope (in place)."""
    for key in _ACCOUNTING_KEYS:
        response.pop(key, None)
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
