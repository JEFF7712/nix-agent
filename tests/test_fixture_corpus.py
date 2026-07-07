"""Every parser runs against captured real output. Format drift breaks
these tests, not users. Fixtures are real captures from a NixOS machine
(2026-07-07); regenerate by rerunning the capture commands in the Phase 4
plan."""

import json
from pathlib import Path

from nix_agent import logparse

FIXTURES = Path(__file__).parent / "fixtures"


def _read(name):
    return (FIXTURES / name).read_text()


def test_nvd_fixture_parses():
    packages = logparse.parse_nvd(_read("nvd-diff.txt"))
    assert packages is not None
    assert any(packages.values())


def test_diff_closures_fixture_parses():
    packages = logparse.parse_diff_closures(_read("diff-closures.txt"))
    assert packages is not None
    assert any(packages.values())


def test_systemctl_fixture_is_unit_list():
    entries = json.loads(_read("systemctl-failed.json"))
    assert isinstance(entries, list)
    assert all("unit" in e for e in entries)


def test_eval_error_fixture_extracts_detail():
    detail = logparse.extract_error_detail(_read("eval-error.txt"))
    assert detail is not None
    assert detail["file"]
    assert detail["line"] > 0


def test_builder_failure_fixture_extracts_drv():
    drvs = logparse.extract_failed_drvs(_read("builder-failure.txt"))
    assert len(drvs) == 1
    assert drvs[0].endswith(".drv")


def test_builder_failure_exit_code_fixture_extracts_drv():
    drvs = logparse.extract_failed_drvs(_read("builder-failure-exit-code.txt"))
    assert len(drvs) == 1
    assert drvs[0].endswith(".drv")
