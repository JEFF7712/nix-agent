from nix_agent.runner import RunResult
from nix_agent.tools import switch as switch_mod
from nix_agent.tools.switch import generations, switch


def _result(ok, stdout="", stderr="", command=("x",)):
    return RunResult(ok=ok, command=list(command), stdout=stdout, stderr=stderr)


NIX_ENV_LISTING = """\
  41   2026-06-01 10:00:00
  42   2026-06-10 09:30:00   (current)
"""

NIXOS_REBUILD_JSON = (
    '[{"generation": 41, "date": "2026-06-01 10:00:00", "current": false},'
    ' {"generation": 42, "date": "2026-06-10 09:30:00", "current": true}]'
)

HM_LISTING = """\
2026-06-10 09:31 : id 88 -> /nix/store/new-hm-gen (current)
2026-06-01 10:01 : id 87 -> /nix/store/old-hm-gen
"""


def test_switch_nixos(monkeypatch):
    calls = []
    gens = iter(["/nix/var/.../system-42-link", "/nix/var/.../system-43-link"])

    def fake_run(argv, cwd=None):
        calls.append(argv)
        return _result(True, command=argv)

    monkeypatch.setattr(switch_mod.runner, "run", fake_run)
    monkeypatch.setattr(switch_mod.runner, "resolve_binary", lambda n: f"/bin/{n}")
    monkeypatch.setattr(switch_mod, "_current_generation", lambda mode: next(gens))
    out = switch(flake_uri="/etc/nixos#zen")
    assert out["status"] == "ok"
    assert out["rollback_generation"] == "/nix/var/.../system-42-link"
    assert out["current_generation"] == "/nix/var/.../system-43-link"
    assert [
        "sudo",
        "/bin/nixos-rebuild",
        "switch",
        "--flake",
        "/etc/nixos#zen",
    ] in calls


def test_switch_hm_no_sudo(monkeypatch):
    calls = []

    def fake_run(argv, cwd=None):
        calls.append(argv)
        return _result(True, command=argv)

    monkeypatch.setattr(switch_mod.runner, "run", fake_run)
    monkeypatch.setattr(switch_mod, "_current_generation", lambda mode: None)
    out = switch(flake_uri="/x#rupan", mode="home-manager")
    assert out["status"] == "ok"
    assert ["home-manager", "switch", "--flake", "/x#rupan"] in calls


def test_switch_failure_keeps_rollback(monkeypatch):
    def fake_run(argv, cwd=None):
        return _result(False, stderr="error: activation failed", command=argv)

    monkeypatch.setattr(switch_mod.runner, "run", fake_run)
    monkeypatch.setattr(switch_mod.runner, "resolve_binary", lambda n: f"/bin/{n}")
    monkeypatch.setattr(switch_mod, "_current_generation", lambda mode: "gen-42")
    out = switch(flake_uri="/x#h")
    assert out["status"] == "failed"
    assert out["rollback_generation"] == "gen-42"
    assert out["first_error"] == "error: activation failed"


SWITCH_LOG = """\
building '/nix/store/aaaa-foo.drv'...
building '/nix/store/bbbb-bar.drv'...
activating the configuration...
stopping the following units: old.service
reloading the following units: dbus.service, systemd-logind.service
restarting the following units: nscd.service
starting the following units: new.service
the following new units were started: fresh.service
"""


def test_switch_summary_and_trimmed_log(monkeypatch):
    def fake_run(argv, cwd=None):
        return _result(True, stdout=SWITCH_LOG, command=argv)

    monkeypatch.setattr(switch_mod.runner, "run", fake_run)
    monkeypatch.setattr(switch_mod.runner, "resolve_binary", lambda n: f"/bin/{n}")
    monkeypatch.setattr(switch_mod, "_current_generation", lambda mode: "gen")
    out = switch(flake_uri="/x#h")
    summary = out["summary"]
    assert summary["derivations_built"] == 2
    assert summary["changed"] is True
    assert summary["units"]["stopped"] == ["old.service"]
    assert summary["units"]["reloaded"] == ["dbus.service", "systemd-logind.service"]
    assert summary["units"]["restarted"] == ["nscd.service"]
    assert summary["units"]["started"] == ["new.service"]
    assert summary["units"]["new"] == ["fresh.service"]


def test_switch_full_log(monkeypatch):
    big = "x" * 5000

    def fake_run(argv, cwd=None):
        return _result(True, stdout=big, command=argv)

    monkeypatch.setattr(switch_mod.runner, "run", fake_run)
    monkeypatch.setattr(switch_mod.runner, "resolve_binary", lambda n: f"/bin/{n}")
    monkeypatch.setattr(switch_mod, "_current_generation", lambda mode: "gen")

    trimmed = switch(flake_uri="/x#h")
    assert trimmed["log_truncated"] is True
    assert len(trimmed["output"]) < len(big)

    full = switch(flake_uri="/x#h", full_log=True)
    assert full["output"] == big
    assert "log_truncated" not in full


