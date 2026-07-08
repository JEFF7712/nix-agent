import subprocess

from nix_agent import runner


def test_run_success_combines_streams(monkeypatch):
    def fake_run(argv, capture_output, text, cwd=None, errors=None, timeout=None):
        return subprocess.CompletedProcess(argv, 0, stdout="out\n", stderr="warn\n")

    monkeypatch.setattr(runner.subprocess, "run", fake_run)
    result = runner.run(["true"])
    assert result.ok
    assert result.stdout == "out\n"
    assert result.output == "out\nwarn"
    assert result.command == ["true"]


def test_run_failure(monkeypatch):
    def fake_run(argv, capture_output, text, cwd=None, errors=None, timeout=None):
        return subprocess.CompletedProcess(argv, 1, stdout="", stderr="error: boom\n")

    monkeypatch.setattr(runner.subprocess, "run", fake_run)
    result = runner.run(["false"])
    assert not result.ok
    assert "error: boom" in result.output


def test_run_missing_binary(monkeypatch):
    def fake_run(argv, capture_output, text, cwd=None, errors=None, timeout=None):
        raise FileNotFoundError(argv[0])

    monkeypatch.setattr(runner.subprocess, "run", fake_run)
    result = runner.run(["nvd", "diff"])
    assert not result.ok
    assert "nvd: command not found" in result.output


def test_run_timeout_returns_failed_result(monkeypatch):
    def fake_run(argv, capture_output, text, cwd=None, errors=None, timeout=None):
        raise subprocess.TimeoutExpired(argv, timeout)

    monkeypatch.setattr(runner.subprocess, "run", fake_run)
    result = runner.run(["nix", "build"], timeout=0.01)
    assert not result.ok
    assert result.command == ["nix", "build"]
    assert "timed out after 0.01 seconds" in result.output


def test_run_uses_timeout_from_environment(monkeypatch):
    seen = []

    def fake_run(argv, capture_output, text, cwd=None, errors=None, timeout=None):
        seen.append(timeout)
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    monkeypatch.setattr(runner.subprocess, "run", fake_run)
    monkeypatch.setenv("NIX_AGENT_COMMAND_TIMEOUT", "12.5")
    result = runner.run(["nix", "build"])
    assert result.ok
    assert seen == [12.5]


def test_invalid_timeout_environment_falls_back(monkeypatch):
    seen = []

    def fake_run(argv, capture_output, text, cwd=None, errors=None, timeout=None):
        seen.append(timeout)
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    monkeypatch.setattr(runner.subprocess, "run", fake_run)
    monkeypatch.setenv("NIX_AGENT_COMMAND_TIMEOUT", "not-a-number")
    runner.run(["nix", "build"])
    assert seen == [runner.COMMAND_TIMEOUT]


def test_truncate_output_keeps_head_and_tail():
    text = "a" * 50_000 + "MIDDLE" + "b" * 50_000
    out = runner.truncate_output(text, cap=10_000)
    assert len(out) < 11_000
    assert out.startswith("a")
    assert out.endswith("b")
    assert "truncated" in out
    assert "MIDDLE" not in out


def test_truncate_output_noop_under_cap():
    assert runner.truncate_output("short") == "short"


def test_extract_first_error():
    output = "building...\nerror: attribute 'foo' missing\nerror: second"
    assert runner.extract_first_error(output) == "error: attribute 'foo' missing"
    assert runner.extract_first_error("all fine") is None
    assert runner.extract_first_error("") is None
    assert (
        runner.extract_first_error("error[E001]: bad thing") == "error[E001]: bad thing"
    )


def test_envelope_failure_includes_first_error():
    result = runner.RunResult(
        ok=False, command=["nix", "eval"], stdout="", stderr="error: nope"
    )
    env = runner.envelope("failed", "/etc/nixos#host", result, extra_field=1)
    assert env["status"] == "failed"
    assert env["resolved_target"] == "/etc/nixos#host"
    assert env["command"] == ["nix", "eval"]
    assert env["first_error"] == "error: nope"
    assert env["extra_field"] == 1


def test_envelope_ok_has_no_first_error():
    result = runner.RunResult(ok=True, command=["x"], stdout="fine", stderr="")
    env = runner.envelope("ok", "t", result)
    assert "first_error" not in env


def test_truncate_output_tiny_cap():
    assert runner.truncate_output("abcdef", cap=1) == "a"
    assert runner.truncate_output("abcdef", cap=0) == ""


def test_envelope_core_keys_win_over_extras():
    result = runner.RunResult(ok=True, command=["x"], stdout="real", stderr="")
    env = runner.envelope("ok", "t", result, command=["bad"])
    assert env["command"] == ["x"]
    assert env["status"] == "ok"


def test_envelope_output_override_wins():
    """A caller can pre-trim `output` (switch's success tail); envelope only
    fills the full log when the caller did not set one."""
    result = runner.RunResult(ok=True, command=["x"], stdout="real", stderr="")
    overridden = runner.envelope("ok", "t", result, output="trimmed")
    assert overridden["output"] == "trimmed"
    default = runner.envelope("ok", "t", result)
    assert default["output"] == "real"


