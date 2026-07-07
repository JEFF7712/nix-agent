import json

from nix_agent.runner import RunResult
from nix_agent.tools import inspect_flake as inspect_mod
from nix_agent.tools.inspect_flake import inspect_flake


def _result(ok, stdout="", stderr="", command=("nix",)):
    return RunResult(ok=ok, command=list(command), stdout=stdout, stderr=stderr)


SHOW_JSON = json.dumps(
    {
        "checks": {},
        "formatter": {"x86_64-linux": {"name": "treefmt", "type": "derivation"}},
        "nixosConfigurations": {"laptop": {}, "iso": {}},
    }
)

SHOW_JSON_STANDALONE_HM = json.dumps(
    {
        "homeConfigurations": {"rupan@zen": {}, "rupan": {}},
        "packages": {},
    }
)


def test_parse_flake_show_hosts_and_formatter():
    facts = inspect_mod.parse_flake_show(json.loads(SHOW_JSON))
    assert facts["hosts"] == ["iso", "laptop"]
    assert facts["home_configurations"] == []
    assert facts["formatter"] == "treefmt"


def test_parse_flake_show_standalone_hm():
    facts = inspect_mod.parse_flake_show(json.loads(SHOW_JSON_STANDALONE_HM))
    assert facts["hosts"] == []
    assert facts["home_configurations"] == ["rupan", "rupan@zen"]
    assert facts["formatter"] == "none"


def test_parse_flake_show_nixfmt_name():
    facts = inspect_mod.parse_flake_show(
        {"formatter": {"x86_64-linux": {"name": "nixfmt-rfc-style"}}}
    )
    assert facts["formatter"] == "nixfmt"


def test_parse_flake_show_unknown_formatter_name_passes_through():
    facts = inspect_mod.parse_flake_show(
        {"formatter": {"x86_64-linux": {"name": "alejandra"}}}
    )
    assert facts["formatter"] == "alejandra"


def test_hm_integration_classification():
    assert inspect_mod.classify_hm(True, []) == "integrated"
    assert inspect_mod.classify_hm(True, ["rupan"]) == "standalone"
    assert inspect_mod.classify_hm(False, ["rupan"]) == "standalone"
    assert inspect_mod.classify_hm(False, []) == "none"


def test_scan_repo_files(tmp_path):
    (tmp_path / "flake.nix").write_text('{ inputs.import-tree.url = "x"; }')
    (tmp_path / "flake.lock").write_text(
        json.dumps({"nodes": {"home-manager": {}, "root": {}}})
    )
    (tmp_path / "modules" / "nixos").mkdir(parents=True)
    (tmp_path / "modules" / "nixos" / "a.nix").write_text("{}")
    (tmp_path / "justfile").write_text("default:\n")
    (tmp_path / ".github" / "workflows").mkdir(parents=True)
    (tmp_path / ".github" / "workflows" / "ci.yml").write_text("on: push\n")

    facts = inspect_mod.scan_repo(str(tmp_path))
    assert facts["hm_in_lock"] is True
    assert facts["auto_import"] == "import-tree"
    assert facts["module_dirs"] == ["modules/nixos"]
    assert facts["has_justfile"] is True
    assert facts["has_ci"] is True
    assert facts["mcp_json"] == "absent"


def test_scan_repo_bare(tmp_path):
    (tmp_path / "flake.nix").write_text("{ outputs = _: {}; }")
    facts = inspect_mod.scan_repo(str(tmp_path))
    assert facts["hm_in_lock"] is False
    assert facts["auto_import"] == "none"
    assert facts["module_dirs"] == []
    assert facts["has_justfile"] is False
    assert facts["has_ci"] is False
    assert facts["mcp_json"] == "absent"


def test_scan_repo_unreadable_flake(tmp_path):
    facts = inspect_mod.scan_repo(str(tmp_path))
    assert facts["auto_import"] == "unknown"


def test_scan_repo_lock_not_an_object(tmp_path):
    (tmp_path / "flake.nix").write_text("{ }")
    (tmp_path / "flake.lock").write_text("[1, 2, 3]")
    facts = inspect_mod.scan_repo(str(tmp_path))
    assert facts["hm_in_lock"] is False


def test_inspect_flake_integrated_hm(monkeypatch, tmp_path):
    (tmp_path / "flake.nix").write_text('{ inputs.import-tree.url = "x"; }')
    (tmp_path / "flake.lock").write_text(json.dumps({"nodes": {"home-manager": {}}}))

    def fake_run(argv, cwd=None):
        assert argv == ["nix", "flake", "show", str(tmp_path), "--json"]
        return _result(True, stdout=SHOW_JSON, command=argv)

    monkeypatch.setattr(inspect_mod.runner, "run", fake_run)
    monkeypatch.setattr(inspect_mod.runner, "resolve_binary", lambda n: f"/bin/{n}")
    out = inspect_flake(flake_uri=str(tmp_path))
    assert out["status"] == "ok"
    assert out["flake_dir"] == str(tmp_path)
    assert out["hosts"] == ["iso", "laptop"]
    assert out["home_configurations"] == []
    assert out["hm_integration"] == "integrated"
    assert out["formatter"] == "treefmt"
    assert out["auto_import"] == "import-tree"
    assert out["lint_tools"] == ["deadnix", "statix"]
    assert out["mcp_json"] == "absent"


