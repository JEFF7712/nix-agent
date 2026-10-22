import concurrent.futures
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import anyio
import pytest
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from nix_agent import jobs
from nix_agent.target import Target
from nix_agent.tools.build import build
from nix_agent.tools.check import check


def eventually(function, timeout=5):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = function()
        if value:
            return value
        time.sleep(0.02)
    raise AssertionError("background build did not reach the expected state")


def wait_for_job(job_id):
    def completed():
        result = build(job_id=job_id)
        return result if result["status"] != "running" else None

    return eventually(completed)


@pytest.fixture
def fake_nix(monkeypatch, tmp_path):
    release = tmp_path / "release"
    calls = tmp_path / "calls"
    binary = tmp_path / "nix"
    binary.write_text(
        f"#!{sys.executable}\n"
        "import os, pathlib, sys, time\n"
        "if sys.argv[1] == 'log':\n"
        "    print('builder failure details')\n"
        "    sys.exit(0)\n"
        "with open(os.environ['FAKE_NIX_CALLS'], 'a') as stream:\n"
        "    stream.write('build\\n')\n"
        "if os.environ.get('FAKE_NIX_NOISE'):\n"
        "    print('x' * 300000, flush=True)\n"
        "print('building test closure', file=sys.stderr, flush=True)\n"
        "deadline = time.monotonic() + 10\n"
        "while not pathlib.Path(os.environ['FAKE_NIX_RELEASE']).exists():\n"
        "    if time.monotonic() > deadline: sys.exit(2)\n"
        "    time.sleep(0.02)\n"
        "if os.environ.get('FAKE_NIX_FAIL'):\n"
        "    print(\"error: builder for '/nix/store/abc-test.drv' failed with exit code 1\", file=sys.stderr)\n"
        "    sys.exit(1)\n"
        "print('/nix/store/test-system')\n"
    )
    binary.chmod(0o700)
    monkeypatch.setenv("PATH", str(tmp_path) + os.pathsep + os.environ["PATH"])
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("FAKE_NIX_RELEASE", str(release))
    monkeypatch.setenv("FAKE_NIX_CALLS", str(calls))
    monkeypatch.setenv("NIX_AGENT_COMMAND_TIMEOUT", "8")
    yield release, calls
    release.touch()
    for request in jobs.jobs_dir().glob("*/request.json"):
        wait_for_job(request.parent.name)


def test_job_survives_starter_exit_and_has_live_logs(fake_nix):
    release, calls = fake_nix
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(
        part for part in (str(Path.cwd() / "src"), env.get("PYTHONPATH")) if part
    )
    starter = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import json; from nix_agent.tools.build import build; "
                "print(json.dumps(build('/test#host')))"
            ),
        ],
        env=env,
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )
    assert starter.returncode == 0, starter.stderr
    started = json.loads(starter.stdout)
    assert started["status"] == "running"
    job_id = started["job_id"]

    def live_logs():
        result = build(job_id=job_id)
        if "building test closure" in result["log_tail"]["stderr"]:
            return result

    running = eventually(live_logs)
    assert running["status"] == "running"
    assert build("/test#host")["job_id"] == job_id
    assert calls.read_text().splitlines() == ["build"]
    release.touch()
    completed = wait_for_job(job_id)
    assert completed["status"] == "ok"
    assert completed["store_path"] == "/nix/store/test-system"
    assert completed["job_id"] == job_id
    assert build(job_id=job_id)["finished_at"] == completed["finished_at"]
    directory = jobs.jobs_dir() / job_id
    assert directory.stat().st_mode & 0o777 == 0o700
    for path in directory.iterdir():
        assert path.stat().st_mode & 0o777 == 0o600


def test_concurrent_starts_reuse_running_job(fake_nix):
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: build("/test#host"), range(4)))
    assert len({result["job_id"] for result in results}) == 1
    assert all(result["status"] == "running" for result in results)


def test_absolute_target_reuses_job_from_another_cwd(fake_nix, monkeypatch, tmp_path):
    job_id = build("path:/test#host")["job_id"]
    monkeypatch.chdir(tmp_path)
    assert build("path:/test#host")["job_id"] == job_id


def test_large_job_logs_are_bounded_and_keep_store_path(fake_nix, monkeypatch):
    monkeypatch.setenv("FAKE_NIX_NOISE", "1")
    release, _ = fake_nix
    job_id = build("/test#host")["job_id"]
    release.touch()
    result = wait_for_job(job_id)
    assert result["status"] == "ok"
    assert result["store_path"] == "/nix/store/test-system"
    assert len(result["output"]) < 2200
    assert result["log_truncated"] is True
    assert "log_tail" not in result
    assert Path(result["log_paths"]["stdout"]).stat().st_size > 300000


