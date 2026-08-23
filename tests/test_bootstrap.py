from nix_agent.bootstrap import bootstrap_rebuild
from nix_agent.runner import RunResult
from nix_agent.tools import switch as switch_mod


def _result(ok, stdout="", stderr="", command=("x",)):
    return RunResult(ok=ok, command=list(command), stdout=stdout, stderr=stderr)


def _unlock(monkeypatch):
    monkeypatch.setattr(
        switch_mod,
        "prepare_privileged_target",
        lambda target, *, mode: target,
    )


def test_bootstrap_rebuild_ok_when_sudo_n_works(monkeypatch):
    _unlock(monkeypatch)

    def fake_run(argv, cwd=None):
        return _result(True, stdout="activating\n", command=argv)

    monkeypatch.setattr(switch_mod.runner, "run", fake_run)
    monkeypatch.setattr(switch_mod.runner, "resolve_binary", lambda n: f"/bin/{n}")
    monkeypatch.setattr(switch_mod, "_current_generation", lambda mode: "gen")
    out = bootstrap_rebuild(flake_uri="/x#h")
    assert out["status"] in {"ok", "degraded"}
    assert out["command"][0] == "sudo"
    assert out["command"][1] == "-n"
    assert "tty_command" not in out


def test_bootstrap_rebuild_prints_tty_command_when_sudo_n_fails(monkeypatch):
    _unlock(monkeypatch)

    def fake_run(argv, cwd=None):
        return _result(
            False,
            stderr="sudo: a password is required",
            command=argv,
        )

    monkeypatch.setattr(switch_mod.runner, "run", fake_run)
    monkeypatch.setattr(switch_mod.runner, "resolve_binary", lambda n: f"/bin/{n}")
    monkeypatch.setattr(switch_mod, "_current_generation", lambda mode: "gen")
    out = bootstrap_rebuild(flake_uri="/x#h")
    assert out["status"] == "needs_bootstrap"
    assert "privilege" in out
    assert out["tty_command"].startswith("sudo ")
    assert " -n " not in f" {out['tty_command']} "
    assert "/bin/nixos-rebuild" in out["tty_command"]
    assert "switch" in out["tty_command"]
