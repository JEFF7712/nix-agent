from nix_agent.runner import RunResult
from nix_agent.tools import build as build_mod
from nix_agent.tools.build import build, diff


def _result(ok, stdout="", stderr="", command=("nix",)):
    return RunResult(ok=ok, command=list(command), stdout=stdout, stderr=stderr)


def test_build_nixos_ok(monkeypatch):
    calls = []

    def fake_run(argv, cwd=None):
        calls.append(argv)
        return _result(True, stdout="/nix/store/abc-nixos-system\n", command=argv)

    monkeypatch.setattr(build_mod.runner, "run", fake_run)
    out = build(flake_uri="/etc/nixos#zen", mode="nixos")
    assert out["status"] == "ok"
    assert out["store_path"] == "/nix/store/abc-nixos-system"
    assert calls[0] == [
        "nix",
        "build",
        "--no-link",
        "--print-out-paths",
        '/etc/nixos#nixosConfigurations."zen".config.system.build.toplevel',
    ]


def test_build_hm_uses_activation_package(monkeypatch):
    calls = []

    def fake_run(argv, cwd=None):
        calls.append(argv)
        return _result(True, stdout="/nix/store/abc-hm\n", command=argv)

    monkeypatch.setattr(build_mod.runner, "run", fake_run)
    out = build(flake_uri="/x#rupan", mode="home-manager")
    assert out["status"] == "ok"
    assert ".activationPackage" in calls[0][-1]


def test_build_failure(monkeypatch):
    def fake_run(argv, cwd=None):
        return _result(False, stderr="error: syntax error", command=argv)

    monkeypatch.setattr(build_mod.runner, "run", fake_run)
    out = build(flake_uri="/x#h", mode="nixos")
    assert out["status"] == "failed"
    assert out["first_error"] == "error: syntax error"


def test_build_dry_run_flag(monkeypatch):
    calls = []

    def fake_run(argv, cwd=None):
        calls.append(argv)
        return _result(True, command=argv)

    monkeypatch.setattr(build_mod.runner, "run", fake_run)
    build(flake_uri="/x#h", mode="nixos", dry_run=True)
    assert "--dry-run" in calls[0]
    assert "--print-out-paths" not in calls[0]


def test_diff_runs_nvd(monkeypatch):
    calls = []

    def fake_run(argv, cwd=None):
        calls.append(argv)
        if argv[0] == "nix":
            return _result(True, stdout="/nix/store/new-system\n", command=argv)
        return _result(True, stdout="[U.]  firefox: 130 -> 131", command=argv)

    monkeypatch.setattr(build_mod.runner, "run", fake_run)
    monkeypatch.setattr(build_mod.runner, "resolve_binary", lambda n: f"/bin/{n}")
    monkeypatch.setattr(
        build_mod, "_current_closure", lambda mode: "/run/current-system"
    )
    out = diff(flake_uri="/etc/nixos#zen", mode="nixos")
    assert out["status"] == "ok"
    assert "firefox" in out["diff"]
    assert calls[-1] == ["/bin/nvd", "diff", "/run/current-system", "/nix/store/new-system"]


def test_diff_falls_back_to_diff_closures(monkeypatch):
    calls = []

    def fake_run(argv, cwd=None):
        calls.append(argv)
        if argv[0] == "nix" and argv[1] == "build":
            return _result(True, stdout="/nix/store/new\n", command=argv)
        return _result(True, stdout="diff output", command=argv)

    monkeypatch.setattr(build_mod.runner, "run", fake_run)
    monkeypatch.setattr(build_mod.runner, "resolve_binary", lambda n: None)
    monkeypatch.setattr(build_mod, "_current_closure", lambda mode: "/cur")
    out = diff(flake_uri="/x#h", mode="nixos")
    assert out["status"] == "ok"
    assert calls[-1] == ["nix", "store", "diff-closures", "/cur", "/nix/store/new"]


def test_diff_build_failure_propagates(monkeypatch):
    def fake_run(argv, cwd=None):
        return _result(False, stderr="error: bad", command=argv)

    monkeypatch.setattr(build_mod.runner, "run", fake_run)
    out = diff(flake_uri="/x#h", mode="nixos")
    assert out["status"] == "failed"


def test_diff_no_current_closure(monkeypatch):
    def fake_run(argv, cwd=None):
        return _result(True, stdout="/nix/store/new\n", command=argv)

    monkeypatch.setattr(build_mod.runner, "run", fake_run)
    monkeypatch.setattr(build_mod, "_current_closure", lambda mode: None)
    out = diff(flake_uri="/x#h", mode="home-manager")
    assert out["status"] == "failed"
    assert "current" in out["error"]
