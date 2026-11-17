from pathlib import Path

from nix_agent.runner import RunResult
from nix_agent.target import resolve_target
from nix_agent.tools import build as build_mod
from nix_agent.tools.build import build_closure, diff

FIXTURES = Path(__file__).parent / "fixtures"


def build(flake_uri, mode="nixos"):
    return build_closure(resolve_target(flake_uri, mode))


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


def test_build_closure_dry_run_flag(monkeypatch):
    from nix_agent.target import Target
    from nix_agent.tools.build import build_closure

    calls = []

    def fake_run(argv, cwd=None):
        calls.append(argv)
        return _result(True, command=argv)

    monkeypatch.setattr(build_mod.runner, "run", fake_run)
    out = build_closure(Target(flake_dir="/x", attr="h", mode="nixos"), dry_run=True)
    assert "--dry-run" in calls[0]
    assert "--print-out-paths" not in calls[0]
    assert "store_path" not in out


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
    assert "output" not in out
    assert calls[-1] == [
        "/bin/nvd",
        "diff",
        "/run/current-system",
        "/nix/store/new-system",
    ]


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


def test_build_store_path_is_last_stdout_line(monkeypatch):
    def fake_run(argv, cwd=None):
        return _result(True, stdout="warning: blah\n/nix/store/abc\n", command=argv)

    monkeypatch.setattr(build_mod.runner, "run", fake_run)
    out = build(flake_uri="/x#h", mode="nixos")
    assert out["store_path"] == "/nix/store/abc"


def test_build_ok_but_empty_stdout_is_failed(monkeypatch):
    def fake_run(argv, cwd=None):
        return _result(True, stdout="", command=argv)

    monkeypatch.setattr(build_mod.runner, "run", fake_run)
    out = build(flake_uri="/x#h", mode="nixos")
    assert out["status"] == "failed"


def test_build_hm_candidate_retry(monkeypatch):
    calls = []

    def fake_run(argv, cwd=None):
        calls.append(argv)
        if "rupan@zen" in argv[-1]:
            return _result(
                False,
                stderr="error: flake does not provide attribute "
                "'homeConfigurations.\"rupan@zen\"'",
                command=argv,
            )
        return _result(True, stdout="/nix/store/hm\n", command=argv)

    monkeypatch.setattr(build_mod.runner, "run", fake_run)
    monkeypatch.setattr(build_mod, "attr_candidates", lambda t: ["rupan@zen", "rupan"])
    out = build(flake_uri="/x", mode="home-manager")
    assert out["status"] == "ok"
    assert len(calls) == 2


NVD_FIXTURE = """\
Version changes:
[U.]  #1  firefox  128.0 -> 129.0
"""


def test_diff_attaches_packages(monkeypatch):
    def fake_run(argv, cwd=None):
        if argv[0] == "/bin/nvd":
            return RunResult(ok=True, command=argv, stdout=NVD_FIXTURE, stderr="")
        return RunResult(
            ok=True, command=argv, stdout="/nix/store/new-toplevel\n", stderr=""
        )

    monkeypatch.setattr(build_mod.runner, "run", fake_run)
    monkeypatch.setattr(build_mod.runner, "resolve_binary", lambda n: f"/bin/{n}")
    monkeypatch.setattr(
        build_mod, "_current_closure", lambda mode: "/run/current-system"
    )
    out = diff(flake_uri="/x#h")
    assert out["status"] == "ok"
    assert out["packages"]["changed"] == [
        {"name": "firefox", "old": "128.0", "new": "129.0"}
    ]


def test_diff_degrades_without_packages(monkeypatch):
    def fake_run(argv, cwd=None):
        if argv[0] == "/bin/nvd":
            return RunResult(ok=True, command=argv, stdout="garbled output", stderr="")
        return RunResult(
            ok=True, command=argv, stdout="/nix/store/new-toplevel\n", stderr=""
        )

    monkeypatch.setattr(build_mod.runner, "run", fake_run)
    monkeypatch.setattr(build_mod.runner, "resolve_binary", lambda n: f"/bin/{n}")
    monkeypatch.setattr(
        build_mod, "_current_closure", lambda mode: "/run/current-system"
    )
    out = diff(flake_uri="/x#h")
    assert out["status"] == "ok"
    assert "packages" not in out
    assert out["diff"] == "garbled output"
    assert "output" not in out


