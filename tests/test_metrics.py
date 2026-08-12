import json
from pathlib import Path

import pytest

from nix_agent import metrics
from nix_agent.server import instrument


def test_enabled_defaults_off(monkeypatch):
    monkeypatch.delenv(metrics.ENABLED_ENV, raising=False)
    assert metrics.enabled() is False


@pytest.mark.parametrize("value", ["1", "true", "YES", "on"])
def test_enabled_truthy(monkeypatch, value):
    monkeypatch.setenv(metrics.ENABLED_ENV, value)
    assert metrics.enabled() is True


@pytest.mark.parametrize("value", ["0", "false", "OFF", "no", "", "maybe"])
def test_enabled_falsey(monkeypatch, value):
    monkeypatch.setenv(metrics.ENABLED_ENV, value)
    assert metrics.enabled() is False


def test_log_path_respects_xdg_and_override(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.delenv(metrics.PATH_ENV, raising=False)
    assert metrics.log_path() == tmp_path / "state" / "nix-agent" / "usage.jsonl"

    override = tmp_path / "custom.jsonl"
    monkeypatch.setenv(metrics.PATH_ENV, str(override))
    assert metrics.log_path() == override


def test_record_appends_jsonl(monkeypatch, tmp_path):
    path = tmp_path / "usage.jsonl"
    monkeypatch.setenv(metrics.PATH_ENV, str(path))
    monkeypatch.setenv(metrics.ENABLED_ENV, "1")

    metrics.record_call(
        tool="diff",
        duration_ms=12.34,
        response={
            "status": "ok",
            "resolved_target": "/home/rupan/nixos#laptop",
            "raw_bytes": 1000,
            "returned_bytes": 400,
        },
        kwargs={"mode": "nixos", "flake_uri": "/home/rupan/nixos"},
    )

    events = metrics.load_events(path)
    assert len(events) == 1
    event = events[0]
    assert event["tool"] == "diff"
    assert event["status"] == "ok"
    assert event["duration_ms"] == 12.3
    assert event["bytes_saved"] == 600
    assert event["mode"] == "nixos"
    assert event["flake_uri"] == "/home/rupan/nixos"
    assert "ts" in event


def test_record_disabled_is_noop(monkeypatch, tmp_path):
    path = tmp_path / "usage.jsonl"
    monkeypatch.setenv(metrics.PATH_ENV, str(path))
    monkeypatch.delenv(metrics.ENABLED_ENV, raising=False)
    metrics.record_call(tool="build", duration_ms=1.0, response={"status": "ok"})
    assert not path.exists()


def test_record_swallows_oserror(monkeypatch, tmp_path):
    blocked = tmp_path / "blocked"
    blocked.write_text("not a dir")
    monkeypatch.setenv(metrics.PATH_ENV, str(blocked / "usage.jsonl"))
    monkeypatch.setenv(metrics.ENABLED_ENV, "1")
    metrics.record({"tool": "check", "duration_ms": 1})  # must not raise


def test_summarize_and_format(tmp_path):
    path = tmp_path / "usage.jsonl"
    path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "tool": "eval_config",
                        "status": "ok",
                        "duration_ms": 10,
                        "raw_bytes": 100,
                        "returned_bytes": 40,
                        "bytes_saved": 60,
                    }
                ),
                json.dumps(
                    {
                        "tool": "eval_config",
                        "status": "failed",
                        "duration_ms": 20,
                        "raw_bytes": 50,
                        "returned_bytes": 50,
                        "bytes_saved": 0,
                    }
                ),
                json.dumps(
                    {"tool": "switch", "error": "RuntimeError", "duration_ms": 5}
                ),
                "not-json",
            ]
        )
        + "\n"
    )
    summary = metrics.summarize(metrics.load_events(path))
    assert summary["events"] == 3
    assert summary["ok"] == 1
    assert summary["failed"] == 1
    assert summary["errors"] == 1
    assert summary["bytes_saved"] == 60
    assert summary["by_tool"]["eval_config"]["calls"] == 2
    assert summary["by_tool"]["eval_config"]["avg_duration_ms"] == 15.0

    text = metrics.format_summary(summary, path=path)
    assert str(path) in text
    assert "eval_config" in text
    assert "saved=60" in text


def test_instrument_records_success_and_error(monkeypatch, tmp_path):
    path = tmp_path / "usage.jsonl"
    monkeypatch.setenv(metrics.PATH_ENV, str(path))
    monkeypatch.setenv(metrics.ENABLED_ENV, "1")

    def ok_tool(*, mode: str = "nixos") -> dict:
        return {
            "status": "ok",
            "resolved_target": "t",
            "raw_bytes": 10,
            "returned_bytes": 4,
        }

    wrapped = instrument("check", ok_tool)
    returned = wrapped(mode="nixos")
    assert returned["status"] == "ok"
    assert "raw_bytes" not in returned
    assert "returned_bytes" not in returned

    def boom() -> dict:
        raise ValueError("nope")

    with pytest.raises(ValueError):
        instrument("build", boom)()

    events = metrics.load_events(path)
    assert len(events) == 2
    assert events[0]["tool"] == "check"
    assert events[0]["status"] == "ok"
    assert events[0]["mode"] == "nixos"
    assert events[0]["raw_bytes"] == 10
    assert events[0]["returned_bytes"] == 4
    assert events[0]["bytes_saved"] == 6
    assert events[1]["tool"] == "build"
    assert events[1]["error"] == "ValueError"


def test_instrument_strips_accounting_when_log_disabled(monkeypatch):
    monkeypatch.delenv(metrics.ENABLED_ENV, raising=False)

    def ok_tool() -> dict:
        return {"status": "ok", "raw_bytes": 10, "returned_bytes": 4}

    returned = instrument("diff", ok_tool)()
    assert returned == {"status": "ok"}


def test_attr_summary_in_event():
    event = metrics.event_from_call(
        tool="eval_config",
        duration_ms=1,
        response={"status": "ok"},
        error=None,
        kwargs={"attr": ["a", "b"]},
    )
    assert event["attr"] == {"count": 2, "attrs": ["a", "b"]}


def test_usage_cli(monkeypatch, tmp_path, capsys):
    path = tmp_path / "usage.jsonl"
    path.write_text(
        json.dumps(
            {
                "tool": "diff",
                "status": "ok",
                "duration_ms": 3,
                "raw_bytes": 8,
                "returned_bytes": 2,
                "bytes_saved": 6,
            }
        )
        + "\n"
    )
    monkeypatch.setattr(
        "sys.argv",
        ["nix-agent", "usage", "--path", str(path), "--json"],
    )
    from nix_agent.__main__ import main

    main()
    payload = json.loads(capsys.readouterr().out)
    assert payload["events"] == 1
    assert payload["path"] == str(path)
    assert payload["by_tool"]["diff"]["bytes_saved"] == 6
