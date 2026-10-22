from __future__ import annotations

import fcntl
import hashlib
import json
import logging
import os
import re
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import asdict
from pathlib import Path

from nix_agent import runner
from nix_agent.target import Target


def jobs_dir() -> Path:
    return runner.state_dir() / "jobs"


def _write_json(path: Path, value: dict[str, object]) -> None:
    temporary = path.with_suffix(".tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        os.chmod(temporary, 0o600)
        json.dump(value, stream)
    temporary.replace(path)


def _active(directory: Path) -> bool:
    with (directory / "worker.lock").open("rb") as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
        return False


def _log_tail(path: Path, offset: int = 0) -> tuple[str, int]:
    """Tail of the log after `offset`, and the log's current size."""
    with path.open("rb") as stream:
        stream.seek(0, os.SEEK_END)
        size = stream.tell()
        stream.seek(max(0, min(offset, size), size - runner.TAIL_CAP * 4))
        text = stream.read(runner.TAIL_CAP * 4).decode("utf-8", errors="replace")
        return runner.tail(text), size


def status(
    job_id: str, root: Path | None = None, log_offset: int | None = None
) -> dict[str, object]:
    root = jobs_dir() if root is None else root
    if not re.fullmatch(r"[0-9a-f]{32}", job_id):
        return {
            "status": "unknown_job",
            "job_id": job_id,
            "error": "invalid build job ID",
        }
    directory = root / job_id
    try:
        request = json.loads((directory / "request.json").read_text())
    except FileNotFoundError:
        return {
            "status": "unknown_job",
            "job_id": job_id,
            "error": "build job not found",
        }
    result_path = directory / "result.json"
    active = _active(directory)
    if result_path.exists():
        response = json.loads(result_path.read_text())
    elif active:
        response = {
            "status": "running",
            "resolved_target": request["resolved_target"],
            "hint": f'Poll build(job_id="{job_id}") for logs and the final result.',
        }
    else:
        response = {
            "status": "interrupted",
            "resolved_target": request["resolved_target"],
            "error": "Build worker exited without recording a result. Nix daemon work "
            "may still be running; inspect the saved logs before retrying.",
        }
    response.update(
        job_id=job_id,
        started_at=request["started_at"],
        elapsed_seconds=round(
            max(0, response.get("finished_at", time.time()) - request["started_at"]), 1
        ),
        log_paths={
            "stdout": str(directory / "stdout.log"),
            "stderr": str(directory / "stderr.log"),
        },
    )
    # A finished result already carries the log tail as `output`.
    if "output" not in response:
        stdout, _ = _log_tail(directory / "stdout.log")
        stderr, stderr_size = _log_tail(directory / "stderr.log", log_offset or 0)
        response["log_tail"] = {"stdout": stdout, "stderr": stderr}
        response["log_offset"] = stderr_size
    return runner.account(response)


def start(target: Target) -> dict[str, object]:
    root = jobs_dir()
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    target_data = asdict(target)
    identity: dict[str, object] = {"target": target_data}
    if not os.path.isabs(target.flake_dir.removeprefix("path:")):
        identity["cwd"] = os.getcwd()
    key = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
    with (root / "start.lock").open("a+b") as start_lock:
        os.chmod(root / "start.lock", 0o600)
        fcntl.flock(start_lock, fcntl.LOCK_EX)
        index = root / f"target-{key}.json"
        if index.exists():
            previous = json.loads(index.read_text())["job_id"]
            existing = status(previous, root)
            if existing["status"] == "running":
                return existing
        job_id = uuid.uuid4().hex
        directory = root / job_id
        directory.mkdir(mode=0o700)
        for name in ("stdout.log", "stderr.log", "worker.lock"):
            (directory / name).touch(mode=0o600)
        _write_json(
            directory / "request.json",
            {
                "target": target_data,
                "resolved_target": target.flake_ref,
                "started_at": time.time(),
                "cwd": os.getcwd(),
            },
        )
        _write_json(index, {"job_id": job_id})
        env = os.environ.copy()
        source_root = str(Path(__file__).resolve().parent.parent)
        env["PYTHONPATH"] = os.pathsep.join(
            part for part in (source_root, env.get("PYTHONPATH")) if part
        )
        with (directory / "worker.lock").open("rb") as worker_lock:
            # The worker inherits this lock so status cannot race its startup.
            fcntl.flock(worker_lock, fcntl.LOCK_EX)
            try:
                with (directory / "stderr.log").open("ab") as error_log:
                    process = subprocess.Popen(
                        [
                            sys.executable,
                            "-m",
                            "nix_agent.jobs",
                            str(directory),
                            str(worker_lock.fileno()),
                        ],
                        stdin=subprocess.DEVNULL,
                        stdout=subprocess.DEVNULL,
                        stderr=error_log,
                        env=env,
                        start_new_session=True,
                        pass_fds=(worker_lock.fileno(),),
                    )
            except OSError as exc:
                _write_json(
                    directory / "result.json",
                    {
                        "status": "failed",
                        "resolved_target": target.flake_ref,
                        "error": f"Could not start build worker: {exc}",
                        "finished_at": time.time(),
                    },
                )
            else:
                threading.Thread(target=process.wait, daemon=True).start()
        return status(job_id, root)


def work(directory: Path, lock_fd: int) -> None:
    from nix_agent.tools.build import build_closure

    with os.fdopen(lock_fd, "rb"):
        request = json.loads((directory / "request.json").read_text())
        try:
            os.chdir(request["cwd"])
            with runner.log_to(directory):
                result = build_closure(Target(**request["target"]))
        except Exception as exc:
            logging.exception("Build worker failed")
            result = {
                "status": "failed",
                "resolved_target": request["resolved_target"],
                "error": f"Build worker failed: {type(exc).__name__}: {exc}",
            }
        result["finished_at"] = time.time()
        _write_json(directory / "result.json", result)


if __name__ == "__main__":
    work(Path(sys.argv[1]), int(sys.argv[2]))
