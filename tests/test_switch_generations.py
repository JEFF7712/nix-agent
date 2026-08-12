from nix_agent.runner import RunResult
from nix_agent.tools import switch as switch_mod
from nix_agent.tools.switch import generations, switch


def _result(ok, stdout="", stderr="", command=("x",)):
    return RunResult(ok=ok, command=list(command), stdout=stdout, stderr=stderr)


def _unlock(monkeypatch):
    monkeypatch.setattr(
        switch_mod,
        "constrain_privileged_target",
        lambda target, *, mode: None,
        raising=False,
    )


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
    _unlock(monkeypatch)
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
    _unlock(monkeypatch)
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
    _unlock(monkeypatch)

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
    _unlock(monkeypatch)

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
    _unlock(monkeypatch)
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
    _unlock(monkeypatch)

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
    _unlock(monkeypatch)
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
    _unlock(monkeypatch)
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
    assert [
        {k: g[k] for k in ("id", "date", "current")} for g in out["generations"]
    ] == [
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
    assert [
        {k: g[k] for k in ("id", "date", "current")} for g in out["generations"]
    ] == [
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
    _unlock(monkeypatch)
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
    _unlock(monkeypatch)

    def fake_run(argv, cwd=None):
        assert argv[0] != "/bin/nvd"
        return _result(True, stdout=SWITCH_LOG, command=argv)

    monkeypatch.setattr(switch_mod.runner, "run", fake_run)
    monkeypatch.setattr(switch_mod.runner, "resolve_binary", lambda n: f"/bin/{n}")
    monkeypatch.setattr(switch_mod, "_current_generation", lambda mode: None)
    out = switch(flake_uri="/x#h")
    assert "packages" not in out["summary"]


def test_switch_reports_newly_failed_units(monkeypatch):
    _unlock(monkeypatch)
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
    _unlock(monkeypatch)

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
    _unlock(monkeypatch)

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


def test_switch_summary_packages_unparseable(monkeypatch):
    _unlock(monkeypatch)
    gens = iter(["/nix/store/old-gen", "/nix/store/new-gen"])

    def fake_run(argv, cwd=None):
        if argv[0] == "/bin/nvd":
            return _result(True, stdout="garbled beyond recognition", command=argv)
        if argv[0] == "systemctl":
            return _result(True, stdout="[]", command=argv)
        return _result(True, stdout=SWITCH_LOG, command=argv)

    monkeypatch.setattr(switch_mod.runner, "run", fake_run)
    monkeypatch.setattr(switch_mod.runner, "resolve_binary", lambda n: f"/bin/{n}")
    monkeypatch.setattr(switch_mod, "_current_generation", lambda mode: next(gens))
    out = switch(flake_uri="/x#h")
    assert out["status"] == "ok"
    assert "packages" not in out["summary"]


def test_generations_list_nixos_includes_path(monkeypatch, tmp_path):
    store41 = tmp_path / "store-41"
    store41.mkdir()
    profile = tmp_path / "system"
    (tmp_path / "system-41-link").symlink_to(store41)
    monkeypatch.setattr(switch_mod, "SYSTEM_PROFILE", str(profile))

    def fake_run(argv, cwd=None):
        return _result(True, stdout=NIXOS_REBUILD_JSON, command=argv)

    monkeypatch.setattr(switch_mod.runner, "run", fake_run)
    monkeypatch.setattr(switch_mod.runner, "resolve_binary", lambda n: f"/bin/{n}")
    out = generations()
    by_id = {g["id"]: g for g in out["generations"]}
    assert by_id[41]["path"] == str(store41.resolve())
    assert "path" not in by_id[42]


def test_generations_targeted_rollback_nixos_by_id(monkeypatch, tmp_path):
    calls = []
    profile = tmp_path / "system"
    monkeypatch.setattr(switch_mod, "SYSTEM_PROFILE", str(profile))

    def fake_run(argv, cwd=None):
        calls.append(argv)
        if "list-generations" in argv:
            return _result(True, stdout=NIXOS_REBUILD_JSON, command=argv)
        return _result(True, command=argv)

    monkeypatch.setattr(switch_mod.runner, "run", fake_run)
    monkeypatch.setattr(switch_mod.runner, "resolve_binary", lambda n: f"/bin/{n}")
    monkeypatch.setattr(switch_mod, "_current_generation", lambda mode: "gen")
    out = generations(action="rollback", generation=41)
    assert out["status"] == "ok"
    assert [
        "sudo",
        "/bin/nix-env",
        "-p",
        str(profile),
        "--switch-generation",
        "41",
    ] in calls
    assert [
        "sudo",
        f"{profile}/bin/switch-to-configuration",
        "switch",
    ] in calls
    assert not any("--rollback" in argv for argv in calls)
    assert not any(
        any(
            arg.startswith("/nix/store/") and "switch-to-configuration" in arg
            for arg in argv
        )
        for argv in calls
    )


def test_generations_targeted_rollback_nixos_by_digit_string(monkeypatch, tmp_path):
    calls = []
    profile = tmp_path / "system"
    monkeypatch.setattr(switch_mod, "SYSTEM_PROFILE", str(profile))

    def fake_run(argv, cwd=None):
        calls.append(argv)
        if "list-generations" in argv:
            return _result(True, stdout=NIXOS_REBUILD_JSON, command=argv)
        return _result(True, command=argv)

    monkeypatch.setattr(switch_mod.runner, "run", fake_run)
    monkeypatch.setattr(switch_mod.runner, "resolve_binary", lambda n: f"/bin/{n}")
    monkeypatch.setattr(switch_mod, "_current_generation", lambda mode: "gen")
    out = generations(action="rollback", generation="41")
    assert out["status"] == "ok"
    assert any("--switch-generation" in argv and "41" in argv for argv in calls)
    assert not any("--rollback" in argv for argv in calls)


def test_generations_targeted_rollback_nixos_by_profile_and_store_path(
    monkeypatch, tmp_path
):
    store41 = tmp_path / "store-41"
    store41.mkdir()
    profile = tmp_path / "system"
    link = tmp_path / "system-41-link"
    link.symlink_to(store41)
    monkeypatch.setattr(switch_mod, "SYSTEM_PROFILE", str(profile))

    def fake_run(argv, cwd=None):
        if "list-generations" in argv:
            return _result(True, stdout=NIXOS_REBUILD_JSON, command=argv)
        return _result(True, command=argv)

    monkeypatch.setattr(switch_mod.runner, "run", fake_run)
    monkeypatch.setattr(switch_mod.runner, "resolve_binary", lambda n: f"/bin/{n}")
    monkeypatch.setattr(switch_mod, "_current_generation", lambda mode: "gen")

    by_link = generations(action="rollback", generation=str(link))
    assert by_link["status"] == "ok"
    by_store = generations(action="rollback", generation=str(store41.resolve()))
    assert by_store["status"] == "ok"


def test_generations_unknown_generation_runs_no_sudo(monkeypatch):
    calls = []

    def fake_run(argv, cwd=None):
        calls.append(argv)
        if "list-generations" in argv:
            return _result(True, stdout=NIXOS_REBUILD_JSON, command=argv)
        return _result(True, command=argv)

    monkeypatch.setattr(switch_mod.runner, "run", fake_run)
    monkeypatch.setattr(switch_mod.runner, "resolve_binary", lambda n: f"/bin/{n}")
    out = generations(action="rollback", generation=99)
    assert out["status"] == "unknown_generation"
    assert "command" not in out
    assert "output" not in out
    assert "raw_bytes" not in out
    assert "returned_bytes" not in out
    assert not any(argv and argv[0] == "sudo" for argv in calls)


def test_generations_rollback_sudo_diagnosis(monkeypatch):
    def fake_run(argv, cwd=None):
        return _result(
            False,
            stderr="sudo: a terminal is required to read the password",
            command=argv,
        )

    monkeypatch.setattr(switch_mod.runner, "run", fake_run)
    monkeypatch.setattr(switch_mod.runner, "resolve_binary", lambda n: f"/bin/{n}")
    monkeypatch.setattr(switch_mod, "_current_generation", lambda mode: "gen")
    out = generations(action="rollback")
    assert out["status"] == "failed"
    assert "sudo" in out["privilege"]["cause"]
    assert out["privilege"]["command_form"][0] == "sudo"


def test_generations_targeted_rollback_sudo_diagnosis(monkeypatch, tmp_path):
    calls = []
    profile = tmp_path / "system"
    monkeypatch.setattr(switch_mod, "SYSTEM_PROFILE", str(profile))

    def fake_run(argv, cwd=None):
        calls.append(argv)
        if "list-generations" in argv:
            return _result(True, stdout=NIXOS_REBUILD_JSON, command=argv)
        return _result(
            False,
            stderr="sudo: a terminal is required to read the password",
            command=argv,
        )

    monkeypatch.setattr(switch_mod.runner, "run", fake_run)
    monkeypatch.setattr(switch_mod.runner, "resolve_binary", lambda n: f"/bin/{n}")
    monkeypatch.setattr(switch_mod, "_current_generation", lambda mode: "gen")
    out = generations(action="rollback", generation=41)
    assert out["status"] == "failed"
    assert "privilege" in out
    assert "--switch-generation" in out["privilege"]["command_form"]
    assert not any(
        "switch-to-configuration" in (argv[1] if len(argv) > 1 else "")
        for argv in calls
    )


def test_generations_targeted_step1_fail_skips_step2(monkeypatch, tmp_path):
    calls = []
    profile = tmp_path / "system"
    monkeypatch.setattr(switch_mod, "SYSTEM_PROFILE", str(profile))

    def fake_run(argv, cwd=None):
        calls.append(argv)
        if "list-generations" in argv:
            return _result(True, stdout=NIXOS_REBUILD_JSON, command=argv)
        if "--switch-generation" in argv:
            return _result(False, stderr="error: boom", command=argv)
        return _result(True, command=argv)

    monkeypatch.setattr(switch_mod.runner, "run", fake_run)
    monkeypatch.setattr(switch_mod.runner, "resolve_binary", lambda n: f"/bin/{n}")
    monkeypatch.setattr(switch_mod, "_current_generation", lambda mode: "gen")
    out = generations(action="rollback", generation=41)
    assert out["status"] == "failed"
    assert not any(
        "switch-to-configuration" in (argv[1] if len(argv) > 1 else "")
        for argv in calls
    )


def test_generations_targeted_step2_fail_notes_pointer(monkeypatch, tmp_path):
    profile = tmp_path / "system"
    monkeypatch.setattr(switch_mod, "SYSTEM_PROFILE", str(profile))

    def fake_run(argv, cwd=None):
        if "list-generations" in argv:
            return _result(True, stdout=NIXOS_REBUILD_JSON, command=argv)
        if len(argv) > 1 and "switch-to-configuration" in argv[1]:
            return _result(False, stderr="error: activate failed", command=argv)
        return _result(True, command=argv)

    monkeypatch.setattr(switch_mod.runner, "run", fake_run)
    monkeypatch.setattr(switch_mod.runner, "resolve_binary", lambda n: f"/bin/{n}")
    monkeypatch.setattr(
        switch_mod, "_current_generation", lambda mode: "/nix/store/gen-41"
    )
    out = generations(action="rollback", generation=41)
    assert out["status"] == "failed"
    assert out["current_generation"] == "/nix/store/gen-41"
    assert "note" in out


def test_generations_targeted_rollback_hm_by_id(monkeypatch):
    calls = []

    def fake_run(argv, cwd=None):
        calls.append(argv)
        if argv[0] == "home-manager":
            return _result(True, stdout=HM_LISTING, command=argv)
        return _result(True, command=argv)

    monkeypatch.setattr(switch_mod.runner, "run", fake_run)
    out = generations(action="rollback", mode="home-manager", generation=87)
    assert out["status"] == "ok"
    assert calls[-1] == ["/nix/store/old-hm-gen/activate"]


def test_generations_targeted_rollback_hm_by_path(monkeypatch):
    calls = []

    def fake_run(argv, cwd=None):
        calls.append(argv)
        if argv[0] == "home-manager":
            return _result(True, stdout=HM_LISTING, command=argv)
        return _result(True, command=argv)

    monkeypatch.setattr(switch_mod.runner, "run", fake_run)
    out = generations(
        action="rollback",
        mode="home-manager",
        generation="/nix/store/old-hm-gen",
    )
    assert out["status"] == "ok"
    assert calls[-1] == ["/nix/store/old-hm-gen/activate"]


def test_generations_unknown_generation_hm(monkeypatch):
    calls = []

    def fake_run(argv, cwd=None):
        calls.append(argv)
        return _result(True, stdout=HM_LISTING, command=argv)

    monkeypatch.setattr(switch_mod.runner, "run", fake_run)
    out = generations(action="rollback", mode="home-manager", generation=1)
    assert out["status"] == "unknown_generation"
    assert not any(str(argv[0]).endswith("/activate") for argv in calls if argv)


def test_switch_remote_ref_rejected_no_sudo(monkeypatch):
    calls = []

    def fake_run(argv, cwd=None):
        calls.append(argv)
        return _result(True, command=argv)

    monkeypatch.setattr(switch_mod.runner, "run", fake_run)
    monkeypatch.delenv("NIX_AGENT_ALLOW_REMOTE", raising=False)
    out = switch(flake_uri="github:example/nixos#host")
    assert out["status"] == "remote_ref_rejected"
    assert calls == []
    assert "NIX_AGENT_ALLOW_REMOTE" not in str(out)
    assert "command" not in out
    assert "raw_bytes" not in out


def test_switch_pin_lock(monkeypatch, tmp_path):
    pin = tmp_path / "nixos"
    pin.mkdir()
    (pin / "flake.nix").write_text("{ }\n")
    monkeypatch.setenv("NIX_AGENT_FLAKE", f"{pin}#laptop")
    monkeypatch.delenv("NIX_AGENT_ALLOW_REMOTE", raising=False)
    calls = []

    def fake_run(argv, cwd=None):
        calls.append(argv)
        return _result(True, command=argv)

    monkeypatch.setattr(switch_mod.runner, "run", fake_run)
    out = switch(flake_uri="/tmp/other#host")
    assert out["status"] == "target_locked"
    assert out["pin"] == f"{pin}#laptop"
    assert calls == []


def test_switch_same_dir_different_attr_proceeds(monkeypatch, tmp_path):
    pin = tmp_path / "nixos"
    pin.mkdir()
    (pin / "flake.nix").write_text("{ }\n")
    monkeypatch.setenv("NIX_AGENT_FLAKE", f"{pin}#laptop")
    calls = []

    def fake_run(argv, cwd=None):
        calls.append(argv)
        return _result(True, command=argv)

    monkeypatch.setattr(switch_mod.runner, "run", fake_run)
    monkeypatch.setattr(switch_mod.runner, "resolve_binary", lambda n: f"/bin/{n}")
    monkeypatch.setattr(switch_mod, "_current_generation", lambda mode: "gen")
    out = switch(flake_uri=f"{pin}#other")
    assert out["status"] == "ok"
    assert any(argv[0] == "sudo" for argv in calls)


def test_switch_nixos_pin_does_not_lock_hm(monkeypatch, tmp_path):
    nixos = tmp_path / "nixos"
    nixos.mkdir()
    (nixos / "flake.nix").write_text("{ }\n")
    hm = tmp_path / "home-manager"
    hm.mkdir()
    (hm / "flake.nix").write_text("{ }\n")
    monkeypatch.setenv("NIX_AGENT_FLAKE", f"{nixos}#laptop")
    monkeypatch.delenv("NIX_AGENT_HM_FLAKE", raising=False)
    calls = []

    def fake_run(argv, cwd=None):
        calls.append(argv)
        return _result(True, command=argv)

    monkeypatch.setattr(switch_mod.runner, "run", fake_run)
    monkeypatch.setattr(switch_mod, "_current_generation", lambda mode: None)
    out = switch(flake_uri=f"{hm}#me", mode="home-manager")
    assert out["status"] == "ok"
    assert ["home-manager", "switch", "--flake", f"{hm}#me"] in calls


def test_switch_allow_remote(monkeypatch):
    monkeypatch.setenv("NIX_AGENT_ALLOW_REMOTE", "1")
    monkeypatch.delenv("NIX_AGENT_FLAKE", raising=False)
    calls = []

    def fake_run(argv, cwd=None):
        calls.append(argv)
        return _result(True, command=argv)

    monkeypatch.setattr(switch_mod.runner, "run", fake_run)
    monkeypatch.setattr(switch_mod.runner, "resolve_binary", lambda n: f"/bin/{n}")
    monkeypatch.setattr(switch_mod, "_current_generation", lambda mode: "gen")
    out = switch(flake_uri="github:example/nixos#host")
    assert out["status"] == "ok"
    assert any(
        "--flake" in argv and "github:example/nixos#host" in argv for argv in calls
    )


def test_switch_validate_remote_skips_dry_build(monkeypatch):
    checked = []

    def fake_check(*a, **k):
        checked.append(1)
        return {"status": "ok"}

    monkeypatch.setattr(switch_mod, "check", fake_check)
    monkeypatch.delenv("NIX_AGENT_ALLOW_REMOTE", raising=False)
    out = switch(flake_uri="github:example/nixos#host", validate=True)
    assert out["status"] == "remote_ref_rejected"
    assert checked == []


def test_generations_does_not_apply_classifier(monkeypatch):
    calls = []

    def fake_run(argv, cwd=None):
        calls.append(argv)
        return _result(True, command=argv)

    monkeypatch.setattr(switch_mod.runner, "run", fake_run)
    monkeypatch.setattr(switch_mod.runner, "resolve_binary", lambda n: f"/bin/{n}")
    monkeypatch.setattr(switch_mod, "_current_generation", lambda mode: "gen")
    monkeypatch.setenv("NIX_AGENT_FLAKE", "/some/pin#host")
    out = generations(action="rollback")
    assert out["status"] == "ok"
    assert calls[0] == ["sudo", "/bin/nixos-rebuild", "switch", "--rollback"]
