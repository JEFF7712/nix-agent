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
    monkeypatch.setattr(
        eval_mod, "attr_candidates", lambda t: ["rupan@zen", "rupan"]
    )
    out = eval_config(
        "wayland.windowManager", flake_uri="/x", mode="home-manager"
    )
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


def test_eval_real_failure(monkeypatch):
    def fake_run(argv, cwd=None):
        return _result(
            False, stderr="error: attribute 'nope' missing", command=argv
        )

    monkeypatch.setattr(eval_mod.runner, "run", fake_run)
    out = eval_config("services.nope", flake_uri="/x#h", mode="nixos")
    assert out["status"] == "failed"
    assert out["first_error"] == "error: attribute 'nope' missing"


def test_eval_no_target(monkeypatch, tmp_path):
    from nix_agent import target as target_mod

    monkeypatch.setattr(target_mod, "NIXOS_DEFAULT_DIR", tmp_path / "nope")
    out = eval_config("a.b", mode="nixos")
    assert out["status"] == "no_target"
    assert "flake_uri" in out["error"]


def test_eval_invalid_mode():
    out = eval_config("a.b", flake_uri="/x", mode="bogus")
    assert out["status"] == "no_target"