def test_tail_keeps_end():
    text = "head" + "z" * 5000 + "TAILEND"
    out = runner.tail(text, cap=100)
    assert out.endswith("TAILEND")
    assert "head" not in out
    assert "omitted" in out
    assert runner.tail("short", cap=100) == "short"


def test_output_drops_whitespace_only_streams():
    r = runner.RunResult(ok=True, command=["x"], stdout="\n", stderr="   ")
    assert r.output == ""


def test_envelope_failure_includes_error_detail():
    stderr = "error: attribute 'foo' missing\n  at /home/u/nixos/net.nix:12:5:"
    result = runner.RunResult(
        ok=False, command=["nix", "build"], stdout="", stderr=stderr
    )
    env = runner.envelope("failed", "t", result)
    assert env["error_detail"]["file"] == "/home/u/nixos/net.nix"
    assert env["error_detail"]["line"] == 12


def test_envelope_failure_omits_error_detail_when_unparseable():
    result = runner.RunResult(ok=False, command=["x"], stdout="", stderr="error: nope")
    env = runner.envelope("failed", "t", result)
    assert "error_detail" not in env
    assert env["first_error"] == "error: nope"


def test_failed_derivation_info_fetches_log(monkeypatch):
    calls = []

    def fake_run(argv, capture_output, text, cwd=None, errors=None, timeout=None):
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout="log line\n", stderr="")

    monkeypatch.setattr(runner.subprocess, "run", fake_run)
    info = runner.failed_derivation_info(
        "error: builder for '/nix/store/abc-x.drv' failed with exit code 1"
    )
    assert info == {"drv": "/nix/store/abc-x.drv", "log_tail": "log line\n"}
    assert calls == [["nix", "log", "/nix/store/abc-x.drv"]]


def test_failed_derivation_info_log_unavailable(monkeypatch):
    def fake_run(argv, capture_output, text, cwd=None, errors=None, timeout=None):
        return subprocess.CompletedProcess(argv, 1, stdout="", stderr="error: gone")

    monkeypatch.setattr(runner.subprocess, "run", fake_run)
    info = runner.failed_derivation_info(
        "error: builder for '/nix/store/abc-x.drv' failed with exit code 1"
    )
    assert info["drv"] == "/nix/store/abc-x.drv"
    assert "log_tail" not in info
    assert "unavailable" in info["note"]


def test_failed_derivation_info_no_drv():
    assert runner.failed_derivation_info("error: eval only") is None


def test_run_tolerates_non_utf8_output():
    import sys

    result = runner.run(
        [sys.executable, "-c", "import sys; sys.stdout.buffer.write(b'ok \\xff bad')"]
    )
    assert result.ok
    assert "ok" in result.stdout


def test_failed_derivation_info_empty_log(monkeypatch):
    def fake_run(argv, capture_output, text, cwd=None, errors=None, timeout=None):
        return subprocess.CompletedProcess(argv, 0, stdout="  \n", stderr="")

    monkeypatch.setattr(runner.subprocess, "run", fake_run)
    info = runner.failed_derivation_info(
        "error: builder for '/nix/store/abc-x.drv' failed with exit code 1"
    )
    assert info == {
        "drv": "/nix/store/abc-x.drv",
        "note": "nix log unavailable for this derivation",
    }


def test_run_records_raw_bytes(monkeypatch):
    big = "x" * 100_000

    def fake_run(argv, capture_output, text, cwd=None, errors=None, timeout=None):
        return subprocess.CompletedProcess(argv, 0, stdout=big, stderr="err")

    monkeypatch.setattr(runner.subprocess, "run", fake_run)
    result = runner.run(["x"])
    assert result.raw_bytes == 100_003
    assert len(result.stdout) < 100_000


def test_envelope_accounting_fields():
    result = runner.RunResult(
        ok=True, command=["x"], stdout="out", stderr="", raw_bytes=1234
    )
    env = runner.envelope("ok", "t", result)
    assert env["raw_bytes"] == 1234
    assert env["returned_bytes"] > 0
    import json as json_mod

    without = {k: v for k, v in env.items() if k not in ("raw_bytes", "returned_bytes")}
    assert env["returned_bytes"] == len(json_mod.dumps(without))


def test_envelope_accounting_defaults_to_stream_sizes():
    result = runner.RunResult(ok=True, command=["x"], stdout="abcd", stderr="ef")
    env = runner.envelope("ok", "t", result)
    assert env["raw_bytes"] == 6


def test_account_helper_on_hand_built_envelope():
    response = {"status": "ok", "value": 1}
    runner.account(response)
    assert "raw_bytes" not in response
    assert response["returned_bytes"] == len('{"status": "ok", "value": 1}')


def test_run_raw_bytes_counts_bytes_not_chars(monkeypatch):
    def fake_run(argv, capture_output, text, cwd=None, errors=None, timeout=None):
        return subprocess.CompletedProcess(argv, 0, stdout="héllo", stderr="")

    monkeypatch.setattr(runner.subprocess, "run", fake_run)
    result = runner.run(["x"])
    assert result.raw_bytes == 6
