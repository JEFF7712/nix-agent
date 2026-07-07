import importlib
import sys


def test_package_import_does_not_import_server():
    sys.modules.pop("nix_agent", None)
    sys.modules.pop("nix_agent.server", None)

    import nix_agent

    assert nix_agent.__all__ == ["build_server"]
    assert "nix_agent.server" not in sys.modules


def test_build_server_lazy_export():
    import nix_agent

    build_server = nix_agent.build_server

    assert callable(build_server)
    assert "nix_agent.server" in sys.modules


def test_old_modules_are_gone():
    for gone in (
        "nix_agent.models",
        "nix_agent.patching",
        "nix_agent.inspect",
        "nix_agent.system_apply",
    ):
        assert importlib.util.find_spec(gone) is None
