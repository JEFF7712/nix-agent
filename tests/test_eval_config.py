import json

from nix_agent.runner import RunResult
from nix_agent.tools import eval as eval_mod
from nix_agent.tools.eval import eval_config


def _result(ok, stdout="", stderr="", command=("nix",)):
    return RunResult(ok=ok, command=list(command), stdout=stdout, stderr=stderr)


def test_eval_ok_json(monkeypatch):
    calls = []

    def fake_run(argv, cwd=None):
        calls.append(argv)
        return _result(True, stdout="true\n", command=argv)

    monkeypatch.setattr(eval_mod.runner, "run", fake_run)
    out = eval_config(
        "services.openssh.enable", flake_uri="/etc/nixos#zen", mode="nixos"
    )
    assert out["status"] == "ok"
    assert out["value"] is True
    assert calls[0] == [
        "nix",
        "eval",
        '/etc/nixos#nixosConfigurations."zen".config.services.openssh.enable',
        "--json",
    ]


def test_eval_hm_candidate_fallback(monkeypatch):
    calls = []

    def fake_run(argv, cwd=None):
        calls.append(argv)
        if "rupan@zen" in argv[2]:
            return _result(
                False,
                stderr="error: flake does not provide attribute "
                "'homeConfigurations.\"rupan@zen\"'",
                command=argv,
            )
        return _result(True, stdout='"niri"\n', command=argv)

    monkeypatch.setattr(eval_mod.runner, "run", fake_run)
    monkeypatch.setattr(eval_mod, "attr_candidates", lambda t: ["rupan@zen", "rupan"])
    out = eval_config("wayland.windowManager", flake_uri="/x", mode="home-manager")
    assert out["status"] == "ok"
    assert out["value"] == "niri"
    assert len(calls) == 2


def test_eval_non_json_fallback(monkeypatch):
    def fake_run(argv, cwd=None):
        if "--json" in argv:
            return _result(
                False,
                stderr="error: cannot convert a function to JSON",
                command=argv,
            )
        return _result(True, stdout="<LAMBDA>", command=argv)

    monkeypatch.setattr(eval_mod.runner, "run", fake_run)
    out = eval_config("lib.mkIf", flake_uri="/x#h", mode="nixos")
    assert out["status"] == "ok"
    assert out["value"] == "<LAMBDA>"
    assert out["json_fallback"] is True


def test_eval_truncated_json_does_not_crash(monkeypatch):
    def fake_run(argv, cwd=None):
        # Simulate runner truncation producing invalid JSON on an ok result
        return _result(True, stdout='{"a": 1, "b": ... [truncated]', command=argv)

    monkeypatch.setattr(eval_mod.runner, "run", fake_run)
    out = eval_config("environment.systemPackages", flake_uri="/x#h", mode="nixos")
    assert out["status"] == "ok"
    assert out["value"] == '{"a": 1, "b": ... [truncated]'
    assert out["json_parse_failed"] is True


def test_eval_real_failure(monkeypatch):
    def fake_run(argv, cwd=None):
        return _result(False, stderr="error: attribute 'nope' missing", command=argv)

    monkeypatch.setattr(eval_mod.runner, "run", fake_run)
    out = eval_config("services.nope", flake_uri="/x#h", mode="nixos")
    assert out["status"] == "failed"
    assert out["first_error"] == "error: attribute 'nope' missing"


def test_eval_no_target(monkeypatch, tmp_path):
    from pathlib import Path

    from nix_agent import target as target_mod

    monkeypatch.delenv("NIX_AGENT_FLAKE", raising=False)
    monkeypatch.setattr(target_mod, "NIXOS_DEFAULT_DIR", tmp_path / "nope")
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "empty-home")
    out = eval_config("a.b", mode="nixos")
    assert out["status"] == "no_target"
    assert "flake_uri" in out["error"]


def test_eval_invalid_mode():
    out = eval_config("a.b", flake_uri="/x", mode="bogus")
    assert out["status"] == "no_target"


def test_guard_value_small_passthrough():
    value, truncated = eval_mod.guard_value({"a": 1})
    assert value == {"a": 1}
    assert truncated is False


def test_guard_value_large_dict_returns_attr_names():
    big = {f"key{i:03d}": "x" * 50 for i in range(100)}
    value, truncated = eval_mod.guard_value(big)
    assert truncated is True
    assert value["attr_names"] == sorted(big)
    assert value["truncated"] is True
    assert "hint" in value