def test_switch_sudo_diagnosis(monkeypatch):
    def fake_run(argv, cwd=None):
        return _result(
            False,
            stderr="sudo: a terminal is required to read the password",
            command=argv,
        )

    monkeypatch.setattr(switch_mod.runner, "run", fake_run)
    monkeypatch.setattr(switch_mod.runner, "resolve_binary", lambda n: f"/bin/{n}")
    monkeypatch.setattr(switch_mod, "_current_generation", lambda mode: "gen")
    out = switch(flake_uri="/x#h")
    assert out["status"] == "failed"
    assert out["rollback_generation"] == "gen"
    assert "sudo" in out["privilege"]["cause"]
    assert out["privilege"]["command_form"][0] == "sudo"


def test_switch_validate_aborts_on_failed_dry_build(monkeypatch):
    ran = []

    def fake_run(argv, cwd=None):
        ran.append(argv)
        return _result(True, command=argv)

    monkeypatch.setattr(switch_mod.runner, "run", fake_run)
    monkeypatch.setattr(switch_mod.runner, "resolve_binary", lambda n: f"/bin/{n}")
    monkeypatch.setattr(
        switch_mod,
        "check",
        lambda *a, **k: {"status": "failed", "first_error": "error: boom"},
    )
    out = switch(flake_uri="/x#h", validate=True)
    assert out["status"] == "preflight_failed"
    assert out["first_error"] == "error: boom"
    assert ran == []


def test_switch_validate_proceeds_when_dry_build_ok(monkeypatch):
    ran = []

    def fake_run(argv, cwd=None):
        ran.append(argv)
        return _result(True, command=argv)

    monkeypatch.setattr(switch_mod.runner, "run", fake_run)
    monkeypatch.setattr(switch_mod.runner, "resolve_binary", lambda n: f"/bin/{n}")
    monkeypatch.setattr(switch_mod, "_current_generation", lambda mode: "gen")
    monkeypatch.setattr(switch_mod, "check", lambda *a, **k: {"status": "ok"})
    out = switch(flake_uri="/x#h", validate=True)
    assert out["status"] == "ok"
    assert any(argv[0] == "sudo" for argv in ran)


def test_generations_list_nixos(monkeypatch):
    def fake_run(argv, cwd=None):
        assert argv == ["/bin/nixos-rebuild", "list-generations", "--json"]
        return _result(True, stdout=NIXOS_REBUILD_JSON, command=argv)

    monkeypatch.setattr(switch_mod.runner, "run", fake_run)
    monkeypatch.setattr(switch_mod.runner, "resolve_binary", lambda n: f"/bin/{n}")
    out = generations()
    assert out["status"] == "ok"
    assert out["generations"] == [
        {"id": 41, "date": "2026-06-01 10:00:00", "current": False},
        {"id": 42, "date": "2026-06-10 09:30:00", "current": True},
    ]


def test_generations_list_nixos_falls_back_to_nix_env(monkeypatch):
    def fake_run(argv, cwd=None):
        if "list-generations" in argv:
            return _result(False, stderr="error: unknown command", command=argv)
        assert argv == [
            "nix-env",
            "--list-generations",
            "-p",
            "/nix/var/nix/profiles/system",
        ]
        return _result(True, stdout=NIX_ENV_LISTING, command=argv)

    monkeypatch.setattr(switch_mod.runner, "run", fake_run)
    monkeypatch.setattr(switch_mod.runner, "resolve_binary", lambda n: f"/bin/{n}")
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
    monkeypatch.setattr(switch_mod.runner, "resolve_binary", lambda n: f"/bin/{n}")
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
    single = "2026-06-10 09:31 : id 88 -> /nix/store/only-gen (current)\n"

    def fake_run(argv, cwd=None):
        return _result(True, stdout=single, command=argv)

    monkeypatch.setattr(switch_mod.runner, "run", fake_run)
    out = generations(action="rollback", mode="home-manager")
    assert out["status"] == "failed"
    assert "previous" in out["error"]


def test_generations_rollback_hm_current_not_newest(monkeypatch):
    listing = (
        "2026-06-10 09:31 : id 88 -> /nix/store/new-hm-gen\n"
        "2026-06-01 10:01 : id 87 -> /nix/store/mid-hm-gen (current)\n"
        "2026-05-20 08:00 : id 86 -> /nix/store/old-hm-gen\n"
    )
    calls = []

    def fake_run(argv, cwd=None):
        calls.append(argv)
        if argv[0] == "home-manager":
            return _result(True, stdout=listing, command=argv)
        return _result(True, command=argv)

    monkeypatch.setattr(switch_mod.runner, "run", fake_run)
    out = generations(action="rollback", mode="home-manager")
    assert out["status"] == "ok"
    assert calls[-1] == ["/nix/store/old-hm-gen/activate"]