def test_diff_empty_diff_closures_is_empty_packages(monkeypatch):
    def fake_run(argv, cwd=None):
        if argv[:3] == ["nix", "store", "diff-closures"]:
            return RunResult(ok=True, command=argv, stdout="", stderr="")
        return RunResult(
            ok=True, command=argv, stdout="/nix/store/new-toplevel\n", stderr=""
        )

    monkeypatch.setattr(build_mod.runner, "run", fake_run)
    monkeypatch.setattr(build_mod.runner, "resolve_binary", lambda n: None)
    monkeypatch.setattr(
        build_mod, "_current_closure", lambda mode: "/run/current-system"
    )
    out = diff(flake_uri="/x#h")
    assert out["status"] == "ok"
    assert out["packages"] == {"added": [], "removed": [], "changed": []}


def test_build_failure_attaches_failed_derivation(monkeypatch):
    from nix_agent.runner import RunResult
    from nix_agent.tools import build as build_mod

    def fake_run(argv, cwd=None):
        if argv[:2] == ["nix", "log"]:
            return RunResult(
                ok=True, command=argv, stdout="builder said no\n", stderr=""
            )
        return RunResult(
            ok=False,
            command=argv,
            stdout="",
            stderr="error: builder for '/nix/store/abc-x.drv' failed with exit code 1",
        )

    monkeypatch.setattr(build_mod.runner, "run", fake_run)
    out = build(flake_uri="/x#h")
    assert out["status"] == "failed"
    assert out["failed_derivation"]["drv"] == "/nix/store/abc-x.drv"
    assert out["failed_derivation"]["log_tail"] == "builder said no\n"


def test_diff_tool_failure_keeps_store_path(monkeypatch):
    def fake_run(argv, cwd=None):
        if argv[0] == "/bin/nvd":
            return RunResult(ok=False, command=argv, stdout="", stderr="nvd exploded")
        return RunResult(
            ok=True, command=argv, stdout="/nix/store/new-toplevel\n", stderr=""
        )

    monkeypatch.setattr(build_mod.runner, "run", fake_run)
    monkeypatch.setattr(build_mod.runner, "resolve_binary", lambda n: f"/bin/{n}")
    monkeypatch.setattr(
        build_mod, "_current_closure", lambda mode: "/run/current-system"
    )
    out = diff(flake_uri="/x#h")
    assert out["status"] == "failed"
    assert out["store_path"] == "/nix/store/new-toplevel"
    assert "packages" not in out


def test_build_unique_host_fallback(monkeypatch):
    calls = []

    def fake_run(argv, cwd=None):
        calls.append(argv)
        if "flake" in argv and "show" in argv:
            return _result(
                True,
                stdout='{"nixosConfigurations": {"laptop": {}}}',
                command=argv,
            )
        if 'nixosConfigurations."zen"' in argv[-1]:
            return _result(
                False,
                stderr="error: flake does not provide attribute "
                "'nixosConfigurations.\"zen\"'",
                command=argv,
            )
        return _result(True, stdout="/nix/store/sys\n", command=argv)

    monkeypatch.setattr(build_mod.runner, "run", fake_run)
    monkeypatch.setattr(build_mod, "attr_candidates", lambda t: ["zen"])
    out = build(flake_uri="/x", mode="nixos")
    assert out["status"] == "ok"
    assert out["store_path"] == "/nix/store/sys"
    assert any('nixosConfigurations."laptop"' in argv[-1] for argv in calls)


def test_diff_keeps_nvd_closure_size(monkeypatch):
    nvd_output = (FIXTURES / "nvd-diff.txt").read_text()

    def fake_run(argv, cwd=None):
        if argv[0] == "/bin/nvd":
            return RunResult(ok=True, command=argv, stdout=nvd_output, stderr="")
        return RunResult(
            ok=True, command=argv, stdout="/nix/store/new-toplevel\n", stderr=""
        )

    monkeypatch.setattr(build_mod.runner, "run", fake_run)
    monkeypatch.setattr(build_mod.runner, "resolve_binary", lambda n: f"/bin/{n}")
    monkeypatch.setattr(
        build_mod, "_current_closure", lambda mode: "/run/current-system"
    )
    out = diff(flake_uri="/x#h")
    assert out["closure_size"].startswith("4348 -> 4606")
    assert out["returned_bytes"] < len(nvd_output)


