from dataclasses import dataclass
import os
import shutil
import subprocess

OUTPUT_CAP = 64_000


@dataclass(frozen=True)
class RunResult:
    ok: bool
    command: list[str]
    stdout: str
    stderr: str

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
    omitted = len(text) - cap
    return (
        text[:half]
        + f"\n... [nix-agent: {omitted} bytes truncated] ...\n"
        + text[-half:]
    )


def run(argv: list[str], cwd: str | None = None) -> RunResult:
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, cwd=cwd)
    except FileNotFoundError:
        return RunResult(
            ok=False,
            command=argv,
            stdout="",
            stderr=f"{argv[0]}: command not found",
        )
    return RunResult(
        ok=proc.returncode == 0,
        command=argv,
        stdout=truncate_output(proc.stdout or ""),
        stderr=truncate_output(proc.stderr or ""),
    )


def extract_first_error(output: str) -> str | None:
    """First line of Nix stderr that looks like an error; the actionable
    signal in an otherwise verbose log."""
    if not output:
        return None
    for line in output.splitlines():
        stripped = line.strip()
        if stripped.startswith("error:") or stripped.startswith("error ("):
            return stripped
    return None


def envelope(
    status: str,
    resolved_target: str,
    result: RunResult,
    **extra: object,
) -> dict[str, object]:
    response: dict[str, object] = {
        "status": status,
        "resolved_target": resolved_target,
        "command": result.command,
        "output": result.output,
    }
    if status == "failed":
        response["first_error"] = extract_first_error(result.output)
    response.update(extra)
    return response
