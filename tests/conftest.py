import pytest


@pytest.fixture(autouse=True)
def isolate_local_state(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
