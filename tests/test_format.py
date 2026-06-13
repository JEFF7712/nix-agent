from nix_agent.runner import RunResult
from nix_agent.tools import fmt as fmt_mod
from nix_agent.tools.fmt import format_nix


def _result(ok, stdout="", stderr="", command=("x",)):
    return RunResult(ok=ok, command=list(command), stdout=stdout, stderr=stderr)


def test_format_explicit_paths(monkeypatch):
    calls = []

    def fake_run(argv, cwd=None):
        calls.append(argv)
        return _result(True, command=argv)

    monkeypatch.setattr(fmt_mod.runner, "run", fake_run)
    monkeypatch.setattr(fmt_mod.runner, "resolve_binary", lambda n: "/bin/nixfmt")
    out = format_nix(paths=["/etc/nixos/a.nix", "/etc/nixos/b.txt"])
    assert out["status"] == "ok"
    assert out["formatter"] == "nixfmt"
    assert calls[0] == ["/bin/nixfmt", "/etc/nixos/a.nix"]
    assert out["skipped"] == ["/etc/nixos/b.txt"]


def test_format_explicit_paths_nixfmt_missing(monkeypatch):
    monkeypatch.setattr(fmt_mod.runner, "resolve_binary", lambda n: None)
    out = format_nix(paths=["/x/a.nix"])
    assert out["status"] == "tool_missing"
    assert out["missing"] == ["nixfmt"]


def test_format_whole_flake_uses_nix_fmt(monkeypatch, tmp_path):
    (tmp_path / "flake.nix").write_text("{}")
    calls = []

    def fake_run(argv, cwd=None):
        calls.append((argv, cwd))
        return _result(True, command=argv)

    monkeypatch.setattr(fmt_mod.runner, "run", fake_run)
    out = format_nix(flake_uri=str(tmp_path))
    assert out["status"] == "ok"
    assert out["formatter"] == "nix fmt"
    assert calls[0] == (["nix", "fmt"], str(tmp_path))


def test_format_falls_back_to_nixfmt_when_no_flake_formatter(
    monkeypatch, tmp_path
):
    (tmp_path / "flake.nix").write_text("{}")
    (tmp_path / "module.nix").write_text("{}")
    calls = []

    def fake_run(argv, cwd=None):
        calls.append(argv)
        if argv[:2] == ["nix", "fmt"]:
            return _result(
                False,
                stderr="error: flake does not provide attribute 'formatter'",
                command=argv,
            )
        return _result(True, command=argv)

    monkeypatch.setattr(fmt_mod.runner, "run", fake_run)
    monkeypatch.setattr(fmt_mod.runner, "resolve_binary", lambda n: "/bin/nixfmt")
    out = format_nix(flake_uri=str(tmp_path))
    assert out["status"] == "ok"
    assert out["formatter"] == "nixfmt"
    formatted = calls[-1]
    assert formatted[0] == "/bin/nixfmt"
    assert str(tmp_path / "flake.nix") in formatted
    assert str(tmp_path / "module.nix") in formatted


def test_format_real_formatter_failure_is_failed(monkeypatch, tmp_path):
    (tmp_path / "flake.nix").write_text("{}")

    def fake_run(argv, cwd=None):
        return _result(
            False,
            stderr="FAILED nixfmt-rfc-style: formatter failed: exit code 1",
            command=argv,
        )

    monkeypatch.setattr(fmt_mod.runner, "run", fake_run)
    out = format_nix(flake_uri=str(tmp_path))
    assert out["status"] == "failed"
    assert out["formatter"] == "nix fmt"


def test_format_fallback_nixfmt_missing(monkeypatch, tmp_path):
    (tmp_path / "flake.nix").write_text("{}")

    def fake_run(argv, cwd=None):
        return _result(
            False,
            stderr="error: flake does not provide attribute 'formatter'",
            command=argv,
        )

    monkeypatch.setattr(fmt_mod.runner, "run", fake_run)
    monkeypatch.setattr(fmt_mod.runner, "resolve_binary", lambda n: None)
    out = format_nix(flake_uri=str(tmp_path))
    assert out["status"] == "tool_missing"
    assert out["missing"] == ["nixfmt"]


def test_format_fallback_formats_flake_nix_itself(monkeypatch, tmp_path):
    (tmp_path / "flake.nix").write_text("{}")
    calls = []

    def fake_run(argv, cwd=None):
        calls.append(argv)
        if argv[:2] == ["nix", "fmt"]:
            return _result(
                False,
                stderr="error: flake does not provide attribute 'formatter'",
                command=argv,
            )
        return _result(True, command=argv)

    monkeypatch.setattr(fmt_mod.runner, "run", fake_run)
    monkeypatch.setattr(fmt_mod.runner, "resolve_binary", lambda n: "/bin/nixfmt")
    out = format_nix(flake_uri=str(tmp_path))
    assert out["status"] == "ok"
    assert calls[-1] == ["/bin/nixfmt", str(tmp_path / "flake.nix")]


def test_format_no_target(monkeypatch, tmp_path):
    from nix_agent import target as target_mod

    monkeypatch.setattr(target_mod, "NIXOS_DEFAULT_DIR", tmp_path / "nope")
    out = format_nix()
    assert out["status"] == "no_target"
