import json
from pathlib import Path

from nix_agent import runner
from nix_agent.target import Target
from nix_agent.tools import build as build_mod
from nix_agent.tools import locate as locate_mod
from nix_agent.tools import switch as switch_mod
from nix_agent.tools.build import build, diff
from nix_agent.tools.check import check
from nix_agent.tools.eval import eval_config
from nix_agent.tools.locate import locate_option
from nix_agent.tools.switch import generations, switch


SNAPSHOT = Path("tests/snapshots/tool_envelopes.json")

NIXOS_REBUILD_JSON = (
    '[{"generation": 41, "date": "2026-06-01 10:00:00", "current": false},'
    ' {"generation": 42, "date": "2026-06-10 09:30:00", "current": true}]'
)

SWITCH_LOG = """\
building '/nix/store/aaaa-foo.drv'...
activating the configuration...
stopping the following units: old.service
starting the following units: new.service
"""

NVD_FIXTURE = """\
Version changes:
[U.]  #1  firefox  128.0 -> 129.0
"""

LOCATED = json.dumps(
    {
        "is_option": True,
        "declarations": ["/nix/store/aaa-source/nixos/modules/ssh.nix"],
        "definitions": [
            {"file": "/home/u/nixos/modules/ssh.nix", "value": True},
        ],
    }
)


def _schema(value):
    if isinstance(value, dict):
        return {key: _schema(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        return [_schema(value[0])] if value else []
    if value is None:
        return "null"
    return type(value).__name__


def _result(ok, stdout="", stderr="", command=("x",)):
    return runner.RunResult(ok=ok, command=list(command), stdout=stdout, stderr=stderr)


def _local_flake(tmp_path):
    flake = tmp_path / "flake-root"
    flake.mkdir()
    (flake / "flake.nix").write_text("{ }\n")
    return str(flake)


def test_public_tool_envelope_schemas_match_snapshot(monkeypatch, tmp_path):
    flake = _local_flake(tmp_path)
    monkeypatch.delenv("NIX_AGENT_FLAKE", raising=False)
    monkeypatch.delenv("NIX_AGENT_ALLOW_REMOTE", raising=False)

    def ok_build(argv, cwd=None, timeout=None):
        return runner.RunResult(
            ok=True,
            command=argv,
            stdout="/nix/store/new-system\n",
            stderr="",
            raw_bytes=22,
        )

    monkeypatch.setattr(build_mod.runner, "run", ok_build)
    monkeypatch.setattr(
        build_mod,
        "resolve_target",
        lambda flake_uri, mode: Target(flake_dir="/x", attr="h", mode=mode),
    )
    monkeypatch.setattr(
        build_mod, "_current_closure", lambda mode: "/run/current-system"
    )

    def nvd_aware_run(argv, cwd=None, timeout=None):
        if argv and argv[0] == "/bin/nvd":
            return _result(True, stdout=NVD_FIXTURE, command=argv)
        return ok_build(argv, cwd=cwd, timeout=timeout)

    monkeypatch.setattr(build_mod.runner, "resolve_binary", lambda n: f"/bin/{n}")
    monkeypatch.setattr(build_mod.runner, "run", nvd_aware_run)
    build_ok = build(flake_uri="/x#h")
    diff_ok = diff(flake_uri="/x#h")

    systemctl_calls = iter(["[]", '[{"unit": "broken.service"}]'])

    def switch_success_run(argv, cwd=None):
        if argv and argv[0] == "systemctl":
            return _result(True, stdout=next(systemctl_calls), command=argv)
        if argv and argv[0] == "journalctl":
            return _result(True, stdout="unit crashed\n", command=argv)
        return _result(True, stdout=SWITCH_LOG, command=argv)

    monkeypatch.setattr(switch_mod.runner, "resolve_binary", lambda n: f"/bin/{n}")
    monkeypatch.setattr(switch_mod, "_current_generation", lambda mode: "gen-42")
    monkeypatch.setattr(switch_mod.runner, "run", switch_success_run)
    switch_ok = switch(flake_uri=f"{flake}#h")

    def privilege_run(argv, cwd=None):
        return _result(
            False,
            stderr="sudo: a terminal is required to read the password",
            command=argv,
        )

    monkeypatch.setattr(switch_mod.runner, "run", privilege_run)
    switch_privilege = switch(flake_uri=f"{flake}#h")

    def drv_run(argv, cwd=None):
        if argv[:2] == ["nix", "log"]:
            return _result(True, stdout="unit build exploded\n", command=argv)
        return _result(
            False,
            stderr="error: builder for '/nix/store/abc-x.drv' failed with exit code 1",
            command=argv,
        )

    monkeypatch.setattr(switch_mod.runner, "run", drv_run)
    switch_drv = switch(flake_uri=f"{flake}#h")

    store41 = tmp_path / "store-41"
    store41.mkdir()
    profile = tmp_path / "system"
    (tmp_path / "system-41-link").symlink_to(store41)
    monkeypatch.setattr(switch_mod, "SYSTEM_PROFILE", str(profile))

    def list_run(argv, cwd=None):
        if "list-generations" in argv:
            return _result(True, stdout=NIXOS_REBUILD_JSON, command=argv)
        return _result(True, command=argv)

    monkeypatch.setattr(switch_mod.runner, "run", list_run)
    generations_list = generations()
    unknown_generation = generations(action="rollback", generation=99)

    monkeypatch.setattr(
        locate_mod.runner,
        "run",
        lambda argv, cwd=None: _result(True, stdout=LOCATED, command=argv),
    )
    locate_ok = locate_option("services.openssh.enable", flake_uri="/x#h")

    pin = tmp_path / "nixos"
    pin.mkdir()
    (pin / "flake.nix").write_text("{ }\n")
    monkeypatch.setenv("NIX_AGENT_FLAKE", f"{pin}#laptop")
    target_locked = switch(flake_uri="/tmp/other#host")
    monkeypatch.delenv("NIX_AGENT_FLAKE", raising=False)
    remote_ref_rejected = switch(flake_uri="github:example/nixos#host")

    examples = {
        "build_ok": build_ok,
        "check_invalid_level": check("bogus", flake_uri="/x#h"),
        "eval_invalid_attr": eval_config([], flake_uri="/x#h"),
        "generations_invalid_action": generations(action="bogus"),
        "locate_not_an_option": {
            "status": "not_an_option",
            "resolved_target": '/x#nixosConfigurations."h".options.networking',
            "attr": "networking",
            "hint": "plain config value",
        },
        "switch_ok": switch_ok,
        "switch_privilege": switch_privilege,
        "switch_failed_derivation": switch_drv,
        "diff_ok_packages": diff_ok,
        "locate_ok": locate_ok,
        "generations_list_nixos": generations_list,
        "unknown_generation": unknown_generation,
        "target_locked": target_locked,
        "remote_ref_rejected": remote_ref_rejected,
    }

    actual = {
        name: _schema(runner.strip_accounting(dict(value)))
        for name, value in examples.items()
    }
    expected = json.loads(SNAPSHOT.read_text())
    assert actual == expected
