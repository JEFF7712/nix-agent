import subprocess

from nix_agent import runner


def test_run_success_combines_streams(monkeypatch):
    def fake_run(argv, capture_output, text, cwd=None):
        return subprocess.CompletedProcess(argv, 0, stdout="out\n", stderr="warn\n")

    monkeypatch.setattr(runner.subprocess, "run", fake_run)
    result = runner.run(["true"])
    assert result.ok
    assert result.stdout == "out\n"
    assert result.output == "out\nwarn"
    assert result.command == ["true"]


def test_run_failure(monkeypatch):
    def fake_run(argv, capture_output, text, cwd=None):
        return subprocess.CompletedProcess(argv, 1, stdout="", stderr="error: boom\n")

    monkeypatch.setattr(runner.subprocess, "run", fake_run)
    result = runner.run(["false"])
    assert not result.ok
    assert "error: boom" in result.output


def test_run_missing_binary(monkeypatch):
    def fake_run(argv, capture_output, text, cwd=None):
        raise FileNotFoundError(argv[0])

    monkeypatch.setattr(runner.subprocess, "run", fake_run)
    result = runner.run(["nvd", "diff"])
    assert not result.ok
    assert "nvd: command not found" in result.output


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
