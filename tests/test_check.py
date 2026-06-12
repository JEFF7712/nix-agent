import json

from nix_agent.runner import RunResult
from nix_agent.tools import check as check_mod
from nix_agent.tools.check import _parse_deadnix, _parse_statix, check

# Real statix emits a single JSON object (not an array) with exit code 1
# when findings exist. Verified against statix 0.6.x via nix shell.
STATIX_FIXTURE = json.dumps(
    {
        "file": "/etc/nixos/configuration.nix",
        "report": [
            {
                "note": "Useless if-then-else",
                "code": 1,
                "severity": "Warn",
                "diagnostics": [
                    {
                        "at": {
                            "from": {"line": 4, "column": 9},
                            "to": {"line": 4, "column": 40},
                        },
                        "message": "This if-then-else is useless",
                        "suggestion": None,
                    }
                ],
            }
        ],
    }
)

# deadnix emits a single JSON object on one line; exit code 0 even with findings.
DEADNIX_FIXTURE = (
    '{"file": "/etc/nixos/configuration.nix", "results": '
    '[{"column": 5, "endColumn": 6, "line": 1, "message": '
    '"Unused let binding: x"}]}'
)


def _result(ok, stdout="", stderr="", command=("x",)):
    return RunResult(ok=ok, command=list(command), stdout=stdout, stderr=stderr)


def test_parse_statix():
    findings = _parse_statix(STATIX_FIXTURE)
    assert findings == [
        {
            "tool": "statix",
            "file": "/etc/nixos/configuration.nix",
            "line": 4,
            "column": 9,
            "severity": "Warn",
            "message": "This if-then-else is useless",
        }
    ]


def test_parse_statix_empty_and_garbage():
    assert _parse_statix("") == []
    garbage = _parse_statix("not json at all")
    assert len(garbage) == 1
    assert garbage[0]["tool"] == "statix"
    assert "not json" in garbage[0]["message"]


def test_parse_deadnix():
    findings = _parse_deadnix(DEADNIX_FIXTURE)
    assert findings == [
        {
            "tool": "deadnix",
            "file": "/etc/nixos/configuration.nix",
            "line": 1,
            "column": 5,
            "severity": "warning",
            "message": "Unused let binding: x",
        }
    ]


def test_parse_deadnix_empty():
    assert _parse_deadnix("") == []


def test_check_invalid_level():
    out = check("vibes", flake_uri="/x")
    assert out["status"] == "invalid_level"
    assert "lint" in out["error"]


def test_check_lint_combines_tools(monkeypatch):
    def fake_run(argv, cwd=None):
        if argv[0].endswith("statix"):
            return _result(False, stdout=STATIX_FIXTURE, command=argv)
        return _result(False, stdout=DEADNIX_FIXTURE, command=argv)

    monkeypatch.setattr(check_mod.runner, "run", fake_run)
    monkeypatch.setattr(check_mod.runner, "resolve_binary", lambda n: f"/bin/{n}")
    out = check("lint", flake_uri="/etc/nixos#zen")
    assert out["status"] == "ok"
    assert len(out["findings"]) == 2
    tools = {f["tool"] for f in out["findings"]}
    assert tools == {"statix", "deadnix"}


def test_check_lint_missing_binaries(monkeypatch):
    monkeypatch.setattr(check_mod.runner, "resolve_binary", lambda n: None)
    out = check("lint", flake_uri="/x")
    assert out["status"] == "tool_missing"
    assert set(out["missing"]) == {"statix", "deadnix"}


def test_check_flake(monkeypatch):
    calls = []

    def fake_run(argv, cwd=None):
        calls.append(argv)
        return _result(True, command=argv)

    monkeypatch.setattr(check_mod.runner, "run", fake_run)
    out = check("flake", flake_uri="/etc/nixos#zen")
    assert out["status"] == "ok"
    assert calls[0] == ["nix", "flake", "check", "/etc/nixos"]


def test_check_dry_build_delegates_to_build_closure(monkeypatch):
    seen = {}

    def fake_build_closure(target, dry_run=False):
        seen["dry_run"] = dry_run
        return {"status": "ok", "resolved_target": "x", "command": [], "output": ""}

    monkeypatch.setattr(check_mod, "build_closure", fake_build_closure)
    out = check("dry-build", flake_uri="/x#h")
    assert out["status"] == "ok"
    assert seen["dry_run"] is True


def test_check_dry_activate_nixos(monkeypatch):
    calls = []

    def fake_run(argv, cwd=None):
        calls.append(argv)
        return _result(True, command=argv)

    monkeypatch.setattr(check_mod.runner, "run", fake_run)
    monkeypatch.setattr(
        check_mod.runner, "resolve_binary", lambda n: f"/bin/{n}"
    )
    out = check("dry-activate", flake_uri="/etc/nixos#zen")
    assert out["status"] == "ok"
    assert calls[0] == [
        "sudo", "/bin/nixos-rebuild", "dry-activate", "--flake", "/etc/nixos#zen",
    ]


def test_check_dry_activate_hm_not_applicable():
    out = check("dry-activate", flake_uri="/x", mode="home-manager")
    assert out["status"] == "not_applicable"
    assert "dry-build" in out["hint"]
