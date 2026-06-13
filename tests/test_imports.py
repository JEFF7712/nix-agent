from nix_agent.server import build_server


def test_build_server_exists():
    assert callable(build_server)


def test_old_modules_are_gone():
    import importlib.util

    for gone in ("nix_agent.models", "nix_agent.patching",
                 "nix_agent.inspect", "nix_agent.system_apply"):
        assert importlib.util.find_spec(gone) is None