def test_guard_value_large_list_summarized():
    big = ["/nix/store/" + "a" * 60 for _ in range(100)]
    value, truncated = eval_mod.guard_value(big)
    assert truncated is True
    assert value["length"] == 100
    assert value["truncated"] is True
    assert "hint" in value


def test_guard_value_large_string_head_truncated():
    big = "z" * 10_000
    value, truncated = eval_mod.guard_value(big)
    assert truncated is True
    assert isinstance(value, str)
    assert len(value) < 3_000
    assert value.endswith("... [nix-agent: truncated]")


def test_eval_large_value_guarded(monkeypatch):
    big = json.dumps({f"k{i:03d}": "x" * 50 for i in range(100)})

    def fake_run(argv, cwd=None):
        return _result(True, stdout=big, command=argv)

    monkeypatch.setattr(eval_mod.runner, "run", fake_run)
    out = eval_config("environment.etc", flake_uri="/x#h", mode="nixos")
    assert out["status"] == "ok"
    assert out["truncated"] is True
    assert out["value"]["attr_names"] == sorted(json.loads(big))
    assert out["output"] == ""


def test_eval_success_omits_raw_output(monkeypatch):
    def fake_run(argv, cwd=None):
        return _result(True, stdout="true\n", command=argv)

    monkeypatch.setattr(eval_mod.runner, "run", fake_run)
    out = eval_config("services.openssh.enable", flake_uri="/x#h")
    assert out["status"] == "ok"
    assert out["value"] is True
    assert out["output"] == ""


def test_eval_failure_keeps_output(monkeypatch):
    def fake_run(argv, cwd=None):
        return _result(False, stderr="error: attribute 'nope' missing", command=argv)

    monkeypatch.setattr(eval_mod.runner, "run", fake_run)
    out = eval_config("services.nope", flake_uri="/x#h")
    assert out["status"] == "failed"
    assert "error: attribute 'nope' missing" in out["output"]


def test_guard_value_at_cap_passthrough():
    big = "z" * (eval_mod.GUARD_CAP - 2)
    assert len(json.dumps(big)) == eval_mod.GUARD_CAP
    value, truncated = eval_mod.guard_value(big)
    assert value == big
    assert truncated is False


def test_guard_value_one_over_cap_truncated():
    big = "z" * (eval_mod.GUARD_CAP - 1)
    assert len(json.dumps(big)) == eval_mod.GUARD_CAP + 1
    value, truncated = eval_mod.guard_value(big)
    assert truncated is True
    assert value.endswith("... [nix-agent: truncated]")


def test_eval_batched_attrs(monkeypatch):
    def fake_run(argv, cwd=None):
        if "hostName" in argv[2]:
            return _result(True, stdout='"laptop"\n', command=argv)
        return _result(True, stdout="true\n", command=argv)

    monkeypatch.setattr(eval_mod.runner, "run", fake_run)
    out = eval_config(
        ["networking.hostName", "services.openssh.enable"],
        flake_uri="/x#h",
        mode="nixos",
    )
    assert out["status"] == "ok"
    assert out["results"] == [
        {"attr": "networking.hostName", "status": "ok", "value": "laptop"},
        {"attr": "services.openssh.enable", "status": "ok", "value": True},
    ]
    assert "value" not in out


def test_eval_batched_partial_failure(monkeypatch):
    def fake_run(argv, cwd=None):
        if "nope" in argv[2]:
            return _result(
                False, stderr="error: attribute 'nope' missing", command=argv
            )
        return _result(True, stdout="true\n", command=argv)

    monkeypatch.setattr(eval_mod.runner, "run", fake_run)
    out = eval_config(["services.nope", "services.openssh.enable"], flake_uri="/x#h")
    assert out["status"] == "ok"
    assert out["results"][0]["attr"] == "services.nope"
    assert out["results"][0]["status"] == "failed"
    assert "first_error" in out["results"][0]
    assert out["results"][1] == {
        "attr": "services.openssh.enable",
        "status": "ok",
        "value": True,
    }


def test_eval_batched_empty_list():
    out = eval_config([], flake_uri="/x#h")
    assert out["status"] == "invalid_attr"
