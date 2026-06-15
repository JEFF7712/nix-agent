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
    assert runner.extract_first_error("error[E001]: bad thing") == "error[E001]: bad thing"


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