def test_inspect_flake_show_failure_degrades(monkeypatch, tmp_path):
    (tmp_path / "flake.nix").write_text("{ }")

    def fake_run(argv, cwd=None):
        return _result(False, stderr="error: cannot evaluate", command=argv)

    monkeypatch.setattr(inspect_mod.runner, "run", fake_run)
    monkeypatch.setattr(inspect_mod.runner, "resolve_binary", lambda n: None)
    out = inspect_flake(flake_uri=str(tmp_path))
    assert out["status"] == "ok"
    assert out["hosts"] is None
    assert out["home_configurations"] is None
    assert out["hm_integration"] == "unknown"
    assert out["formatter"] == "unknown"
    assert "flake show failed" in out["note"]
    assert out["first_error"] == "error: cannot evaluate"
    assert out["lint_tools"] == []


def test_inspect_flake_strips_attr_from_uri(monkeypatch, tmp_path):
    (tmp_path / "flake.nix").write_text("{ }")
    calls = []

    def fake_run(argv, cwd=None):
        calls.append(argv)
        return _result(True, stdout=SHOW_JSON, command=argv)

    monkeypatch.setattr(inspect_mod.runner, "run", fake_run)
    monkeypatch.setattr(inspect_mod.runner, "resolve_binary", lambda n: f"/bin/{n}")
    out = inspect_flake(flake_uri=f"{tmp_path}#laptop")
    assert out["status"] == "ok"
    assert calls[0][3] == str(tmp_path)


def test_inspect_flake_no_target(monkeypatch, tmp_path):
    from pathlib import Path

    from nix_agent import target as target_mod

    monkeypatch.delenv("NIX_AGENT_FLAKE", raising=False)
    monkeypatch.delenv("NIX_AGENT_HM_FLAKE", raising=False)
    monkeypatch.setattr(target_mod, "NIXOS_DEFAULT_DIR", tmp_path / "nope")
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "empty-home")
    out = inspect_flake()
    assert out["status"] == "no_target"


def test_inspect_flake_no_target_reports_both_modes(monkeypatch, tmp_path):
    from pathlib import Path

    from nix_agent import target as target_mod

    monkeypatch.delenv("NIX_AGENT_FLAKE", raising=False)
    monkeypatch.delenv("NIX_AGENT_HM_FLAKE", raising=False)
    monkeypatch.setattr(target_mod, "NIXOS_DEFAULT_DIR", tmp_path / "nope")
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "empty-home")
    out = inspect_flake()
    assert out["status"] == "no_target"
    assert "NIX_AGENT_FLAKE" in out["error"]
    assert "NIX_AGENT_HM_FLAKE" in out["error"]


def test_inspect_flake_show_non_dict_json(monkeypatch, tmp_path):
    (tmp_path / "flake.nix").write_text("{ }")

    def fake_run(argv, cwd=None):
        return _result(True, stdout="[]", command=argv)

    monkeypatch.setattr(inspect_mod.runner, "run", fake_run)
    monkeypatch.setattr(inspect_mod.runner, "resolve_binary", lambda n: None)
    out = inspect_flake(flake_uri=str(tmp_path))
    assert out["status"] == "ok"
    assert out["hosts"] is None
    assert out["note"] == "flake show output was not valid JSON"


def test_scan_repo_nested_host_dirs(tmp_path):
    (tmp_path / "flake.nix").write_text("{ }")
    (tmp_path / "hosts" / "laptop").mkdir(parents=True)
    (tmp_path / "hosts" / "laptop" / "default.nix").write_text("{}")
    facts = inspect_mod.scan_repo(str(tmp_path))
    assert facts["module_dirs"] == ["hosts"]


def test_scan_repo_parent_dir_not_duplicated(tmp_path):
    (tmp_path / "flake.nix").write_text("{ }")
    (tmp_path / "modules" / "nixos").mkdir(parents=True)
    (tmp_path / "modules" / "nixos" / "a.nix").write_text("{}")
    facts = inspect_mod.scan_repo(str(tmp_path))
    assert facts["module_dirs"] == ["modules/nixos"]


def test_inspect_flake_envelope_accounted(monkeypatch, tmp_path):
    (tmp_path / "flake.nix").write_text("{ }")

    def fake_run(argv, cwd=None):
        return _result(True, stdout=SHOW_JSON, command=argv)

    monkeypatch.setattr(inspect_mod.runner, "run", fake_run)
    monkeypatch.setattr(inspect_mod.runner, "resolve_binary", lambda n: None)
    out = inspect_flake(flake_uri=str(tmp_path))
    assert out["raw_bytes"] == len(SHOW_JSON)
    assert out["returned_bytes"] > 0
