import json
from pathlib import Path

from nix_agent import runner
from nix_agent.target import Target
from nix_agent.tools import build as build_mod
from nix_agent.tools.build import build
from nix_agent.tools.check import check
from nix_agent.tools.eval import eval_config
from nix_agent.tools.switch import generations


SNAPSHOT = Path("tests/snapshots/tool_envelopes.json")


def _schema(value):
    if isinstance(value, dict):
        return {key: _schema(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        return [_schema(value[0])] if value else []
    if value is None:
        return "null"
    return type(value).__name__


def test_public_tool_envelope_schemas_match_snapshot(monkeypatch):
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

    examples = {
        "build_ok": build(flake_uri="/x#h"),
        "check_invalid_level": check("bogus", flake_uri="/x#h"),
        "eval_invalid_attr": eval_config([], flake_uri="/x#h"),
        "generations_invalid_action": generations(action="bogus"),
        "locate_not_an_option": {
            "status": "not_an_option",
            "resolved_target": '/x#nixosConfigurations."h".options.networking',
            "attr": "networking",
            "hint": "plain config value",
        },
    }

    actual = {name: _schema(value) for name, value in examples.items()}
    expected = json.loads(SNAPSHOT.read_text())
    assert actual == expected