def test_switch_no_target(monkeypatch, tmp_path):
    from pathlib import Path

    from nix_agent import target as target_mod

    monkeypatch.delenv("NIX_AGENT_FLAKE", raising=False)
    monkeypatch.setattr(target_mod, "NIXOS_DEFAULT_DIR", tmp_path / "nope")
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "empty-home")
    out = switch()
    assert out["status"] == "no_target"


def test_generations_invalid_mode():
    out = generations(mode="bogus")
    assert out["status"] == "no_target"


def test_generations_invalid_action():
    out = generations(action="explode")
    assert out["status"] == "invalid_action"


def test_switch_summary_packages(monkeypatch):
    gens = iter(["/nix/store/old-gen", "/nix/store/new-gen"])
    nvd_out = "Version changes:\n[U.]  #1  firefox  128.0 -> 129.0\n"

    def fake_run(argv, cwd=None):
        if argv[0] == "/bin/nvd":
            assert argv[1:] == ["diff", "/nix/store/old-gen", "/nix/store/new-gen"]
            return _result(True, stdout=nvd_out, command=argv)
        return _result(True, stdout=SWITCH_LOG, command=argv)

    monkeypatch.setattr(switch_mod.runner, "run", fake_run)
    monkeypatch.setattr(switch_mod.runner, "resolve_binary", lambda n: f"/bin/{n}")
    monkeypatch.setattr(switch_mod, "_current_generation", lambda mode: next(gens))
    out = switch(flake_uri="/x#h")
    assert out["summary"]["packages"]["changed"] == [
        {"name": "firefox", "old": "128.0", "new": "129.0"}
    ]


def test_switch_summary_packages_skipped_without_generations(monkeypatch):
    def fake_run(argv, cwd=None):
        assert argv[0] != "/bin/nvd"
        return _result(True, stdout=SWITCH_LOG, command=argv)

    monkeypatch.setattr(switch_mod.runner, "run", fake_run)
    monkeypatch.setattr(switch_mod.runner, "resolve_binary", lambda n: f"/bin/{n}")
    monkeypatch.setattr(switch_mod, "_current_generation", lambda mode: None)
    out = switch(flake_uri="/x#h")
    assert "packages" not in out["summary"]


def test_switch_reports_newly_failed_units(monkeypatch):
    systemctl_calls = iter(["[]", '[{"unit": "broken.service"}]'])

    def fake_run(argv, cwd=None):
        if argv[0] == "systemctl":
            return _result(True, stdout=next(systemctl_calls), command=argv)
        if argv[0] == "journalctl":
            return _result(True, stdout="unit crashed\n", command=argv)
        return _result(True, stdout=SWITCH_LOG, command=argv)

    monkeypatch.setattr(switch_mod.runner, "run", fake_run)
    monkeypatch.setattr(switch_mod.runner, "resolve_binary", lambda n: f"/bin/{n}")
    monkeypatch.setattr(switch_mod, "_current_generation", lambda mode: "gen")
    out = switch(flake_uri="/x#h")
    assert out["status"] == "ok"
    health = out["summary"]["health"]
    assert health["newly_failed"] == [
        {"unit": "broken.service", "log_tail": "unit crashed\n"}
    ]
    assert health["resolved"] == []
    assert health["still_failed"] == []


def test_switch_health_degrades_to_note(monkeypatch):
    def fake_run(argv, cwd=None):
        if argv[0] == "systemctl":
            return _result(False, stderr="nope", command=argv)
        return _result(True, stdout=SWITCH_LOG, command=argv)

    monkeypatch.setattr(switch_mod.runner, "run", fake_run)
    monkeypatch.setattr(switch_mod.runner, "resolve_binary", lambda n: f"/bin/{n}")
    monkeypatch.setattr(switch_mod, "_current_generation", lambda mode: "gen")
    out = switch(flake_uri="/x#h")
    assert out["status"] == "ok"
    assert "health" not in out["summary"]
    assert "skipped" in out["health_note"]


def test_switch_failure_attaches_failed_derivation(monkeypatch):
    def fake_run(argv, cwd=None):
        if argv[:2] == ["nix", "log"]:
            return _result(True, stdout="unit build exploded\n", command=argv)
        return _result(
            False,
            stderr="error: builder for '/nix/store/abc-x.drv' failed with exit code 1",
            command=argv,
        )

    monkeypatch.setattr(switch_mod.runner, "run", fake_run)
    monkeypatch.setattr(switch_mod.runner, "resolve_binary", lambda n: f"/bin/{n}")
    monkeypatch.setattr(switch_mod, "_current_generation", lambda mode: "gen")
    out = switch(flake_uri="/x#h")
    assert out["status"] == "failed"
    assert out["failed_derivation"]["drv"] == "/nix/store/abc-x.drv"
    assert out["failed_derivation"]["log_tail"] == "unit build exploded\n"
