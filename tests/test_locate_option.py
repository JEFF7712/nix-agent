import json

from nix_agent.runner import RunResult
from nix_agent.tools import locate as locate_mod
from nix_agent.tools.locate import locate_option


def _result(ok, stdout="", stderr="", command=("nix",)):
    return RunResult(ok=ok, command=list(command), stdout=stdout, stderr=stderr)


LOCATED = json.dumps(
    {
        "is_option": True,
        "declarations": ["/nix/store/aaa-source/nixos/modules/ssh.nix"],
        "definitions": [
            {"file": "/home/u/nixos/modules/ssh.nix", "value": True},
            {"file": "/home/u/nixos/hosts/laptop.nix", "value": False},
        ],
    }
)


def test_locate_option_ok(monkeypatch):
    calls = []

    def fake_run(argv, cwd=None):
        calls.append(argv)
        return _result(True, stdout=LOCATED, command=argv)

    monkeypatch.setattr(locate_mod.runner, "run", fake_run)
    out = locate_option("services.openssh.enable", flake_uri="/x#h")
    assert out["status"] == "ok"
    assert out["attr"] == "services.openssh.enable"
    assert out["declarations"] == ["/nix/store/aaa-source/nixos/modules/ssh.nix"]
    assert out["definitions"][0] == {
        "file": "/home/u/nixos/modules/ssh.nix",
        "value": True,
    }
    argv = calls[0]
    assert argv[0:2] == ["nix", "eval"]
    assert argv[2] == '/x#nixosConfigurations."h".options.services.openssh.enable'
    assert argv[3] == "--apply"
    assert "scrub" in argv[4]
    assert argv[5] == "--json"


def test_locate_option_not_an_option(monkeypatch):
    payload = json.dumps({"is_option": False, "declarations": [], "definitions": []})

    def fake_run(argv, cwd=None):
        return _result(True, stdout=payload, command=argv)

    monkeypatch.setattr(locate_mod.runner, "run", fake_run)
    out = locate_option("networking", flake_uri="/x#h")
    assert out["status"] == "not_an_option"
    assert "eval_config" in out["hint"]


def test_locate_option_candidate_retry(monkeypatch):
    calls = []

    def fake_run(argv, cwd=None):
        calls.append(argv)
        if '"rupan@zen"' in argv[2]:
            return _result(
                False,
                stderr="error: flake does not provide attribute "
                "'homeConfigurations.\"rupan@zen\"'",
                command=argv,
            )
        return _result(True, stdout=LOCATED, command=argv)

    monkeypatch.setattr(locate_mod.runner, "run", fake_run)
    monkeypatch.setattr(locate_mod, "attr_candidates", lambda t: ["rupan@zen", "rupan"])
    out = locate_option("programs.fish.enable", flake_uri="/x", mode="home-manager")
    assert out["status"] == "ok"
    assert len(calls) == 2


def test_locate_option_missing_attr_is_not_an_option(monkeypatch):
    def fake_run(argv, cwd=None):
        return _result(
            False,
            stderr="error: flake 'git+file:///x' does not provide attribute "
            "'nixosConfigurations.\"h\".options.services.bogus.enable'",
            command=argv,
        )

    monkeypatch.setattr(locate_mod.runner, "run", fake_run)
    out = locate_option("services.bogus.enable", flake_uri="/x#h")
    assert out["status"] == "not_an_option"


def test_locate_option_real_failure(monkeypatch):
    def fake_run(argv, cwd=None):
        return _result(
            False, stderr="error: infinite recursion encountered", command=argv
        )

    monkeypatch.setattr(locate_mod.runner, "run", fake_run)
    out = locate_option("services.openssh.enable", flake_uri="/x#h")
    assert out["status"] == "failed"
    assert out["first_error"] == "error: infinite recursion encountered"


def test_locate_option_definition_values_guarded(monkeypatch):
    big = {
        "is_option": True,
        "declarations": [],
        "definitions": [
            {"file": "/f.nix", "value": {f"k{i:03d}": "x" * 50 for i in range(100)}}
        ],
    }

    def fake_run(argv, cwd=None):
        return _result(True, stdout=json.dumps(big), command=argv)

    monkeypatch.setattr(locate_mod.runner, "run", fake_run)
    out = locate_option("environment.etc", flake_uri="/x#h")
    assert out["status"] == "ok"
    definition = out["definitions"][0]
    assert definition["truncated"] is True
    assert definition["value"]["attr_names"] == sorted(big["definitions"][0]["value"])


def test_locate_option_no_target(monkeypatch, tmp_path):
    from pathlib import Path

    from nix_agent import target as target_mod

    monkeypatch.delenv("NIX_AGENT_FLAKE", raising=False)
    monkeypatch.setattr(target_mod, "NIXOS_DEFAULT_DIR", tmp_path / "nope")
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "empty-home")
    out = locate_option("a.b")
    assert out["status"] == "no_target"
