import json

from nix_agent.runner import RunResult
from nix_agent.tools import inspect_flake as inspect_mod


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
