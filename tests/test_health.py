from nix_agent import health
from nix_agent.runner import RunResult


def _result(ok, stdout="", stderr="", command=("x",)):
    return RunResult(ok=ok, command=list(command), stdout=stdout, stderr=stderr)


FAILED_JSON = '[{"unit": "b.service", "active": "failed"}, {"unit": "a.service", "active": "failed"}]'

FAILED_PLAIN = """\
a.service loaded failed failed A thing
b.service loaded failed failed Another thing
"""


def test_failed_units_json(monkeypatch):
    calls = []

    def fake_run(argv, cwd=None):
        calls.append(argv)
        return _result(True, stdout=FAILED_JSON, command=argv)

    monkeypatch.setattr(health.runner, "run", fake_run)
    units, note = health.failed_units("nixos")
    assert units == ["a.service", "b.service"]
    assert note is None
    assert calls[0] == [
        "systemctl",
        "--failed",
        "--output=json",
        "--no-pager",
    ]


def test_failed_units_hm_uses_user_bus(monkeypatch):
    calls = []

    def fake_run(argv, cwd=None):
        calls.append(argv)
        return _result(True, stdout="[]", command=argv)

    monkeypatch.setattr(health.runner, "run", fake_run)
    units, note = health.failed_units("home-manager")
    assert units == []
    assert calls[0][:2] == ["systemctl", "--user"]


def test_failed_units_falls_back_to_plain(monkeypatch):
    def fake_run(argv, cwd=None):
        if "--output=json" in argv:
            return _result(False, stderr="unknown option", command=argv)
        return _result(True, stdout=FAILED_PLAIN, command=argv)

    monkeypatch.setattr(health.runner, "run", fake_run)
    units, note = health.failed_units("nixos")
    assert units == ["a.service", "b.service"]
    assert note is None


def test_failed_units_undetectable(monkeypatch):
    def fake_run(argv, cwd=None):
        return _result(False, stderr="no systemd here", command=argv)

    monkeypatch.setattr(health.runner, "run", fake_run)
    units, note = health.failed_units("nixos")
    assert units is None
    assert "health check skipped" in note


def test_failed_units_bad_json_falls_back(monkeypatch):
    def fake_run(argv, cwd=None):
        if "--output=json" in argv:
            return _result(True, stdout="not json at all", command=argv)
        return _result(True, stdout=FAILED_PLAIN, command=argv)

    monkeypatch.setattr(health.runner, "run", fake_run)
    units, note = health.failed_units("nixos")
    assert units == ["a.service", "b.service"]
    assert note is None


def test_health_report_classifies(monkeypatch):
    def fake_run(argv, cwd=None):
        if argv[0] == "journalctl":
            return _result(
                True, stdout=f"log for {argv[argv.index('-u') + 1]}\n", command=argv
            )
        return _result(
            True,
            stdout='[{"unit": "new.service"}, {"unit": "old.service"}]',
            command=argv,
        )

    monkeypatch.setattr(health.runner, "run", fake_run)
    report = health.health_report(["old.service", "gone.service"], "nixos")
    assert report == {
        "newly_failed": [{"unit": "new.service", "log_tail": "log for new.service\n"}],
        "resolved": ["gone.service"],
        "still_failed": ["old.service"],
    }


def test_health_report_none_when_before_missing():
    assert health.health_report(None, "nixos") is None


def test_health_report_none_when_after_undetectable(monkeypatch):
    def fake_run(argv, cwd=None):
        return _result(False, stderr="dbus gone", command=argv)

    monkeypatch.setattr(health.runner, "run", fake_run)
    assert health.health_report([], "nixos") is None


def test_journal_tail_permission_denied(monkeypatch):
    def fake_run(argv, cwd=None):
        return _result(False, stderr="Permission denied", command=argv)

    monkeypatch.setattr(health.runner, "run", fake_run)
    assert "unavailable" in health.journal_tail("x.service", "nixos")


def test_journal_tail_hm_uses_user_bus(monkeypatch):
    calls = []

    def fake_run(argv, cwd=None):
        calls.append(argv)
        return _result(True, stdout="line\n", command=argv)

    monkeypatch.setattr(health.runner, "run", fake_run)
    health.journal_tail("x.service", "home-manager")
    assert calls[0][:2] == ["journalctl", "--user"]
