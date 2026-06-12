from nix_agent.runner import RunResult
from nix_agent.tools import switch as switch_mod
from nix_agent.tools.switch import generations, switch


def _result(ok, stdout="", stderr="", command=("x",)):
    return RunResult(ok=ok, command=list(command), stdout=stdout, stderr=stderr)


NIX_ENV_LISTING = """\
  41   2026-06-01 10:00:00
  42   2026-06-10 09:30:00   (current)
"""

HM_LISTING = """\
2026-06-10 09:31 : id 88 -> /nix/store/new-hm-gen
2026-06-01 10:01 : id 87 -> /nix/store/old-hm-gen
"""


def test_switch_nixos(monkeypatch):
    calls = []
    gens = iter(["/nix/var/.../system-42-link", "/nix/var/.../system-43-link"])

    def fake_run(argv, cwd=None):
        calls.append(argv)
        return _result(True, command=argv)

    monkeypatch.setattr(switch_mod.runner, "run", fake_run)
    monkeypatch.setattr(
        switch_mod.runner, "resolve_binary", lambda n: f"/bin/{n}"
    )
    monkeypatch.setattr(
        switch_mod, "_current_generation", lambda mode: next(gens)
    )
    out = switch(flake_uri="/etc/nixos#zen")
    assert out["status"] == "ok"
    assert out["rollback_generation"] == "/nix/var/.../system-42-link"
    assert out["current_generation"] == "/nix/var/.../system-43-link"
    assert calls[0] == [
        "sudo", "/bin/nixos-rebuild", "switch", "--flake", "/etc/nixos#zen",
    ]


def test_switch_hm_no_sudo(monkeypatch):
    calls = []

    def fake_run(argv, cwd=None):
        calls.append(argv)
        return _result(True, command=argv)

    monkeypatch.setattr(switch_mod.runner, "run", fake_run)
    monkeypatch.setattr(switch_mod, "_current_generation", lambda mode: None)
    out = switch(flake_uri="/x#rupan", mode="home-manager")
    assert out["status"] == "ok"
    assert calls[0] == ["home-manager", "switch", "--flake", "/x#rupan"]


def test_switch_failure_keeps_rollback(monkeypatch):
    def fake_run(argv, cwd=None):
        return _result(False, stderr="error: activation failed", command=argv)

    monkeypatch.setattr(switch_mod.runner, "run", fake_run)
    monkeypatch.setattr(
        switch_mod.runner, "resolve_binary", lambda n: f"/bin/{n}"
    )
    monkeypatch.setattr(switch_mod, "_current_generation", lambda mode: "gen-42")
    out = switch(flake_uri="/x#h")
    assert out["status"] == "failed"
    assert out["rollback_generation"] == "gen-42"
    assert out["first_error"] == "error: activation failed"


def test_generations_list_nixos(monkeypatch):
    def fake_run(argv, cwd=None):
        assert argv == [
            "nix-env", "--list-generations", "-p", "/nix/var/nix/profiles/system",
        ]
        return _result(True, stdout=NIX_ENV_LISTING, command=argv)

    monkeypatch.setattr(switch_mod.runner, "run", fake_run)
    out = generations()
    assert out["status"] == "ok"
    assert out["generations"] == [
        {"id": 41, "date": "2026-06-01 10:00:00", "current": False},
        {"id": 42, "date": "2026-06-10 09:30:00", "current": True},
    ]


def test_generations_list_hm(monkeypatch):
    def fake_run(argv, cwd=None):
        return _result(True, stdout=HM_LISTING, command=argv)

    monkeypatch.setattr(switch_mod.runner, "run", fake_run)
    out = generations(mode="home-manager")
    assert out["status"] == "ok"
    assert out["generations"] == [
        {
            "id": 88,
            "date": "2026-06-10 09:31",
            "path": "/nix/store/new-hm-gen",
            "current": True,
        },
        {
            "id": 87,
            "date": "2026-06-01 10:01",
            "path": "/nix/store/old-hm-gen",
            "current": False,
        },
    ]


def test_generations_rollback_nixos(monkeypatch):
    calls = []

    def fake_run(argv, cwd=None):
        calls.append(argv)
        return _result(True, command=argv)

    monkeypatch.setattr(switch_mod.runner, "run", fake_run)
    monkeypatch.setattr(
        switch_mod.runner, "resolve_binary", lambda n: f"/bin/{n}"
    )
    monkeypatch.setattr(switch_mod, "_current_generation", lambda mode: "gen")
    out = generations(action="rollback")
    assert out["status"] == "ok"
    assert calls[0] == ["sudo", "/bin/nixos-rebuild", "switch", "--rollback"]


def test_generations_rollback_hm_activates_previous(monkeypatch):
    calls = []

    def fake_run(argv, cwd=None):
        calls.append(argv)
        if argv[0] == "home-manager":
            return _result(True, stdout=HM_LISTING, command=argv)
        return _result(True, command=argv)

    monkeypatch.setattr(switch_mod.runner, "run", fake_run)
    out = generations(action="rollback", mode="home-manager")
    assert out["status"] == "ok"
    assert calls[-1] == ["/nix/store/old-hm-gen/activate"]


def test_generations_rollback_hm_no_previous(monkeypatch):
    single = "2026-06-10 09:31 : id 88 -> /nix/store/only-gen\n"

    def fake_run(argv, cwd=None):
        return _result(True, stdout=single, command=argv)

    monkeypatch.setattr(switch_mod.runner, "run", fake_run)
    out = generations(action="rollback", mode="home-manager")
    assert out["status"] == "failed"
    assert "previous" in out["error"]


def test_generations_invalid_action():
    out = generations(action="explode")
    assert out["status"] == "invalid_action"