def test_diff_reuses_store_path_without_rebuilding(monkeypatch, tmp_path):
    built_dir = tmp_path / "new-system"
    built_dir.mkdir()
    cur_dir = tmp_path / "cur-system"
    cur_dir.mkdir()
    calls = []

    def fake_run(argv, cwd=None):
        calls.append(argv)
        return RunResult(ok=True, command=argv, stdout=NVD_FIXTURE, stderr="")

    monkeypatch.setattr(build_mod.runner, "run", fake_run)
    monkeypatch.setattr(build_mod.runner, "resolve_binary", lambda n: f"/bin/{n}")
    monkeypatch.setattr(
        build_mod, "_current_closure", lambda mode: str(cur_dir.resolve())
    )
    out = diff(store_path=str(built_dir))
    assert out["status"] == "ok"
    assert out["store_path"] == str(built_dir.resolve())
    assert calls == [["/bin/nvd", "diff", str(cur_dir.resolve()), str(built_dir.resolve())]]


def test_diff_against_explicit_baseline_closure(monkeypatch, tmp_path):
    built_dir = tmp_path / "remote-new"
    built_dir.mkdir()
    base_dir = tmp_path / "remote-old"
    base_dir.mkdir()
    calls = []

    def fake_run(argv, cwd=None):
        calls.append(argv)
        return RunResult(ok=True, command=argv, stdout=NVD_FIXTURE, stderr="")

    monkeypatch.setattr(build_mod.runner, "run", fake_run)
    monkeypatch.setattr(build_mod.runner, "resolve_binary", lambda n: f"/bin/{n}")
    out = diff(
        flake_uri="/homelab#homelab-04",
        store_path=str(built_dir),
        against=str(base_dir),
    )
    assert out["status"] == "ok"
    assert out["resolved_target"] == "/homelab#homelab-04"
    assert out["current_closure"] == str(base_dir.resolve())
    assert out["store_path"] == str(built_dir.resolve())
    assert calls == [["/bin/nvd", "diff", str(base_dir.resolve()), str(built_dir.resolve())]]


def test_diff_missing_store_path_or_against_fails_cleanly(monkeypatch, tmp_path):
    built_dir = tmp_path / "ok-store"
    built_dir.mkdir()
    calls = []
    monkeypatch.setattr(build_mod.runner, "run", lambda argv, cwd=None: calls.append(argv))

    bad_store = diff(store_path=str(tmp_path / "missing"))
    assert bad_store["status"] == "failed"
    assert "store_path" in bad_store["error"]

    bad_against = diff(store_path=str(built_dir), against=str(tmp_path / "missing-base"))
    assert bad_against["status"] == "failed"
    assert "baseline" in bad_against["error"]
    assert calls == []


def test_diff_accounts_for_suppressed_build_raw_bytes(monkeypatch):
    def fake_build_closure(target, dry_run=False):
        return {
            "status": "ok",
            "resolved_target": "/x#h",
            "command": ["nix", "build"],
            "output": "tail",
            "store_path": "/nix/store/new-toplevel",
            "raw_bytes": 50_000,
        }

    monkeypatch.setattr(build_mod, "build_closure", fake_build_closure)
    monkeypatch.setattr(
        build_mod.runner,
        "run",
        lambda argv, cwd=None: RunResult(
            ok=True, command=argv, stdout=NVD_FIXTURE, stderr="", raw_bytes=500
        ),
    )
    monkeypatch.setattr(build_mod.runner, "resolve_binary", lambda n: f"/bin/{n}")
    monkeypatch.setattr(
        build_mod, "_current_closure", lambda mode: "/run/current-system"
    )
    out = diff(flake_uri="/x#h")
    assert out["status"] == "ok"
    assert out["raw_bytes"] == 50_500
    assert out["raw_bytes"] > out["returned_bytes"]