def test_successful_dry_build_returns_tail_and_full_saved_log(fake_nix, monkeypatch):
    monkeypatch.setenv("FAKE_NIX_NOISE", "1")
    release, _ = fake_nix
    release.touch()
    result = check("dry-build", flake_uri="/test#host")
    assert result["status"] == "ok"
    assert result["log_truncated"] is True
    assert len(result["output"]) < 2200
    assert "store_path" not in result
    stdout_path = Path(result["log_paths"]["stdout"])
    assert stdout_path.stat().st_size > 300000
    assert stdout_path.stat().st_mode & 0o777 == 0o600
    assert stdout_path.parent.stat().st_mode & 0o777 == 0o700


def test_failed_job_keeps_builder_diagnostics(fake_nix, monkeypatch):
    monkeypatch.setenv("FAKE_NIX_FAIL", "1")
    monkeypatch.setenv("FAKE_NIX_NOISE", "1")
    release, _ = fake_nix
    job_id = build("/test#host")["job_id"]
    release.touch()
    result = wait_for_job(job_id)
    assert result["status"] == "failed"
    assert result["failed_derivation"]["drv"] == "/nix/store/abc-test.drv"
    assert "builder failure details" in result["failed_derivation"]["log_tail"]
    assert len(result["output"]) > 2200
    assert "failed with exit code 1" in result["first_error"]
    assert Path(result["log_paths"]["stdout"]).stat().st_size > 300000


def test_job_timeout_records_failure_and_partial_log(fake_nix, monkeypatch):
    monkeypatch.setenv("NIX_AGENT_COMMAND_TIMEOUT", "0.3")
    job_id = build("/test#host")["job_id"]
    result = wait_for_job(job_id)
    assert result["status"] == "failed"
    assert "timed out after 0.3 seconds" in result["output"]
    assert "building test closure" in result["output"]


def test_log_offset_returns_only_new_stderr(fake_nix):
    job_id = build("/test#host")["job_id"]

    def live_logs():
        result = build(job_id=job_id)
        if "building test closure" in result["log_tail"]["stderr"]:
            return result

    first = eventually(live_logs)
    again = build(job_id=job_id, log_offset=first["log_offset"])
    assert again["status"] == "running"
    assert again["log_tail"]["stderr"] == ""
    assert again["log_offset"] == first["log_offset"]


def test_unknown_job_does_not_start_build(fake_nix):
    _, calls = fake_nix
    assert build(job_id="../outside")["status"] == "unknown_job"
    assert build(job_id="a" * 32)["status"] == "unknown_job"
    assert not calls.exists()


def test_worker_spawn_failure_is_recorded(fake_nix, monkeypatch):
    def fail_spawn(*args, **kwargs):
        raise OSError("no worker executable")

    monkeypatch.setattr(jobs.subprocess, "Popen", fail_spawn)
    started = build("/test#host")
    assert started["status"] == "failed"
    assert "no worker executable" in started["error"]
    assert build(job_id=started["job_id"])["error"] == started["error"]


def test_exited_worker_is_interrupted_not_running(fake_nix, monkeypatch):
    monkeypatch.setattr(jobs.sys, "executable", shutil.which("false"))
    job_id = build("/test#host")["job_id"]
    result = wait_for_job(job_id)
    assert result["status"] == "interrupted"
    assert "may still be running" in result["error"]


def test_new_start_after_completion_creates_new_job(fake_nix):
    release, _ = fake_nix
    release.touch()
    first = build("/test#host")["job_id"]
    eventually(lambda: build(job_id=first)["status"] == "ok")
    second = build("/test#host")["job_id"]
    assert second != first


def test_mode_and_target_are_distinct_jobs(fake_nix):
    system = jobs.start(Target("/test", "host", "nixos"))
    home = jobs.start(Target("/test", "host", "home-manager"))
    other = build("/test#other")
    assert len({system["job_id"], home["job_id"], other["job_id"]}) == 3


def test_mcp_reconnect_retrieves_build_after_server_restart(fake_nix):
    release, _ = fake_nix
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(
        part for part in (str(Path.cwd() / "src"), env.get("PYTHONPATH")) if part
    )
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "nix_agent"],
        env=env,
    )

    async def call(arguments):
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool("build", arguments)
                assert not result.isError
                return json.loads(
                    next(block.text for block in result.content if block.type == "text")
                )

    async def reconnect():
        started = await call({"flake_uri": "/test#host"})
        assert started["status"] == "running"
        assert "raw_bytes" not in started
        job_id = started["job_id"]
        resumed = await call({"job_id": job_id})
        assert resumed["status"] == "running"
        assert resumed["job_id"] == job_id
        release.touch()
        with anyio.fail_after(5):
            while True:
                completed = await call({"job_id": job_id})
                if completed["status"] != "running":
                    break
                await anyio.sleep(0.02)
        assert completed["status"] == "ok"
        assert completed["store_path"] == "/nix/store/test-system"
        assert "raw_bytes" not in completed

    anyio.run(reconnect)
